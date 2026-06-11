"""OTLP JSON (trace signal) importer — 1_trace-format.md.

`matches` claims a payload for this format (used by the upload endpoint);
`import_payload` parses it into normalized trace/span records (used by the
ingest task). Pure: JSON in, records out.
"""

from typing import Any

from app.importers.otlp.normalize import (
    ImportResult as ImportResult,
)
from app.importers.otlp.normalize import (
    NormalizedSpan as NormalizedSpan,
)
from app.importers.otlp.normalize import (
    NormalizedTrace as NormalizedTrace,
)
from app.importers.otlp.normalize import (
    import_payload as import_payload,
)

SOURCE_FORMAT = "otlp_json"

# Bump on any change to decode/mapping/normalize output; stored on every
# trace row for provenance (2_data-model.md). 1.1.0: redaction scrub
# (7_redaction.md) — content fields carry placeholders. 1.2.0: trace
# total_tokens + bare-id name fallback (A2).
IMPORTER_VERSION = "1.2.0"


def matches(payload: Any) -> bool:
    """True if decoded JSON looks like OTLP trace JSON."""
    return isinstance(payload, dict) and "resourceSpans" in payload
