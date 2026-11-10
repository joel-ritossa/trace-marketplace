"""Verdict shapes (9_session-analysis.md) and per-call usage metadata."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.analysis.models import FAILURE_MODES, TASK_CATEGORIES, Outcome

# An empty failure-mode set already says "none identified".
AGENT_FAILURE_MODES = FAILURE_MODES - {"inconclusive"}


def _member(vocabulary: frozenset[str]):
    def check(value: str) -> str:
        if value not in vocabulary:
            raise ValueError(f"unknown value {value!r}")
        return value

    return check


FailureMode = Annotated[str, AfterValidator(_member(AGENT_FAILURE_MODES))]
TaskCategory = Annotated[str, AfterValidator(_member(TASK_CATEGORIES))]


class FailureLabel(BaseModel):
    value: FailureMode
    span_ids: list[str] = Field(min_length=1)
    reason: str


def merge_labels(labels: list[FailureLabel]) -> list[FailureLabel]:
    """One label per value: a failure mode cited twice is merged — its span
    ids unioned, the first reason kept."""
    merged: dict[str, FailureLabel] = {}
    for label in labels:
        first = merged.get(label.value)
        span_ids = list(dict.fromkeys([*(first.span_ids if first else []), *label.span_ids]))
        merged[label.value] = (first or label).model_copy(update={"span_ids": span_ids})
    return list(merged.values())


class TurnVerdict(BaseModel):
    turn_index: int
    outcome: Outcome
    summary: str
    task_categories: list[TaskCategory] = Field(min_length=1)
    failure_modes: list[FailureLabel]
    uncertain: str | None


class SubagentVerdict(BaseModel):
    """One linked subagent, judged against its brief (the spawn span's input)."""

    span_id: str  # source_span_id of the spawn span
    outcome: Outcome
    summary: str
    failure_modes: list[FailureLabel]  # span_ids inside this subagent


class SessionVerdict(BaseModel):
    goal: str
    outcome: Outcome
    summary: str
    tags: list[str]
    description: str


class AgentMeta(BaseModel):
    """What one judge_turn / judge_subagent / roll_up run cost, summed over its LLM calls."""

    model: str
    llm_calls: int
    tool_calls: int
    latency_ms: int
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
