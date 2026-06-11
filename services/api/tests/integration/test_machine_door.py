"""Stage 2 A1: dual auth (API keys), uploads.source, profile endpoints.

Requires the live local stack (supabase + compose), like the rest of the
integration suite.
"""

import uuid

import httpx
import pytest

from tests.integration.conftest import API_URL, otlp_payload


@pytest.fixture
async def keyed(api: httpx.AsyncClient):
    """Mint a key as the JWT user; yield (plaintext key, key_id, jwt client)."""
    res = await api.post("/v1/api-keys", json={"name": "integration"})
    assert res.status_code == 201
    body = res.json()
    assert body["api_key"].startswith("tmk_")
    assert len(body["api_key"]) == 36
    yield body["api_key"], body["api_key_id"], api


@pytest.fixture
async def key_client(keyed):
    key, _, _ = keyed
    async with httpx.AsyncClient(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {key}"},
        timeout=30.0,
    ) as client:
        yield client


def _file(marker: str):
    return {"file": (f"{marker}.json", otlp_payload(marker), "application/json")}


async def test_key_uploads_with_cli_source(keyed, key_client, db):
    _, key_id, api = keyed
    marker = uuid.uuid4().hex

    res = await key_client.post("/v1/uploads", files=_file(marker))
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]

    # The key reaches the status endpoint too (its whole surface).
    res = await key_client.get(f"/v1/uploads/{upload_id}")
    assert res.status_code == 200
    assert res.json()["source"] == "cli"

    # Same bytes again → the CLI's skip signal.
    res = await key_client.post("/v1/uploads", files=_file(marker))
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "duplicate_upload"

    # Web uploads keep source = web (JWT client, fresh bytes).
    res = await api.post("/v1/uploads", files=_file(uuid.uuid4().hex))
    assert res.status_code == 201
    res = await api.get(f"/v1/uploads/{res.json()['upload_id']}")
    assert res.json()["source"] == "web"

    # last_used_at is stamped by key auth (throttled, but this was first use).
    last_used = await db.fetchval("select last_used_at from api_keys where id = $1", key_id)
    assert last_used is not None


async def test_key_is_upload_only(key_client):
    for path in ("/v1/traces", "/v1/uploads", "/v1/profile", "/v1/api-keys"):
        res = await key_client.get(path)
        assert res.status_code == 401, path
        assert res.json()["error"]["code"] == "unauthorized"


async def test_garbage_key_rejected(keyed, key_client):
    bad = httpx.AsyncClient(
        base_url=API_URL, headers={"Authorization": f"Bearer tmk_{'x' * 32}"}, timeout=30.0
    )
    async with bad:
        res = await bad.post("/v1/uploads", files=_file(uuid.uuid4().hex))
        assert res.status_code == 401


async def test_revoked_key_fails_auth(keyed, key_client):
    _, key_id, api = keyed
    res = await api.delete(f"/v1/api-keys/{key_id}")
    assert res.status_code == 204
    # Idempotent revoke.
    res = await api.delete(f"/v1/api-keys/{key_id}")
    assert res.status_code == 204

    res = await key_client.post("/v1/uploads", files=_file(uuid.uuid4().hex))
    assert res.status_code == 401

    # The row remains, marked revoked; plaintext never reappears anywhere.
    res = await api.get("/v1/api-keys")
    rows = res.json()["api_keys"]
    mine = next(r for r in rows if r["api_key_id"] == key_id)
    assert mine["revoked_at"] is not None
    assert "api_key" not in mine
    assert mine["key_display"].startswith("tmk_")
    assert len(mine["key_display"]) < 36


async def test_foreign_key_revoke_is_404(keyed):
    _, key_id, _ = keyed
    from tests.integration.conftest import signup_token

    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=API_URL, headers={"Authorization": f"Bearer {other_token}"}, timeout=30.0
    ) as other:
        res = await other.delete(f"/v1/api-keys/{key_id}")
        assert res.status_code == 404


async def test_profile_roundtrip(api: httpx.AsyncClient):
    res = await api.get("/v1/profile")
    assert res.status_code == 200
    before = res.json()
    assert before["allow_private_llm_analysis"] is True  # default on

    res = await api.patch(
        "/v1/profile",
        json={"display_name": "Integration Tester", "allow_private_llm_analysis": False},
    )
    assert res.status_code == 200

    res = await api.get("/v1/profile")
    body = res.json()
    assert body["display_name"] == "Integration Tester"
    assert body["allow_private_llm_analysis"] is False

    # Partial update leaves the other field untouched.
    res = await api.patch("/v1/profile", json={"allow_private_llm_analysis": True})
    assert res.status_code == 200
    assert res.json()["display_name"] == "Integration Tester"

    # Validation: empty display name is a 422, not a silent null.
    res = await api.patch("/v1/profile", json={"display_name": "   "})
    assert res.status_code == 422


async def test_uploads_list_carries_source_and_trace_ids(api: httpx.AsyncClient):
    import asyncio

    marker = uuid.uuid4().hex
    res = await api.post("/v1/uploads", files=_file(marker))
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]

    for _ in range(30):
        res = await api.get(f"/v1/uploads/{upload_id}")
        if res.json()["status"] in ("complete", "failed"):
            break
        await asyncio.sleep(1)
    assert res.json()["status"] == "complete"

    res = await api.get("/v1/uploads")
    row = next(u for u in res.json()["uploads"] if u["upload_id"] == upload_id)
    assert row["source"] == "web"
    assert len(row["trace_ids"]) == 1
