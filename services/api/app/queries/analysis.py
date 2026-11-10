"""Analysis-domain queries: trace loading, the analyze_trace bookkeeping
(claim / budget / sweep), and the persistence of per-turn verdicts
(`turn_analysis` + `trace_labels`) and the session roll-up
(`trace_analysis`) per 9_session-analysis.md — with the review-item sync in
the same transaction.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import asyncpg

from app.analysis import AnalyzerRun, SignalsResult, TraceInput
from app.analysis.agent.models import AgentMeta, FailureLabel, SessionVerdict, TurnVerdict
from app.importers.otlp import SOURCE_FORMAT as OTLP_FORMAT
from app.queries import dead_letters
from app.queries import review_items as review_items_q

SIGNAL_FIELDS = tuple(SignalsResult.model_fields)

# (field, value, span_ids, reason) — one trace_labels row.
Label = tuple[str, str, list[str], str | None]


@dataclass(frozen=True)
class TurnWrite:
    """One machine turn row to persist. No verdict = LLM analysis skipped:
    signals only, never a fake label."""

    turn_index: int
    fingerprint: str
    signals: SignalsResult
    verdict: TurnVerdict | None = None
    meta: AgentMeta | None = None


def is_session_format(source_format: str) -> bool:
    return source_format != OTLP_FORMAT


def needs_judging(row: Mapping[str, Any] | None, fingerprint: str, llm: bool) -> bool:
    """A turn is (re)judged when it has no row, its spans changed, or it was
    stored unjudged and a judge is now available. Human turns never are."""
    if row is None:
        return True
    if row["provenance"] == "human":
        return False
    return row["fingerprint"] != fingerprint or (llm and row["outcome"] is None)


def verdict_labels(verdict: TurnVerdict) -> list[Label]:
    return [("task_category", value, [], None) for value in verdict.task_categories] + [
        ("failure_mode", label.value, label.span_ids, label.reason)
        for label in verdict.failure_modes
    ]


def stored_verdict(turn: Mapping[str, Any]) -> TurnVerdict:
    """A stored judged turn back as the verdict the roll-up consumes.
    Constructed without validation: human labels may cite no spans."""
    labels = turn["labels"]
    return TurnVerdict.model_construct(
        turn_index=turn["turn_index"],
        outcome=turn["outcome"],
        summary=turn["summary"] or "",
        task_categories=[lb["value"] for lb in labels if lb["field"] == "task_category"],
        failure_modes=[
            FailureLabel.model_construct(
                value=lb["value"], span_ids=list(lb["span_ids"]), reason=lb["reason"] or ""
            )
            for lb in labels
            if lb["field"] == "failure_mode"
        ],
        uncertain=turn["uncertain"],
    )


def derive_status(llm_status: str | None, analyzed_at: Any, attempts: int) -> str:
    """The session analysis status (9_session-analysis.md API): one rule for
    every surface. `final` needs a current roll-up and no re-ingest since
    the last claim (attempts reset to 0 = content changed, not yet seen)."""
    if llm_status is None:
        return "pending"
    if llm_status == "skipped":
        return "skipped"
    return "final" if analyzed_at is not None and attempts > 0 else "in_progress"


async def fetch_trace_input(pool: asyncpg.Pool, trace_id: str) -> TraceInput | None:
    """Normalized rows → `TraceInput` — the one DB read path into the
    analysis contract, shared by the offline runner's DB mode, the
    `analyze_trace` worker job, and relabel span validation. `select *` is
    deliberate: `TraceInput` ignores platform-only columns."""
    trace_row = await pool.fetchrow(
        """
        select t.*, p.task_categories as owner_task_categories
        from traces t join profiles p on p.id = t.owner_id
        where t.id = $1
        """,
        trace_id,
    )
    if trace_row is None:
        return None
    span_rows = await pool.fetch(
        "select * from spans where trace_id = $1 order by started_at, source_span_id",
        trace_id,
    )
    return TraceInput.from_db_rows(trace_row, list(span_rows))


async def fetch_llm_gate(pool: asyncpg.Pool, trace_id: str) -> asyncpg.Record | None:
    """The facts the worker's LLM gate needs (1_analysis.md owner opt-out):
    visibility, consent, upload id (fault injection is armed per upload),
    owner id (review digest recipient), source format (session or not) and
    tags/description (listing-copy fill-if-empty)."""
    return await pool.fetchrow(
        """
        select t.visibility, t.upload_id, t.owner_id, t.tags, t.description,
               t.source_format, p.allow_private_llm_analysis
        from traces t
        join profiles p on p.id = t.owner_id
        where t.id = $1
        """,
        trace_id,
    )


async def claim(pool: asyncpg.Pool, trace_id: str) -> int | None:
    """Count the attempt and stamp the claim — the durable retry budget,
    mirroring uploads.mark_processing. None when the trace is gone."""
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
    """Fresh budget before an explicit enqueue (operator requeue, owner
    analyze). Stamped now so the sweep doesn't re-kick it meanwhile."""
    await pool.execute(
        "update traces set analysis_attempts = 0, analysis_attempted_at = now() where id = $1",
        trace_id,
    )


