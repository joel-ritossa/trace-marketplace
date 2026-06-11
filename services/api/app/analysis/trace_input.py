"""Analyzer input: the normalized trace + spans rows (1_analysis.md contract).

One shape regardless of source — built either from DB rows (worker, runner DB
mode) or from the stage-1 importer's output (runner fixture mode), so fixtures
take the exact ingestion path. Analyzers depend on neither asyncpg nor the
importer. Never the raw storage object.
"""

import dataclasses
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.importers.otlp import NormalizedTrace


class SpanInput(BaseModel):
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


class TraceInput(BaseModel):
    # DB id when loaded from the database; None in fixture mode.
    trace_id: str | None = None
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
    # Owner task scope (1_analysis.md Taxonomies): the analysis input the
    # category call's vocabulary is built from. None/empty = unscoped —
    # fixture mode and the offline runner always run unscoped.
    owner_task_categories: list[str] | None = None
    # Chronological (started_at, source_span_id) — both sources guarantee it.
    spans: list[SpanInput]

    @classmethod
    def from_import(cls, trace: NormalizedTrace) -> "TraceInput":
        return cls.model_validate(dataclasses.asdict(trace))

    @classmethod
    def from_db_rows(
        cls, trace_row: Mapping[str, Any], span_rows: list[Mapping[str, Any]]
    ) -> "TraceInput":
        data = {**dict(trace_row), "trace_id": str(trace_row["id"])}
        data["spans"] = [dict(row) for row in span_rows]
        return cls.model_validate(data)
