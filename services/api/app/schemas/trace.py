import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.schemas.analysis import AnalysisState, Provenance

# Mirrors the traces.status check constraint and the frontend types
# (apps/web/src/lib/api/traces.ts).
TraceStatus = Literal["ok", "error"]

# The ternary label vocabulary (1_analysis.md label model).
Outcome = Literal["success", "failure", "indeterminate"]

TraceSort = Literal["created_at", "duration_ms", "span_count"]

TraceScope = Literal["mine", "marketplace", "acquired"]

TraceVisibility = Literal["private", "listed"]

# Value validation splits by stability (A4 decision 2): check-constrained
# sets validate strictly; evolving taxonomies and metric names are
# format-checked only — soft-retired values must stay matchable, and metric
# keys come from observed data. Unknown values match nothing ("null never
# matches" makes that the honest semantics).
OUTCOME_VALUES = {"success", "failure", "indeterminate"}
PROVENANCE_VALUES = {"machine", "human_confirmed", "human"}
LOOP_KIND_VALUES = {"exact_repeat", "cycle", "stagnation"}
_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def csv_values(raw: str) -> list[str]:
    """Comma-separated equality values OR within a field (3_api.md)."""
    return [v.strip() for v in raw.split(",") if v.strip()]


def parse_metric(raw: str) -> tuple[str, float | bool]:
    """The `metric=<name>:<min>` grammar; `<name>:true` for boolean flags.

    Raises ValueError on malformed input — the model validator surfaces it
    as a 422.
    """
    name, sep, value = raw.partition(":")
    if not sep or not _SLUG_RE.fullmatch(name):
        raise ValueError(f"metric must be <name>:<min> or <name>:true, got {raw!r}")
    if value == "true":
        return name, True
    try:
        return name, float(value)
    except ValueError:
        raise ValueError(f"metric bound must be a number or 'true', got {raw!r}") from None


class TraceFilterQuery(BaseModel):
    """The one filter vocabulary (A4 decision 1): GET /v1/traces parses it
    from query params, subscriptions validate and store it, and stored
    queries re-parse through it on execution — one parser, three call
    sites. Scope/sort/pagination deliberately live outside it (they are
    request shape, not query)."""

    model_config = ConfigDict(populate_by_name=True)

    # Stage-1 params, unchanged.
    q: str | None = Field(default=None, max_length=200)
    provider: str | None = None
    model: str | None = None
    tool: str | None = None
    has_errors: bool = False
    date_from: Annotated[datetime | None, Field(alias="from")] = None
    date_to: Annotated[datetime | None, Field(alias="to")] = None

    # Analysis equality filters; comma-separated values OR within a field.
    outcome: str | None = None
    failure_mode: str | None = None
    task_category: str | None = None
    loop_kind: str | None = None
    outcome_provenance: str | None = None
    failure_mode_provenance: str | None = None
    task_category_provenance: str | None = None

    # Promoted signal booleans; false is a real filter, absent is none.
    has_retry_loop: bool | None = None
    recovered_from_error: bool | None = None
    truncation_suspected: bool | None = None

    # Min-bounds — the only range shape in stage 2 (3_api.md).
    outcome_confidence_gte: float | None = Field(default=None, ge=0, le=1)
    task_category_confidence_gte: float | None = Field(default=None, ge=0, le=1)
    duration_ms_gte: int | None = Field(default=None, ge=0)
    total_tokens_gte: int | None = Field(default=None, ge=0)
    llm_call_count_gte: int | None = Field(default=None, ge=0)
    tool_call_count_gte: int | None = Field(default=None, ge=0)

    # Repeatable: metric=<name>:<min> / metric=<name>:true; repeats AND.
    metric: list[str] = Field(default_factory=list)

    @field_validator("outcome")
    @classmethod
    def _outcome_known(cls, v: str | None) -> str | None:
        return _check_csv(v, OUTCOME_VALUES, "outcome")

    @field_validator("outcome_provenance", "failure_mode_provenance", "task_category_provenance")
    @classmethod
    def _provenance_known(cls, v: str | None) -> str | None:
        return _check_csv(v, PROVENANCE_VALUES, "provenance")

    @field_validator("loop_kind")
    @classmethod
    def _loop_kind_known(cls, v: str | None) -> str | None:
        return _check_csv(v, LOOP_KIND_VALUES, "loop_kind")

    @field_validator("failure_mode", "task_category")
    @classmethod
    def _taxonomy_shape(cls, v: str | None) -> str | None:
        if v is not None:
            for value in csv_values(v):
                if not _SLUG_RE.fullmatch(value):
                    raise ValueError(f"not a valid taxonomy value: {value!r}")
        return v

    @field_validator("metric")
    @classmethod
    def _metric_grammar(cls, v: list[str]) -> list[str]:
        for item in v:
            parse_metric(item)
        return v

    @property
    def parsed_metrics(self) -> list[tuple[str, float | bool]]:
        return [parse_metric(item) for item in self.metric]

    @property
    def has_analysis_predicate(self) -> bool:
        """True when any trace_analysis-backed predicate is active — drives
        the excluded-unanalyzed note (A4 decision 4)."""
        return bool(
            self.outcome
            or self.failure_mode
            or self.task_category
            or self.loop_kind
            or self.outcome_provenance
            or self.failure_mode_provenance
            or self.task_category_provenance
            or self.has_retry_loop is not None
            or self.recovered_from_error is not None
            or self.truncation_suspected is not None
            or self.outcome_confidence_gte is not None
            or self.task_category_confidence_gte is not None
            or self.llm_call_count_gte is not None
            or self.tool_call_count_gte is not None
            or self.metric
        )


