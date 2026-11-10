import asyncio
import logging
import time
from dataclasses import replace

from app import obs
from app.analysis import (
    AnalysisSettings,
    AnalyzerRun,
    MalformedResponse,
    PermanentAnalysisError,
    SignalsResult,
    TraceInput,
    combine,
    llm_configured,
    run_signals,
)
from app.analysis.agent import judge
from app.analysis.agent.models import AgentMeta, SessionVerdict, SubagentVerdict, TurnVerdict
from app.analysis.agent.turns import TurnView, deepest_first, split, subagents
from app.analysis.embedding import EMBEDDING_VERSION, embedding_input, run_embedding
from app.clients import db
from app.config import settings as platform
from app.dev import faults
from app.queries import analysis as analysis_q
from app.queries import embeddings as embeddings_q
from app.queries import traces as traces_q
from app.queries.analysis import SubagentWrite, TurnWrite
from app.worker.broker import broker
from app.worker.tasks.match import match_trace

logger = logging.getLogger(__name__)

Canned = tuple[str, bool]


@broker.task(retry_dlq="trace")
async def analyze_trace(trace_id: str, finalize: bool = True) -> None:
    """Judge the turns that need it and persist them (9_session-analysis.md).

    Two modes. Incremental (`finalize=False`, every session ingest): judge
    complete turns only — a session's last turn is still being written —
    and refresh the session arrays; the roll-up is left stale. Finalize
    (non-session traces always; sessions from the idle sweep, the owner's
    analyze request, listing, or a relabel): also judge the last turn and
    run the roll-up (goal/outcome/summary, listing copy, embedding).

    One run per trace at a time: a run takes the trace's lease (extended by
    a heartbeat while it lives); a run that finds it held exits at once,
    leaving its mode on the trace, and the holder enqueues one rerun in that
    mode when it releases — so a finalize asked for mid-run still happens.

    A turn's linked subagents are judged first, deepest first, and the turn
    judge reads their verdicts (`_judge_subagents`).

    Turns whose row is current are never re-judged, and human turns never
    are. A turn the judge permanently cannot process is stored as
    indeterminate + uncertain and the run goes on; a transient failure
    writes what succeeded, then raises so the retry judges only the rest.
    """
    obs.bind(trace_id=trace_id)
    pool = db.pool()
    attempt = await analysis_q.claim(
        pool, trace_id, finalize=finalize, lease_seconds=platform.analysis_lease_seconds
    )
    if attempt is None:
        logger.warning("analyze_trace: trace %s no longer exists; dropping", trace_id)
        return
    if attempt == "leased":
        logger.info("analyze_trace: another run holds the lease; rerun noted")
        return
    heartbeat = asyncio.create_task(_heartbeat(trace_id))
    try:
        await _run(trace_id, finalize, attempt)
    finally:
        heartbeat.cancel()
        rerun = await analysis_q.release(pool, trace_id)
        if rerun is not None:
            try:
                await analyze_trace.kiq(trace_id, finalize=rerun == "finalize")
            except Exception:
                logger.exception("analyze_trace: failed to enqueue the noted rerun")


async def _heartbeat(trace_id: str) -> None:
    while True:
        await asyncio.sleep(platform.analysis_lease_seconds / 3)
        try:
            await analysis_q.extend_lease(db.pool(), trace_id, platform.analysis_lease_seconds)
        except Exception:
            logger.exception("analyze_trace: lease heartbeat failed for trace %s", trace_id)


