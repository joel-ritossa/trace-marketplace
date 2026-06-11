import logging

from app.analysis import (
    ANALYZERS,
    AnalysisSettings,
    AnalyzerRun,
    JudgeVerdict,
    SignalsResult,
    llm_configured,
    run_analyzer,
)
from app.clients import db
from app.dev import faults
from app.queries import analysis as analysis_q
from app.worker.broker import broker

logger = logging.getLogger(__name__)

# What a production run executes, in run order — never the registry
# wholesale (the stub analyzer is a harness fixture). Metrics land by
# registration when B3 ships.
SIGNAL_FIELDS = (
    "has_retry_loop",
    "loop_kind",
    "recovered_from_error",
    "truncation_suspected",
    "llm_call_count",
    "tool_call_count",
)


def _metric_specs():
    return [spec for name, spec in ANALYZERS.items() if name.startswith("metric:")]


@broker.task(retry_dlq="trace")
async def analyze_trace(trace_id: str) -> None:
    """Run the production analyzers over one trace and persist the results.

    Idempotent by delete-and-rewrite of the trace's `analyzer_results` +
    `trace_analysis` rows in one transaction (1_analysis.md runtime rules);
    human-provenance label fields are preserved by the rewrite. Retry/DLQ
    rides the same middleware as ingestion, trace-scoped (A2).
    """
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
    await faults.trip_analysis(str(gate["upload_id"]), attempt)

    settings = AnalysisSettings()
    runs: list[AnalyzerRun] = []

    signals_run = await run_analyzer(ANALYZERS["signals"], trace, settings)
    if signals_run is None:  # signals apply to every trace; can't happen
        raise RuntimeError("signals analyzer reported inapplicable")
    runs.append(signals_run)
    signals = SignalsResult.model_validate(signals_run.output)

    # The LLM gate (1_analysis.md degradation rules). Consent beats
    # configuration when both apply (A2 decision 6).
    skip_reason: str | None = None
    if gate["visibility"] == "private" and not gate["allow_private_llm_analysis"]:
        skip_reason = "owner_opt_out"
    elif not llm_configured(settings.judge_model):
        skip_reason = "not_configured"

    verdict: JudgeVerdict | None = None
    if skip_reason is None:
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
            for spec in _metric_specs():
                metric_run = await run_analyzer(spec, trace, settings)
                if metric_run is not None:  # inapplicable -> no row, never a garbage score
                    runs.append(metric_run)

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

    await analysis_q.rewrite(
        pool,
        trace_id,
        runs=runs,
        promoted=promoted,
        llm_status="skipped" if skip_reason else "complete",
        llm_skip_reason=skip_reason,
    )
    logger.info(
        "analyze_trace: trace %s analyzed (attempt %d, analyzers %d, llm %s%s)",
        trace_id,
        attempt,
        len(runs),
        "skipped" if skip_reason else "complete",
        f" [{skip_reason}]" if skip_reason else "",
    )
