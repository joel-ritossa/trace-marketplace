"""Analyzer registry: the registration seam between streams.

An analyzer is a pure async function `(TraceInput, AnalysisSettings) ->
result | None` (None = inapplicable, no row). The worker (A2) and the offline
runner both execute analyzers only through `run_analyzer`, which wraps the
output in the `AnalyzerRun` envelope the worker persists. Swapping a stub for
a real analyzer is a registration change, not a rework (6_build-order.md).
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel

from app.analysis.config import AnalysisSettings
from app.analysis.judge import JUDGE_VERSION, run_judge
from app.analysis.listing import LISTING_VERSION, run_listing
from app.analysis.metrics import METRIC_RUNNERS, METRIC_VERSIONS
from app.analysis.models import (
    AnalyzerRun,
    JudgeVerdict,
    ListingResult,
    MetricResult,
    SignalsResult,
)
from app.analysis.signals import SIGNALS_VERSION, run_signals
from app.analysis.trace_input import TraceInput

AnalyzerFn = Callable[[TraceInput, AnalysisSettings], Awaitable[BaseModel | None]]


@dataclass(frozen=True)
class AnalyzerSpec:
    name: str
    version: str
    result_model: type[BaseModel]
    run: AnalyzerFn
    # Envelope confidence (analyzer_results.confidence), e.g. the judge's
    # outcome vote share. None where not applicable (2_data-model.md).
    confidence: Callable[[BaseModel], float | None] = lambda _: None
    # Model id for LLM analyzers; deterministic analyzers leave it None.
    model_id: Callable[[AnalysisSettings], str | None] = lambda _: None


async def run_analyzer(
    spec: AnalyzerSpec, trace: TraceInput, settings: AnalysisSettings
) -> AnalyzerRun | None:
    output = await spec.run(trace, settings)
    if output is None:
        return None
    return AnalyzerRun(
        analyzer=spec.name,
        analyzer_version=spec.version,
        model_id=spec.model_id(settings),
        confidence=spec.confidence(output),
        output=output.model_dump(mode="json"),
    )


class StubResult(BaseModel):
    """Deterministic counts off the input — exists to exercise the full
    registry → run → envelope → JSON path until real analyzers land."""

    span_count: int
    llm_span_count: int
    tool_span_count: int
    error_span_count: int


async def _run_stub(trace: TraceInput, settings: AnalysisSettings) -> StubResult:
    return StubResult(
        span_count=len(trace.spans),
        llm_span_count=sum(1 for s in trace.spans if s.kind == "llm"),
        tool_span_count=sum(1 for s in trace.spans if s.kind == "tool"),
        error_span_count=sum(1 for s in trace.spans if s.status == "error"),
    )


ANALYZERS: dict[str, AnalyzerSpec] = {
    "stub": AnalyzerSpec(name="stub", version="1", result_model=StubResult, run=_run_stub),
    "signals": AnalyzerSpec(
        name="signals", version=SIGNALS_VERSION, result_model=SignalsResult, run=run_signals
    ),
    "judge": AnalyzerSpec(
        name="judge",
        version=JUDGE_VERSION,
        result_model=JudgeVerdict,
        run=run_judge,
        # The judge applies the disagreement cap internally, so this is the
        # final (capped) outcome confidence — what analyzer_results stores.
        confidence=lambda v: v.outcome_confidence,
        model_id=lambda s: s.judge_model,
    ),
    # Listing copy (not a label family): free-form tags + description for
    # the marketplace listing; no envelope confidence — there is no vote
    # share or self-report with defined semantics for prose.
    "listing": AnalyzerSpec(
        name="listing",
        version=LISTING_VERSION,
        result_model=ListingResult,
        run=run_listing,
        model_id=lambda s: s.judge_model,
    ),
    # Family 3 (B3): metric scores are not labels and carry no envelope
    # confidence (1_analysis.md).
    **{
        f"metric:{name}": AnalyzerSpec(
            name=f"metric:{name}",
            version=METRIC_VERSIONS[name],
            result_model=MetricResult,
            run=run,
            model_id=lambda s: s.judge_model,
        )
        for name, run in METRIC_RUNNERS.items()
    },
}


def enabled_metric_specs(settings: AnalysisSettings) -> list[AnalyzerSpec]:
    """The metric set a run executes — the registry's `metric:*` entries
    filtered by `ANALYSIS_METRICS` (the default-on knob, 1_analysis.md).
    Settings validation guarantees every name is registered."""
    return [ANALYZERS[f"metric:{name}"] for name in settings.metric_names]


async def run_metric_set(trace: TraceInput, settings: AnalysisSettings) -> list[AnalyzerRun]:
    """Run the enabled metrics concurrently — independent analyzers sharing
    no state, so sequential execution was pure latency (~7 LLM round-trips
    chained per trace). Envelopes return in spec order; inapplicable metrics
    (None) drop out. Settle every metric before re-raising the first error
    (the judge's gather discipline): typed permanent/transient classification
    reaches the worker's retry machinery intact, and no metric's in-flight
    call is abandoned mid-await."""
    specs = enabled_metric_specs(settings)
    results = await asyncio.gather(
        *(run_analyzer(spec, trace, settings) for spec in specs), return_exceptions=True
    )
    for result in results:
        if isinstance(result, BaseException):
            raise result
    return [run for run in results if isinstance(run, AnalyzerRun)]
