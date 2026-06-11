from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# Mirrors the traces.status check constraint and the frontend types
# (apps/web/src/lib/api/traces.ts).
TraceStatus = Literal["ok", "error"]

TraceSort = Literal["created_at", "duration_ms", "span_count"]

# Slice 2 serves owner-only reads; marketplace/acquired scopes are Slice 3.
TraceScope = Literal["mine"]


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
    owner_display_name: str | None
    # Always false until acquisitions land in Slice 3.
    acquired: bool


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
    source_format: str
    importer_version: str
    created_at: datetime
    # Caller's relationship to the trace (3_api.md). Owner-only this slice:
    # is_owner is always true and acquired always false until Slice 3.
    is_owner: bool
    acquired: bool
    can_download: bool
