"""A2 analysis plumbing: real signals persisted, honest skip states, stable
trace identity across re-ingest, human-label preservation, and the injected
failure → dead letter → `failed` → requeue loop.

The compose worker gets no provider key (docker-compose.yml passes none), so
the LLM gate deterministically lands on `not_configured` here; live-judge
behavior is exercised by B2's offline runner against a real key.
"""

import asyncio
import json
import subprocess
import uuid
from pathlib import Path

import asyncpg
import httpx
import pytest

from tests.integration.test_uploads import upload_file, wait_terminal

pytestmark = pytest.mark.asyncio


async def wait_until(probe, timeout: float, message: str):
    """Poll an async probe until it returns a non-None value."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        value = await probe()
        if value is not None:
            return value
        await asyncio.sleep(0.5)
    raise AssertionError(message)


SERVICE_DIR = Path(__file__).resolve().parents[2]

NANO = 1_000_000_000
T0 = 1_768_471_200 * NANO


def _tool_span(i: int, span_id: str) -> dict:
    return {
        "traceId": "ab" * 16,
        "spanId": span_id,
        "name": "search",
        "startTimeUnixNano": str(T0 + i * NANO),
        "endTimeUnixNano": str(T0 + (i + 1) * NANO),
        "attributes": [
            {"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}},
            {"key": "gen_ai.tool.name", "value": {"stringValue": "search"}},
            {"key": "gen_ai.tool.call.arguments", "value": {"stringValue": '{"q": "same"}'}},
        ],
        "status": {"code": 1},
    }


def loop_payload(marker: str) -> bytes:
    """One trace: an LLM span with token usage + three identical tool calls
    — a real exact-repeat loop for the signals analyzer, not a stub."""
    llm_span = {
        "traceId": "ab" * 16,
        "spanId": "0a" * 8,
        "name": "chat gpt-test",
        "startTimeUnixNano": str(T0 - NANO),
        "endTimeUnixNano": str(T0),
        "attributes": [
            {"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}},
            {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "30"}},
            {"key": "gen_ai.usage.output_tokens", "value": {"intValue": "15"}},
        ],
        "status": {"code": 1},
    }
    spans = [llm_span] + [_tool_span(i, f"{i + 1:02d}" * 8) for i in range(3)]
    return json.dumps(
        {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}], "_marker": marker}
    ).encode()


async def upload_and_ingest(api: httpx.AsyncClient, payload: bytes, **kwargs) -> str:
    """Upload, wait for ingest, return the single trace id."""
    res = await upload_file(api, payload, **kwargs)
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]
    status = await wait_terminal(api, upload_id)
    assert status["status"] == "complete", status
    assert len(status["trace_ids"]) == 1
    return status["trace_ids"][0]


async def wait_analysis(api: httpx.AsyncClient, trace_id: str, timeout: float = 30.0) -> dict:
    """Poll the analysis endpoint until it leaves `pending`."""

    async def probe():
        res = await api.get(f"/v1/traces/{trace_id}/analysis")
        res.raise_for_status()
        body = res.json()
        return body if body["analysis_state"] != "pending" else None

    return await wait_until(probe, timeout, f"trace {trace_id} analysis never left pending")


async def test_real_signals_persisted_keyless_skip(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """Done-when #1 and #2: upload → trace_analysis row with real signals;
    a keyless run shows `skipped` with the right reason, never fake pending."""
    trace_id = await upload_and_ingest(api, loop_payload(uuid.uuid4().hex))
    analysis = await wait_analysis(api, trace_id)

    assert analysis["analysis_state"] == "skipped"
    assert analysis["skip_reason"] == "not_configured"
    # Signals are real, computed from the payload's actual structure.
    signals = analysis["signals"]
    assert signals["has_retry_loop"] is True
    assert signals["loop_kind"] == "exact_repeat"
    assert signals["tool_call_count"] == 3
    assert signals["llm_call_count"] == 1
    # No LLM ran: every label honestly null, audit carries signals only.
    assert analysis["labels"] == {"outcome": None, "failure_mode": None, "task_category": None}
    assert [a["analyzer"] for a in analysis["audit"]["analyzers"]] == ["signals"]

    # failure_suspected is routing-internal: stored on the result row,
    # never in the API response (1_analysis.md).
    assert "failure_suspected" not in signals
    stored = await db.fetchval(
        "select output from analyzer_results where trace_id = $1 and analyzer = 'signals'",
        uuid.UUID(trace_id),
    )
    assert "failure_suspected" in json.loads(stored)

    # Importer deltas: trace-level token sum on the detail.
    detail = (await api.get(f"/v1/traces/{trace_id}")).json()
    assert detail["total_tokens"] == 45
    assert detail["analysis_state"] == "skipped"
    assert detail["outcome"] is None

    # List surfaces carry the derived state too.
    listed = (await api.get("/v1/traces?scope=mine")).json()
    row = next(t for t in listed["traces"] if t["trace_id"] == trace_id)
    assert row["analysis_state"] == "skipped"
    assert row["outcome"] is None


async def test_owner_opt_out_beats_not_configured(api: httpx.AsyncClient) -> None:
    """Consent wins over configuration when both gates apply (A2 ratified
    decision): a private trace of an opted-out owner skips as owner_opt_out
    even on a keyless stack."""
    res = await api.patch("/v1/profile", json={"allow_private_llm_analysis": False})
    assert res.status_code == 200

    trace_id = await upload_and_ingest(api, loop_payload(uuid.uuid4().hex))
    analysis = await wait_analysis(api, trace_id)
    assert analysis["analysis_state"] == "skipped"
    assert analysis["skip_reason"] == "owner_opt_out"
    # Signals still run for skipped traces.
    assert analysis["signals"]["has_retry_loop"] is True


async def test_trace_name_falls_back_to_filename(api: httpx.AsyncClient) -> None:
    """2_data-model.md trace-name check: a bare-id root span name is
    replaced by the source filename stem."""
    payload = json.loads(loop_payload(uuid.uuid4().hex))
    for span in payload["resourceSpans"][0]["scopeSpans"][0]["spans"]:
        span["name"] = "a1b2c3d4e5f6a7b8c9d0"  # hex-shaped bare id
    trace_id = await upload_and_ingest(
        api, json.dumps(payload).encode(), filename="checkout-agent-run.json"
    )
    detail = (await api.get(f"/v1/traces/{trace_id}")).json()
    assert detail["name"] == "checkout-agent-run"


async def test_transient_failure_retries_to_success(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """Trace-scoped retries ride the same middleware as ingestion: a
    transient analysis fault burns budget, then succeeds."""
    res = await upload_file(
        api, loop_payload(uuid.uuid4().hex), headers={"X-Fault": "analyze:transient:1"}
    )
    assert res.status_code == 201
    status = await wait_terminal(api, res.json()["upload_id"])
    trace_id = status["trace_ids"][0]

    analysis = await wait_analysis(api, trace_id, timeout=60.0)
    assert analysis["analysis_state"] == "skipped"  # recovered, keyless-complete
    attempts = await db.fetchval(
        "select analysis_attempts from traces where id = $1", uuid.UUID(trace_id)
    )
    assert attempts == 2  # one injected failure + the success
    dlq = await db.fetchval(
        "select count(*) from dead_letters where trace_id = $1", uuid.UUID(trace_id)
    )
    assert dlq == 0


async def test_analysis_access_mirrors_trace_visibility(api: httpx.AsyncClient) -> None:
    """Private analysis 404s for non-owners (not 403 — existence isn't
    leaked); listing opens it."""
    from tests.integration.conftest import signup_token

    trace_id = await upload_and_ingest(api, loop_payload(uuid.uuid4().hex))
    await wait_analysis(api, trace_id)

    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=str(api.base_url),
        headers={"Authorization": f"Bearer {other_token}"},
        timeout=30.0,
    ) as other:
        res = await other.get(f"/v1/traces/{trace_id}/analysis")
        assert res.status_code == 404

        listed = await api.patch(
            f"/v1/traces/{trace_id}",
            json={"visibility": "listed", "confirm_ownership": True},
        )
        assert listed.status_code == 200

        res = await other.get(f"/v1/traces/{trace_id}/analysis")
        assert res.status_code == 200
        assert res.json()["analysis_state"] == "skipped"


async def test_injected_failure_dead_letters_and_requeues(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """Done-when #4: an injected analysis failure dead-letters and surfaces
    as `failed`; the operator requeue recovers it."""
    res = await upload_file(
        api, loop_payload(uuid.uuid4().hex), headers={"X-Fault": "analyze:permanent"}
    )
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]
    status = await wait_terminal(api, upload_id)
    assert status["status"] == "complete"  # ingestion is untouched by the analyze fault
    trace_id = status["trace_ids"][0]

    analysis = await wait_analysis(api, trace_id)
    assert analysis["analysis_state"] == "failed"
    assert "Fault injection" in analysis["failed_reason"]

    row = await db.fetchrow(
        "select task_name, attempts, upload_id, requeued_at from dead_letters where trace_id = $1",
        uuid.UUID(trace_id),
    )
    assert row is not None
    assert row["task_name"] == "app.worker.tasks.analyze:analyze_trace"
    assert row["attempts"] == 1  # permanent: no retries burned
    assert str(row["upload_id"]) == upload_id
    assert row["requeued_at"] is None

    # Disarm (faults are keyed by upload), then requeue the trace.
    from redis.asyncio import Redis

    from app.config import settings

    redis = Redis.from_url(settings.redis_url)
    await redis.delete(f"fault:{upload_id}")
    await redis.aclose()

    result = subprocess.run(
        ["uv", "run", "python", "-m", "app.cli.requeue", "trace", trace_id],
        cwd=SERVICE_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    analysis = await wait_analysis(api, trace_id)
    assert analysis["analysis_state"] == "skipped"  # keyless stack
    requeued_at = await db.fetchval(
        "select requeued_at from dead_letters where trace_id = $1", uuid.UUID(trace_id)
    )
    assert requeued_at is not None


async def test_reingest_clears_failed_state(api: httpx.AsyncClient, db: asyncpg.Connection) -> None:
    """A successful re-run is newer truth than an old dead letter: operator
    re-ingest of the upload (not just `requeue trace`) closes the open dead
    letter in the rewrite, so the trace can't stay `failed` after recovery."""
    res = await upload_file(
        api, loop_payload(uuid.uuid4().hex), headers={"X-Fault": "analyze:permanent"}
    )
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]
    status = await wait_terminal(api, upload_id)
    trace_id = status["trace_ids"][0]
    analysis = await wait_analysis(api, trace_id)
    assert analysis["analysis_state"] == "failed"

    from redis.asyncio import Redis

    from app.config import settings

    redis = Redis.from_url(settings.redis_url)
    await redis.delete(f"fault:{upload_id}")
    await redis.aclose()

    result = subprocess.run(
        ["uv", "run", "python", "-m", "app.cli.requeue", "upload", upload_id],
        cwd=SERVICE_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    status = await wait_terminal(api, upload_id)
    assert status["trace_ids"] == [trace_id]

    async def recovered():
        body = (await api.get(f"/v1/traces/{trace_id}/analysis")).json()
        return body if body["analysis_state"] == "skipped" else None

    await wait_until(recovered, 30.0, f"trace {trace_id} stayed failed after re-ingest")
    open_dlq = await db.fetchval(
        "select count(*) from dead_letters where trace_id = $1 and requeued_at is null",
        uuid.UUID(trace_id),
    )
    assert open_dlq == 0


async def test_sweep_predicate_recovers_lost_kicks(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """stale_pending_ids covers both lost-kick shapes — re-ingest reset
    (attempts = 0 beside an existing row) and a crash on the final budgeted
    attempt (no row, budget exhausted) — and excludes the healthy case."""
    from app.config import settings
    from app.queries import analysis as analysis_q

    trace_id = await upload_and_ingest(api, loop_payload(uuid.uuid4().hex))
    await wait_analysis(api, trace_id)

    # Analyzed and claimed: never re-enqueued, even with a zero timeout.
    assert trace_id not in await analysis_q.stale_pending_ids(db, older_than_minutes=0)

    # Re-ingest whose analyze kick was lost: budget reset beside a stale row.
    await db.execute(
        "update traces set analysis_attempts = 0, analysis_attempted_at = null where id = $1",
        uuid.UUID(trace_id),
    )
    assert trace_id in await analysis_q.stale_pending_ids(db, older_than_minutes=0)

    # Crash on the final budgeted attempt: claimed to the cap, no row, no
    # dead letter — must still re-enqueue (the middleware enforces the
    # budget on failure), never an eternal pending.
    await db.execute("delete from trace_analysis where trace_id = $1", uuid.UUID(trace_id))
    await db.execute(
        "update traces set analysis_attempts = $2, "
        "analysis_attempted_at = now() - interval '1 hour' where id = $1",
        uuid.UUID(trace_id),
        settings.ingest_max_attempts,
    )
    assert trace_id in await analysis_q.stale_pending_ids(db, older_than_minutes=30)


async def test_reingest_keeps_identity_and_reanalyzes(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """Done-when #3 plus the stable-identity decision: re-ingesting a
    complete upload preserves traces.id, reproduces analysis rows, and
    keeps human-provenance labels."""
    res = await upload_file(api, loop_payload(uuid.uuid4().hex))
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]
    status = await wait_terminal(api, upload_id)
    trace_id = status["trace_ids"][0]
    first = await wait_analysis(api, trace_id)
    first_analyzed_at = await db.fetchval(
        "select analyzed_at from trace_analysis where trace_id = $1", uuid.UUID(trace_id)
    )

    # Simulate A3's human relabel: outcome with human provenance.
    await db.execute(
        """
        update trace_analysis
        set outcome = 'failure', outcome_confidence = null, outcome_provenance = 'human'
        where trace_id = $1
        """,
        uuid.UUID(trace_id),
    )

    result = subprocess.run(
        ["uv", "run", "python", "-m", "app.cli.requeue", "upload", upload_id],
        cwd=SERVICE_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    status = await wait_terminal(api, upload_id)
    assert status["status"] == "complete"
    # Stable identity: the same trace id survives the rewrite.
    assert status["trace_ids"] == [trace_id]

    async def reanalyzed():
        ts = await db.fetchval(
            "select analyzed_at from trace_analysis where trace_id = $1", uuid.UUID(trace_id)
        )
        return ts if ts is not None and ts != first_analyzed_at else None

    await wait_until(reanalyzed, 30.0, f"trace {trace_id} was never re-analyzed")

    second = await wait_analysis(api, trace_id)
    # Machine output reproduces; the human label survives the rewrite.
    assert second["signals"] == first["signals"]
    assert second["analysis_state"] == first["analysis_state"] == "skipped"
    assert second["labels"]["outcome"] == {
        "value": "failure",
        "confidence": None,
        "provenance": "human",
    }