async def due_ids(
    pool: asyncpg.Pool, *, older_than_minutes: int, idle_seconds: int
) -> list[tuple[str, bool]]:
    """What the minute sweep enqueues, as (trace_id, finalize):

    - lost kicks: re-ingested (attempts reset to 0) or never analyzed
      traces whose claim stamp is older than the timeout;
    - finalization: traces that should be final but are not — non-session
      traces always, session traces once `ended_at` is idle.

    Stamps the claim time so each trace re-enqueues at most once per
    timeout window. Open dead letters are excluded — those are failed.
    """
    rows = await pool.fetch(
        """
        update traces t set analysis_attempted_at = now()
        from (
          select t.id,
                 (t.source_format = $3 or t.ended_at < now() - make_interval(secs => $2))
                   as finalize,
                 ta.trace_id is not null as has_row,
                 ta.analyzed_at is not null as rolled_up
          from traces t
          left join trace_analysis ta on ta.trace_id = t.id
        ) d
        where t.id = d.id
          and coalesce(t.analysis_attempted_at, t.created_at) < now() - make_interval(mins => $1)
          and not exists (
            select 1 from dead_letters dl
            where dl.trace_id = t.id and dl.requeued_at is null
          )
          and (t.analysis_attempts = 0 or (d.finalize and not (d.has_row and d.rolled_up)))
        returning t.id, d.finalize
        """,
        older_than_minutes,
        idle_seconds,
        OTLP_FORMAT,
    )
    return [(str(r["id"]), r["finalize"]) for r in rows]


async def fetch_turns(
    executor: asyncpg.Pool | asyncpg.Connection, trace_id: str
) -> list[dict[str, Any]]:
    """The trace's turn rows in order, each with its `labels`."""
    turns = await executor.fetch(
        "select * from turn_analysis where trace_id = $1 order by turn_index", trace_id
    )
    labels = await executor.fetch(
        """
        select turn_index, field, value, span_ids, reason from trace_labels
        where trace_id = $1 order by turn_index, field, id
        """,
        trace_id,
    )
    by_turn: dict[int, list[dict[str, Any]]] = {}
    for label in labels:
        by_turn.setdefault(label["turn_index"], []).append(dict(label))
    return [{**dict(t), "labels": by_turn.get(t["turn_index"], [])} for t in turns]


async def count_turns(executor: asyncpg.Pool | asyncpg.Connection, trace_id: str) -> int:
    """Turns as the judge splits them (agent/turns.split): spans carrying an
    integer `turn.index`, or one synthetic turn when there are none."""
    count = await executor.fetchval(
        """
        select count(*) from spans
        where trace_id = $1 and jsonb_typeof(attributes -> 'turn.index') = 'number'
        """,
        trace_id,
    )
    return max(count, 1)


async def fetch_analysis(pool: asyncpg.Pool, trace_id: str) -> asyncpg.Record | None:
    return await pool.fetchrow("select * from trace_analysis where trace_id = $1", trace_id)


async def _lock_trace(conn: asyncpg.Connection, trace_id: str) -> bool:
    """Serializes the analysis rewrite and owner relabels per trace."""
    return await conn.fetchval("select true from traces where id = $1 for update", trace_id)


async def _replace_labels(
    conn: asyncpg.Connection, trace_id: str, turn_index: int, labels: list[Label]
) -> None:
    await conn.execute(
        "delete from trace_labels where trace_id = $1 and turn_index = $2", trace_id, turn_index
    )
    await conn.executemany(
        """
        insert into trace_labels (trace_id, turn_index, field, value, span_ids, reason)
        values ($1, $2, $3, $4, $5, $6)
        """,
        [(trace_id, turn_index, *label) for label in labels],
    )


async def _recompute_arrays(conn: asyncpg.Connection, trace_id: str) -> None:
    """Session task_categories / failure_modes = the union over every turn's
    labels, human and machine alike."""
    await conn.execute(
        """
        update trace_analysis set
          task_categories = coalesce((
            select array_agg(distinct value order by value) from trace_labels
            where trace_id = $1 and field = 'task_category'
          ), '{}'),
          failure_modes = coalesce((
            select array_agg(distinct value order by value) from trace_labels
            where trace_id = $1 and field = 'failure_mode'
          ), '{}')
        where trace_id = $1
        """,
        trace_id,
    )


