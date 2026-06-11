from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

# Mirrors the spans.kind / spans.status check constraints and the frontend
# types (apps/web/src/lib/api/traces.ts).
SpanKind = Literal["llm", "agent", "tool", "chain", "retriever", "embedding", "other"]
SpanStatus = Literal["ok", "error", "unset"]


class SpanListItem(BaseModel):
    """Tree-building fields only; attributes/events live on the per-span
    endpoint so list payloads stay bounded (3_api.md)."""

    span_id: str
    source_span_id: str
    source_parent_span_id: str | None
    name: str
    kind: SpanKind
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    status: SpanStatus
    status_message: str | None
    error_type: str | None
    provider: str | None
    model: str | None
    tool_name: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class SpanListResponse(BaseModel):
    spans: list[SpanListItem]
    total: int


class SpanDetailResponse(SpanListItem):
    attributes: dict[str, Any]
    events: list[dict[str, Any]]
