"""Analysis package — analyzers, rendering, and the frozen stream contract.

Everything here is pure over normalized rows: no DB writes, no queue, no
HTTP (1_analysis.md). The A-stream imports the contract from this package
surface; `models.py` and `routing.py` are frozen at B0 close.
"""

from app.analysis.config import AnalysisSettings, RendererConfig
from app.analysis.embedding import EMBEDDING_VERSION, run_embedding
from app.analysis.judge import JUDGE_VERSION, run_judge
from app.analysis.listing import LISTING_VERSION, run_listing
from app.analysis.llm import MalformedResponse, PermanentAnalysisError, llm_configured
from app.analysis.models import (
    FAILURE_MODES,
    METRICS,
    TASK_CATEGORIES,
    AnalyzerRun,
    JudgeVerdict,
    JudgeVote,
    ListingResult,
    MetricCall,
    MetricResult,
    RenderedMessage,
    RenderedTrace,
    SignalsResult,
    SummaryResult,
)
from app.analysis.registry import (
    ANALYZERS,
    AnalyzerSpec,
    enabled_metric_specs,
    run_analyzer,
    run_metric_set,
)
from app.analysis.rendering import RENDERER_VERSION, render_trace
from app.analysis.routing import (
    RoutingReason,
    RoutingReasonCode,
    finalize_verdict,
    route,
)
from app.analysis.sample import TraceSample, trace_to_sample
from app.analysis.summary import SUMMARY_VERSION, run_summary
from app.analysis.trace_input import SpanInput, TraceInput
from app.analysis.validation import (
    AgreementEntry,
    AgreementReport,
    TraceLabel,
    agreement_report,
    load_labels,
)

__all__ = [
    "ANALYZERS",
    "EMBEDDING_VERSION",
    "FAILURE_MODES",
    "JUDGE_VERSION",
    "LISTING_VERSION",
    "METRICS",
    "RENDERER_VERSION",
    "SUMMARY_VERSION",
    "TASK_CATEGORIES",
    "AgreementEntry",
    "AgreementReport",
    "AnalysisSettings",
    "AnalyzerRun",
    "AnalyzerSpec",
    "JudgeVerdict",
    "JudgeVote",
    "ListingResult",
    "MalformedResponse",
    "MetricCall",
    "MetricResult",
    "PermanentAnalysisError",
    "RenderedMessage",
    "RenderedTrace",
    "RendererConfig",
    "RoutingReason",
    "RoutingReasonCode",
    "SignalsResult",
    "SpanInput",
    "SummaryResult",
    "TraceInput",
    "TraceLabel",
    "TraceSample",
    "agreement_report",
    "enabled_metric_specs",
    "finalize_verdict",
    "llm_configured",
    "load_labels",
    "render_trace",
    "route",
    "run_analyzer",
    "run_embedding",
    "run_judge",
    "run_listing",
    "run_metric_set",
    "run_summary",
    "trace_to_sample",
]
