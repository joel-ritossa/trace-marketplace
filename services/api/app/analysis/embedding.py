"""Trace embedding for similar-behavior retrieval
(docs/proposals/similar-behavior.md).

Embeds the judge rendering — the research result behind the feature
(sandbox/behavior-similarity): whole-transcript embeddings are the best
behavior retriever; structural skeletons and window matching underperform.
Pure over normalized rows like every analyzer: no DB, no queue.
"""

from app.analysis.config import CHARS_PER_TOKEN, AnalysisSettings, RendererConfig
from app.analysis.llm import CallMeta, embed
from app.analysis.rendering import render_trace, rendering_text
from app.analysis.trace_input import TraceInput

EMBEDDING_VERSION = "1"

_ELISION = "\n[…elided for embedding…]\n"


def embedding_input(trace: TraceInput, settings: AnalysisSettings) -> str:
    """The judge rendering, middle-out re-truncated to the embedding window
    (the render budget is larger). Middle-out keeps the task setup and the
    ending — where the behavior signal concentrates."""
    rendered = render_trace(trace, RendererConfig.from_settings(settings))
    text = rendering_text(rendered.messages)
    budget = settings.embedding_budget_tokens * CHARS_PER_TOKEN
    if len(text) <= budget:
        return text
    half = (budget - len(_ELISION)) // 2
    return text[:half] + _ELISION + text[-half:]


async def run_embedding(
    trace: TraceInput, settings: AnalysisSettings
) -> tuple[list[float], CallMeta]:
    text = embedding_input(trace, settings) or "(empty trace)"
    return await embed(settings.embedding_model, text)
