"""Subscription models (3_api.md). Mirrored by the frontend types in
apps/web/src/lib/api/subscriptions.ts.
"""

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.trace import TraceFilterQuery, TraceListItem

SubscriptionName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]

# Open interval: 0 would match everything embedded, 1 only a byte-identical
# rendering — both footguns, both rejected at write time (mirrors the
# migration's check constraint).
SimilarityThreshold = Annotated[float, Field(gt=0, lt=1)]


class SubscriptionQuery(TraceFilterQuery):
    """The stored query: the GET /v1/traces vocabulary, strictly — unknown
    params (including scope/sort/pagination, which are request shape, not
    query) are a 422 at write time (3_api.md). May be empty when the
    subscription carries a behavior anchor — the at-least-one-predicate
    floor lives on the requests, where the anchor is in view."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    def stored(self) -> dict[str, Any]:
        """The jsonb shape: param names as sent, defaults dropped — chips
        render exactly what was saved."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=True)


def validate_anchor_pair(trace_id: str | None, threshold: float | None) -> None:
    """The behavior anchor is one predicate with two fields — never split
    (docs/proposals/similar-behavior.md)."""
    if (trace_id is None) != (threshold is None):
        raise ValueError("similar_to_trace_id and similarity_threshold must be set together")


class SubscriptionCreateRequest(BaseModel):
    name: SubscriptionName
    query: SubscriptionQuery
    similar_to_trace_id: str | None = None
    similarity_threshold: SimilarityThreshold | None = None

    @model_validator(mode="after")
    def _at_least_one_predicate(self) -> "SubscriptionCreateRequest":
        validate_anchor_pair(self.similar_to_trace_id, self.similarity_threshold)
        # A subscribe-to-everything subscription is a footgun with no use;
        # the behavior anchor counts as a predicate.
        if not self.query.stored() and self.similar_to_trace_id is None:
            raise ValueError(
                "query must contain at least one filter predicate or a behavior anchor"
            )
        return self


class SubscriptionPatchRequest(BaseModel):
    """Omitted fields are left untouched. The anchor pair is patched as a
    unit: send both to set, both null to clear; the effective-state floor
    (a predicate or an anchor must remain) is checked in the router against
    the stored row."""

    name: SubscriptionName | None = None
    query: SubscriptionQuery | None = None
    similar_to_trace_id: str | None = None
    similarity_threshold: SimilarityThreshold | None = None


class Subscription(BaseModel):
    subscription_id: str
    name: str
    query: dict[str, Any]
    similar_to_trace_id: str | None = None
    similarity_threshold: float | None = None
    # The anchor trace's name for display; null when the anchor was deleted
    # (the subscription then matches nothing until edited).
    similar_to_name: str | None = None
    created_at: datetime
    last_seen_at: datetime
    # Live: the stored query executed as a count over listed traces.
    match_count: int
    # From the first-match ledger; null until an event-driven match lands.
    last_match_at: datetime | None


class SubscriptionListResponse(BaseModel):
    subscriptions: list[Subscription]


class SeenResponse(BaseModel):
    last_seen_at: datetime


class SubscriptionFeedItem(TraceListItem):
    """A result card (same shape as GET /v1/traces) plus the feed
    annotation (3_api.md)."""

    new_since_last_seen: bool


class SubscriptionFeedResponse(BaseModel):
    traces: list[SubscriptionFeedItem]
    total: int
    excluded_unanalyzed: int | None = None
