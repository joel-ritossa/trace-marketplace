"""Retry / DLQ / requeue behavior via X-Fault injection (DEV_ROUTES only)."""

import subprocess
import uuid
from pathlib import Path

import asyncpg
import httpx
import pytest
from redis.asyncio import Redis

from app.config import settings
from app.queries import uploads as uploads_q
from tests.integration.conftest import otlp_payload
from tests.integration.test_uploads import upload_file, wait_terminal

pytestmark = pytest.mark.asyncio

SERVICE_DIR = Path(__file__).resolve().parents[2]


async def test_permanent_failure_fails_immediately(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    res = await upload_file(api, otlp_payload(uuid.uuid4().hex), headers={"X-Fault": "permanent"})
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]

    status = await wait_terminal(api, upload_id)
    assert status["status"] == "failed"
    assert status["error_message"]  # readable reason, per 6_architecture.md

    row = await db.fetchrow(
        "select attempts, (select count(*) from dead_letters d where d.upload_id = u.id) as dlq "
        "from uploads u where id = $1",
        uuid.UUID(upload_id),
    )
    assert row["attempts"] == 1  # no retries
    assert row["dlq"] == 0  # permanent failures don't dead-letter


async def test_invalid_fault_rejected_without_side_effects(api: httpx.AsyncClient) -> None:
    data = otlp_payload(uuid.uuid4().hex)
    res = await upload_file(api, data, headers={"X-Fault": "bogus"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "invalid_request"

    # Nothing was stored: the same bytes upload cleanly (no duplicate_upload).
    retry = await upload_file(api, data)
    assert retry.status_code == 201


async def test_transient_failure_retries_to_success(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    res = await upload_file(api, otlp_payload(uuid.uuid4().hex), headers={"X-Fault": "transient:2"})
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]

    status = await wait_terminal(api, upload_id, timeout=60.0)
    assert status["status"] == "complete"

    attempts = await db.fetchval("select attempts from uploads where id = $1", uuid.UUID(upload_id))
    assert attempts == 3  # two injected failures + the success

    dlq = await db.fetchval(
        "select count(*) from dead_letters where upload_id = $1", uuid.UUID(upload_id)
    )
    assert dlq == 0


async def test_exhausted_retries_dead_letter_and_requeue(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    res = await upload_file(api, otlp_payload(uuid.uuid4().hex), headers={"X-Fault": "exhaust"})
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]

    status = await wait_terminal(api, upload_id, timeout=120.0)
    assert status["status"] == "failed"
    assert "attempts" in status["error_message"]

    row = await db.fetchrow(
        "select task_name, attempts, last_error, requeued_at from dead_letters "
        "where upload_id = $1",
        uuid.UUID(upload_id),
    )
    assert row is not None
    # taskiq's canonical registered name (module:task)
    assert row["task_name"] == "app.worker.tasks.ingest:ingest_upload"
    assert row["attempts"] == settings.ingest_max_attempts
    assert row["requeued_at"] is None

    # The retry budget is the durable counter, so the DLQ record can't lie.
    upload_attempts = await db.fetchval(
        "select attempts from uploads where id = $1", uuid.UUID(upload_id)
    )
    assert upload_attempts == row["attempts"]

    # Disarm the fault, then requeue through the operator CLI.
    redis = Redis.from_url(settings.redis_url)
    await redis.delete(f"fault:{upload_id}")
    await redis.aclose()

    result = subprocess.run(
        ["uv", "run", "python", "-m", "app.cli.requeue", upload_id],
        cwd=SERVICE_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    status = await wait_terminal(api, upload_id, timeout=60.0)
    assert status["status"] == "complete"

    requeued_at = await db.fetchval(
        "select requeued_at from dead_letters where upload_id = $1", uuid.UUID(upload_id)
    )
    assert requeued_at is not None


async def test_complete_is_terminal(api: httpx.AsyncClient, db: asyncpg.Connection) -> None:
    """A stale retry chain or duplicate delivery must not regress `complete`."""
    res = await upload_file(api, otlp_payload(uuid.uuid4().hex))
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]
    status = await wait_terminal(api, upload_id)
    assert status["status"] == "complete"

    # Exhausted stale chain trying to dead-letter: guarded no-op.
    await uploads_q.mark_failed(db, upload_id, "stale failure from a duplicate delivery")
    assert (
        await db.fetchval("select status from uploads where id = $1", uuid.UUID(upload_id))
        == "complete"
    )

    # Stale duplicate delivery trying to re-claim: refused atomically.
    assert await uploads_q.mark_processing(db, upload_id) is None
    assert (
        await db.fetchval("select status from uploads where id = $1", uuid.UUID(upload_id))
        == "complete"
    )


async def test_missing_storage_object_fails_permanently(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """A 404 from storage is permanent: fail on attempt 1, no retry burn."""
    res = await upload_file(api, otlp_payload(uuid.uuid4().hex))
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]
    await wait_terminal(api, upload_id)

    # Point the upload at an object that doesn't exist and force a fresh run.
    await db.execute(
        "update uploads set status = 'failed', storage_path = 'raw/nope/missing.json' "
        "where id = $1",
        uuid.UUID(upload_id),
    )
    result = subprocess.run(
        ["uv", "run", "python", "-m", "app.cli.requeue", upload_id],
        cwd=SERVICE_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    status = await wait_terminal(api, upload_id, timeout=30.0)
    assert status["status"] == "failed"
    assert "missing" in status["error_message"].lower()

    attempts = await db.fetchval("select attempts from uploads where id = $1", uuid.UUID(upload_id))
    assert attempts == 1  # permanent: no retries
    dlq = await db.fetchval(
        "select count(*) from dead_letters where upload_id = $1", uuid.UUID(upload_id)
    )
    assert dlq == 0