def _check_csv(v: str | None, allowed: set[str], label: str) -> str | None:
    if v is not None:
        for value in csv_values(v):
            if value not in allowed:
                raise ValueError(f"unknown {label} value: {value!r}")
    return v


class TraceListParams(TraceFilterQuery):
    """GET /v1/traces request shape: the filter vocabulary plus
    scope/sort/pagination. A separate subclass because FastAPI query models
    cannot mix with loose query params — and because these fields are
    deliberately *not* part of the subscribable vocabulary."""

    scope: TraceScope = "mine"
    sort: TraceSort = "created_at"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class TraceListItem(BaseModel):
    trace_id: str
    name: str
    status: TraceStatus
    started_at: datetime
    duration_ms: int
    span_count: int
    error_count: int
    provider: str | None
    model: str | None
    created_at: datetime
    visibility: TraceVisibility
    tags: list[str]
    description: str | None
    listed_at: datetime | None
    owner_display_name: str | None
    is_owner: bool
    acquired: bool
    # Set when acquired; the library card shows it.
    acquired_at: datetime | None
    # Label-at-list-level fields (3_api.md result cards): outcome triplet +
    # the derived analysis state.
    outcome: Outcome | None
    outcome_confidence: float | None
    outcome_provenance: Provenance | None
    analysis_state: AnalysisState
    # Owner-only (A3 decision 8): the needs-review indicator + its link
    # target; always false/null on a non-owner's card.
    has_open_review_item: bool
    open_review_item_id: str | None


class TraceListResponse(BaseModel):
    traces: list[TraceListItem]
    total: int
    # Set when analysis predicates are active (A4 decision 4): how many
    # traces matched the non-analysis filters but have no trace_analysis
    # row yet — backs the "N not-yet-analyzed traces excluded" note.
    excluded_unanalyzed: int | None = None


class SimilarTraceItem(TraceListItem):
    """A result card plus cosine similarity to the anchor
    (docs/proposals/similar-behavior.md)."""

    similarity: float


class SimilarTracesResponse(BaseModel):
    # False when the anchor has no embedding (analysis pending, or the LLM
    # gate is closed for it) — the UI explains instead of showing nothing.
    anchor_embedded: bool
    items: list[SimilarTraceItem]
    # Count of visible traces at/above min_similarity, when it was sent —
    # the subscription threshold slider's live preview.
    total_above: int | None = None


class TraceDetailResponse(BaseModel):
    trace_id: str
    upload_id: str
    source_trace_id: str
    name: str
    status: TraceStatus
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    span_count: int
    error_count: int
    provider: str | None
    model: str | None
    service_name: str | None
    tool_names: list[str]
    error_types: list[str]
    tags: list[str]
    description: str | None
    visibility: TraceVisibility
    listed_at: datetime | None
    owner_display_name: str | None
    source_format: str
    importer_version: str
    created_at: datetime
    # Caller's relationship to the trace (3_api.md): drives the actions UI.
    is_owner: bool
    acquired: bool
    can_download: bool
    total_tokens: int | None
    # Header label strip (4_pages.md); the Analysis section fetches the
    # full view from GET /v1/traces/{id}/analysis.
    outcome: Outcome | None
    outcome_confidence: float | None
    outcome_provenance: Provenance | None
    analysis_state: AnalysisState
    has_open_review_item: bool
    open_review_item_id: str | None


# Bounded: tags ride along on every result card, and lexemes past ~2KB are
# silently dropped from search_tsv anyway.
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class TraceUpdateRequest(BaseModel):
    """PATCH body; omitted fields are left untouched."""

    visibility: TraceVisibility | None = None
    tags: list[Tag] | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=2000)
    # The "this data is yours to share" checkbox; required to list.
    confirm_ownership: bool = False


class AcquireResponse(BaseModel):
    acquisition_id: str
    trace_id: str
    price_usd: float
    acquired_at: datetime


class MetricKeysResponse(BaseModel):
    """Observed metric_scores keys over traces visible to the caller —
    the filter UI enumerates these, never a hardcoded list (4_pages.md)."""

    keys: list[str]


# Bulk operations (3_api.md): ≤100 ids per call, itemized results — partial
# success is normal, never all-or-nothing.

BulkAcquireStatus = Literal["acquired", "already_acquired", "not_listed", "not_found"]

BulkVisibilityStatus = Literal["updated", "not_found"]


class BulkAcquireRequest(BaseModel):
    trace_ids: list[str] = Field(min_length=1, max_length=100)


class BulkAcquireItem(BaseModel):
    trace_id: str
    status: BulkAcquireStatus


class BulkAcquireResponse(BaseModel):
    results: list[BulkAcquireItem]


class BulkVisibilityRequest(BaseModel):
    trace_ids: list[str] = Field(min_length=1, max_length=100)
    visibility: TraceVisibility
    # Batched consent: one confirmation covering the named selection,
    # required when listing (3_api.md).
    confirm_ownership: bool = False


class BulkVisibilityItem(BaseModel):
    trace_id: str
    status: BulkVisibilityStatus


class BulkVisibilityResponse(BaseModel):
    results: list[BulkVisibilityItem]


class BulkDownloadRequest(BaseModel):
    trace_ids: list[str] = Field(min_length=1, max_length=100)
