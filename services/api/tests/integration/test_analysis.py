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
    """Poll the trace detail until its analysis block is terminal: the
    session is final or skipped, or the run failed (open dead letter)."""

    async def probe():
        res = await api.get(f"/v1/traces/{trace_id}")
        res.raise_for_status()
        analysis = res.json()["analysis"]
        done = analysis["session"]["status"] in ("final", "skipped") or analysis["failed_reason"]
        return analysis if done else None

    return await wait_until(probe, timeout, f"trace {trace_id} analysis never became terminal")


async def test_real_signals_persisted_keyless_skip(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """Upload → session and turn rows with real signals; a keyless run shows
    `skipped` with the right reason, never fake pending or fake labels."""
    trace_id = await upload_and_ingest(api, loop_payload(uuid.uuid4().hex))
    analysis = await wait_analysis(api, trace_id)
    session = analysis["session"]

    assert session["status"] == "skipped"
    assert session["skip_reason"] == "not_configured"
    # Signals are real, computed from the payload's actual structure.
    signals = session["signals"]
    assert signals["has_retry_loop"] is True
    assert signals["loop_kind"] == "exact_repeat"
    assert signals["tool_call_count"] == 3
    assert signals["llm_call_count"] == 1
    # No LLM ran: no verdict, no labels, no audit row.
    assert (session["goal"], session["outcome"], session["summary"]) == (None, None, None)
    assert session["task_categories"] == session["failure_modes"] == []
    assert (
        await db.fetchval(
            "select count(*) from analyzer_results where trace_id = $1", uuid.UUID(trace_id)
        )
        == 0
    )
    # A non-session trace is one turn covering every span.
    (turn,) = analysis["turns"]
    assert turn["turn_index"] == 0
    assert turn["outcome"] is None
    assert turn["provenance"] == "machine"
    assert turn["labels"] == []
    assert turn["signals"]["has_retry_loop"] is True
    assert turn["signals"]["tool_call_count"] == 3

    # Importer deltas: trace-level token sum on the detail.
    detail = (await api.get(f"/v1/traces/{trace_id}")).json()
    assert detail["total_tokens"] == 45

    # List surfaces carry the derived status too.
    listed = (await api.get("/v1/traces?scope=mine")).json()
    row = next(t for t in listed["traces"] if t["trace_id"] == trace_id)
    assert row["analysis_status"] == "skipped"
    assert row["analysis_failed"] is False
    assert row["outcome"] is None
    assert row["task_categories"] == row["failure_modes"] == []


async def test_owner_opt_out_beats_not_configured(api: httpx.AsyncClient) -> None:
    """Consent wins over configuration when both gates apply (A2 ratified
    decision): a private trace of an opted-out owner skips as owner_opt_out
    even on a keyless stack."""
    res = await api.patch("/v1/profile", json={"allow_private_llm_analysis": False})
    assert res.status_code == 200

    trace_id = await upload_and_ingest(api, loop_payload(uuid.uuid4().hex))
    session = (await wait_analysis(api, trace_id))["session"]
    assert session["status"] == "skipped"
    assert session["skip_reason"] == "owner_opt_out"
    # Signals still run for skipped traces.
    assert session["signals"]["has_retry_loop"] is True


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
    assert analysis["session"]["status"] == "skipped"  # recovered, keyless-complete
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
    leaked); listing opens it. Only the owner can request analysis."""
    from tests.integration.conftest import signup_token

    trace_id = await upload_and_ingest(api, loop_payload(uuid.uuid4().hex))
    await wait_analysis(api, trace_id)

    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=str(api.base_url),
        headers={"Authorization": f"Bearer {other_token}"},
        timeout=30.0,
    ) as other:
        assert (await other.get(f"/v1/traces/{trace_id}")).status_code == 404
        assert (await other.post(f"/v1/traces/{trace_id}/analyze")).status_code == 404

        listed = await api.patch(
            f"/v1/traces/{trace_id}",
            json={"visibility": "listed", "confirm_ownership": True},
        )
        assert listed.status_code == 200

        res = await other.get(f"/v1/traces/{trace_id}")
        assert res.status_code == 200
        assert res.json()["analysis"]["session"]["status"] == "skipped"
        assert (await other.post(f"/v1/traces/{trace_id}/analyze")).status_code == 403

    assert (await api.post(f"/v1/traces/{uuid.uuid4()}/analyze")).status_code == 404
    assert (await api.post(f"/v1/traces/{trace_id}/analyze")).status_code == 202


async def test_injected_failure_dead_letters_and_requeues(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """Done-when #4: an injected analysis failure dead-letters and surfaces
    as failed; the operator requeue recovers it."""
    res = await upload_file(
        api, loop_payload(uuid.uuid4().hex), headers={"X-Fault": "analyze:permanent"}
    )
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]
    status = await wait_terminal(api, upload_id)
    assert status["status"] == "complete"  # ingestion is untouched by the analyze fault
    trace_id = status["trace_ids"][0]

    analysis = await wait_analysis(api, trace_id)
    assert "Fault injection" in analysis["failed_reason"]
    assert analysis["session"]["status"] == "pending"  # nothing was persisted
    listed = (await api.get("/v1/traces?scope=mine")).json()
    row = next(t for t in listed["traces"] if t["trace_id"] == trace_id)
    assert row["analysis_failed"] is True

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
    assert analysis["session"]["status"] == "skipped"  # keyless stack
    assert analysis["failed_reason"] is None
    requeued_at = await db.fetchval(
        "select requeued_at from dead_letters where trace_id = $1", uuid.UUID(trace_id)
    )
    assert requeued_at is not None


async def test_reingest_clears_failed_state(api: httpx.AsyncClient, db: asyncpg.Connection) -> None:
    """A successful re-run is newer truth than an old dead letter: operator
    re-ingest of the upload (not just `requeue trace`) closes the open dead
    letter in the rewrite, so the trace can't stay failed after recovery."""
    res = await upload_file(
        api, loop_payload(uuid.uuid4().hex), headers={"X-Fault": "analyze:permanent"}
    )
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]
    status = await wait_terminal(api, upload_id)
    trace_id = status["trace_ids"][0]
    analysis = await wait_analysis(api, trace_id)
    assert analysis["failed_reason"] is not None

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
        analysis = (await api.get(f"/v1/traces/{trace_id}")).json()["analysis"]
        return analysis if analysis["session"]["status"] == "skipped" else None

    analysis = await wait_until(recovered, 30.0, f"trace {trace_id} stayed failed after re-ingest")
    assert analysis["failed_reason"] is None
    open_dlq = await db.fetchval(
        "select count(*) from dead_letters where trace_id = $1 and requeued_at is null",
        uuid.UUID(trace_id),
    )
    assert open_dlq == 0


