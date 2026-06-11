"""Redaction at ingestion (7_redaction.md): owner sees raw, everyone and
everything else sees deterministic placeholders; re-ingest is byte-identical."""

import json
import re
import uuid

import asyncpg
import httpx
import pytest

from tests.integration.conftest import signup_token
from tests.integration.test_ingestion import fixture_bytes, ingest_fixture
from tests.integration.test_uploads import upload_file, wait_terminal

pytestmark = pytest.mark.asyncio

PLACEHOLDER = re.compile(r"<[A-Z_]+_[0-9a-f]{8}>")

SEEDED_EMAIL = "alice@example.com"
SEEDED_KEY = "AKIAIOSFODNN7EXAMPLE"


async def llm_span_detail(api: httpx.AsyncClient, trace_id: str) -> dict:
    spans = (await api.get(f"/v1/traces/{trace_id}/spans")).json()
    llm = next(s for s in spans["spans"] if s["source_span_id"] == "d000000000000001")
    return (await api.get(f"/v1/traces/{trace_id}/spans/{llm['span_id']}")).json()


async def test_owner_raw_others_placeholders(api: httpx.AsyncClient) -> None:
    status = await ingest_fixture(api, "redaction-seeded")
    trace_id = status["trace_ids"][0]

    # Counts surface on the upload (per-kind, from the artifact walk).
    counts = status["redaction_counts"]
    assert counts["EMAIL"] >= 2
    assert counts["API_KEY"] >= 1
    assert counts["PRIVATE_KEY"] == 1

    # Trace name is scrubbed in place — single representation, even for the
    # owner.
    trace = (await api.get(f"/v1/traces/{trace_id}")).json()
    assert SEEDED_EMAIL not in trace["name"]
    assert PLACEHOLDER.search(trace["name"])

    # Owner span detail: original content via span_raw.
    detail = await llm_span_detail(api, trace_id)
    assert SEEDED_EMAIL in detail["attributes"]["gen_ai.prompt"]
    assert detail["status_message"] == "auth failed for alice@example.com"

    # List the trace; a second user inspects it and sees placeholders only.
    listed = await api.patch(
        f"/v1/traces/{trace_id}",
        json={"visibility": "listed", "confirm_ownership": True},
    )
    assert listed.status_code == 200

    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=api.base_url,
        headers={"Authorization": f"Bearer {other_token}"},
        timeout=30.0,
    ) as other:
        other_detail = await llm_span_detail(other, trace_id)
        rendered = json.dumps(other_detail)
        assert SEEDED_EMAIL not in rendered
        assert SEEDED_KEY not in rendered
        assert PLACEHOLDER.search(other_detail["attributes"]["gen_ai.prompt"])
        assert PLACEHOLDER.search(other_detail["status_message"])

        # Same value, same placeholder across representations: the seeded
        # email appears in both the prompt and the trace name.
        email_placeholder = re.search(
            r"<EMAIL_[0-9a-f]{8}>", other_detail["attributes"]["gen_ai.prompt"]
        ).group(0)
        assert email_placeholder in trace["name"]

        # Acquirer download serves the scrubbed artifact, never the raw bytes.
        assert (await other.post(f"/v1/traces/{trace_id}/acquire")).status_code == 201
        download = await other.get(f"/v1/traces/{trace_id}/download")
        assert download.status_code == 200
        downloaded = download.content.decode()
        assert SEEDED_EMAIL not in downloaded
        assert SEEDED_KEY not in downloaded
        assert "BEGIN RSA PRIVATE KEY" not in downloaded
        assert PLACEHOLDER.search(downloaded)

    # Owner download still returns the exact original bytes.
    owner_download = await api.get(f"/v1/traces/{trace_id}/download")
    assert SEEDED_EMAIL in owner_download.content.decode()


async def test_reingest_is_byte_identical(api: httpx.AsyncClient, db: asyncpg.Connection) -> None:
    """Same payload + same stored salt ⇒ identical scrubbed rows and artifact
    on every re-run (the delete-and-rewrite + determinism contract)."""
    from app.clients import db as app_db
    from app.clients import redis as app_redis
    from app.clients import storage as app_storage
    from app.worker.tasks.ingest import ingest_upload

    status = await ingest_fixture(api, "redaction-seeded")
    upload_id = uuid.UUID(status["upload_id"])

    async def snapshot() -> tuple[list, bytes]:
        rows = await db.fetch(
            """
            select s.name, s.status_message, s.attributes, s.events, t.name as trace_name
            from spans s join traces t on t.id = s.trace_id
            where t.upload_id = $1
            order by s.source_span_id
            """,
            upload_id,
        )
        storage_path = await db.fetchval(
            "select storage_path from uploads where id = $1", upload_id
        )
        artifact = await app_storage.get(app_storage.scrubbed_path(storage_path))
        return [tuple(r) for r in rows], artifact

    await app_db.open_pool()
    await app_redis.open_client()
    await app_storage.open_client()
    try:
        before = await snapshot()
        await db.execute("update uploads set status = 'received' where id = $1", upload_id)
        await ingest_upload.original_func(str(upload_id))
        after = await snapshot()
    finally:
        await app_storage.close_client()
        await app_redis.close_client()
        await app_db.close_pool()

    assert before == after


async def test_negative_fixture_masks_nothing(api: httpx.AsyncClient) -> None:
    status = await ingest_fixture(api, "redaction-negative")
    assert status["redaction_counts"] is None

    trace_id = status["trace_ids"][0]
    spans = (await api.get(f"/v1/traces/{trace_id}/spans")).json()
    detail = (await api.get(f"/v1/traces/{trace_id}/spans/{spans['spans'][0]['span_id']}")).json()
    assert not PLACEHOLDER.search(json.dumps(detail))
    assert detail["attributes"]["payload.sha256"] == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


async def test_missing_artifact_download_is_honest(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """An upload with no scrubbed artifact (ingested before A5 shipped) 404s
    for acquirers with a readable reason instead of leaking raw bytes."""
    from app.clients import storage as app_storage

    created = await upload_file(api, fixture_bytes("minimal"), filename="minimal.json")
    status = await wait_terminal(api, created.json()["upload_id"])
    trace_id = status["trace_ids"][0]
    await api.patch(
        f"/v1/traces/{trace_id}", json={"visibility": "listed", "confirm_ownership": True}
    )

    # Simulate the pre-A5 state by removing the artifact.
    storage_path = await db.fetchval(
        "select storage_path from uploads where id = $1", uuid.UUID(status["upload_id"])
    )
    await app_storage.open_client()
    try:
        await app_storage.delete(app_storage.scrubbed_path(storage_path))
    finally:
        await app_storage.close_client()

    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=api.base_url,
        headers={"Authorization": f"Bearer {other_token}"},
        timeout=30.0,
    ) as other:
        assert (await other.post(f"/v1/traces/{trace_id}/acquire")).status_code == 201
        download = await other.get(f"/v1/traces/{trace_id}/download")
        assert download.status_code == 404
        assert "re-ingest" in download.json()["error"]["message"]

    # The owner's raw download is unaffected.
    assert (await api.get(f"/v1/traces/{trace_id}/download")).status_code == 200
