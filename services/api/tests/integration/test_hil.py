"""HIL loop (9_session-analysis.md Review): an uncertain turn → one review
item per trace + a digested notification → queue → owner relabel of the
turn; re-judging keeps, supersedes or replaces the item; human turns are
never re-judged; upload_failed for CLI uploads.

Keyless by design: the canned-verdict fault (X-Fault: analyze:verdict:…)
stands in for the judge, so the item/digest/queue/relabel loop runs
end-to-end on the compose stack with no provider key (A3 decision 9).
"""

import json
import uuid

import asyncpg
import httpx
import pytest

from tests.integration.conftest import API_URL, otlp_payload, signup_token
from tests.integration.test_analysis import upload_and_ingest, wait_analysis, wait_until
from tests.integration.test_uploads import upload_file, wait_terminal

pytestmark = pytest.mark.asyncio

UNCERTAIN = {"X-Fault": "analyze:verdict:success:uncertain"}
CANNED_TURN = {
    "turn_index": 0,
    "reason": "Fault injection: canned uncertain turn.",
    "summary": "Fault injection: canned verdict.",
}
SPAN_ID = "cd" * 8  # otlp_payload's only span


def tool_payload(marker: str) -> bytes:
    """otlp_payload with its span as a tool call — citable evidence (only
    llm/tool spans in the turn are)."""
    payload = json.loads(otlp_payload(marker))
    span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    span["attributes"] = [
        {"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}}
    ]
    return json.dumps(payload).encode()


def two_trace_payload(marker: str) -> bytes:
    """Two traces in one upload — the digest's 'N traces from upload X'."""

    def span(trace_id: str) -> dict:
        return {
            "traceId": trace_id,
            "spanId": "cd" * 8,
            "name": f"span {trace_id[:4]}",
            "startTimeUnixNano": "1768471200000000000",
            "endTimeUnixNano": "1768471201000000000",
            "attributes": [],
            "status": {"code": 1},
        }

    return json.dumps(
        {
            "resourceSpans": [{"scopeSpans": [{"spans": [span("ab" * 16), span("ba" * 16)]}]}],
            "_marker": marker,
        }
    ).encode()


async def upload_routed(
    api: httpx.AsyncClient,
    payload: bytes,
    *,
    fault: dict = UNCERTAIN,
    filename: str = "trace.json",
) -> tuple[str, list[str]]:
    """Upload with a canned-verdict fault armed; wait for ingest."""
    res = await upload_file(api, payload, filename=filename, headers=fault)
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]
    status = await wait_terminal(api, upload_id)
    assert status["status"] == "complete", status
    return upload_id, status["trace_ids"]


async def wait_open_items(api: httpx.AsyncClient, upload_id: str, count: int) -> list[dict]:
    async def probe():
        res = await api.get(f"/v1/review-items?upload_id={upload_id}")
        res.raise_for_status()
        body = res.json()
        return body["items"] if len(body["items"]) == count else None

    return await wait_until(probe, 30.0, f"upload {upload_id} never reached {count} open items")


async def disarm(upload_id: str) -> None:
    from redis.asyncio import Redis

    from app.config import settings

    redis = Redis.from_url(settings.redis_url)
    await redis.delete(f"fault:{upload_id}")
    await redis.aclose()


async def rearm(upload_id: str, spec: str) -> None:
    """Swap the armed fault between runs — e.g. uncertain verdict on the
    first analysis, confident verdict on the re-run."""
    from redis.asyncio import Redis

    from app.config import settings

    redis = Redis.from_url(settings.redis_url)
    await redis.set(f"fault:{upload_id}", spec, ex=3600)
    await redis.aclose()


