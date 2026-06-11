"""Builders for analysis-package unit tests: synthetic TraceInput/SpanInput
and fixture loading through the real importer path."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.analysis import TraceInput
from app.analysis.trace_input import SpanInput
from app.importers import otlp
from app.redaction import OFFLINE_SALT

FIXTURES_DIR = Path(__file__).parents[4] / "fixtures"

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def load_fixture_trace(name: str, index: int = 0) -> TraceInput:
    payload = json.loads((FIXTURES_DIR / f"{name}.json").read_text())
    return TraceInput.from_import(
        otlp.import_payload(payload, redaction_salt=OFFLINE_SALT).traces[index]
    )


def make_span(
    i: int,
    *,
    kind: str = "other",
    status: str = "ok",
    attributes: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    tool_name: str | None = None,
    name: str | None = None,
) -> SpanInput:
    return SpanInput(
        source_span_id=f"{i:016x}",
        source_parent_span_id=None,
        name=name or f"span-{i}",
        kind=kind,
        started_at=_T0 + timedelta(seconds=i),
        ended_at=_T0 + timedelta(seconds=i + 1),
        duration_ms=1000,
        status=status,
        status_message=None,
        error_type="BoomError" if status == "error" else None,
        provider=None,
        model=None,
        tool_name=tool_name,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        attributes=attributes or {},
        events=events or [],
    )


def make_trace(
    spans: list[SpanInput], owner_task_categories: list[str] | None = None
) -> TraceInput:
    error_count = sum(1 for s in spans if s.status == "error")
    return TraceInput(
        owner_task_categories=owner_task_categories,
        source_trace_id="t" * 32,
        name="synthetic-trace",
        status="error" if error_count else "ok",
        started_at=spans[0].started_at,
        ended_at=spans[-1].ended_at,
        duration_ms=len(spans) * 1000,
        span_count=len(spans),
        error_count=error_count,
        provider=None,
        model=None,
        service_name=None,
        tool_names=sorted({s.tool_name for s in spans if s.tool_name}),
        error_types=sorted({s.error_type for s in spans if s.error_type}),
        spans=spans,
    )
