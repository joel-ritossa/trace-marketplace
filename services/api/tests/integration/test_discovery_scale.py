"""A4 discovery at scale: the analysis filter extension, subscriptions
(CRUD, event-driven matching, digested notifications, the feed), bulk
operations, and the listing→re-run hook.

Keyless by design (A4 decision 15): label/metric predicates are exercised by
seeding `trace_analysis` directly — the analyzer contract guarantees shape,
and B-stream tests own how values get computed.
"""

import io
import json
import uuid
import zipfile

import asyncpg
import httpx
import pytest

from tests.integration.conftest import API_URL, signup_token
from tests.integration.test_analysis import (
    loop_payload,
    upload_and_ingest,
    wait_analysis,
    wait_until,
)
from tests.integration.test_discovery import list_trace

pytestmark = pytest.mark.asyncio


def unique_payload() -> bytes:
    """loop_payload with a unique source trace id: identity is
    (owner, source_trace_id) since migration 11, so reusing the fixture's
    hardcoded id would adopt-and-rewrite one trace instead of creating
    many."""
    data = json.loads(loop_payload(uuid.uuid4().hex))
    trace_id = uuid.uuid4().hex
    for span in data["resourceSpans"][0]["scopeSpans"][0]["spans"]:
        span["traceId"] = trace_id
    return json.dumps(data).encode()