async def rejudge(api: httpx.AsyncClient, db: asyncpg.Connection, trace_id: str) -> None:
    """Re-judge the trace's machine turns as if their spans changed: stale
    fingerprints and roll-up (a final trace queues nothing), then the
    owner's analyze request; wait until rewritten."""
    await db.execute(
        "update turn_analysis set fingerprint = 'stale' where trace_id = $1", uuid.UUID(trace_id)
    )
    await db.execute(
        "update trace_analysis set analyzed_at = null where trace_id = $1", uuid.UUID(trace_id)
    )
    assert (await api.post(f"/v1/traces/{trace_id}/analyze")).status_code == 202

    async def rewritten():
        return await db.fetchval(
            "select case when count(*) = 0 then true end from turn_analysis"
            " where trace_id = $1 and fingerprint = 'stale'",
            uuid.UUID(trace_id),
        )

    await wait_until(rewritten, 30.0, f"trace {trace_id} was never re-judged")


async def review_digests(api: httpx.AsyncClient) -> list[dict]:
    body = (await api.get("/v1/notifications")).json()
    return [n for n in body["notifications"] if n["type"] == "review_request"]


async def test_uncertain_turns_create_items_and_one_digest(api: httpx.AsyncClient) -> None:
    """Done-when core: an uncertain turn creates a review item listing it,
    and exactly one unread digest notification per upload, item_count
    accumulating."""
    upload_id, trace_ids = await upload_routed(
        api, two_trace_payload(uuid.uuid4().hex), filename="batch.json"
    )
    items = await wait_open_items(api, upload_id, 2)

    for item in items:
        assert item["status"] == "open"
        assert item["upload_filename"] == "batch.json"
        assert item["context"] == {"turns": [CANNED_TURN]}
        assert item["trace_id"] in trace_ids
        assert item["resolved_by"] is None
    # Newest first (3_api.md).
    assert items == sorted(items, key=lambda i: i["created_at"], reverse=True)

    # One digest, not two: the second item upserted into the first's slot.
    digests = await review_digests(api)
    assert len(digests) == 1
    assert digests[0]["payload"]["upload_id"] == upload_id
    assert digests[0]["payload"]["filename"] == "batch.json"
    assert digests[0]["payload"]["item_count"] == 2
    # Items span two traces: the digest stops naming one, counts the turns.
    assert "trace_id" not in digests[0]["payload"]
    assert digests[0]["payload"]["uncertain_turns"] == 2
    assert digests[0]["read_at"] is None
    assert (await api.get("/v1/notifications")).json()["unread_count"] == 1

    # The owner's surfaces carry the open item (A3 decision 8).
    listed = (await api.get("/v1/traces?scope=mine")).json()
    by_id = {t["trace_id"]: t for t in listed["traces"]}
    open_ids = {i["trace_id"]: i["review_item_id"] for i in items}
    for trace_id in trace_ids:
        assert by_id[trace_id]["analysis_status"] == "final"
        assert by_id[trace_id]["has_open_review_item"] is True
        assert by_id[trace_id]["open_review_item_id"] == open_ids[trace_id]
    analysis = (await api.get(f"/v1/traces/{trace_ids[0]}")).json()["analysis"]
    assert analysis["session"]["status"] == "final"
    assert analysis["session"]["outcome"] == "success"
    assert analysis["session"]["task_categories"] == ["other"]
    assert analysis["open_review_item_id"] == open_ids[trace_ids[0]]
    (turn,) = analysis["turns"]
    assert turn["uncertain"] == CANNED_TURN["reason"]
    assert turn["provenance"] == "machine"

    # Unresolved items leave the trace machine-labeled and listable; the
    # owner's review backlog never shows on a non-owner's card (decision 8).
    res = await api.patch(
        f"/v1/traces/{trace_ids[0]}",
        json={"visibility": "listed", "confirm_ownership": True},
    )
    assert res.status_code == 200
    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=API_URL, headers={"Authorization": f"Bearer {other_token}"}, timeout=30.0
    ) as other:
        market = (await other.get("/v1/traces?scope=marketplace")).json()
        card = next(t for t in market["traces"] if t["trace_id"] == trace_ids[0])
        assert card["outcome"] == "success"  # machine label intact
        assert card["has_open_review_item"] is False
        assert card["open_review_item_id"] is None
        foreign = (await other.get(f"/v1/traces/{trace_ids[0]}")).json()["analysis"]
        assert foreign["open_review_item_id"] is None
        # `uncertain` is review content: owner-only.
        assert [t["uncertain"] for t in foreign["turns"]] == [None]


