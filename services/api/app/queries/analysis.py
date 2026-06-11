"""Analysis-domain queries: trace loading, the analyze_trace bookkeeping
(claim / budget / sweep), and the delete-and-rewrite persistence of
`analyzer_results` + `trace_analysis` (1_analysis.md persistence rules).
"""

from typing import Any

import asyncpg

from app.analysis import AnalyzerRun, TraceInput
from app.queries import dead_letters

# Label triplets whose human provenance must survive a machine rewrite
# (1_analysis.md: human fields are never machine-overwritten).
LABEL_FIELDS = ("outcome", "failure_mode", "task_category")

HUMAN_PROVENANCE = {"human", "human_confirmed"}


async def fetch_trace_input(pool: asyncpg.Pool, trace_id: str) -> TraceInput | None:
    """Normalized rows → `TraceInput` — the one DB read path into the
    analysis contract, shared by the offline runner's DB mode and the
    `analyze_trace` worker job. `select *` is deliberate: `TraceInput`
    mirrors the full normalized column set and ignores platform-only
    columns (owner_id, upload_id, …)."""
    trace_row = await pool.fetchrow("select * from traces where id = $1", trace_id)
    if trace_row is None:
        return None
    span_rows = await pool.fetch(
        "select * from spans where trace_id = $1 order by started_at, source_span_id",
        trace_id,
    )
    return TraceInput.from_db_rows(trace_row, list(span_rows))


async def fetch_llm_gate(pool: asyncpg.Pool, trace_id: str) -> asyncpg.Record | None:
    """The facts the worker's LLM gate needs (1_analysis.md owner opt-out):
    trace visibility, the owner's consent flag, and the upload id (fault
    injection is armed per upload)."""
    return await pool.fetchrow(
        """
        select t.visibility, t.upload_id, p.allow_private_llm_analysis
        from traces t
        join profiles p on p.id = t.owner_id
        where t.id = $1
        """,
        trace_id,
    )


async def claim(pool: asyncpg.Pool, trace_id: str) -> int | None:
    """Count the attempt and stamp the claim — the durable retry budget,
    mirroring uploads.mark_processing. Returns None when the trace is gone
    (deleted mid-flight); analysis has no terminal status to guard."""
    return await pool.fetchval(
        """
        update traces
        set analysis_attempts = analysis_attempts + 1, analysis_attempted_at = now()
        where id = $1
        returning analysis_attempts
        """,
        trace_id,
    )


async def attempt_count(pool: asyncpg.Pool, trace_id: str) -> int | None:
    return await pool.fetchval("select analysis_attempts from traces where id = $1", trace_id)


async def reset_attempts(pool: asyncpg.Pool, trace_id: str) -> None:
    """Fresh budget for an operator requeue (cli/requeue.py trace mode)."""
    await pool.execute(
        "update traces set analysis_attempts = 0, analysis_attempted_at = null where id = $1",
        trace_id,
    )


async def stale_pending_ids(pool: asyncpg.Pool, *, older_than_minutes: int) -> list[str]:
    """Traces whose analysis job was likely lost, keyed off the claim stamp
    so a trace re-enqueues at most once per timeout window (mirrors
    uploads.stuck_ids). Two shapes of "lost":

    - never analyzed: no result row, at any attempt count — no budget
      filter, because a crash on the final budgeted attempt would otherwise
      leave an eternal `pending`; like ingestion, the sweep re-kicks and the
      middleware enforces the budget on failure (dead letter, not a loop);
    - re-ingested but never re-claimed: the ingest upsert resets the budget
      to zero and kicks best-effort, so attempts = 0 beside an existing row
      marks a lost re-analysis kick (the claim immediately sets it to 1).

    Open dead letters are excluded — those traces are `failed`, not pending.
    """
    rows = await pool.fetch(
        """
        select t.id from traces t
        where coalesce(t.analysis_attempted_at, t.created_at)
              < now() - make_interval(mins => $1)
          and not exists (
            select 1 from dead_letters dl
            where dl.trace_id = t.id and dl.requeued_at is null
          )
          and (
            not exists (select 1 from trace_analysis ta where ta.trace_id = t.id)
            or t.analysis_attempts = 0
          )
        """,
        older_than_minutes,
    )
    return [str(r["id"]) for r in rows]


