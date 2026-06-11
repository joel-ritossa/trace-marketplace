"""Coding-agent session-log importers (8_session-ingestion.md).

Detects raw JSONL session logs (Codex rollouts, Claude Code / Cursor
transcripts), converts them into a per-turn OTLP payload, and hands off to
the one OTLP normalize path. Pure: bytes/records in, OTLP dict out.
"""

from __future__ import annotations

import json
from datetime import datetime

from app.importers.sessions import anthropic_jsonl, codex
from app.importers.sessions.turns import NANO

SOURCE_FORMAT_CODEX = "codex_jsonl"
SOURCE_FORMAT_ANTHROPIC = "anthropic_jsonl"

# Bump on any change to parsing/turn-splitting/OTLP emission; stored on every
# session-converted trace row for provenance (2_data-model.md).
IMPORTER_VERSION = "1.2.0"

_PARSERS = {
    SOURCE_FORMAT_CODEX: codex.parse,
    SOURCE_FORMAT_ANTHROPIC: anthropic_jsonl.parse,
}


def parse_records(data: bytes, limit: int | None = None) -> list[dict]:
    """JSONL lines decoded to dicts, unparseable lines skipped (tolerant,
    mirroring the span-level partial-success stance of the OTLP decoder)."""
    records: list[dict] = []
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            records.append(obj)
            if limit is not None and len(records) >= limit:
                break
    return records


def detect(records: list[dict]) -> str | None:
    """Source-format id for the records, or None when no schema matches."""
    if not records:
        return None
    if codex.matches(records):
        return SOURCE_FORMAT_CODEX
    if anthropic_jsonl.matches(records):
        return SOURCE_FORMAT_ANTHROPIC
    return None


def convert(source_format: str, records: list[dict], *, session_id: str, anchor: datetime) -> dict:
    """Records → per-turn OTLP payload.

    `session_id` seeds trace identity (overridden by content-borne ids where
    the format carries one); `anchor` ends the synthesized-timestamp walk
    for clockless logs — callers pass the upload's created_at so re-ingest
    is deterministic.

    Raises PermanentIngestError when the session yields no turns.
    """
    builder = _PARSERS[source_format](records, session_id)
    return builder.to_otlp(anchor_ns=int(anchor.timestamp() * NANO))