async def test_relabel_resolves_item(api: httpx.AsyncClient, db: asyncpg.Connection) -> None:
    """Relabeling the uncertain turn makes it human, recomputes the session
    arrays and resolves the item (resolved_by = owner); a later re-analysis
    never re-judges the human turn or reopens the item; foreign access 404s."""
    upload_id, (trace_id,) = await upload_routed(api, tool_payload(uuid.uuid4().hex))
    (item,) = await wait_open_items(api, upload_id, 1)
    item_id = item["review_item_id"]
    digest = (await review_digests(api))[0]["payload"]
    assert (digest["trace_id"], digest["uncertain_turns"]) == (trace_id, 1)
    assert digest["trace_name"]
    owner_id = (await api.get("/v1/profile")).json()["id"]

    labels = {
        "outcome": "failure",
        "task_categories": ["coding", "debugging"],
        "failure_modes": [
            {"value": "invalid_invocation", "span_ids": [SPAN_ID], "reason": "Bad args."}
        ],
    }
    res = await api.put(f"/v1/traces/{trace_id}/turns/0/labels", json=labels)
    assert res.status_code == 200, res.text
    analysis = res.json()
    (turn,) = analysis["turns"]
    assert turn["provenance"] == "human"
    assert turn["outcome"] == "failure"
    assert turn["uncertain"] is None
    assert {(lb["field"], lb["value"]) for lb in turn["labels"]} == {
        ("task_category", "coding"),
        ("task_category", "debugging"),
        ("failure_mode", "invalid_invocation"),
    }
    failure = next(lb for lb in turn["labels"] if lb["field"] == "failure_mode")
    assert failure["span_ids"] == [SPAN_ID]
    assert failure["reason"] == "Bad args."
    assert analysis["session"]["task_categories"] == ["coding", "debugging"]
    assert analysis["session"]["failure_modes"] == ["invalid_invocation"]
    assert analysis["open_review_item_id"] is None  # nothing open anymore

    resolved = (await api.get(f"/v1/review-items/{item_id}")).json()
    assert resolved["status"] == "resolved"
    assert resolved["resolved_by"] == owner_id
    assert resolved["resolved_at"] is not None

    # The list-level labels reflect the human turn.
    listed = (await api.get("/v1/traces?scope=mine")).json()
    row = next(t for t in listed["traces"] if t["trace_id"] == trace_id)
    assert row["task_categories"] == ["coding", "debugging"]
    assert row["failure_modes"] == ["invalid_invocation"]
    assert row["has_open_review_item"] is False

    # A finalizing re-run (stale roll-up, stale fingerprint, verdict still
    # armed) leaves the human turn alone and opens nothing.
    await db.execute(
        "update turn_analysis set fingerprint = 'stale' where trace_id = $1", uuid.UUID(trace_id)
    )
    await db.execute(
        "update trace_analysis set analyzed_at = null where trace_id = $1", uuid.UUID(trace_id)
    )
    assert (await api.post(f"/v1/traces/{trace_id}/analyze")).status_code == 202
    analysis = await wait_analysis(api, trace_id)
    assert analysis["session"]["status"] == "final"
    (turn,) = analysis["turns"]
    assert (turn["provenance"], turn["outcome"], turn["uncertain"]) == ("human", "failure", None)
    assert analysis["session"]["task_categories"] == ["coding", "debugging"]
    assert (await api.get(f"/v1/review-items?upload_id={upload_id}")).json()["items"] == []
    assert (await api.get(f"/v1/review-items/{item_id}")).json()["status"] == "resolved"
    assert (await review_digests(api))[0]["payload"]["item_count"] == 1
    await disarm(upload_id)

    # Review items and relabels are owner-scoped: foreign access is 404.
    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=API_URL, headers={"Authorization": f"Bearer {other_token}"}, timeout=30.0
    ) as other:
        assert (await other.get(f"/v1/review-items/{item_id}")).status_code == 404
        res = await other.put(f"/v1/traces/{trace_id}/turns/0/labels", json=labels)
        assert res.status_code == 404
        assert (await other.get("/v1/notifications")).json()["total"] == 0


