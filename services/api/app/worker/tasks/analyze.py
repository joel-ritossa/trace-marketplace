import logging
import time

from app import obs
from app.analysis import (
    ANALYZERS,
    RENDERER_VERSION,
    AnalysisSettings,
    AnalyzerRun,
    JudgeVerdict,
    ListingResult,
    PermanentAnalysisError,
    SignalsResult,
    finalize_verdict,
    llm_configured,
    route,
    run_analyzer,
    run_metric_set,
)
from app.analysis.embedding import run_embedding
from app.clients import db
from app.dev import faults
from app.queries import analysis as analysis_q
from app.queries import embeddings as embeddings_q
from app.queries import traces as traces_q
from app.worker.broker import broker
from app.worker.tasks.match import match_trace

logger = logging.getLogger(__name__)

# What a production run executes, in run order — never the registry
# wholesale (the stub analyzer is a harness fixture): signals, judge, then
# the enabled metric set.
SIGNAL_FIELDS = (
    "has_retry_loop",
    "loop_kind",
    "recovered_from_error",
    "truncation_suspected",
    "llm_call_count",
    "tool_call_count",
)


@broker.task(retry_dlq="trace")
async def analyze_trace(trace_id: str) -> None:
    """Run the production analyzers over one trace and persist the results.

    Idempotent by delete-and-rewrite of the trace's `analyzer_results` +
    `trace_analysis` rows in one transaction (1_analysis.md runtime rules);
    human-provenance label fields are preserved by the rewrite. Retry/DLQ
    rides the same middleware as ingestion, trace-scoped (A2).
    """
    obs.bind(trace_id=trace_id)
    started = time.perf_counter()
    pool = db.pool()
    attempt = await analysis_q.claim(pool, trace_id)
    if attempt is None:
        logger.warning("analyze_trace: trace %s no longer exists; dropping", trace_id)
        return

    gate = await analysis_q.fetch_llm_gate(pool, trace_id)
    trace = await analysis_q.fetch_trace_input(pool, trace_id)
    if gate is None or trace is None:
        logger.warning("analyze_trace: trace %s vanished mid-run; dropping", trace_id)
        return
    obs.bind(upload_id=str(gate["upload_id"]))
    logger.info(
        "analyze_trace: started (attempt %d, %d spans)",
        attempt,
        trace.span_count,
        extra={"attempt": attempt},
    )
    await faults.trip_analysis(str(gate["upload_id"]), attempt)

    settings = AnalysisSettings()
    runs: list[AnalyzerRun] = []

    with obs.stage(logger, "signals"):
        signals_run = await run_analyzer(ANALYZERS["signals"], trace, settings)
    if signals_run is None:  # signals apply to every trace; can't happen
        raise RuntimeError("signals analyzer reported inapplicable")
    runs.append(signals_run)
    signals = SignalsResult.model_validate(signals_run.output)

    # The LLM gate (1_analysis.md degradation rules). Consent beats
    # configuration when both apply (A2 decision 6).
    opt_out = gate["visibility"] == "private" and not gate["allow_private_llm_analysis"]
    skip_reason: str | None = None
    if opt_out:
        skip_reason = "owner_opt_out"
    elif not llm_configured(settings.judge_model):
        skip_reason = "not_configured"

    verdict: JudgeVerdict | None = None
    canned = await faults.canned_verdict(str(gate["upload_id"]))
    if canned is not None:
        # The keyless routing lever (A3 decision 9): a dev-armed verdict
        # stands in for the judge; the real cap + routing math run over it.
        skip_reason = None
        verdict = finalize_verdict(signals, canned)
        runs.append(
            AnalyzerRun(
                analyzer="judge",
                analyzer_version="fault:canned",
                model_id="fault:canned",
                output=verdict.model_dump(),
                confidence=verdict.outcome_confidence,
            )
        )
    elif skip_reason is None:
        with obs.stage(logger, "judge"):
            judge_run = await run_analyzer(ANALYZERS["judge"], trace, settings)
        if judge_run is None:
            # Defense-in-depth: the judge's own keyless check fired between
            # our gate and the call.
            skip_reason = "not_configured"
        else:
            # run_judge applies the disagreement cap before the verdict
            # leaves the analyzer (B2), so the envelope already carries the
            # final capped confidence — nothing to patch here.
            verdict = JudgeVerdict.model_validate(judge_run.output)
            runs.append(judge_run)
            logger.info(
                "analyze_trace: judge verdict outcome=%s (%.2f)",
                verdict.outcome,
                verdict.outcome_confidence or 0.0,
                extra={
                    "outcome": verdict.outcome,
                    "outcome_confidence": verdict.outcome_confidence,
                    "failure_mode": verdict.failure_mode,
                    "task_category": verdict.task_category,
                },
            )
            # Concurrent: metrics are independent (inapplicable -> no row,
            # never a garbage score); run_metric_set settles all before
            # raising, preserving error classification for retry/DLQ.
            with obs.stage(logger, "metrics"):
                runs.extend(await run_metric_set(trace, settings))

    if skip_reason:
        logger.info(
            "analyze_trace: llm analysis gated off (%s)",
            skip_reason,
            extra={"skip_reason": skip_reason},
        )

    # Listing copy (1_analysis.md listing-copy rules): generated only when
    # the owner left tags/description empty — never regenerated over
    # existing copy (its non-determinism would churn the listing), never
    # past the consent gate. Keyless, the analyzer returns None itself.
    listing: ListingResult | None = None
    if not opt_out and (not gate["tags"] or gate["description"] is None):
        with obs.stage(logger, "listing"):
            listing_run = await run_analyzer(ANALYZERS["listing"], trace, settings)
        if listing_run is not None:
            runs.append(listing_run)
            listing = ListingResult.model_validate(listing_run.output)

    # Behavior summary (1_analysis.md behavior-summary rules): machine-owned
    # display prose, regenerated on every run with the rest of the rewrite —
    # never past the consent gate. Keyless, the analyzer returns None itself;
    # malformed output fails open (no row, no summary).
    if not opt_out:
        with obs.stage(logger, "summary"):
            summary_run = await run_analyzer(ANALYZERS["summary"], trace, settings)
        if summary_run is not None:
            runs.append(summary_run)

    promoted: dict = {field: getattr(signals, field) for field in SIGNAL_FIELDS}
    if verdict is not None:
        for field in analysis_q.LABEL_FIELDS:
            value = getattr(verdict, field)
            promoted[field] = value
            promoted[f"{field}_confidence"] = (
                getattr(verdict, f"{field}_confidence") if value is not None else None
            )
            promoted[f"{field}_provenance"] = "machine" if value is not None else None
    metric_scores = {
        run.output["metric"]: run.output["value"]
        for run in runs
        if run.analyzer.startswith("metric:")
    }
    if metric_scores:
        promoted["metric_scores"] = metric_scores

    # HIL routing (1_analysis.md): only the outcome judge creates review
    # items — skipped runs have no verdict and never route. A verdict with
    # no reasons still carries the (empty) routing context so the rewrite
    # supersedes any stale open item: the fresh verdict answered the
    # question. The rewrite transaction applies the provenance filter and
    # persists item + digest atomically with the analysis rows (A3
    # decisions 1 and 3).
    routing = None
    if verdict is not None:
        reasons = route(signals, verdict, settings.confidence_threshold)
        if reasons:
            logger.info(
                "analyze_trace: routed to review (%s)",
                ", ".join(r.code for r in reasons),
                extra={"review_reasons": [r.code for r in reasons]},
            )
        routing = analysis_q.RoutingContext(
            reasons=reasons,
            verdict_snapshot={
                field: getattr(verdict, field)
                for label in analysis_q.LABEL_FIELDS
                for field in (label, f"{label}_confidence")
            },
            owner_id=str(gate["owner_id"]),
            upload_id=str(gate["upload_id"]),
        )

    with obs.stage(logger, "rewrite"):
        await analysis_q.rewrite(
            pool,
            trace_id,
            runs=runs,
            promoted=promoted,
            llm_status="skipped" if skip_reason else "complete",
            llm_skip_reason=skip_reason,
            routing=routing,
        )

    # Fill-if-empty in SQL: an owner edit landing mid-run wins, and a re-run
    # that raced an edit can never clobber it. Before the match kick so
    # subscription search sees the tags.
    if listing is not None:
        await traces_q.fill_listing_meta(
            pool, trace_id, tags=listing.tags, description=listing.description
        )

    # Similar-behavior embedding (docs/proposals/similar-behavior.md), after
    # the rewrite (labels are the product; the vector is an enhancement) and
    # before the match kick (anchored subscriptions read it). Gated like the
    # judge — but independently of the canned-verdict dev lever, which
    # routes labels, not consent. Gate closed or permanently failed ⇒ delete,
    # keeping the table a pure function of (payload, gates); transient
    # failures keep any prior vector and are retried by the next analyze run
    # rather than failing this one.
    if opt_out:
        embed_skip = "owner_opt_out"
    elif not llm_configured(settings.embedding_model):
        embed_skip = "not_configured"
    else:
        embed_skip = None
    if embed_skip is None:
        try:
            with obs.stage(logger, "embedding"):
                vector, _meta = await run_embedding(trace, settings)
            await embeddings_q.upsert(
                pool,
                trace_id,
                embedding=vector,
                model=settings.embedding_model,
                renderer_version=RENDERER_VERSION,
            )
        except PermanentAnalysisError:
            logger.exception("analyze_trace: permanent embedding failure for trace %s", trace_id)
            await embeddings_q.delete(pool, trace_id)
        except Exception:
            logger.exception("analyze_trace: transient embedding failure for trace %s", trace_id)
    else:
        await embeddings_q.delete(pool, trace_id)

    # Subscription trigger (b), 3_api.md: analyze_trace completed on a
    # listed trace. Visibility re-read post-rewrite (a listing mid-run must
    # not be missed); best-effort like ingest's analysis kick — matching is
    # idempotent and re-fired by later events, so a lost kick costs a
    # notification, not correctness (A4 decision 6).
    visibility = await pool.fetchval("select visibility from traces where id = $1", trace_id)
    if visibility == "listed":
        try:
            await match_trace.kiq(trace_id)
        except Exception:
            logger.exception("analyze_trace: failed to enqueue matching for trace %s", trace_id)

    total_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "analyze_trace: trace %s analyzed in %dms (attempt %d, analyzers %d, llm %s%s)",
        trace_id,
        total_ms,
        attempt,
        len(runs),
        "skipped" if skip_reason else "complete",
        f" [{skip_reason}]" if skip_reason else "",
        extra={
            "attempt": attempt,
            "duration_ms": total_ms,
            "analyzer_count": len(runs),
            "llm_status": "skipped" if skip_reason else "complete",
            "skip_reason": skip_reason,
            "match_kicked": visibility == "listed",
        },
    )