@pytest.fixture
async def consumer():
    token = await signup_token()
    async with httpx.AsyncClient(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as client:
        yield client


async def seed_analysis(
    db: asyncpg.Connection,
    trace_id: str,
    *,
    outcome: str = "failure",
    outcome_confidence: float = 0.9,
    metric_scores: dict | None = None,
    **extra,
) -> None:
    """Promote a keyless-skipped row to a 'complete' one with known labels —
    the analyzer contract's shape, without an LLM key."""
    cols = {
        "llm_status": "complete",
        "llm_skip_reason": None,
        "outcome": outcome,
        "outcome_confidence": outcome_confidence,
        "outcome_provenance": "machine",
        "metric_scores": json.dumps(metric_scores) if metric_scores is not None else None,
        **extra,
    }
    sets = ", ".join(
        f"{name} = ${i + 2}" + ("::jsonb" if name == "metric_scores" else "")
        for i, name in enumerate(cols)
    )
    await db.execute(
        f"update trace_analysis set {sets} where trace_id = $1",
        uuid.UUID(trace_id),
        *cols.values(),
    )


async def analyzed_trace(api: httpx.AsyncClient, db: asyncpg.Connection, **seed) -> str:
    """Ingest one loop-payload trace, wait for analysis, seed labels."""
    trace_id = await upload_and_ingest(api, unique_payload())
    await wait_analysis(api, trace_id)
    await seed_analysis(db, trace_id, **seed)
    return trace_id


async def ids(api: httpx.AsyncClient, **params) -> set[str]:
    res = await api.get("/v1/traces", params=params)
    assert res.status_code == 200, res.text
    return {t["trace_id"] for t in res.json()["traces"]}


async def test_filter_extension(api: httpx.AsyncClient, db: asyncpg.Connection) -> None:
    failure = await analyzed_trace(
        api,
        db,
        metric_scores={"faithfulness": 0.81, "noise_sensitivity": True},
        task_category="coding",
        task_category_confidence=0.6,
        task_category_provenance="machine",
        failure_mode="invention_of_information",
        failure_mode_provenance="machine",
    )
    success = await analyzed_trace(api, db, outcome="success", outcome_confidence=0.7)
    # A pending (never-analyzed) trace: drop the keyless row.
    pending = await upload_and_ingest(api, unique_payload())
    await wait_analysis(api, pending)
    await db.execute("delete from trace_analysis where trace_id = $1", uuid.UUID(pending))

    everything = {failure, success, pending}
    assert await ids(api) >= everything

    # Equality + CSV OR-within-field.
    assert await ids(api, outcome="failure") == {failure}
    assert await ids(api, outcome="failure,success") == {failure, success}
    assert await ids(api, failure_mode="invention_of_information") == {failure}
    # Unknown-but-well-formed taxonomy value: matches nothing, never errors.
    assert await ids(api, failure_mode="some_future_mode") == set()
    assert await ids(api, task_category="coding") == {failure}
    assert await ids(api, outcome_provenance="machine") == {failure, success}
    assert await ids(api, outcome_provenance="human") == set()

    # Confidence and signal-count min-bounds (loop payload: 1 llm, 3 tools).
    assert await ids(api, outcome_confidence_gte=0.8) == {failure}
    assert await ids(api, tool_call_count_gte=3) >= {failure, success}
    assert await ids(api, tool_call_count_gte=4) == set()

    # Signal booleans: both values are real filters.
    assert await ids(api, has_retry_loop="true") >= {failure, success}
    assert await ids(api, has_retry_loop="false") == set()
    assert await ids(api, loop_kind="exact_repeat") >= {failure, success}

    # Metric predicates: number min-bound, boolean flag, repeats AND.
    assert await ids(api, metric="faithfulness:0.8") == {failure}
    assert await ids(api, metric="faithfulness:0.9") == set()
    assert await ids(api, metric="noise_sensitivity:true") == {failure}
    res = await api.get(
        "/v1/traces", params=[("metric", "faithfulness:0.8"), ("metric", "noise_sensitivity:true")]
    )
    assert {t["trace_id"] for t in res.json()["traces"]} == {failure}
    # A flag queried as a number (and vice versa) matches nothing, no error.
    assert await ids(api, metric="noise_sensitivity:0.5") == set()
    assert await ids(api, metric="faithfulness:true") == set()

    # The excluded-unanalyzed note: only with analysis predicates active.
    res = await api.get("/v1/traces", params={"outcome": "failure"})
    assert res.json()["excluded_unanalyzed"] == 1  # the pending trace
    res = await api.get("/v1/traces")
    assert res.json()["excluded_unanalyzed"] is None

    # Malformed values are 422s, not silent empties.
    for params in (
        {"outcome": "bogus"},
        {"outcome_provenance": "llm"},
        {"loop_kind": "spiral"},
        {"failure_mode": "Bad-Value"},
        {"metric": "faithfulness:high"},
        {"metric": "faithfulness"},
        {"outcome_confidence_gte": "1.5"},
    ):
        res = await api.get("/v1/traces", params=params)
        assert res.status_code == 422, params

    # Metric keys are enumerated from observed data, visible-to-caller.
    res = await api.get("/v1/traces/metric-keys")
    assert {"faithfulness", "noise_sensitivity"} <= set(res.json()["keys"])


async def test_subscription_crud_and_validation(
    api: httpx.AsyncClient, consumer: httpx.AsyncClient
) -> None:
    query = {"outcome": "failure", "metric": ["faithfulness:0.8"]}
    res = await consumer.post("/v1/subscriptions", json={"name": "hard failures", "query": query})
    assert res.status_code == 201, res.text
    sub = res.json()
    assert sub["query"] == query
    assert isinstance(sub["match_count"], int)
    assert sub["last_match_at"] is None

    # The stored query is validated against the filter vocabulary; request
    # shape (scope/sort/pagination) and unknown params are 422.
    for bad in (
        {"outcome": "bogus"},
        {"scope": "marketplace"},
        {"limit": 10},
        {"nonsense": 1},
        {"metric": ["faithfulness:high"]},
        {},  # subscribe-to-everything is rejected at write time
    ):
        res = await consumer.post("/v1/subscriptions", json={"name": "x", "query": bad})
        assert res.status_code == 422, bad
    res = await consumer.post("/v1/subscriptions", json={"name": "   ", "query": query})
    assert res.status_code == 422

    sub_id = sub["subscription_id"]
    res = await consumer.patch(f"/v1/subscriptions/{sub_id}", json={"name": "renamed"})
    assert res.status_code == 200 and res.json()["name"] == "renamed"
    res = await consumer.patch(
        f"/v1/subscriptions/{sub_id}", json={"query": {"outcome": "success"}}
    )
    assert res.status_code == 200 and res.json()["query"] == {"outcome": "success"}
    res = await consumer.patch(f"/v1/subscriptions/{sub_id}", json={})
    assert res.status_code == 422

    listed = (await consumer.get("/v1/subscriptions")).json()["subscriptions"]
    assert [s["subscription_id"] for s in listed] == [sub_id]

    # Owner-scoped: another user sees/touches nothing (404, never 403).
    assert (await api.get(f"/v1/subscriptions/{sub_id}/results")).status_code == 404
    assert (await api.patch(f"/v1/subscriptions/{sub_id}", json={"name": "x"})).status_code == 404
    assert (await api.delete(f"/v1/subscriptions/{sub_id}")).status_code == 404
    assert (await api.get("/v1/subscriptions")).json()["subscriptions"] == []

    assert (await consumer.delete(f"/v1/subscriptions/{sub_id}")).status_code == 204
    assert (await consumer.delete(f"/v1/subscriptions/{sub_id}")).status_code == 404


async def subscription_match_notifications(client: httpx.AsyncClient) -> list[dict]:
    res = await client.get("/v1/notifications", params={"limit": 50})
    res.raise_for_status()
    return [n for n in res.json()["notifications"] if n["type"] == "subscription_match"]


async def wait_for_digest(client: httpx.AsyncClient, sub_id: str, match_count: int) -> dict:
    async def probe():
        for n in await subscription_match_notifications(client):
            payload = n["payload"]
            if (
                payload["subscription_id"] == sub_id
                and n["read_at"] is None
                and payload["match_count"] == match_count
            ):
                return n
        return None

    return await wait_until(
        probe, 30.0, f"no unread subscription_match digest with count {match_count}"
    )


async def test_matching_notifications_and_feed(
    api: httpx.AsyncClient, consumer: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    # Subscriptions execute marketplace-wide, and the local stack's data
    # persists across runs — a per-run metric name pins matching (and the
    # live counts) to this test's traces. Stripped again on the way out so
    # markers don't accumulate in the observed metric-keys vocabulary that
    # the filter UI enumerates.
    marker = f"m_{uuid.uuid4().hex[:10]}"
    query = {"outcome": "failure", "metric": [f"{marker}:0.5"]}
    sub = (
        await consumer.post("/v1/subscriptions", json={"name": "failures", "query": query})
    ).json()
    sub_id = sub["subscription_id"]
    assert sub["match_count"] == 0

    # Trigger (a): a matching trace becomes listed → one first-match record,
    # one notification; the single-match payload deep-links the trace.
    first = await analyzed_trace(api, db, metric_scores={marker: 0.9})
    assert (await list_trace(api, first)).status_code == 200
    digest = await wait_for_digest(consumer, sub_id, 1)
    assert digest["payload"]["trace_id"] == first
    assert digest["payload"]["name"] == "failures"

    # Re-listing re-fires the trigger but the unique pair dedupes: still one
    # match record, the digest count untouched.
    await api.patch(f"/v1/traces/{first}", json={"visibility": "private"})
    assert (await list_trace(api, first)).status_code == 200

    # A second match digests into the same unread notification: count 2, the
    # deep link gives way to the feed link (trace_id dropped).
    second = await analyzed_trace(api, db, metric_scores={marker: 0.7})
    assert (await list_trace(api, second)).status_code == 200
    digest = await wait_for_digest(consumer, sub_id, 2)
    assert "trace_id" not in digest["payload"]
    match_rows = await db.fetchval(
        "select count(*) from subscription_matches where subscription_id = $1",
        uuid.UUID(sub_id),
    )
    assert match_rows == 2
    assert len(await subscription_match_notifications(consumer)) == 1

    # A matching-but-private trace never matches.
    private = await analyzed_trace(api, db, metric_scores={marker: 0.9})
    non_matching = await analyzed_trace(api, db, outcome="success", metric_scores={marker: 0.9})
    assert (await list_trace(api, non_matching)).status_code == 200
    # (give the listing trigger a beat; the count must stay at 2)
    await wait_until(
        lambda: db.fetchval(
            "select case when count(*) = 2 then true end from subscription_matches"
            " where subscription_id = $1",
            uuid.UUID(sub_id),
        ),
        10.0,
        "match ledger drifted",
    )
    assert private not in [
        str(r["trace_id"])
        for r in await db.fetch(
            "select trace_id from subscription_matches where subscription_id = $1",
            uuid.UUID(sub_id),
        )
    ]

    # The feed is the stored query run live: both matches, marked new.
    feed = (await consumer.get(f"/v1/subscriptions/{sub_id}/results")).json()
    feed_ids = {t["trace_id"] for t in feed["traces"]}
    assert feed_ids == {first, second}
    assert all(t["new_since_last_seen"] for t in feed["traces"])
    # Seen stamps; the markers clear.
    assert (await consumer.post(f"/v1/subscriptions/{sub_id}/seen")).status_code == 200
    feed = (await consumer.get(f"/v1/subscriptions/{sub_id}/results")).json()
    assert not any(t["new_since_last_seen"] for t in feed["traces"])

    # Reading the digest frees the slot: the next match starts a fresh one.
    await consumer.post("/v1/notifications/read", json={"all": True})
    third = await analyzed_trace(api, db, metric_scores={marker: 0.6})
    assert (await list_trace(api, third)).status_code == 200
    digest = await wait_for_digest(consumer, sub_id, 1)
    assert digest["payload"]["trace_id"] == third

    # The list view carries the live match count and the ledger's last match.
    listed = (await consumer.get("/v1/subscriptions")).json()["subscriptions"][0]
    assert listed["match_count"] == 3  # first, second, third are listed now
    assert listed["last_match_at"] is not None

    # Own listed traces are not excluded (A4 decision 8, demo scope): the
    # owner subscribing to their own vocabulary sees their traces in the
    # feed and the live count.
    own_sub = (await api.post("/v1/subscriptions", json={"name": "own", "query": query})).json()
    assert own_sub["match_count"] == 3
    own_feed = (await api.get(f"/v1/subscriptions/{own_sub['subscription_id']}/results")).json()
    assert {t["trace_id"] for t in own_feed["traces"]} == {first, second, third}
    assert all(t["is_owner"] for t in own_feed["traces"])

    await db.execute(
        "update trace_analysis set metric_scores = metric_scores - $1::text"
        " where metric_scores ? $1::text",
        marker,
    )


async def test_listing_reruns_opt_out_analysis(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """The listing→re-run hook (1_analysis.md runtime): an owner_opt_out skip
    re-enqueues analyze_trace when the trace becomes listed — listing is the
    consent act. On this keyless stack the re-run lands on not_configured,
    which is exactly the proof the gate re-ran. Matching then arrives via
    trigger (b), analyze-completed-on-a-listed-trace."""
    res = await api.patch("/v1/profile", json={"allow_private_llm_analysis": False})
    assert res.status_code == 200
    trace_id = await upload_and_ingest(api, unique_payload())
    analysis = await wait_analysis(api, trace_id)
    assert analysis["skip_reason"] == "owner_opt_out"

    # Signal-only query: satisfiable keyless, and own traces are not
    # excluded (decision 8) so the owner's own subscription can prove it.
    sub = (
        await api.post(
            "/v1/subscriptions",
            json={"name": "loops", "query": {"has_retry_loop": True}},
        )
    ).json()

    assert (await list_trace(api, trace_id)).status_code == 200

    async def reanalyzed():
        body = (await api.get(f"/v1/traces/{trace_id}/analysis")).json()
        return body if body["skip_reason"] == "not_configured" else None

    await wait_until(reanalyzed, 30.0, "listing never re-ran the opt-out skip")

    async def matched():
        return await db.fetchval(
            "select true from subscription_matches where subscription_id = $1 and trace_id = $2",
            uuid.UUID(sub["subscription_id"]),
            uuid.UUID(trace_id),
        )

    await wait_until(matched, 30.0, "trigger (b) never matched the re-analyzed trace")


async def test_bulk_acquire_and_visibility(
    api: httpx.AsyncClient, consumer: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    listed = await analyzed_trace(api, db)
    private = await analyzed_trace(api, db)
    own = await upload_and_ingest(consumer, unique_payload())
    ghost = str(uuid.uuid4())

    # Bulk listing requires the batched consent.
    res = await api.post(
        "/v1/traces/visibility", json={"trace_ids": [listed], "visibility": "listed"}
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "confirmation_required"

    # Itemized visibility results: not-owned and absent alike are not_found.
    res = await api.post(
        "/v1/traces/visibility",
        json={
            "trace_ids": [listed, ghost, own],
            "visibility": "listed",
            "confirm_ownership": True,
        },
    )
    assert res.status_code == 200
    assert {r["trace_id"]: r["status"] for r in res.json()["results"]} == {
        listed: "updated",
        ghost: "not_found",
        own: "not_found",
    }

    # Itemized acquire: every outcome named, partial success is normal.
    res = await consumer.post(
        "/v1/traces/acquire", json={"trace_ids": [listed, private, ghost, own]}
    )
    assert res.status_code == 200
    assert {r["trace_id"]: r["status"] for r in res.json()["results"]} == {
        listed: "acquired",
        private: "not_found",  # invisible == absent
        ghost: "not_found",
        own: "own_trace",
    }
    # Idempotent re-acquire.
    res = await consumer.post("/v1/traces/acquire", json={"trace_ids": [listed]})
    assert res.json()["results"][0]["status"] == "already_acquired"

    # Bounded batches.
    res = await consumer.post(
        "/v1/traces/acquire", json={"trace_ids": [str(uuid.uuid4()) for _ in range(101)]}
    )
    assert res.status_code == 422
    res = await consumer.post("/v1/traces/acquire", json={"trace_ids": []})
    assert res.status_code == 422


async def test_bulk_download(
    api: httpx.AsyncClient, consumer: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    analyzed = await analyzed_trace(api, db, metric_scores={"faithfulness": 0.81})
    plain = await upload_and_ingest(api, unique_payload())
    await wait_analysis(api, plain)
    await db.execute("delete from trace_analysis where trace_id = $1", uuid.UUID(plain))
    for trace_id in (analyzed, plain):
        assert (await list_trace(api, trace_id)).status_code == 200

    # Every id must be owner-or-acquired: 403 names the offenders.
    res = await consumer.post("/v1/traces/download", json={"trace_ids": [analyzed, plain]})
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "acquisition_required"
    assert analyzed in res.json()["error"]["message"]

    # Owner: raw payloads (deduped per upload) + labels.jsonl.
    res = await api.post("/v1/traces/download", json={"trace_ids": [analyzed, plain]})
    assert res.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(res.content))
    names = archive.namelist()
    assert "labels.jsonl" in names
    payload_entries = [n for n in names if n != "labels.jsonl"]
    assert len(payload_entries) == 2  # two uploads → two distinct payloads
    lines = [json.loads(line) for line in archive.read("labels.jsonl").decode().splitlines()]
    by_id = {line["trace_id"]: line for line in lines}
    assert set(by_id) == {analyzed, plain}
    assert by_id[analyzed]["outcome"]["value"] == "failure"
    assert by_id[analyzed]["metric_scores"] == {"faithfulness": 0.81}
    assert by_id[analyzed]["signals"]["has_retry_loop"] is True
    assert by_id[analyzed]["analyzer_versions"]
    # The unanalyzed trace gets an honest all-null line.
    assert by_id[plain]["outcome"] is None
    assert by_id[plain]["metric_scores"] is None
    assert by_id[plain]["signals"] is None

    # Acquirer: the scrubbed artifact serves, never the raw object.
    res = await consumer.post("/v1/traces/acquire", json={"trace_ids": [analyzed]})
    assert res.json()["results"][0]["status"] == "acquired"
    res = await consumer.post("/v1/traces/download", json={"trace_ids": [analyzed]})
    assert res.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(res.content))
    assert "labels.jsonl" in archive.namelist()
    assert len(archive.namelist()) == 2