async def test_rejudge_keeps_supersedes_or_replaces_item(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """A re-judge asking the same question keeps the open item (no
    duplicate, no digest bump); a confident one supersedes it; a new
    uncertain one opens a fresh item into the same unread digest."""
    upload_id, (trace_id,) = await upload_routed(api, otlp_payload(uuid.uuid4().hex))
    (first,) = await wait_open_items(api, upload_id, 1)

    await rejudge(api, db, trace_id)
    (same,) = await wait_open_items(api, upload_id, 1)
    assert same["review_item_id"] == first["review_item_id"]
    assert (await review_digests(api))[0]["payload"]["item_count"] == 1

    await rearm(upload_id, "analyze:verdict:success")
    await rejudge(api, db, trace_id)
    assert (await api.get(f"/v1/review-items/{first['review_item_id']}")).json()[
        "status"
    ] == "superseded"
    assert (await api.get(f"/v1/review-items?upload_id={upload_id}")).json()["items"] == []

    await rearm(upload_id, UNCERTAIN["X-Fault"])
    await rejudge(api, db, trace_id)
    (fresh,) = await wait_open_items(api, upload_id, 1)
    assert fresh["review_item_id"] != first["review_item_id"]
    digests = await review_digests(api)
    assert len(digests) == 1
    assert digests[0]["payload"]["item_count"] == 2

    await disarm(upload_id)


async def test_relabel_validation(api: httpx.AsyncClient, db: asyncpg.Connection) -> None:
    """Owners relabel any analyzed turn — even a keyless-skipped one, with
    no review item involved. Bad vocabularies and span ids outside the
    turn are 422; an unknown turn 404s; a turn with no row yet 409s;
    non-owners get 404 on private traces and 403 on listed ones."""
    trace_id = await upload_and_ingest(api, tool_payload(uuid.uuid4().hex))
    analysis = await wait_analysis(api, trace_id)
    assert analysis["session"]["status"] == "skipped"  # keyless, no fault
    url = f"/v1/traces/{trace_id}/turns/0/labels"

    for bad in (
        {},
        {"outcome": "maybe", "task_categories": ["coding"]},
        {"outcome": "success", "task_categories": []},
        {"outcome": "success", "task_categories": ["x"]},
        {"outcome": "failure", "task_categories": ["coding"], "failure_modes": [{"value": "x"}]},
        # `inconclusive` left the taxonomy: an empty set says "none identified".
        {
            "outcome": "failure",
            "task_categories": ["coding"],
            "failure_modes": [{"value": "inconclusive"}],
        },
        {
            "outcome": "failure",
            "task_categories": ["coding"],
            "failure_modes": [{"value": "invalid_invocation", "span_ids": ["ff" * 8]}],
        },
        # Duplicates are rejected, not merged.
        {"outcome": "success", "task_categories": ["coding", "coding"]},
        {
            "outcome": "failure",
            "task_categories": ["coding"],
            "failure_modes": [{"value": "invalid_invocation"}, {"value": "invalid_invocation"}],
        },
    ):
        res = await api.put(url, json=bad)
        assert res.status_code == 422, bad

    body = {"outcome": "indeterminate", "task_categories": ["other"]}
    res = await api.put(f"/v1/traces/{trace_id}/turns/5/labels", json=body)
    assert res.status_code == 404

    res = await api.put(url, json=body)
    assert res.status_code == 200
    assert res.json()["turns"][0]["provenance"] == "human"
    assert (await api.get("/v1/review-items?status=all")).json()["items"] == []

    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=API_URL, headers={"Authorization": f"Bearer {other_token}"}, timeout=30.0
    ) as other:
        assert (await other.put(url, json=body)).status_code == 404
        res = await api.patch(
            f"/v1/traces/{trace_id}", json={"visibility": "listed", "confirm_ownership": True}
        )
        assert res.status_code == 200
        assert (await other.put(url, json=body)).status_code == 403

    # No turn row yet -> nothing to relabel -> 409. Let the finalizing run
    # each relabel enqueues settle first, or it would recreate the row.
    async def settled() -> bool | None:
        return (
            await db.fetchval(
                """
            select analysis_attempts > 0 and analysis_lease_until is null
                   and analysis_rerun is null
            from traces where id = $1
            """,
                uuid.UUID(trace_id),
            )
            or None
        )

    await wait_until(settled, 60.0, "relabel finalization never settled")
    await db.execute("delete from turn_analysis where trace_id = $1", uuid.UUID(trace_id))
    res = await api.put(url, json=body)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "analysis_pending"