async def _run(trace_id: str, finalize: bool, attempt: int) -> None:
    started = time.perf_counter()
    pool = db.pool()
    gate = await analysis_q.fetch_llm_gate(pool, trace_id)
    trace = await analysis_q.fetch_trace_input(pool, trace_id)
    if gate is None or trace is None:
        logger.warning("analyze_trace: trace %s vanished mid-run; dropping", trace_id)
        return
    upload_id = str(gate["upload_id"])
    obs.bind(upload_id=upload_id)
    await faults.trip_analysis(upload_id, attempt)

    analysis = AnalysisSettings()
    finalize = finalize or not analysis_q.is_session_format(gate["source_format"])

    # The LLM gate (1_analysis.md degradation rules). Consent beats
    # configuration when both apply. A dev-armed canned verdict stands in
    # for the judge (the keyless review lever).
    opt_out = gate["visibility"] == "private" and not gate["allow_private_llm_analysis"]
    canned = await faults.canned_verdict(upload_id)
    skip_reason: str | None = None
    if canned is None:
        if opt_out:
            skip_reason = "owner_opt_out"
        elif not llm_configured(analysis.judge_model):
            skip_reason = "not_configured"
    llm = skip_reason is None

    turns = split(trace)
    stored = {t["turn_index"]: t for t in await analysis_q.fetch_turns(pool, trace_id)}
    current = await analysis_q.fetch_analysis(pool, trace_id)
    present = [t.index for t in turns]
    vanished = set(stored) - set(present)
    stale = [t for t in turns if analysis_q.needs_judging(stored.get(t.index), t.fingerprint, llm)]
    pending = stale if finalize else [t for t in stale if t is not turns[-1]]
    rolled_up = (
        current is not None
        and current["analyzed_at"] is not None
        and current["llm_skip_reason"] == skip_reason
    )
    # Write when there is something to judge or drop, when finalizing a
    # roll-up that is not current, or to mark a current roll-up stale
    # because a turn (typically the still-open last one) changed.
    if not (
        pending
        or vanished
        or (finalize and not rolled_up)
        or (not finalize and rolled_up and bool(stale))
    ):
        logger.info("analyze_trace: nothing to judge (finalize=%s)", finalize)
        return

    logger.info(
        "analyze_trace: started (attempt %d, %d turns, %d to judge, finalize=%s)",
        attempt,
        len(turns),
        len(pending),
        finalize,
        extra={"attempt": attempt, "turns_to_judge": len(pending), "finalize": finalize},
    )

    signals = {
        t.index: await run_signals(trace.model_copy(update={"spans": t.spans}), analysis)
        for t in pending
    }
    judged = pending
    results: list = [(None, None)] * len(pending)
    subagent_writes: list[SubagentWrite] = []
    failure: BaseException | None = None
    if llm and pending:
        semaphore = asyncio.Semaphore(analysis.turn_concurrency)
        subagent_verdicts: dict[str, SubagentVerdict] = {}
        if canned is None:
            with obs.stage(logger, "judge_subagents"):
                subagent_writes, subagent_verdicts, blocked, failure = await _judge_subagents(
                    trace,
                    pending,
                    await analysis_q.fetch_subagents(pool, trace_id),
                    analysis,
                    semaphore,
                )
            judged = [t for t in pending if t.index not in blocked]

        async def judge_one(turn_index: int) -> tuple[TurnVerdict, AgentMeta | None]:
            async with semaphore:
                return await _judge_turn(trace, turn_index, analysis, canned, subagent_verdicts)

        with obs.stage(logger, "judge"):
            results = await asyncio.gather(
                *(judge_one(t.index) for t in judged), return_exceptions=True
            )

    writes: list[TurnWrite] = []
    for turn, result in zip(judged, results, strict=True):
        if isinstance(result, PermanentAnalysisError):
            logger.warning(
                "analyze_trace: turn %d permanently failed; marked uncertain", turn.index
            )
            result = (_unprocessable(turn.index), None)
        elif isinstance(result, BaseException):
            failure = failure or result
            continue
        verdict, meta = result
        writes.append(TurnWrite(turn.index, turn.fingerprint, signals[turn.index], verdict, meta))

    session: SessionVerdict | None = None
    roll_meta: AgentMeta | None = None
    verdicts: list[TurnVerdict] = []
    if finalize and llm and failure is None:
        written = {w.turn_index: w.verdict for w in writes}
        for index in present:
            if index in written:
                verdicts.append(written[index])
            elif index in stored and stored[index]["outcome"] is not None:
                verdicts.append(analysis_q.stored_verdict(stored[index]))
        try:
            with obs.stage(logger, "roll_up"):
                session, roll_meta = await _roll_up(trace, verdicts, analysis, canned)
        except Exception as exc:
            failure = exc

    finalized = finalize and failure is None
    turn_signals = [w.signals for w in writes] + [
        SignalsResult.model_validate(stored[i]["signals"])
        for i in present
        if i in stored and i not in {w.turn_index for w in writes}
    ]
    run = (
        _audit_run(writes, subagent_writes, roll_meta, finalize, canned, analysis)
        if llm and (writes or subagent_writes or session)
        else None
    )
    # The fingerprints this run read for every turn it saw as changed — the
    # rewrite only applies turns still in that state.
    expected = {
        t.index: stored[t.index]["fingerprint"] if t.index in stored else None for t in stale
    }
    with obs.stage(logger, "rewrite"):
        await analysis_q.rewrite(
            pool,
            trace_id,
            turns=writes,
            subagents=subagent_writes,
            expected=expected,
            signals=combine(turn_signals),
            llm_status="complete" if llm else "skipped",
            llm_skip_reason=skip_reason,
            finalized=finalized,
            succeeded=failure is None,
            session=session,
            run=run,
            owner_id=str(gate["owner_id"]),
            upload_id=upload_id,
        )
    if failure is not None:
        logger.warning(
            "analyze_trace: %d of %d turns judged; raising the first failure",
            len(writes),
            len(pending),
        )
        raise failure

    if finalized:
        # Fill-if-empty in SQL: an owner edit landing mid-run wins. Before
        # the match kick so subscription search sees the tags.
        if session is not None and canned is None:
            await traces_q.fill_listing_meta(
                pool, trace_id, tags=session.tags, description=session.description
            )
        await _embed(trace_id, session, verdicts, analysis, opt_out)

    # Subscription trigger (b), 3_api.md: analysis wrote labels on a listed
    # trace. Visibility re-read post-rewrite; best-effort — matching is
    # idempotent and re-fired by later events.
    visibility = await pool.fetchval("select visibility from traces where id = $1", trace_id)
    if visibility == "listed":
        try:
            await match_trace.kiq(trace_id)
        except Exception:
            logger.exception("analyze_trace: failed to enqueue matching for trace %s", trace_id)

    total_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "analyze_trace: trace %s analyzed in %dms "
        "(attempt %d, %d turns judged, finalized %s, llm %s)",
        trace_id,
        total_ms,
        attempt,
        len(writes),
        finalized,
        "complete" if llm else f"skipped [{skip_reason}]",
        extra={
            "attempt": attempt,
            "duration_ms": total_ms,
            "turns_judged": len(writes),
            "finalized": finalized,
            "llm_status": "complete" if llm else "skipped",
            "skip_reason": skip_reason,
            "match_kicked": visibility == "listed",
        },
    )


