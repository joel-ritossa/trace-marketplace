"""Slice 3: visibility, search/filters, acquisition, and deletion."""

import asyncio
import json
import uuid

import asyncpg
import httpx
import pytest

from app.config import settings
from tests.integration.conftest import API_URL, signup_token
from tests.integration.test_ingestion import fixture_bytes, ingest_fixture
from tests.integration.test_uploads import upload_file, wait_terminal

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def consumer():
    """A second authenticated user (the marketplace side of every test)."""
    token = await signup_token()
    async with httpx.AsyncClient(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as client:
        yield client


async def list_trace(api: httpx.AsyncClient, trace_id: str, **extra) -> httpx.Response:
    return await api.patch(
        f"/v1/traces/{trace_id}",
        json={"visibility": "listed", "confirm_ownership": True, **extra},
    )


async def ingest_listed(api: httpx.AsyncClient, name: str = "minimal") -> str:
    trace_id = (await ingest_fixture(api, name))["trace_ids"][0]
    assert (await list_trace(api, trace_id)).status_code == 200
    return trace_id


async def test_patch_validation_and_listing(api: httpx.AsyncClient) -> None:
    trace_id = (await ingest_fixture(api, "minimal"))["trace_ids"][0]

    # Listing without the ownership confirmation is refused.
    res = await api.patch(f"/v1/traces/{trace_id}", json={"visibility": "listed"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "confirmation_required"

    # An empty patch is refused too.
    res = await api.patch(f"/v1/traces/{trace_id}", json={})
    assert res.status_code == 422

    res = await list_trace(api, trace_id, tags=["weather-demo"], description="demo session")
    assert res.status_code == 200
    body = res.json()
    assert body["visibility"] == "listed"
    assert body["tags"] == ["weather-demo"]
    assert body["description"] == "demo session"
    first_listed_at = body["listed_at"]
    assert first_listed_at is not None

    # Unlist, relist: listed_at keeps the original date.
    await api.patch(f"/v1/traces/{trace_id}", json={"visibility": "private"})
    relisted = await list_trace(api, trace_id)
    assert relisted.json()["listed_at"] == first_listed_at

    # Clearing the description (explicit null) sticks.
    res = await api.patch(f"/v1/traces/{trace_id}", json={"description": None})
    assert res.json()["description"] is None

    # Only description is nullable: explicit nulls elsewhere are 422, not 500.
    for body in ({"visibility": None}, {"tags": None}):
        res = await api.patch(f"/v1/traces/{trace_id}", json=body)
        assert res.status_code == 422, res.text
        assert res.json()["error"]["code"] == "invalid_request"

    # Tags are bounded: no empty/whitespace items, no unbounded lengths.
    for tags in ([""], ["   "], ["x" * 81]):
        res = await api.patch(f"/v1/traces/{trace_id}", json={"tags": tags})
        assert res.status_code == 422, res.text


async def test_visibility_and_scopes(api: httpx.AsyncClient, consumer: httpx.AsyncClient) -> None:
    trace_id = (await ingest_fixture(api, "minimal"))["trace_ids"][0]

    # Private: invisible to the consumer everywhere — 404, never 403.
    for path in (f"/v1/traces/{trace_id}", f"/v1/traces/{trace_id}/spans"):
        assert (await consumer.get(path)).status_code == 404
    marketplace = (await consumer.get("/v1/traces", params={"scope": "marketplace"})).json()
    assert trace_id not in [t["trace_id"] for t in marketplace["traces"]]

    assert (await list_trace(api, trace_id)).status_code == 200

    # Listed: fully inspectable by any authenticated user.
    detail = (await consumer.get(f"/v1/traces/{trace_id}")).json()
    assert not detail["is_owner"] and not detail["acquired"] and not detail["can_download"]
    assert detail["visibility"] == "listed"
    assert detail["owner_display_name"]
    spans = (await consumer.get(f"/v1/traces/{trace_id}/spans")).json()
    assert spans["total"] == 1
    span_detail = await consumer.get(f"/v1/traces/{trace_id}/spans/{spans['spans'][0]['span_id']}")
    assert span_detail.status_code == 200

    # Marketplace card carries the contributor and listing fields.
    marketplace = (await consumer.get("/v1/traces", params={"scope": "marketplace"})).json()
    card = next(t for t in marketplace["traces"] if t["trace_id"] == trace_id)
    assert card["owner_display_name"] and card["listed_at"] and not card["is_owner"]

    # Listing doesn't leak into other people's "mine" scope.
    assert trace_id not in [
        t["trace_id"] for t in (await consumer.get("/v1/traces")).json()["traces"]
    ]

    # Non-owners can't modify or delete a listed trace (403: existence isn't
    # secret once listed).
    assert (await list_trace(consumer, trace_id)).status_code == 403
    assert (await consumer.delete(f"/v1/traces/{trace_id}")).status_code == 403


async def test_search_and_filters(api: httpx.AsyncClient) -> None:
    agent = (await ingest_fixture(api, "agent-session"))["trace_ids"][0]
    failure = (await ingest_fixture(api, "failure-trace"))["trace_ids"][0]
    minimal = (await ingest_fixture(api, "minimal"))["trace_ids"][0]
    await api.patch(
        f"/v1/traces/{agent}",
        json={"tags": ["weather-demo"], "description": "synthetic assistant run"},
    )

    async def ids(**params) -> set[str]:
        res = await api.get("/v1/traces", params=params)
        assert res.status_code == 200, res.text
        return {t["trace_id"] for t in res.json()["traces"]}

    assert await ids() == {agent, failure, minimal}
    assert await ids(provider="openai") == {agent, failure}
    assert await ids(model="gpt-5") == {agent, failure}
    assert await ids(tool="get_weather") == {agent}
    assert await ids(has_errors="true") == {failure}
    # Full-text: tags (A weight), description (B), error types (C).
    assert await ids(q="weather-demo") == {agent}
    assert await ids(q="synthetic assistant") == {agent}
    assert await ids(q="TimeoutError") == {failure}
    assert await ids(q="weather-demo", has_errors="true") == set()
    # Date range on started_at.
    assert await ids(**{"to": "1999-01-01T00:00:00Z"}) == set()
    assert await ids(**{"from": "1999-01-01T00:00:00Z"}) == {agent, failure, minimal}


async def test_acquire_and_download_gating(
    api: httpx.AsyncClient, consumer: httpx.AsyncClient
) -> None:
    data = fixture_bytes("minimal")
    created = await upload_file(api, data, filename="minimal.json")
    status = await wait_terminal(api, created.json()["upload_id"])
    trace_id = status["trace_ids"][0]
    assert (await list_trace(api, trace_id)).status_code == 200

    # Listed-but-not-acquired: inspectable, not downloadable.
    res = await consumer.get(f"/v1/traces/{trace_id}/download")
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "acquisition_required"

    # Owners don't acquire their own traces.
    res = await api.post(f"/v1/traces/{trace_id}/acquire")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "own_trace"

    # Acquire, then acquire again: idempotent, same record.
    first = await consumer.post(f"/v1/traces/{trace_id}/acquire")
    assert first.status_code == 201
    assert first.json()["price_usd"] == 0
    again = await consumer.post(f"/v1/traces/{trace_id}/acquire")
    assert again.status_code == 200
    assert again.json()["acquisition_id"] == first.json()["acquisition_id"]

    # Acquisition gates the download: byte-identical raw payload.
    download = await consumer.get(f"/v1/traces/{trace_id}/download")
    assert download.status_code == 200
    assert download.content == data

    detail = (await consumer.get(f"/v1/traces/{trace_id}")).json()
    assert detail["acquired"] and detail["can_download"] and not detail["is_owner"]

    # The library scope shows it, with the acquisition date.
    library = (await consumer.get("/v1/traces", params={"scope": "acquired"})).json()
    card = next(t for t in library["traces"] if t["trace_id"] == trace_id)
    assert card["acquired"] and card["acquired_at"]
    # ... and the owner's library is empty.
    assert (await api.get("/v1/traces", params={"scope": "acquired"})).json()["total"] == 0

    # Private traces can't be acquired (invisible: 404).
    private_id = (await ingest_fixture(api, "agent-session"))["trace_ids"][0]
    assert (await consumer.post(f"/v1/traces/{private_id}/acquire")).status_code == 404


async def test_unlist_revokes_consumer_access(
    api: httpx.AsyncClient, consumer: httpx.AsyncClient
) -> None:
    trace_id = await ingest_listed(api)
    assert (await consumer.post(f"/v1/traces/{trace_id}/acquire")).status_code == 201

    # Unlist: the trace stops resolving for non-owners, downloads included;
    # the acquisition row stays.
    await api.patch(f"/v1/traces/{trace_id}", json={"visibility": "private"})
    assert (await consumer.get(f"/v1/traces/{trace_id}")).status_code == 404
    assert (await consumer.get(f"/v1/traces/{trace_id}/download")).status_code == 404
    assert (await consumer.get("/v1/traces", params={"scope": "acquired"})).json()["total"] == 0

    # Relist: access (and the library entry) come back without re-acquiring.
    assert (await list_trace(api, trace_id)).status_code == 200
    assert (await consumer.get("/v1/traces", params={"scope": "acquired"})).json()["total"] == 1
    assert (await consumer.get(f"/v1/traces/{trace_id}/download")).status_code == 200


def two_trace_payload() -> bytes:
    def span(trace_id: str, span_id: str) -> dict:
        return {
            "traceId": trace_id,
            "spanId": span_id,
            "name": "discovery test span",
            "startTimeUnixNano": "1768471200000000000",
            "endTimeUnixNano": "1768471201000000000",
            "attributes": [],
            "status": {"code": 1},
        }

    return json.dumps(
        {
            "resourceSpans": [
                {"scopeSpans": [{"spans": [span("11" * 16, "aa" * 8), span("22" * 16, "bb" * 8)]}]}
            ],
            "_test_marker": uuid.uuid4().hex,
        }
    ).encode()


async def test_delete_cascades_and_upload_cleanup(
    api: httpx.AsyncClient, consumer: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    created = await upload_file(api, two_trace_payload(), filename="two-traces.json")
    status = await wait_terminal(api, created.json()["upload_id"])
    upload_id = uuid.UUID(status["upload_id"])
    first, second = status["trace_ids"]
    assert (await list_trace(api, first)).status_code == 200
    assert (await consumer.post(f"/v1/traces/{first}/acquire")).status_code == 201

    storage_path = await db.fetchval("select storage_path from uploads where id = $1", upload_id)

    async def object_exists() -> bool:
        async with httpx.AsyncClient(
            base_url=settings.supabase_storage_url,
            headers={"Authorization": f"Bearer {settings.supabase_service_role_key}"},
        ) as storage:
            return (await storage.get(f"/object/raw-traces/{storage_path}")).status_code == 200

    # Delete the first trace: spans and acquisitions cascade; the upload (and
    # its object) survive because the second trace still references it.
    assert (await api.delete(f"/v1/traces/{first}")).status_code == 204
    assert (await api.get(f"/v1/traces/{first}")).status_code == 404
    assert (
        await db.fetchval("select count(*) from spans where trace_id = $1", uuid.UUID(first)) == 0
    )
    assert (
        await db.fetchval("select count(*) from acquisitions where trace_id = $1", uuid.UUID(first))
        == 0
    )
    assert await db.fetchval("select count(*) from uploads where id = $1", upload_id) == 1
    assert await object_exists()

    # Delete the last trace: the upload row and storage object go with it.
    assert (await api.delete(f"/v1/traces/{second}")).status_code == 204
    assert await db.fetchval("select count(*) from uploads where id = $1", upload_id) == 0
    assert not await object_exists()

    # Deleting again: gone is gone.
    assert (await api.delete(f"/v1/traces/{second}")).status_code == 404


async def test_simultaneous_deletes_still_clean_up_upload(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """Concurrent deletes of an upload's last traces must not orphan the
    upload row (the upload-row lock serializes them; without it, each delete
    counts the other's uncommitted delete as a survivor and both skip
    cleanup)."""
    created = await upload_file(api, two_trace_payload(), filename="delete-race.json")
    status = await wait_terminal(api, created.json()["upload_id"])
    upload_id = uuid.UUID(status["upload_id"])

    responses = await asyncio.gather(
        *(api.delete(f"/v1/traces/{trace_id}") for trace_id in status["trace_ids"])
    )
    assert sorted(r.status_code for r in responses) == [204, 204]
    assert await db.fetchval("select count(*) from uploads where id = $1", upload_id) == 0


async def test_rls_mirrors_api_rules(api: httpx.AsyncClient, db: asyncpg.Connection) -> None:
    """Defense in depth: the policies enforce owner-or-listed without the API.

    Simulates PostgREST by switching to the `authenticated` role with a JWT
    claims GUC, inside a rolled-back transaction.
    """
    trace_id = (await ingest_fixture(api, "minimal"))["trace_ids"][0]
    owner_id = await db.fetchval("select owner_id from traces where id = $1", uuid.UUID(trace_id))
    stranger = uuid.uuid4()

    async def visible_as(uid) -> bool:
        tx = db.transaction()
        await tx.start()
        try:
            await db.execute(
                "select set_config('request.jwt.claims', $1, true)",
                json.dumps({"sub": str(uid), "role": "authenticated"}),
            )
            await db.execute("set local role authenticated")
            count = await db.fetchval(
                "select count(*) from traces where id = $1", uuid.UUID(trace_id)
            )
            return count == 1
        finally:
            await tx.rollback()

    assert await visible_as(owner_id)
    assert not await visible_as(stranger)

    await list_trace(api, trace_id)
    assert await visible_as(stranger)
