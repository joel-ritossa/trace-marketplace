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
    """One row per (field, value): a failure mode the judge cites twice is
    merged — its span ids unioned, the first reason kept."""
    labels: dict[tuple[str, str], Label] = {
        ("task_category", value): ("task_category", value, [], None)
        for value in verdict.task_categories
    }
    for label in verdict.failure_modes:
        key = ("failure_mode", label.value)
        if key in labels:
            _, _, span_ids, reason = labels[key]
            merged = list(dict.fromkeys([*span_ids, *label.span_ids]))
            labels[key] = ("failure_mode", label.value, merged, reason)
        else:
            labels[key] = ("failure_mode", label.value, list(label.span_ids), label.reason)
    return list(labels.values())


def roll_up_state(finalized: bool, written: int, applied: int, changed: bool) -> str:
    """What a rewrite does to the roll-up stamp (`analyzed_at`): `stamp` a
    finalize whose every turn write landed; mark it `stale` when a turn the
    roll-up saw actually changed (written, deleted, or still outdated);
    otherwise `keep` it as is."""
    if finalized and applied == written:
        return "stamp"
    return "stale" if changed else "keep"


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


async def note_rerun_if_leased(
    executor: asyncpg.Pool | asyncpg.Connection, trace_id: str, finalize: bool
) -> bool:
    """When a run holds the trace's lease, record that another run is
    wanted (finalize wins over incremental) for the holder to enqueue on
    release, and return True."""
    return bool(
        await executor.fetchval(
            """
            update traces
            set analysis_rerun = case when $2 then 'finalize'
                                      else coalesce(analysis_rerun, 'incremental') end
            where id = $1 and analysis_lease_until > now()
            returning true
            """,
            trace_id,
            finalize,
        )
    )


async def claim(
    pool: asyncpg.Pool, trace_id: str, *, finalize: bool, lease_seconds: int
) -> int | str | None:
    """Take the per-trace run lease and count the attempt — the durable
    retry budget, mirroring uploads.mark_processing. Returns the attempt
    number, "leased" when another run holds the lease (this run's mode is
    recorded for it), or None when the trace is gone."""
    async with pool.acquire() as conn, conn.transaction():
        if not await _lock_trace(conn, trace_id):
            return None
        if await note_rerun_if_leased(conn, trace_id, finalize):
            return "leased"
        return await conn.fetchval(
            """
            update traces
            set analysis_attempts = analysis_attempts + 1, analysis_attempted_at = now(),
                analysis_lease_until = now() + make_interval(secs => $2)
            where id = $1
            returning analysis_attempts
            """,
            trace_id,
            lease_seconds,
        )


async def extend_lease(pool: asyncpg.Pool, trace_id: str, lease_seconds: int) -> None:
    """Heartbeat: a live run keeps its lease."""
    await pool.execute(
        """
        update traces set analysis_lease_until = now() + make_interval(secs => $2)
        where id = $1 and analysis_lease_until is not null
        """,
        trace_id,
        lease_seconds,
    )


