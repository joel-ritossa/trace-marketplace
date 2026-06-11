"""Group decoded spans into normalized trace records per 1_trace-format.md."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.importers.errors import PermanentIngestError
from app.importers.otlp import mapping
from app.importers.otlp.decode import MAX_INT32, DecodedSpan, DecodeResult, decode_payload


@dataclass
class NormalizedSpan:
    source_span_id: str
    source_parent_span_id: str | None
    name: str
    kind: str
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    status: str
    status_message: str | None
    error_type: str | None
    provider: str | None
    model: str | None
    tool_name: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    attributes: dict[str, Any]
    events: list[dict[str, Any]]


@dataclass
class NormalizedTrace:
    source_trace_id: str
    name: str
    status: str
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
    spans: list[NormalizedSpan]


@dataclass
class ImportResult:
    traces: list[NormalizedTrace]
    # {"skipped_spans": N, "samples": [...]} — None when nothing was skipped.
    parse_warnings: dict[str, Any] | None


def _normalize_span(span: DecodedSpan) -> NormalizedSpan:
    input_tokens, output_tokens, total_tokens = mapping.token_counts(span.attributes)
    return NormalizedSpan(
        source_span_id=span.span_id,
        source_parent_span_id=span.parent_span_id,
        name=span.name,
        kind=mapping.span_kind(span.attributes),
        started_at=span.started_at,
        ended_at=span.ended_at,
        duration_ms=span.duration_ms,
        status=span.status,
        status_message=span.status_message,
        error_type=mapping.error_type(span),
        provider=mapping.provider(span.attributes),
        model=mapping.model(span.attributes),
        tool_name=mapping.tool_name(span.attributes),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        attributes=span.attributes,
        events=span.events,
    )


def _dominant(values: list[str | None]) -> str | None:
    """Most frequent non-null value; ties break on first occurrence."""
    present = [v for v in values if v]
    return Counter(present).most_common(1)[0][0] if present else None


def _trace_name(decoded: list[DecodedSpan]) -> str:
    span_ids = {s.span_id for s in decoded}
    roots = [s for s in decoded if not s.parent_span_id or s.parent_span_id not in span_ids]
    candidates = roots or decoded
    return min(candidates, key=lambda s: s.started_at).name


def _build_trace(trace_id: str, decoded: list[DecodedSpan]) -> NormalizedTrace:
    spans = [_normalize_span(s) for s in decoded]
    spans.sort(key=lambda s: (s.started_at, s.source_span_id))
    started_at = min(s.started_at for s in spans)
    ended_at = max(s.ended_at for s in spans)
    error_count = sum(1 for s in spans if s.status == "error")
    return NormalizedTrace(
        source_trace_id=trace_id,
        name=_trace_name(decoded),
        status="error" if error_count else "ok",
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=min(round((ended_at - started_at).total_seconds() * 1000), MAX_INT32),
        span_count=len(spans),
        error_count=error_count,
        provider=_dominant([s.provider for s in spans]),
        model=_dominant([s.model for s in spans]),
        service_name=_dominant([mapping.service_name(s.resource_attributes) for s in decoded]),
        tool_names=sorted({s.tool_name for s in spans if s.tool_name}),
        error_types=sorted({s.error_type for s in spans if s.error_type}),
        spans=spans,
    )


def import_payload(payload: dict[str, Any]) -> ImportResult:
    """Decode and normalize an OTLP JSON payload.

    Raises PermanentIngestError when no valid span exists — a payload that
    can never ingest, so retrying is pointless (1_trace-format.md validation).
    """
    decoded: DecodeResult = decode_payload(payload)
    if not decoded.spans:
        detail = decoded.skip_samples[0] if decoded.skip_samples else "no spans found"
        raise PermanentIngestError(f"Payload contains no valid spans ({detail}).")

    by_trace: dict[str, list[DecodedSpan]] = {}
    for span in decoded.spans:
        by_trace.setdefault(span.trace_id, []).append(span)

    traces = [_build_trace(trace_id, spans) for trace_id, spans in by_trace.items()]
    traces.sort(key=lambda t: (t.started_at, t.source_trace_id))

    parse_warnings = None
    if decoded.skipped:
        parse_warnings = {"skipped_spans": decoded.skipped, "samples": decoded.skip_samples}
    return ImportResult(traces=traces, parse_warnings=parse_warnings)
