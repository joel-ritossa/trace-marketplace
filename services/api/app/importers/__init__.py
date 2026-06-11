"""Source-format importers: one module per supported trace format.

An importer owns everything format-specific: recognizing a payload (used by
the upload endpoint) and — from Slice 2 — parsing it into normalized
trace/span rows. Importers are pure (bytes/JSON in, rows out); they never
touch HTTP or the database.
"""

from __future__ import annotations

import json


def sniff_format(data: bytes) -> str | None:
    """Cheap format id from raw bytes (8_session-ingestion.md): 'otlp_json',
    a session format, or None. Shared by the upload endpoint (reject early
    with a readable 422) and the ingest task (route to the converter) so the
    two can never disagree."""
    from app.importers import otlp, sessions

    try:
        payload = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        payload = None
    if isinstance(payload, dict) and otlp.matches(payload):
        return otlp.SOURCE_FORMAT
    # Not OTLP: try JSONL session schemas. A single-record transcript parses
    # as whole-document JSON above, so this path must run for dicts too.
    return sessions.detect(sessions.parse_records(data, limit=50))