async def _judge_subagents(
    trace: TraceInput,
    pending: list[TurnView],
    stored: dict[str, dict],
    settings: AnalysisSettings,
    semaphore: asyncio.Semaphore,
) -> tuple[list[SubagentWrite], dict[str, SubagentVerdict], set[int], BaseException | None]:
    """Judge the pending turns' linked subagents that have no current row,
    deepest level first so each judge reads the verdicts below it.

    Returns the rows to write, every current verdict by spawn span id (new
    and stored), the turns to leave for the retry, and the first transient
    failure. A subagent the judge permanently cannot process, answers
    malformed for, or gives no verdict it can stand behind is left without
    a row (its turn judge reads it inline); a transient failure stops its turn.
    """
    writes: list[SubagentWrite] = []
    verdicts: dict[str, SubagentVerdict] = {}
    blocked: set[int] = set()
    failure: BaseException | None = None

    async def judge_one(view: TurnView) -> tuple[SubagentVerdict | None, AgentMeta]:
        async with semaphore:
            return await judge.judge_subagent_with_meta(
                trace, view.index, view.under, settings, verdicts
            )

    for level in deepest_first([v for t in pending for v in subagents(trace, t)]):
        stale = []
        for view in level:
            row = stored.get(view.under)
            if row is not None and row["fingerprint"] == view.fingerprint:
                verdicts[view.under] = SubagentVerdict.model_validate(row)
            elif view.index not in blocked:
                stale.append(view)
        results = await asyncio.gather(*(judge_one(v) for v in stale), return_exceptions=True)
        for view, result in zip(stale, results, strict=True):
            write = SubagentWrite(view.under, view.index, view.fingerprint)
            if isinstance(result, (PermanentAnalysisError, MalformedResponse)):
                logger.warning("analyze_trace: a subagent could not be judged; left without a row")
                writes.append(write)
            elif isinstance(result, BaseException):
                failure = failure or result
                blocked.add(view.index)
            else:
                verdict, meta = result
                if verdict is not None:
                    verdicts[view.under] = verdict
                writes.append(replace(write, verdict=verdict, meta=meta))
    return writes, verdicts, blocked, failure