async def rewrite(
    pool: asyncpg.Pool,
    trace_id: str,
    *,
    runs: list[AnalyzerRun],
    promoted: dict[str, Any],
    llm_status: str,
    llm_skip_reason: str | None,
) -> None:
    """Delete-and-rewrite this trace's analysis rows in one transaction —
    idempotent by construction (1_analysis.md runtime rules).

    Exception, applied here so no caller can forget it: label triplets whose
    existing provenance is human/human_confirmed are carried over the new
    machine values, never overwritten.
    """
    promoted = dict(promoted)  # the carryover mutates; don't leak into the caller
    async with pool.acquire() as conn, conn.transaction():
        prior = await conn.fetchrow(
            "select * from trace_analysis where trace_id = $1 for update", trace_id
        )
        if prior is not None:
            for field in LABEL_FIELDS:
                if prior[f"{field}_provenance"] in HUMAN_PROVENANCE:
                    promoted[field] = prior[field]
                    promoted[f"{field}_confidence"] = prior[f"{field}_confidence"]
                    promoted[f"{field}_provenance"] = prior[f"{field}_provenance"]
        await conn.execute("delete from analyzer_results where trace_id = $1", trace_id)
        await conn.execute("delete from trace_analysis where trace_id = $1", trace_id)
        await conn.executemany(
            """
            insert into analyzer_results
              (trace_id, analyzer, analyzer_version, model_id, output, confidence)
            values ($1, $2, $3, $4, $5, $6)
            """,
            [
                (
                    trace_id,
                    run.analyzer,
                    run.analyzer_version,
                    run.model_id,
                    run.output,
                    run.confidence,
                )
                for run in runs
            ],
        )
        columns = ["trace_id", "llm_status", "llm_skip_reason", *promoted.keys()]
        values = [trace_id, llm_status, llm_skip_reason, *promoted.values()]
        placeholders = ", ".join(f"${i + 1}" for i in range(len(values)))
        await conn.execute(
            f"insert into trace_analysis ({', '.join(columns)}) values ({placeholders})",
            *values,
        )
        # A successful run is newer truth than any old failure: close open
        # analyze dead letters so the derived state can't stay `failed`
        # after a recovery that bypassed the trace-requeue CLI (operator
        # re-ingest of the upload, a sweep re-kick that succeeded).
        await dead_letters.mark_requeued_for_trace(conn, trace_id)


async def fetch_results(pool: asyncpg.Pool, trace_id: str) -> list[asyncpg.Record]:
    """The audit rows in run order — signals, judge, then metrics by name.
    The rank is explicit: created_at is the transaction timestamp, identical
    across one rewrite, so insertion order is not recoverable from it."""
    return await pool.fetch(
        """
        select * from analyzer_results where trace_id = $1
        order by case analyzer when 'signals' then 0 when 'judge' then 1 else 2 end,
                 analyzer
        """,
        trace_id,
    )


async def fetch_analysis(pool: asyncpg.Pool, trace_id: str) -> asyncpg.Record | None:
    return await pool.fetchrow("select * from trace_analysis where trace_id = $1", trace_id)


def derive_state(llm_status: str | None, failed: bool) -> str:
    """The derived analysis state (2_data-model.md): one rule for every
    surface — list rows, trace detail, and the analysis endpoint."""
    if failed:
        return "failed"
    if llm_status is None:
        return "pending"
    return "complete" if llm_status == "complete" else "skipped"


async def fetch_open_dead_letter(pool: asyncpg.Pool, trace_id: str) -> asyncpg.Record | None:
    """The failed-state probe: a non-requeued analyze dead letter. Newest
    first in the pathological multi-row case."""
    return await pool.fetchrow(
        """
        select last_error, failed_at from dead_letters
        where trace_id = $1 and requeued_at is null
        order by failed_at desc
        limit 1
        """,
        trace_id,
    )
