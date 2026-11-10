"""Review-item view models (9_session-analysis.md Review).

Mirrored by the frontend types in apps/web/src/lib/api/review.ts.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.trace import TraceStatus

ReviewStatus = Literal["open", "resolved", "superseded"]

ReviewListStatus = Literal["open", "resolved", "superseded", "all"]


class ReviewTurn(BaseModel):
    """An uncertain machine turn and why the agent could not judge it."""

    turn_index: int
    reason: str
    summary: str | None = None


class ReviewContext(BaseModel):
    turns: list[ReviewTurn]


class ReviewTraceSummary(BaseModel):
    trace_id: str
    name: str
    # The session roll-up goal; null until finalized.
    goal: str | None
    status: TraceStatus
    started_at: datetime
    duration_ms: int


class ReviewItemResponse(BaseModel):
    review_item_id: str
    trace_id: str
    # For per-upload grouping in the queue and the digest's filtered link.
    upload_id: str
    upload_filename: str
    context: ReviewContext
    status: ReviewStatus
    created_at: datetime
    trace: ReviewTraceSummary
    # Set when the owner's relabels left no uncertain turn.
    resolved_at: datetime | None = None
    resolved_by: str | None = None


class ReviewItemListResponse(BaseModel):
    items: list[ReviewItemResponse]
    total: int