async def rewrite(
    pool: asyncpg.Pool,
    trace_id: str,
    *,
    turns: list[TurnWrite],
    present: list[int],
    signals: SignalsResult,
    llm_status: str,
    llm_skip_reason: str | None,
    finalized: bool,
    session: SessionVerdict | None = None,
    run: AnalyzerRun | None = None,
    owner_id: str,
    upload_id: str,
) -> None:
    """Persist one analysis run in one transaction: drop turns that no
    longer exist, upsert the judged machine turns with their labels (a turn
    that is human by now is skipped — never overwritten), write the session
    row, recompute the union arrays, append the audit row, and sync the
    review item. `finalized` writes the roll-up (`session`, None when the
    LLM is gated off) and stamps `analyzed_at`; otherwise the roll-up is
    marked stale (analyzed_at null) and the previous one kept for display.
    """
    async with pool.acquire() as conn, conn.transaction():
        if not await _lock_trace(conn, trace_id):
            return
        await conn.execute(
            "delete from turn_analysis where trace_id = $1 and not (turn_index = any($2::int[]))",
            trace_id,
            present,
        )
        human = {
            r["turn_index"]
            for r in await conn.fetch(
                "select turn_index from turn_analysis where trace_id = $1 and provenance = 'human'",
                trace_id,
            )
        }
        for turn in turns:
            if turn.turn_index in human:
                continue
            verdict, meta = turn.verdict, turn.meta
            await conn.execute(
                """
                insert into turn_analysis (trace_id, turn_index, fingerprint, outcome, summary,
                                           uncertain, signals, model, usage)
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                on conflict (trace_id, turn_index) do update set
                  fingerprint = excluded.fingerprint, outcome = excluded.outcome,
                  summary = excluded.summary, uncertain = excluded.uncertain,
                  signals = excluded.signals, model = excluded.model, usage = excluded.usage,
                  analyzed_at = now()
                """,
                trace_id,
                turn.turn_index,
                turn.fingerprint,
                verdict.outcome if verdict else None,
                verdict.summary if verdict else None,
                verdict.uncertain if verdict else None,
                turn.signals.model_dump(mode="json"),
                meta.model if meta else None,
                meta.model_dump(mode="json", exclude={"model"}) if meta else None,
            )
            labels = verdict_labels(verdict) if verdict else []
            await _replace_labels(conn, trace_id, turn.turn_index, labels)

        await conn.execute(
            f"""
            insert into trace_analysis (trace_id, llm_status, llm_skip_reason,
                                        {", ".join(SIGNAL_FIELDS)},
                                        goal, outcome, summary, analyzed_at)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                    case when $13 then now() end)
            on conflict (trace_id) do update set
              llm_status = excluded.llm_status,
              llm_skip_reason = excluded.llm_skip_reason,
              {", ".join(f"{f} = excluded.{f}" for f in SIGNAL_FIELDS)},
              goal = case when $13 then excluded.goal else trace_analysis.goal end,
              outcome = case when $13 then excluded.outcome else trace_analysis.outcome end,
              summary = case when $13 then excluded.summary else trace_analysis.summary end,
              analyzed_at = excluded.analyzed_at
            """,
            trace_id,
            llm_status,
            llm_skip_reason,
            *(getattr(signals, f) for f in SIGNAL_FIELDS),
            session.goal if session else None,
            session.outcome if session else None,
            session.summary if session else None,
            finalized,
        )
        await _recompute_arrays(conn, trace_id)
        if run is not None:
            await conn.execute(
                """
                insert into analyzer_results
                  (trace_id, analyzer, analyzer_version, model_id, output)
                values ($1, $2, $3, $4, $5)
                """,
                trace_id,
                run.analyzer,
                run.analyzer_version,
                run.model_id,
                run.output,
            )
        await review_items_q.sync(conn, trace_id, owner_id=owner_id, upload_id=upload_id)
        # A successful run is newer truth than any old failure: close open
        # analyze dead letters so the trace can't stay failed after a
        # recovery that bypassed the requeue CLI.
        await dead_letters.mark_requeued_for_trace(conn, trace_id)


async def relabel(
    pool: asyncpg.Pool,
    trace_id: str,
    turn_index: int,
    *,
    outcome: str,
    labels: list[Label],
    owner_id: str,
) -> bool:
    """Owner relabel of one turn: it becomes `human` (never re-judged),
    `uncertain` clears, the session arrays are recomputed, and the review
    item closes once no uncertain turn is left. False when the turn has no
    row (not analyzed yet)."""
    async with pool.acquire() as conn, conn.transaction():
        if not await _lock_trace(conn, trace_id):
            return False
        updated = await conn.fetchval(
            """
            update turn_analysis set outcome = $3, uncertain = null, provenance = 'human'
            where trace_id = $1 and turn_index = $2
            returning true
            """,
            trace_id,
            turn_index,
            outcome,
        )
        if not updated:
            return False
        await _replace_labels(conn, trace_id, turn_index, labels)
        await _recompute_arrays(conn, trace_id)
        await review_items_q.sync(conn, trace_id, resolved_by=owner_id)
        return True


async def fetch_open_dead_letter(pool: asyncpg.Pool, trace_id: str) -> asyncpg.Record | None:
    """The failed probe: a non-requeued analyze dead letter. Newest first in
    the pathological multi-row case."""
    return await pool.fetchrow(
        """
        select last_error, failed_at from dead_letters
        where trace_id = $1 and requeued_at is null
        order by failed_at desc
        limit 1
        """,
        trace_id,
    )