def _unprocessable(turn_index: int) -> TurnVerdict:
    """A turn the judge permanently cannot process: indeterminate, no
    labels, and uncertain so the owner is asked."""
    return TurnVerdict.model_construct(
        turn_index=turn_index,
        outcome="indeterminate",
        summary="",
        task_categories=[],
        failure_modes=[],
        uncertain="The judge could not process this turn.",
    )


async def _judge_turn(
    trace: TraceInput,
    turn_index: int,
    settings: AnalysisSettings,
    canned: Canned | None,
    verdicts: dict[str, SubagentVerdict],
) -> tuple[TurnVerdict, AgentMeta | None]:
    if canned is None:
        return await judge.judge_turn_with_meta(trace, turn_index, settings, verdicts)
    outcome, uncertain = canned
    verdict = TurnVerdict(
        turn_index=turn_index,
        outcome=outcome,
        summary="Fault injection: canned verdict.",
        task_categories=["other"],
        failure_modes=[],
        uncertain="Fault injection: canned uncertain turn." if uncertain else None,
    )
    return verdict, None


async def _roll_up(
    trace: TraceInput,
    verdicts: list[TurnVerdict],
    settings: AnalysisSettings,
    canned: Canned | None,
) -> tuple[SessionVerdict, AgentMeta | None]:
    if canned is None:
        return await judge.roll_up_with_meta(trace, verdicts, settings)
    session = SessionVerdict(
        goal="Fault injection: canned verdict.",
        outcome=canned[0],
        summary="Fault injection: canned verdict.",
        tags=[],
        description="",
    )
    return session, None


def _audit_run(
    writes: list[TurnWrite],
    subagent_writes: list[SubagentWrite],
    roll_meta: AgentMeta | None,
    finalize: bool,
    canned: Canned | None,
    settings: AnalysisSettings,
) -> AnalyzerRun:
    """The run's analyzer_results row: what each judged turn and subagent
    and the roll-up cost (model, tokens, cost, latency, tool calls)."""
    return AnalyzerRun(
        analyzer="agent",
        analyzer_version="fault:canned" if canned else judge.AGENT_VERSION,
        model_id="fault:canned" if canned else settings.judge_model,
        output={
            "finalize": finalize,
            "turns": [
                {"turn_index": w.turn_index, **(w.meta.model_dump(mode="json") if w.meta else {})}
                for w in writes
            ],
            "subagents": [
                {"span_id": w.span_id, "turn_index": w.turn_index, **w.meta.model_dump(mode="json")}
                for w in subagent_writes
                if w.meta
            ],
            "roll_up": roll_meta.model_dump(mode="json") if roll_meta else None,
        },
    )


async def _embed(
    trace_id: str,
    session: SessionVerdict | None,
    verdicts: list[TurnVerdict],
    settings: AnalysisSettings,
    opt_out: bool,
) -> None:
    """Similar-behavior embedding over the roll-up text, before the match
    kick (anchored subscriptions read it). No roll-up or gate closed or
    permanently failed ⇒ delete, keeping the table a pure function of
    (payload, gates); transient failures keep any prior vector and are
    retried by the next finalizing run rather than failing this one."""
    pool = db.pool()
    if session is None or opt_out or not llm_configured(settings.embedding_model):
        await embeddings_q.delete(pool, trace_id)
        return
    text = embedding_input(
        session.goal,
        session.summary,
        [(v.turn_index, v.outcome, v.summary) for v in verdicts],
        settings,
    )
    try:
        with obs.stage(logger, "embedding"):
            vector, _meta = await run_embedding(text, settings)
        await embeddings_q.upsert(
            pool,
            trace_id,
            embedding=vector,
            model=settings.embedding_model,
            input_version=EMBEDDING_VERSION,
        )
    except PermanentAnalysisError:
        logger.exception("analyze_trace: permanent embedding failure for trace %s", trace_id)
        await embeddings_q.delete(pool, trace_id)
    except Exception:
        logger.exception("analyze_trace: transient embedding failure for trace %s", trace_id)