async def release(pool: asyncpg.Pool, trace_id: str) -> str | None:
    """Drop the lease; returns the rerun mode other runs asked for meanwhile
    ('incremental' / 'finalize'), cleared here, for the holder to enqueue."""
    return await pool.fetchval(
        """
        with old as (select id, analysis_rerun from traces where id = $1 for update)
        update traces t set analysis_lease_until = null, analysis_rerun = null
        from old where t.id = old.id
        returning old.analysis_rerun
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
    pool: asyncpg.Pool, *, older_than_minutes: int, idle_seconds: int, limit: int
) -> list[tuple[str, bool]]:
    """What the minute sweep enqueues, as (trace_id, finalize):

    - lost kicks: re-ingested (attempts reset to 0) or never analyzed
      traces whose claim stamp is older than the timeout;
    - finalization: traces that should be final but are not — non-session
      traces always, session traces once `ended_at` is idle.

    Stamps the claim time so each trace re-enqueues at most once per
    timeout window, oldest claim first, at most `limit` per tick. Traces
    with a live run lease or an open dead letter (failed) are skipped.
    """
    rows = await pool.fetch(
        """
        update traces t set analysis_attempted_at = now()
        from (
          select c.id, c.finalize from (
            select t.id, coalesce(t.analysis_attempted_at, t.created_at) as claimed,
                   t.analysis_attempts,
                   (t.source_format = $3 or t.ended_at < now() - make_interval(secs => $2))
                     as finalize,
                   coalesce(ta.analyzed_at is not null, false) as rolled_up
            from traces t
            left join trace_analysis ta on ta.trace_id = t.id
            where coalesce(t.analysis_attempted_at, t.created_at)
                    < now() - make_interval(mins => $1)
              and (t.analysis_lease_until is null or t.analysis_lease_until < now())
              and not exists (
                select 1 from dead_letters dl
                where dl.trace_id = t.id and dl.requeued_at is null
              )
          ) c
          where c.analysis_attempts = 0 or (c.finalize and not c.rolled_up)
          order by c.claimed
          limit $4
        ) d
        where t.id = d.id
        returning t.id, d.finalize
        """,
        older_than_minutes,
        idle_seconds,
        OTLP_FORMAT,
        limit,
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


async def turn_origins(
    executor: asyncpg.Pool | asyncpg.Connection, trace_id: str
) -> dict[int, str]:
    """The trace's current turns as the judge splits them (agent/turns.split),
    each with its origin: the distinct integer `turn.index` values on its
    spans, `automated` when the turn span says `turn.origin = automated`,
    else `human` — or the one synthetic human turn 0 when there are none."""
    rows = await executor.fetch(
        """
        select (attributes ->> 'turn.index')::int as turn_index,
               bool_or(attributes ->> 'turn.origin' = 'automated') as automated
        from spans
        where trace_id = $1 and attributes ? 'turn.index'
          and jsonb_typeof(attributes -> 'turn.index') = 'number'
          and attributes ->> 'turn.index' ~ '^-?[0-9]+$'
        group by 1
        """,
        trace_id,
    )
    return {r["turn_index"]: "automated" if r["automated"] else "human" for r in rows} or {
        0: "human"
    }


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
    labels, human and machine alike — ordered by how many turns carry each
    value (then alphabetically), so truncated displays show the dominant ones."""
    await conn.execute(
        """
        update trace_analysis set
          task_categories = coalesce((
            select array_agg(value order by turns desc, value) from (
              select value, count(distinct turn_index) as turns from trace_labels
              where trace_id = $1 and field = 'task_category' group by value
            ) c
          ), '{}'),
          failure_modes = coalesce((
            select array_agg(value order by turns desc, value) from (
              select value, count(distinct turn_index) as turns from trace_labels
              where trace_id = $1 and field = 'failure_mode' group by value
            ) c
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
    expected: Mapping[int, str | None],
    signals: SignalsResult,
    llm_status: str,
    llm_skip_reason: str | None,
    finalized: bool,
    succeeded: bool,
    session: SessionVerdict | None = None,
    run: AnalyzerRun | None = None,
    owner_id: str,
    upload_id: str,
) -> None:
    """Persist one analysis run in one transaction, defensively against the
    rows having moved since the run read them:

    - turns absent from the trace's CURRENT spans are dropped;
    - a judged turn is written only if its stored fingerprint still equals
      the one this run read (`expected`; None = no row) and it is not human;
    - the roll-up is stamped only by a finalize whose every write landed,
      and marked stale (`analyzed_at` null) only when a turn it saw really
      changed (`roll_up_state`); `session` is None when the LLM is gated.

    Then the session row, the union arrays, the audit row and the review
    item; open dead letters close only when the run `succeeded`.
    """
    async with pool.acquire() as conn, conn.transaction():
        if not await _lock_trace(conn, trace_id):
            return
        live = set(await turn_origins(conn, trace_id))
        deleted = await conn.fetch(
            """
            delete from turn_analysis where trace_id = $1 and not (turn_index = any($2::int[]))
            returning turn_index
            """,
            trace_id,
            list(live),
        )
        rows = {
            r["turn_index"]: r
            for r in await conn.fetch(
                "select turn_index, fingerprint, provenance from turn_analysis where trace_id = $1",
                trace_id,
            )
        }
        unchanged = {
            index
            for index, fingerprint in expected.items()
            if index in live
            and (rows[index]["fingerprint"] if index in rows else None) == fingerprint
            and not (index in rows and rows[index]["provenance"] == "human")
        }
        applied = [t for t in turns if t.turn_index in unchanged]
        state = roll_up_state(finalized, len(turns), len(applied), bool(unchanged or deleted))
        for turn in applied:
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
                    case when $13 = 'stamp' then now() end)
            on conflict (trace_id) do update set
              llm_status = excluded.llm_status,
              llm_skip_reason = excluded.llm_skip_reason,
              {", ".join(f"{f} = excluded.{f}" for f in SIGNAL_FIELDS)},
              goal = case when $13 = 'stamp' then excluded.goal else trace_analysis.goal end,
              outcome = case when $13 = 'stamp' then excluded.outcome
                             else trace_analysis.outcome end,
              summary = case when $13 = 'stamp' then excluded.summary
                             else trace_analysis.summary end,
              analyzed_at = case $13 when 'stamp' then now() when 'stale' then null
                                     else trace_analysis.analyzed_at end
            """,
            trace_id,
            llm_status,
            llm_skip_reason,
            *(getattr(signals, f) for f in SIGNAL_FIELDS),
            session.goal if session else None,
            session.outcome if session else None,
            session.summary if session else None,
            state,
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
        # recovery that bypassed the requeue CLI. A failing run leaves them.
        if succeeded:
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
    `uncertain` clears, the session arrays are recomputed, the roll-up is
    marked stale (the caller enqueues a finalize to redo it), and the review
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
        await conn.execute(
            "update trace_analysis set analyzed_at = null where trace_id = $1", trace_id
        )
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
