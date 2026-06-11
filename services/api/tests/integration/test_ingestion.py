"""Ingestion pipeline: upload → normalized trace/span rows → trace API."""

import asyncio
import json
import uuid
from pathlib import Path

import asyncpg
import httpx
import pytest

from tests.integration.conftest import signup_token
from tests.integration.test_uploads import upload_file, wait_terminal

pytestmark = pytest.mark.asyncio

FIXTURES_DIR = Path(__file__).parents[4] / "fixtures"


def fixture_bytes(name: str) -> bytes:
    """Fixture payload made unique per call so duplicate-hash never trips."""
    payload = json.loads((FIXTURES_DIR / f"{name}.json").read_text())
    payload["_test_marker"] = uuid.uuid4().hex
    return json.dumps(payload).encode()


async def ingest_fixture(api: httpx.AsyncClient, name: str) -> dict:
    created = await upload_file(api, fixture_bytes(name), filename=f"{name}.json")
    assert created.status_code == 201
    status = await wait_terminal(api, created.json()["upload_id"])
    assert status["status"] == "complete", status["error_message"]
    return status


async def test_agent_session_normalizes(api: httpx.AsyncClient) -> None:
    status = await ingest_fixture(api, "agent-session")
    assert status["parse_warnings"] is None
    assert len(status["trace_ids"]) == 1
    trace_id = status["trace_ids"][0]

    trace = (await api.get(f"/v1/traces/{trace_id}")).json()
    assert trace["name"] == "invoke_agent demo-agent"
    assert trace["status"] == "ok"
    assert trace["span_count"] == 7
    assert trace["error_count"] == 0
    assert trace["provider"] == "openai"
    assert trace["model"] == "gpt-5"
    assert trace["service_name"] == "demo-agent-service"
    assert trace["tool_names"] == ["get_weather"]
    assert trace["duration_ms"] == 5000
    assert trace["is_owner"] and trace["can_download"] and not trace["acquired"]

    spans = (await api.get(f"/v1/traces/{trace_id}/spans")).json()
    assert spans["total"] == 7
    by_kind = {s["kind"] for s in spans["spans"]}
    assert by_kind == {"agent", "llm", "chain", "retriever", "embedding", "tool"}
    # Light list never carries content fields.
    assert "attributes" not in spans["spans"][0]

    # Tree is reconstructible: every parent id resolves within the trace.
    ids = {s["source_span_id"] for s in spans["spans"]}
    parents = {s["source_parent_span_id"] for s in spans["spans"] if s["source_parent_span_id"]}
    assert parents <= ids

    # Per-span detail carries the full raw attributes.
    llm = next(s for s in spans["spans"] if s["source_span_id"] == "a000000000000002")
    detail = (await api.get(f"/v1/traces/{trace_id}/spans/{llm['span_id']}")).json()
    assert detail["attributes"]["gen_ai.request.model"] == "gpt-5"
    assert detail["input_tokens"] == 1200 and detail["output_tokens"] == 85


async def test_failure_trace_flags_errors(api: httpx.AsyncClient) -> None:
    status = await ingest_fixture(api, "failure-trace")
    trace_id = status["trace_ids"][0]

    trace = (await api.get(f"/v1/traces/{trace_id}")).json()
    assert trace["status"] == "error"
    assert trace["error_count"] == 2
    assert trace["error_types"] == ["TimeoutError"]

    spans = (await api.get(f"/v1/traces/{trace_id}/spans")).json()
    tool = next(s for s in spans["spans"] if s["kind"] == "tool")
    assert tool["status"] == "error"
    assert tool["error_type"] == "TimeoutError"
    detail = (await api.get(f"/v1/traces/{trace_id}/spans/{tool['span_id']}")).json()
    assert detail["events"][0]["attributes"]["exception.type"] == "TimeoutError"


async def test_partial_success_reports_warnings(api: httpx.AsyncClient) -> None:
    status = await ingest_fixture(api, "malformed-spans")
    assert status["parse_warnings"]["skipped_spans"] == 2
    assert len(status["parse_warnings"]["samples"]) == 2

    trace = (await api.get(f"/v1/traces/{status['trace_ids'][0]}")).json()
    assert trace["span_count"] == 2  # valid spans still ingested


