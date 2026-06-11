"""Review-item view models (3_api.md Review items).

Mirrored by the frontend types in apps/web/src/lib/api/review.ts.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from app.analysis import FAILURE_MODES, TASK_CATEGORIES
from app.schemas.analysis import Provenance
from app.schemas.trace import Outcome, TraceStatus

ReviewStatus = Literal["open", "resolved", "superseded"]

ReviewListStatus = Literal["open", "resolved", "superseded", "all"]


class ReviewVerdictContext(BaseModel):
    """The machine verdict snapshot recorded when the item was created —
    shown as context, never pre-selected (4_pages.md)."""

    outcome: Outcome | None = None
    outcome_confidence: float | None = None
    failure_mode: str | None = None
    failure_mode_confidence: float | None = None
    task_category: str | None = None
    task_category_confidence: float | None = None


class ReviewReason(BaseModel):
    code: str
    message: str


class ReviewContext(BaseModel):
    verdict: ReviewVerdictContext
    # Empty = owner-initiated relabel (2_data-model.md).
    reasons: list[ReviewReason]


class ReviewAnswer(BaseModel):
    """The resolved (partial) answer as recorded on the item."""

    outcome: Outcome | None = None
    failure_mode: str | None = None
    task_category: str | None = None


class ReviewTraceSummary(BaseModel):
    trace_id: str
    name: str
    status: TraceStatus
    started_at: datetime
    duration_ms: int


class ReviewItemResponse(BaseModel):
    review_item_id: str
    trace_id: str
    # For per-upload grouping in the queue and the digest's filtered link.
    upload_id: str
    upload_filename: str
    question_type: str
    context: ReviewContext
    status: ReviewStatus
    created_at: datetime
    trace: ReviewTraceSummary
    # Resolution fields; null while open.
    answer: ReviewAnswer | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None


class ReviewItemListResponse(BaseModel):
    items: list[ReviewItemResponse]
    total: int


class ReviewResolveRequest(BaseModel):
    """Partial answer: any of the three label fields (3_api.md). Values are
    app-validated against the analysis-package taxonomies — the one source
    of truth (1_analysis.md evolution policy)."""

    outcome: Outcome | None = None
    failure_mode: str | None = None
    task_category: str | None = None

    @field_validator("failure_mode")
    @classmethod
    def _failure_mode_known(cls, v: str | None) -> str | None:
        if v is not None and v not in FAILURE_MODES:
            raise ValueError(f"Unknown failure_mode; expected one of {sorted(FAILURE_MODES)}.")
        return v

    @field_validator("task_category")
    @classmethod
    def _task_category_known(cls, v: str | None) -> str | None:
        if v is not None and v not in TASK_CATEGORIES:
            raise ValueError(f"Unknown task_category; expected one of {sorted(TASK_CATEGORIES)}.")
        return v

    @model_validator(mode="after")
    def _coherent(self) -> "ReviewResolveRequest":
        if self.outcome is None and self.failure_mode is None and self.task_category is None:
            raise ValueError("Provide at least one of: outcome, failure_mode, task_category.")
        # failure_mode only accompanies a failure outcome (1_analysis.md label
        # model). failure_mode alone stays legal — refining a machine failure
        # verdict without touching its outcome.
        if self.failure_mode is not None and self.outcome is not None and self.outcome != "failure":
            raise ValueError("failure_mode requires a failure outcome.")
        return self


class ResolvedLabel(BaseModel):
    value: str
    confidence: float
    provenance: Provenance


class ReviewResolveResponse(BaseModel):
    item: ReviewItemResponse
    # The label triplets as written — the post-resolve per-field
    # provenance + confidence display (4_pages.md).
    labels: dict[str, ResolvedLabel]
