"""Analysis package — analyzers, rendering, and the frozen stream contract.

Everything here is pure over normalized rows: no DB writes, no queue, no
HTTP (1_analysis.md). The A-stream imports the contract from this package
surface; `models.py` and `routing.py` are frozen at B0 close.
"""

from app.analysis.config import AnalysisSettings, RendererConfig
from app.analysis.judge import JUDGE_VERSION, run_judge
from app.analysis.llm import MalformedResponse, PermanentAnalysisError, llm_configured
from app.analysis.models import (
    FAILURE_MODES,
    TASK_CATEGORIES,
    AnalyzerRun,
    JudgeVerdict,
    JudgeVote,
    MetricResult,
    RenderedMessage,
    RenderedTrace,
    SignalsResult,
)
from app.analysis.registry import ANALYZERS, AnalyzerSpec, run_analyzer
from app.analysis.rendering import RENDERER_VERSION, render_trace
from app.analysis.routing import (
    RoutingReason,
    RoutingReasonCode,
    finalize_verdict,
    route,
)
from app.analysis.sample import TraceSample, trace_to_sample
from app.analysis.trace_input import SpanInput, TraceInput

__all__ = [
    "ANALYZERS",
    "FAILURE_MODES",
    "JUDGE_VERSION",
    "RENDERER_VERSION",
    "TASK_CATEGORIES",
    "AnalysisSettings",
    "AnalyzerRun",
    "AnalyzerSpec",
    "JudgeVerdict",
    "JudgeVote",
    "MalformedResponse",
    "MetricResult",
    "PermanentAnalysisError",
    "RenderedMessage",
    "RenderedTrace",
    "RendererConfig",
    "RoutingReason",
    "RoutingReasonCode",
    "SignalsResult",
    "SpanInput",
    "TraceInput",
    "TraceSample",
    "finalize_verdict",
    "llm_configured",
    "render_trace",
    "route",
    "run_analyzer",
    "run_judge",
    "trace_to_sample",
]
