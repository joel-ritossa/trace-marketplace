"""Trace embedding for similar-behavior retrieval
(docs/proposals/similar-behavior.md).

Embeds the session roll-up text — goal, summary, one line per turn
(9_session-analysis.md). Pure like every analyzer: no DB, no queue.
"""

from app.analysis.config import CHARS_PER_TOKEN, AnalysisSettings
from app.analysis.llm import CallMeta, embed

EMBEDDING_VERSION = "2"


def embedding_input(
    goal: str,
    summary: str,
    turns: list[tuple[int, str | None, str | None]],
    settings: AnalysisSettings,
) -> str:
    """The roll-up text from (turn_index, outcome, summary) rows, cut to the
    embedding budget."""
    lines = [f"Goal: {goal}", f"Summary: {summary}"]
    lines += [f"Turn {index} ({outcome}): {text}" for index, outcome, text in turns]
    return "\n".join(lines)[: settings.embedding_budget_tokens * CHARS_PER_TOKEN]


async def run_embedding(text: str, settings: AnalysisSettings) -> tuple[list[float], CallMeta]:
    return await embed(settings.embedding_model, text)
