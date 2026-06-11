"""Analyzer registry: the registration seam between streams.

An analyzer is a pure async function `(TraceInput, AnalysisSettings) ->
result | None` (None = inapplicable, no row). The worker (A2) and the offline
runner both execute analyzers only through `run_analyzer`, which wraps the
output in the `AnalyzerRun` envelope the worker persists. Swapping a stub for
a real analyzer is a registration change, not a rework (6_build-order.md).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel

from app.analysis.config import AnalysisSettings
from app.analysis.models import AnalyzerRun, SignalsResult
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
}