async def test_sweep_due_ids(api: httpx.AsyncClient, db: asyncpg.Connection) -> None:
    """due_ids covers both lost-kick shapes — re-ingest reset (attempts = 0
    beside an existing row) and a crash on the final budgeted attempt (no
    row, budget exhausted) — plus session finalization once idle, and
    excludes the healthy case. Claims are backdated past a real timeout:
    the query stamps every trace it returns, so a zero timeout would touch
    the whole shared database."""
    from app.config import settings
    from app.queries import analysis as analysis_q

    trace_id = await upload_and_ingest(api, loop_payload(uuid.uuid4().hex))
    await wait_analysis(api, trace_id)

    async def due(sets: str, *args) -> dict[str, bool]:
        await db.execute(
            f"update traces set analysis_attempted_at = now() - interval '1 hour', {sets} "
            "where id = $1",
            uuid.UUID(trace_id),
            *args,
        )
        rows = await analysis_q.due_ids(
            db,
            older_than_minutes=30,
            idle_seconds=settings.analysis_idle_seconds,
            limit=1_000_000,  # the shared DB may hold older due traces
        )
        return dict(rows)

    # Analyzed, rolled up and claimed: never re-enqueued.
    assert trace_id not in await due("analysis_attempts = 1")
    # Re-ingest whose analyze kick was lost: budget reset beside a stale row.
    assert (await due("analysis_attempts = 0"))[trace_id] is True
    # ...unless a run holds the trace's lease: never a second run.
    leased = "analysis_attempts = 0, analysis_lease_until = now() + interval '1 minute'"
    assert trace_id not in await due(leased)
    await db.execute(
        "update traces set analysis_lease_until = null where id = $1", uuid.UUID(trace_id)
    )

    # Crash on the final budgeted attempt: claimed to the cap, no row, no
    # dead letter — must still re-enqueue (the middleware enforces the
    # budget on failure), never an eternal pending.
    await db.execute("delete from trace_analysis where trace_id = $1", uuid.UUID(trace_id))
    assert (await due("analysis_attempts = $2", settings.ingest_max_attempts))[trace_id] is True

    # Session formats finalize only once idle; before that only a lost kick
    # re-enqueues, as an incremental run.
    assert trace_id not in await due("source_format = 'codex_jsonl', ended_at = now()")
    idle = float(settings.analysis_idle_seconds + 60)
    assert (await due("ended_at = now() - make_interval(secs => $2)", idle))[trace_id] is True
    assert (await due("ended_at = now(), analysis_attempts = 0"))[trace_id] is False

    assert (await api.delete(f"/v1/traces/{trace_id}")).status_code == 204


async def test_reingest_keeps_identity_and_human_turn(
    api: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    """Done-when #3 plus the stable-identity decision: re-ingesting a
    complete upload preserves traces.id, reproduces the machine output, and
    never re-judges or overwrites a human-relabeled turn."""
    res = await upload_file(api, loop_payload(uuid.uuid4().hex))
    assert res.status_code == 201
    upload_id = res.json()["upload_id"]
    status = await wait_terminal(api, upload_id)
    trace_id = status["trace_ids"][0]
    first = await wait_analysis(api, trace_id)

    res = await api.put(
        f"/v1/traces/{trace_id}/turns/0/labels",
        json={"outcome": "failure", "task_categories": ["coding"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["turns"][0]["provenance"] == "human"

    # Mark the roll-up stale so the re-run has to write — its completion
    # signal (a current roll-up is otherwise left untouched).
    await db.execute(
        "update trace_analysis set analyzed_at = null where trace_id = $1", uuid.UUID(trace_id)
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

    async def rolled_up():
        return await db.fetchval(
            "select analyzed_at from trace_analysis where trace_id = $1", uuid.UUID(trace_id)
        )

    await wait_until(rolled_up, 30.0, f"trace {trace_id} was never re-analyzed")

    second = await wait_analysis(api, trace_id)
    # Machine output reproduces; the human turn survives the rewrite.
    assert second["session"]["signals"] == first["session"]["signals"]
    assert second["session"]["status"] == first["session"]["status"] == "skipped"
    (turn,) = second["turns"]
    assert turn["provenance"] == "human"
    assert turn["outcome"] == "failure"
    assert [(lb["field"], lb["value"]) for lb in turn["labels"]] == [("task_category", "coding")]
    assert second["session"]["task_categories"] == ["coding"]