async def test_unparseable_spans_fail_permanently(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """Zero valid spans = permanent failure: one attempt, no retries, no DLQ."""
    payload = json.dumps(
        {
            "resourceSpans": [{"scopeSpans": [{"spans": [{"name": "no ids"}]}]}],
            "_test_marker": uuid.uuid4().hex,
        }
    ).encode()
    created = await upload_file(api, payload)
    status = await wait_terminal(api, created.json()["upload_id"])
    assert status["status"] == "failed"
    assert "no valid spans" in status["error_message"]
    assert status["trace_ids"] == []

    row = await db.fetchrow(
        "select attempts from uploads where id = $1", uuid.UUID(created.json()["upload_id"])
    )
    assert row["attempts"] == 1


async def test_trace_download_returns_raw_payload(api: httpx.AsyncClient) -> None:
    data = fixture_bytes("minimal")
    created = await upload_file(api, data, filename="minimal.json")
    status = await wait_terminal(api, created.json()["upload_id"])
    trace_id = status["trace_ids"][0]

    download = await api.get(f"/v1/traces/{trace_id}/download")
    assert download.status_code == 200
    assert download.content == data
    assert "minimal.json" in download.headers["content-disposition"]


async def test_traces_list_and_sort(api: httpx.AsyncClient) -> None:
    await ingest_fixture(api, "agent-session")
    await ingest_fixture(api, "minimal")

    listed = (await api.get("/v1/traces")).json()
    assert listed["total"] == 2
    # Result cards carry the caller-relationship fields (3_api.md).
    assert listed["traces"][0]["owner_display_name"]  # signup default: email local part
    assert listed["traces"][0]["acquired"] is False

    by_spans = (await api.get("/v1/traces", params={"sort": "span_count"})).json()
    assert [t["span_count"] for t in by_spans["traces"]] == [7, 1]

    bad_scope = await api.get("/v1/traces", params={"scope": "everything"})
    assert bad_scope.status_code == 422  # unknown scopes honestly rejected


async def test_retry_does_not_duplicate_rows(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """Idempotency under retry: re-runs converge to exactly one set of rows."""
    created = await upload_file(
        api,
        fixture_bytes("agent-session"),
        filename="agent-session.json",
        headers={"X-Fault": "transient:2"},
    )
    assert created.status_code == 201
    upload_id = created.json()["upload_id"]

    status = await wait_terminal(api, upload_id, timeout=60.0)
    assert status["status"] == "complete"

    row = await db.fetchrow(
        """
        select u.attempts,
               (select count(*) from traces t where t.upload_id = u.id) as trace_count,
               (select count(*) from spans s
                join traces t on t.id = s.trace_id where t.upload_id = u.id) as span_count
        from uploads u where u.id = $1
        """,
        uuid.UUID(upload_id),
    )
    assert row["attempts"] == 3
    assert row["trace_count"] == 1
    assert row["span_count"] == 7


async def test_simultaneous_ingest_runs_do_not_duplicate(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """Two ingest runs of the same upload racing (sweep re-enqueue during a
    slow run, duplicate delivery) must converge to one set of rows. Sequential
    retries are covered above; this runs the real task twice concurrently
    in-process, where the per-upload row lock is the only thing serializing
    the delete-and-rewrite transactions."""
    from app.clients import db as app_db
    from app.clients import redis as app_redis
    from app.clients import storage as app_storage
    from app.worker.tasks.ingest import ingest_upload

    status = await ingest_fixture(api, "agent-session")
    upload_id = uuid.UUID(status["upload_id"])

    # Re-arm as if two deliveries of the same job landed at once.
    await db.execute("update uploads set status = 'received' where id = $1", upload_id)

    await app_db.open_pool()
    await app_redis.open_client()
    await app_storage.open_client()
    try:
        await asyncio.gather(
            ingest_upload.original_func(str(upload_id)),
            ingest_upload.original_func(str(upload_id)),
        )
    finally:
        await app_storage.close_client()
        await app_redis.close_client()
        await app_db.close_pool()

    row = await db.fetchrow(
        """
        select u.status,
               (select count(*) from traces t where t.upload_id = u.id) as trace_count,
               (select count(*) from spans s
                join traces t on t.id = s.trace_id where t.upload_id = u.id) as span_count
        from uploads u where u.id = $1
        """,
        upload_id,
    )
    assert row["status"] == "complete"
    assert row["trace_count"] == 1
    assert row["span_count"] == 7


async def test_traces_are_owner_scoped(api: httpx.AsyncClient) -> None:
    status = await ingest_fixture(api, "minimal")
    trace_id = status["trace_ids"][0]
    spans = (await api.get(f"/v1/traces/{trace_id}/spans")).json()
    span_id = spans["spans"][0]["span_id"]

    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=api.base_url, headers={"Authorization": f"Bearer {other_token}"}
    ) as other:
        paths = (
            f"/v1/traces/{trace_id}",
            f"/v1/traces/{trace_id}/spans",
            f"/v1/traces/{trace_id}/spans/{span_id}",
            f"/v1/traces/{trace_id}/download",
        )
        for path in paths:
            res = await other.get(path)
            assert res.status_code == 404, path
        assert (await other.get("/v1/traces")).json()["total"] == 0

    # Non-UUID ids 404 too instead of 500.
    assert (await api.get("/v1/traces/not-a-uuid")).status_code == 404
