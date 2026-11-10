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


class TurnVerdict(BaseModel):
    turn_index: int
    outcome: Outcome
    summary: str
    task_categories: list[TaskCategory] = Field(min_length=1)
    failure_modes: list[FailureLabel]
    uncertain: str | None


class SessionVerdict(BaseModel):
    goal: str
    outcome: Outcome
    summary: str
    tags: list[str]
    description: str


class AgentMeta(BaseModel):
    """What one judge_turn / roll_up run cost, summed over its LLM calls."""

    model: str
    llm_calls: int
    tool_calls: int
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
