"""Analysis package — signals, rendering, the agent judge, and the models
they share.

Everything here is pure over normalized rows: no DB writes, no queue, no
HTTP (1_analysis.md). The worker persists what these return.
"""

from app.analysis.config import AnalysisSettings, RendererConfig
from app.analysis.embedding import EMBEDDING_VERSION, run_embedding
from app.analysis.llm import MalformedResponse, PermanentAnalysisError, llm_configured
from app.analysis.models import (
    FAILURE_MODES,
    TASK_CATEGORIES,
    AnalyzerRun,
    Outcome,
    Provenance,
    RenderedMessage,
    RenderedTrace,
    SignalsResult,
)
from app.analysis.rendering import RENDERER_VERSION, render_trace
from app.analysis.signals import SIGNALS_VERSION, combine, run_signals
from app.analysis.trace_input import SpanInput, TraceInput

__all__ = [
    "EMBEDDING_VERSION",
    "FAILURE_MODES",
    "RENDERER_VERSION",
    "SIGNALS_VERSION",
    "TASK_CATEGORIES",
    "AnalysisSettings",
    "AnalyzerRun",
    "MalformedResponse",
    "Outcome",
    "PermanentAnalysisError",
    "Provenance",
    "RenderedMessage",
    "RenderedTrace",
    "RendererConfig",
    "SignalsResult",
    "SpanInput",
    "TraceInput",
    "combine",
    "llm_configured",
    "render_trace",
    "run_embedding",
    "run_signals",
]
