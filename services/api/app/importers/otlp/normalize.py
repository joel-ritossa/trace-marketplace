"""Group decoded spans into normalized trace records per 1_trace-format.md."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app import redaction
from app.importers.errors import PermanentIngestError
from app.importers.otlp import mapping
from app.importers.otlp.decode import MAX_INT32, DecodedSpan, DecodeResult, decode_payload


@dataclass
class NormalizedSpan:
    """Content fields (name, status_message, attributes, events) are scrubbed
    per 7_redaction.md; the raw_* copies feed the owner-only span_raw table."""

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
    raw_attributes: dict[str, Any]
    raw_events: list[dict[str, Any]]
    raw_status_message: str | None


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
    total_tokens: int | None
    spans: list[NormalizedSpan]


@dataclass
class ImportResult:
    traces: list[NormalizedTrace]
    # {"skipped_spans": N, "samples": [...]} — None when nothing was skipped.
    parse_warnings: dict[str, Any] | None


def _normalize_span(span: DecodedSpan, salt: str) -> NormalizedSpan:
    input_tokens, output_tokens, total_tokens = mapping.token_counts(span.attributes)
    # Derivations (kind, provider, error_type, tokens) read the raw
    # attributes: scrubbing must never change what a span *is*, only what
    # its content shows. Key contexts ('name', 'message') match the
    # artifact walk in redaction.scrub_otlp_payload so both representations
    # yield identical placeholders.
    scrubbed_name, _ = redaction.scrub_text(span.name, salt, key="name")
    scrubbed_message = span.status_message
    if scrubbed_message is not None:
        scrubbed_message, _ = redaction.scrub_text(scrubbed_message, salt, key="message")
    scrubbed_attributes, _ = redaction.scrub_tree(span.attributes, salt)
    scrubbed_events, _ = redaction.scrub_tree(span.events, salt)
    return NormalizedSpan(
        source_span_id=span.span_id,
        source_parent_span_id=span.parent_span_id,
        name=scrubbed_name,
        kind=mapping.span_kind(span.attributes),
        started_at=span.started_at,
        ended_at=span.ended_at,
        duration_ms=span.duration_ms,
        status=span.status,
        status_message=scrubbed_message,
        error_type=mapping.error_type(span),
        provider=mapping.provider(span.attributes),
        model=mapping.model(span.attributes),
        tool_name=mapping.tool_name(span.attributes),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        attributes=scrubbed_attributes,
        events=scrubbed_events,
        raw_attributes=span.attributes,
        raw_events=span.events,
        raw_status_message=span.status_message,
    )


def _dominant(values: list[str | None]) -> str | None:
    """Most frequent non-null value; ties break on first occurrence."""
    present = [v for v in values if v]
    return Counter(present).most_common(1)[0][0] if present else None


# Hex/uuid-shaped (with optional dashes) or purely numeric: a "name" that is
# really an id, useless for scanning a list (2_data-model.md trace-name check).
_BARE_ID_RE = re.compile(r"^(?:[0-9a-fA-F-]{16,}|\d+)$")


def _trace_name(decoded: list[DecodedSpan], fallback: str | None) -> str:
    span_ids = {s.span_id for s in decoded}
    roots = [s for s in decoded if not s.parent_span_id or s.parent_span_id not in span_ids]
    candidates = roots or decoded
    name = min(candidates, key=lambda s: s.started_at).name.strip()
    if fallback and (not name or _BARE_ID_RE.match(name)):
        return fallback
    return name


def _build_trace(
    trace_id: str, decoded: list[DecodedSpan], salt: str, fallback_name: str | None
) -> NormalizedTrace:
    spans = [_normalize_span(s, salt) for s in decoded]
    spans.sort(key=lambda s: (s.started_at, s.source_span_id))
    started_at = min(s.started_at for s in spans)
    ended_at = max(s.ended_at for s in spans)
    error_count = sum(1 for s in spans if s.status == "error")
    # Same key context as span names: a trace named after its root span gets
    # the identical placeholder. Single representation — no raw trace name.
    name, _ = redaction.scrub_text(_trace_name(decoded, fallback_name), salt, key="name")
    span_tokens = [s.total_tokens for s in spans if s.total_tokens is not None]
    return NormalizedTrace(
        source_trace_id=trace_id,
        name=name,
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
        total_tokens=min(sum(span_tokens), MAX_INT32) if span_tokens else None,
        spans=spans,
    )


def import_payload(
    payload: dict[str, Any], *, redaction_salt: str, fallback_name: str | None = None
) -> ImportResult:
    """Decode, normalize, and scrub an OTLP JSON payload.

    Raises PermanentIngestError when no valid span exists — a payload that
    can never ingest, so retrying is pointless (1_trace-format.md validation).

    `redaction_salt` keys the placeholder HMAC (7_redaction.md). Required so
    no call path can silently skip scrubbing; offline callers without an
    upload row pass redaction.OFFLINE_SALT.

    `fallback_name` (the source filename, sans extension) replaces a derived
    trace name that is empty or a bare id — names must stay scannable at
    list volume (2_data-model.md trace-name check).
    """
    decoded: DecodeResult = decode_payload(payload)
    if not decoded.spans:
        detail = decoded.skip_samples[0] if decoded.skip_samples else "no spans found"
        raise PermanentIngestError(f"Payload contains no valid spans ({detail}).")

    by_trace: dict[str, list[DecodedSpan]] = {}
    for span in decoded.spans:
        by_trace.setdefault(span.trace_id, []).append(span)

    traces = [
        _build_trace(trace_id, spans, redaction_salt, fallback_name)
        for trace_id, spans in by_trace.items()
    ]
    traces.sort(key=lambda t: (t.started_at, t.source_trace_id))

    parse_warnings = None
    if decoded.skipped:
        parse_warnings = {"skipped_spans": decoded.skipped, "samples": decoded.skip_samples}
    return ImportResult(traces=traces, parse_warnings=parse_warnings)
