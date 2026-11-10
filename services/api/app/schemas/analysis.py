"""Analysis view models (9_session-analysis.md API): the trace detail's
analysis block. Mirrored by the frontend types in apps/web/src/lib/api/traces.ts.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.analysis import TASK_CATEGORIES, Outcome, Provenance
from app.analysis.agent.models import AGENT_FAILURE_MODES

# Derived, never stored (queries/analysis.derive_status).
AnalysisStatus = Literal["pending", "in_progress", "final", "skipped"]

SkipReason = Literal["not_configured", "owner_opt_out"]

LabelField = Literal["task_category", "failure_mode"]


class AnalysisSignals(BaseModel):
    """Deterministic signals — per turn, and their session aggregate."""

    has_retry_loop: bool | None = None
    loop_kind: str | None = None
    recovered_from_error: bool | None = None
    truncation_suspected: bool | None = None
    llm_call_count: int | None = None
    tool_call_count: int | None = None


class TurnLabel(BaseModel):
    field: LabelField
    value: str
    span_ids: list[str]
    reason: str | None


class TurnAnalysis(BaseModel):
    turn_index: int
    # Null = not judged (LLM analysis skipped).
    outcome: Outcome | None
    summary: str | None
    uncertain: str | None
    provenance: Provenance
    signals: AnalysisSignals
    labels: list[TurnLabel]


class SessionAnalysis(BaseModel):
    status: AnalysisStatus
    # Set exactly when skipped.
    skip_reason: SkipReason | None = None
    goal: str | None = None
    outcome: Outcome | None = None
    summary: str | None = None
    task_categories: list[str] = []
    failure_modes: list[str] = []
    # Roll-up time; null until finalized.
    analyzed_at: datetime | None = None
    signals: AnalysisSignals | None = None


class TraceAnalysis(BaseModel):
    session: SessionAnalysis
    turns: list[TurnAnalysis]
    # Open analyze dead letter's error; the run failed and will not retry.
    failed_reason: str | None = None
    # Owner-only: null for non-owners and when nothing is open.
    open_review_item_id: str | None = None


class FailureLabelInput(BaseModel):
    value: str
    span_ids: list[str] = []
    reason: str | None = None

    @field_validator("value")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in AGENT_FAILURE_MODES:
            raise ValueError(
                f"Unknown failure_mode; expected one of {sorted(AGENT_FAILURE_MODES)}."
            )
        return v


class TurnLabelsRequest(BaseModel):
    """PUT /v1/traces/{id}/turns/{turn_index}/labels — the turn's full
    label set, replacing what was there."""

    outcome: Outcome
    task_categories: list[str] = Field(min_length=1)
    failure_modes: list[FailureLabelInput] = []

    @field_validator("task_categories")
    @classmethod
    def _known_categories(cls, v: list[str]) -> list[str]:
        unknown = [c for c in v if c not in TASK_CATEGORIES]
        if unknown:
            raise ValueError(f"Unknown task_category {unknown}.")
        return list(dict.fromkeys(v))
