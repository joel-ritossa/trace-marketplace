"""A3 HIL loop: routing → review item + digested notification → queue →
resolve with provenance; supersede on re-route; the human-provenance filter;
owner relabel; upload_failed for CLI uploads.

Keyless by design: the canned-verdict fault (X-Fault: analyze:verdict:…)
stands in for the judge, so routing/digest/queue/resolve run end-to-end on
the compose stack with no provider key (A3 decision 9).
"""

import json
import subprocess
import uuid

import asyncpg
import httpx
import pytest

from tests.integration.conftest import API_URL, otlp_payload, signup_token
from tests.integration.test_analysis import SERVICE_DIR, wait_analysis, wait_until
from tests.integration.test_uploads import upload_file, wait_terminal

pytestmark = pytest.mark.asyncio

LOW = {"X-Fault": "analyze:verdict:success:0.4"}  # routes: low_outcome_confidence


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
    fault: dict = LOW,
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


def requeue_upload(upload_id: str) -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "app.cli.requeue", "upload", upload_id],
        cwd=SERVICE_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


async def test_routing_creates_items_and_one_digest(api: httpx.AsyncClient) -> None:
    """Done-when core: an uncertain verdict creates review items and exactly
    one unread digest notification per upload, item_count accumulating."""
    upload_id, trace_ids = await upload_routed(
        api, two_trace_payload(uuid.uuid4().hex), filename="batch.json"
    )
    items = await wait_open_items(api, upload_id, 2)

    for item in items:
        assert item["status"] == "open"
        assert item["question_type"] == "verdict"
        assert item["upload_filename"] == "batch.json"
        assert item["context"]["verdict"]["outcome"] == "success"
        assert item["context"]["verdict"]["outcome_confidence"] == 0.4
        assert [r["code"] for r in item["context"]["reasons"]] == ["low_outcome_confidence"]
        assert item["trace_id"] in trace_ids
    # Newest first (3_api.md).
    assert items == sorted(items, key=lambda i: i["created_at"], reverse=True)

    # One digest, not two: the second item upserted into the first's slot.
    res = await api.get("/v1/notifications")
    body = res.json()
    digests = [n for n in body["notifications"] if n["type"] == "review_request"]
    assert len(digests) == 1
    assert digests[0]["payload"]["upload_id"] == upload_id
    assert digests[0]["payload"]["filename"] == "batch.json"
    assert digests[0]["payload"]["item_count"] == 2
    assert digests[0]["read_at"] is None
    assert body["unread_count"] == 1

    # The owner's surfaces carry the open item (A3 decision 8).
    listed = (await api.get("/v1/traces?scope=mine")).json()
    by_id = {t["trace_id"]: t for t in listed["traces"]}
    open_ids = {i["trace_id"]: i["review_item_id"] for i in items}
    for trace_id in trace_ids:
        assert by_id[trace_id]["has_open_review_item"] is True
        assert by_id[trace_id]["open_review_item_id"] == open_ids[trace_id]
    analysis = (await api.get(f"/v1/traces/{trace_ids[0]}/analysis")).json()
    assert analysis["analysis_state"] == "complete"
    assert analysis["open_review_item_id"] == open_ids[trace_ids[0]]

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
        assert card["outcome_provenance"] == "machine"
        assert card["has_open_review_item"] is False
        assert card["open_review_item_id"] is None
        foreign_analysis = (await other.get(f"/v1/traces/{trace_ids[0]}/analysis")).json()
        assert foreign_analysis["open_review_item_id"] is None