async def test_upload_failed_notification_is_cli_only(api: httpx.AsyncClient) -> None:
    """A failed CLI upload notifies its owner; the same failure from the web
    door doesn't (it failed in front of the user). Mark-read is idempotent
    and recipient-scoped."""
    res = await api.post("/v1/api-keys", json={"name": "hil-integration"})
    assert res.status_code == 201
    key = res.json()["api_key"]

    # Valid JSON (passes the upload door) with no spans: a permanent
    # ingest failure in the worker — the unattended kind.
    def broken(marker: str) -> bytes:
        return json.dumps({"resourceSpans": [], "_marker": marker}).encode()

    async with httpx.AsyncClient(
        base_url=API_URL, headers={"Authorization": f"Bearer {key}"}, timeout=30.0
    ) as cli:
        res = await upload_file(cli, broken(uuid.uuid4().hex), filename="broken-sync.json")
        assert res.status_code == 201
        status = await wait_terminal(cli, res.json()["upload_id"])
        assert status["status"] == "failed"

    async def notified():
        body = (await api.get("/v1/notifications")).json()
        failed = [n for n in body["notifications"] if n["type"] == "upload_failed"]
        return failed if failed else None

    (notification,) = await wait_until(notified, 30.0, "upload_failed never arrived")
    assert notification["payload"]["filename"] == "broken-sync.json"
    assert notification["read_at"] is None

    # The same failure through the web door stays silent.
    res = await upload_file(api, broken(uuid.uuid4().hex), filename="broken-web.json")
    status = await wait_terminal(api, res.json()["upload_id"])
    assert status["status"] == "failed"
    body = (await api.get("/v1/notifications")).json()
    assert len([n for n in body["notifications"] if n["type"] == "upload_failed"]) == 1

    # Foreign mark-read no-ops; own mark-read sticks and repeats are 204.
    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=API_URL, headers={"Authorization": f"Bearer {other_token}"}, timeout=30.0
    ) as other:
        res = await other.post(
            "/v1/notifications/read", json={"ids": [notification["notification_id"]]}
        )
        assert res.status_code == 204
    assert (await api.get("/v1/notifications")).json()["unread_count"] == 1

    for _ in range(2):
        res = await api.post(
            "/v1/notifications/read", json={"ids": [notification["notification_id"]]}
        )
        assert res.status_code == 204
    body = (await api.get("/v1/notifications")).json()
    assert body["unread_count"] == 0
    assert all(n["read_at"] is not None for n in body["notifications"])

    # Exactly one of ids/all (3_api.md).
    res = await api.post("/v1/notifications/read", json={})
    assert res.status_code == 422

    # Malformed ids no-op like foreign ones — never a 500.
    res = await api.post("/v1/notifications/read", json={"ids": ["not-a-uuid"]})
    assert res.status_code == 204
