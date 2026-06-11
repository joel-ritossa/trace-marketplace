"""OTLP/JSON envelope decoding: structure only, no AI semantics.

Hand-rolled rather than protobuf ParseDict for two reasons (slice-2 plan):
OTLP/JSON deviates from the proto3 JSON mapping (trace/span IDs are hex, not
base64), and ParseDict is all-or-nothing while the spec requires span-level
partial success.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# OTLP status codes; proto3 JSON allows both the int and the enum name.
_STATUS_CODES = {
    0: "unset",
    1: "ok",
    2: "error",
    "STATUS_CODE_UNSET": "unset",
    "STATUS_CODE_OK": "ok",
    "STATUS_CODE_ERROR": "error",
}

MAX_INT32 = 2**31 - 1


@dataclass
class DecodedSpan:
    """One structurally valid OTLP span, attributes fully decoded."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    status: str  # ok | error | unset
    status_message: str | None
    attributes: dict[str, Any]
    events: list[dict[str, Any]]
    resource_attributes: dict[str, Any]


@dataclass
class DecodeResult:
    spans: list[DecodedSpan] = field(default_factory=list)
    skipped: int = 0
    skip_samples: list[str] = field(default_factory=list)

    def skip(self, reason: str) -> None:
        self.skipped += 1
        if len(self.skip_samples) < 5:
            self.skip_samples.append(reason)


def _brief(value: Any) -> str:
    """repr bounded to 64 chars: skip samples flow into error messages, logs,
    and dead letters, and must never embed unbounded payload content."""
    out = repr(value)
    return out if len(out) <= 64 else out[:64] + "…"


def decode_any_value(value: Any) -> Any:
    """Decode a protobuf AnyValue JSON object into a plain Python value."""
    if not isinstance(value, dict):
        return None
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        # int64 is encoded as a JSON string per the proto3 mapping.
        try:
            return int(value["intValue"])
        except (TypeError, ValueError):
            return None
    if "doubleValue" in value:
        return value["doubleValue"]
    if "boolValue" in value:
        return value["boolValue"]
    if "arrayValue" in value:
        values = value["arrayValue"].get("values", [])
        return [decode_any_value(v) for v in values] if isinstance(values, list) else []
    if "kvlistValue" in value:
        return decode_attributes(value["kvlistValue"].get("values", []))
    if "bytesValue" in value:
        return value["bytesValue"]  # keep the base64 string as-is
    return None


def decode_attributes(attributes: Any) -> dict[str, Any]:
    """Decode an OTLP attribute list ([{key, value: AnyValue}]) to a dict."""
    if not isinstance(attributes, list):
        return {}
    out: dict[str, Any] = {}
    for entry in attributes:
        if isinstance(entry, dict) and isinstance(entry.get("key"), str):
            out[entry["key"]] = decode_any_value(entry.get("value"))
    return out


def _decode_id(value: Any, byte_len: int) -> str | None:
    """Normalize a trace/span ID to lowercase hex.

    OTLP/JSON mandates hex, but emitters that serialize via stock protobuf
    JSON produce base64 — accept both.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        if len(value) == byte_len * 2:
            bytes.fromhex(value)
            return value.lower()
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) == byte_len:
            return decoded.hex()
    except (ValueError, binascii.Error):
        pass
    return None


def _decode_time(value: Any) -> datetime | None:
    """Nanosecond unix timestamp (string or int per proto3 JSON) → datetime."""
    try:
        nanos = int(value)
    except (TypeError, ValueError):
        return None
    if nanos <= 0:
        return None
    try:
        return datetime.fromtimestamp(nanos / 1e9, tz=UTC)
    except (ValueError, OverflowError, OSError):  # beyond datetime's range
        return None


def _decode_status(status: Any) -> tuple[str, str | None]:
    if not isinstance(status, dict):
        return "unset", None
    code = _STATUS_CODES.get(status.get("code", 0), "unset")
    message = status.get("message") or None
    return code, message if isinstance(message, str) else None


def _decode_events(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        return []
    out = []
    for event in events:
        if not isinstance(event, dict):
            continue
        time = _decode_time(event.get("timeUnixNano"))
        out.append(
            {
                "name": event.get("name") or "",
                "timestamp": time.isoformat() if time else None,
                "attributes": decode_attributes(event.get("attributes")),
            }
        )
    return out


def _decode_span(
    span: Any, resource_attributes: dict[str, Any], result: DecodeResult
) -> DecodedSpan | None:
    if not isinstance(span, dict):
        result.skip("span entry is not an object")
        return None
    trace_id = _decode_id(span.get("traceId"), 16)
    span_id = _decode_id(span.get("spanId"), 8)
    if trace_id is None or span_id is None:
        result.skip(f"span {_brief(span.get('spanId'))} has a missing or invalid traceId/spanId")
        return None
    started_at = _decode_time(span.get("startTimeUnixNano"))
    ended_at = _decode_time(span.get("endTimeUnixNano"))
    if started_at is None or ended_at is None or ended_at < started_at:
        result.skip(f"span {span_id} has missing or inverted timestamps")
        return None
    status, status_message = _decode_status(span.get("status"))
    return DecodedSpan(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=_decode_id(span.get("parentSpanId"), 8),
        name=span.get("name") or "(unnamed)",
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=min(round((ended_at - started_at).total_seconds() * 1000), MAX_INT32),
        status=status,
        status_message=status_message,
        attributes=decode_attributes(span.get("attributes")),
        events=_decode_events(span.get("events")),
        resource_attributes=resource_attributes,
    )


def decode_payload(payload: dict[str, Any]) -> DecodeResult:
    """Walk resourceSpans → scopeSpans → spans, skipping malformed spans."""
    result = DecodeResult()
    resource_spans = payload.get("resourceSpans")
    if not isinstance(resource_spans, list):
        return result
    for resource_group in resource_spans:
        if not isinstance(resource_group, dict):
            continue
        resource = resource_group.get("resource")
        resource_attributes = (
            decode_attributes(resource.get("attributes")) if isinstance(resource, dict) else {}
        )
        scope_spans = resource_group.get("scopeSpans")
        if not isinstance(scope_spans, list):
            continue
        for scope_group in scope_spans:
            if not isinstance(scope_group, dict):
                continue
            spans = scope_group.get("spans")
            if not isinstance(spans, list):
                continue
            for raw_span in spans:
                decoded = _decode_span(raw_span, resource_attributes, result)
                if decoded is not None:
                    result.spans.append(decoded)
    return result