async def test_resolve_writes_provenance(api: httpx.AsyncClient) -> None:
    """Resolve writes the answer to trace_analysis with human provenance and
    confidence 1.0; matching the machine value records human_confirmed;
    repeats 409; foreign access 404s."""
    upload_id, (trace_id,) = await upload_routed(api, otlp_payload(uuid.uuid4().hex))
    (item,) = await wait_open_items(api, upload_id, 1)
    item_id = item["review_item_id"]

    # Disagree with the machine on outcome; answer the unlabelled category.
    res = await api.post(
        f"/v1/review-items/{item_id}/resolve",
        json={"outcome": "failure", "task_category": "coding"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["item"]["status"] == "resolved"
    assert body["item"]["answer"] == {
        "outcome": "failure",
        "failure_mode": None,
        "task_category": "coding",
    }
    assert body["labels"]["outcome"] == {
        "value": "failure",
        "confidence": 1.0,
        "provenance": "human",
    }
    # No machine category existed, so this is a fresh human label, not a
    # confirmation.
    assert body["labels"]["task_category"]["provenance"] == "human"

    analysis = (await api.get(f"/v1/traces/{trace_id}/analysis")).json()
    assert analysis["labels"]["outcome"] == {
        "value": "failure",
        "confidence": 1.0,
        "provenance": "human",
    }
    assert analysis["open_review_item_id"] is None  # nothing open anymore

    # The list-level outcome triplet reflects the human label.
    listed = (await api.get("/v1/traces?scope=mine")).json()
    row = next(t for t in listed["traces"] if t["trace_id"] == trace_id)
    assert row["outcome"] == "failure"
    assert row["outcome_provenance"] == "human"
    assert row["has_open_review_item"] is False

    res = await api.post(f"/v1/review-items/{item_id}/resolve", json={"outcome": "failure"})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "already_resolved"

    # Review items are owner-scoped: foreign access is 404, not 403.
    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=API_URL, headers={"Authorization": f"Bearer {other_token}"}, timeout=30.0
    ) as other:
        assert (await other.get(f"/v1/review-items/{item_id}")).status_code == 404
        res = await other.post(f"/v1/review-items/{item_id}/resolve", json={"outcome": "success"})
        assert res.status_code == 404
        assert (await other.get("/v1/notifications")).json()["total"] == 0


async def test_matching_machine_answer_confirms(api: httpx.AsyncClient) -> None:
    upload_id, (trace_id,) = await upload_routed(api, otlp_payload(uuid.uuid4().hex))
    (item,) = await wait_open_items(api, upload_id, 1)

    res = await api.post(
        f"/v1/review-items/{item['review_item_id']}/resolve", json={"outcome": "success"}
    )
    assert res.status_code == 200
    assert res.json()["labels"]["outcome"] == {
        "value": "success",
        "confidence": 1.0,
        "provenance": "human_confirmed",
    }


async def test_non_failure_outcome_nulls_machine_failure_mode(api: httpx.AsyncClient) -> None:
    """A canned failure verdict carries a machine failure_mode; a human
    non-failure outcome clears it (the judge only diagnoses failures)."""
    upload_id, (trace_id,) = await upload_routed(
        api,
        otlp_payload(uuid.uuid4().hex),
        fault={"X-Fault": "analyze:verdict:failure:0.4"},
    )
    (item,) = await wait_open_items(api, upload_id, 1)
    assert item["context"]["verdict"]["failure_mode"] == "inconclusive"

    res = await api.post(
        f"/v1/review-items/{item['review_item_id']}/resolve", json={"outcome": "success"}
    )
    assert res.status_code == 200

    analysis = (await api.get(f"/v1/traces/{trace_id}/analysis")).json()
    assert analysis["labels"]["outcome"]["value"] == "success"
    assert analysis["labels"]["failure_mode"] is None


async def test_reroute_supersedes_then_human_filter_stops_routing(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """A re-run that routes again supersedes the open item (never
    duplicates) and bumps the digest; once the outcome is human-resolved,
    the same routing reasons are filtered and nothing routes again."""
    upload_id, (trace_id,) = await upload_routed(api, otlp_payload(uuid.uuid4().hex))
    (first,) = await wait_open_items(api, upload_id, 1)

    # Re-ingest with the fault still armed: same uncertain verdict again.
    requeue_upload(upload_id)
    assert (await wait_terminal(api, upload_id))["trace_ids"] == [trace_id]

    async def superseded():
        res = await api.get(f"/v1/review-items/{first['review_item_id']}")
        return res.json() if res.json()["status"] == "superseded" else None

    await wait_until(superseded, 30.0, "first item was never superseded")
    (second,) = await wait_open_items(api, upload_id, 1)
    assert second["review_item_id"] != first["review_item_id"]

    # Still one digest; the second routing incremented it.
    digests = [
        n
        for n in (await api.get("/v1/notifications")).json()["notifications"]
        if n["type"] == "review_request"
    ]
    assert len(digests) == 1
    assert digests[0]["payload"]["item_count"] == 2

    # Human-resolve the outcome, re-run again: the only routing reason
    # targets outcome, which now carries human provenance — filtered out.
    res = await api.post(
        f"/v1/review-items/{second['review_item_id']}/resolve", json={"outcome": "failure"}
    )
    assert res.status_code == 200
    before = await db.fetchval(
        "select analyzed_at from trace_analysis where trace_id = $1", uuid.UUID(trace_id)
    )
    requeue_upload(upload_id)
    assert (await wait_terminal(api, upload_id))["trace_ids"] == [trace_id]

    async def reanalyzed():
        ts = await db.fetchval(
            "select analyzed_at from trace_analysis where trace_id = $1", uuid.UUID(trace_id)
        )
        return ts if ts is not None and ts != before else None

    await wait_until(reanalyzed, 30.0, "trace was never re-analyzed")

    open_items = (await api.get(f"/v1/review-items?upload_id={upload_id}")).json()["items"]
    assert open_items == []
    resolved = (await api.get(f"/v1/review-items/{second['review_item_id']}")).json()
    assert resolved["status"] == "resolved"  # newer truth never reopens it
    # The human label survived the machine rewrite.
    analysis = (await api.get(f"/v1/traces/{trace_id}/analysis")).json()
    assert analysis["labels"]["outcome"]["provenance"] == "human"
    # And no third digest bump.
    digests = [
        n
        for n in (await api.get("/v1/notifications")).json()["notifications"]
        if n["type"] == "review_request"
    ]
    assert digests[0]["payload"]["item_count"] == 2

    await disarm(upload_id)


async def test_owner_relabel(api: httpx.AsyncClient, db: asyncpg.Connection) -> None:
    """The owner can self-create an item on an analyzed trace (idempotent
    while open) — even a keyless-skipped one; unanalyzed traces 409."""
    res = await upload_file(api, otlp_payload(uuid.uuid4().hex))
    upload_id = res.json()["upload_id"]
    status = await wait_terminal(api, upload_id)
    trace_id = status["trace_ids"][0]
    analysis = await wait_analysis(api, trace_id)
    assert analysis["analysis_state"] == "skipped"  # keyless, no fault

    res = await api.post(f"/v1/traces/{trace_id}/review-items")
    assert res.status_code == 201
    item = res.json()
    assert item["context"]["reasons"] == []  # owner-initiated marker
    assert item["context"]["verdict"]["outcome"] is None  # no machine take

    # Idempotent while open.
    res = await api.post(f"/v1/traces/{trace_id}/review-items")
    assert res.status_code == 200
    assert res.json()["review_item_id"] == item["review_item_id"]

    # Owner-only, 404-not-403 (review state is private even on listed traces).
    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=API_URL, headers={"Authorization": f"Bearer {other_token}"}, timeout=30.0
    ) as other:
        assert (await other.post(f"/v1/traces/{trace_id}/review-items")).status_code == 404

    # Resolving against a null machine value is a fresh human label.
    res = await api.post(
        f"/v1/review-items/{item['review_item_id']}/resolve", json={"outcome": "indeterminate"}
    )
    assert res.status_code == 200
    assert res.json()["labels"]["outcome"]["provenance"] == "human"

    # Resolved item frees the slot: relabel again creates a fresh one.
    res = await api.post(f"/v1/traces/{trace_id}/review-items")
    assert res.status_code == 201
    assert res.json()["review_item_id"] != item["review_item_id"]

    # No trace_analysis row -> nothing to resolve into -> 409.
    await db.execute("delete from review_items where trace_id = $1", uuid.UUID(trace_id))
    await db.execute("delete from trace_analysis where trace_id = $1", uuid.UUID(trace_id))
    res = await api.post(f"/v1/traces/{trace_id}/review-items")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "analysis_pending"


async def test_resolve_validates_taxonomies(api: httpx.AsyncClient) -> None:
    upload_id, _ = await upload_routed(api, otlp_payload(uuid.uuid4().hex))
    (item,) = await wait_open_items(api, upload_id, 1)
    item_id = item["review_item_id"]

    for bad in (
        {},
        {"outcome": "maybe"},
        {"failure_mode": "gremlins"},
        {"task_category": "x"},
        # failure_mode only accompanies a failure outcome (label model).
        {"outcome": "success", "failure_mode": "inconclusive"},
        {"outcome": "indeterminate", "failure_mode": "inconclusive"},
    ):
        res = await api.post(f"/v1/review-items/{item_id}/resolve", json=bad)
        assert res.status_code == 422, bad


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
