from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

# Mirrors the traces.status check constraint and the frontend types
# (apps/web/src/lib/api/traces.ts).
TraceStatus = Literal["ok", "error"]

TraceSort = Literal["created_at", "duration_ms", "span_count"]

TraceScope = Literal["mine", "marketplace", "acquired"]

TraceVisibility = Literal["private", "listed"]


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


class TraceListResponse(BaseModel):
    traces: list[TraceListItem]
    total: int


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
