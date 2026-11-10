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


TurnOrigin = Literal["human", "automated"]


class TurnAnalysis(BaseModel):
    turn_index: int
    # Who started the turn: a person's ask, or an outside event (importer's
    # `turn.origin` on the turn span; absent = human).
    origin: TurnOrigin
    # Null = not judged (LLM analysis skipped).
    outcome: Outcome | None
    summary: str | None
    # Review-queue content: owner-only, null for everyone else.
    uncertain: str | None
    provenance: Provenance
    signals: AnalysisSignals
    labels: list[TurnLabel]


class SessionAnalysis(BaseModel):
    status: AnalysisStatus
    # Turns in the trace as the judge splits them, judged or not.
    turn_count: int
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


class AnalyzeResponse(BaseModel):
    """POST /v1/traces/{id}/analyze: 200 with queued=false when the trace is
    already final; 202 with queued=true when a finalizing run was enqueued
    or noted for the run in flight."""

    status: AnalysisStatus
    queued: bool


class TraceAnalysis(BaseModel):
    session: SessionAnalysis
    turns: list[TurnAnalysis]
    # Open analyze dead letter's error; the run failed and will not retry.
    failed_reason: str | None = None
    # Owner-only: null for non-owners and when nothing is open.
    open_review_item_id: str | None = None


# Relabel request bounds: one label per value (the taxonomies are small),
# span citations capped like bulk id lists (100), reasons like trace
# descriptions (2000 chars).
MAX_SPAN_IDS = 100
MAX_REASON_CHARS = 2000


def _no_duplicates(values: list[str], what: str) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError(f"Duplicate {what}.")
    return values


class FailureLabelInput(BaseModel):
    value: str
    span_ids: list[str] = Field(default=[], max_length=MAX_SPAN_IDS)
    reason: str | None = Field(default=None, max_length=MAX_REASON_CHARS)

    @field_validator("value")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in AGENT_FAILURE_MODES:
            raise ValueError(
                f"Unknown failure_mode; expected one of {sorted(AGENT_FAILURE_MODES)}."
            )
        return v

    @field_validator("span_ids")
    @classmethod
    def _unique_spans(cls, v: list[str]) -> list[str]:
        return _no_duplicates(v, "span ids")


class TurnLabelsRequest(BaseModel):
    """PUT /v1/traces/{id}/turns/{turn_index}/labels — the turn's full
    label set, replacing what was there."""

    outcome: Outcome
    task_categories: list[str] = Field(min_length=1, max_length=len(TASK_CATEGORIES))
    failure_modes: list[FailureLabelInput] = Field(default=[], max_length=len(AGENT_FAILURE_MODES))

    @field_validator("task_categories")
    @classmethod
    def _known_categories(cls, v: list[str]) -> list[str]:
        unknown = [c for c in v if c not in TASK_CATEGORIES]
        if unknown:
            raise ValueError(f"Unknown task_category {unknown}.")
        return _no_duplicates(v, "task categories")

    @field_validator("failure_modes")
    @classmethod
    def _unique_modes(cls, v: list[FailureLabelInput]) -> list[FailureLabelInput]:
        _no_duplicates([label.value for label in v], "failure modes")
        return v
