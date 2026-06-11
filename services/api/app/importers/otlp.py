"""OTLP JSON (trace signal) importer — 1_trace-format.md.

Slice 1 only claims the format; the upload endpoint stores raw bytes
untouched. Slice 2 adds the parse/normalize pipeline here.
"""

from typing import Any

SOURCE_FORMAT = "otlp_json"


def matches(payload: Any) -> bool:
    """True if decoded JSON looks like OTLP trace JSON."""
    return isinstance(payload, dict) and "resourceSpans" in payload
