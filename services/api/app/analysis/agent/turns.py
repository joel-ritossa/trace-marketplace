"""Split a session trace into turns: the unit the agent judges."""

import hashlib
from dataclasses import dataclass

from app.analysis.content import first_user_message
from app.analysis.trace_input import SpanInput, TraceInput


@dataclass(frozen=True)
class TurnView:
    index: int
    ask: str | None
    # The turn span; None for the single synthetic turn of a turn-less trace.
    span: SpanInput | None
    # Every descendant, chronological, nested subagent spans included.
    spans: list[SpanInput]
    # source_span_id -> nesting depth below the turn (0 = direct child).
    depth: dict[str, int]
    # Stable across re-ingest; changes when the turn gains or ends spans.
    fingerprint: str


def split(trace: TraceInput) -> list[TurnView]:
    children = _children(trace.spans)
    turn_spans = [s for s in trace.spans if isinstance(s.attributes.get("turn.index"), int)]
    if not turn_spans:
        ids = {s.source_span_id for s in trace.spans}
        roots = [s for s in trace.spans if s.source_parent_span_id not in ids]
        return [_view(trace, children, 0, first_user_message(trace.spans), None, roots)]
    turns = [
        _view(
            trace,
            children,
            span.attributes["turn.index"],
            span.attributes.get("turn.user_message"),
            span,
            children.get(span.source_span_id, []),
        )
        for span in turn_spans
    ]
    return sorted(turns, key=lambda t: t.index)


def _children(spans: list[SpanInput]) -> dict[str, list[SpanInput]]:
    children: dict[str, list[SpanInput]] = {}
    for span in spans:
        if span.source_parent_span_id is not None:
            children.setdefault(span.source_parent_span_id, []).append(span)
    return children


def _view(
    trace: TraceInput,
    children: dict[str, list[SpanInput]],
    index: int,
    ask: str | None,
    span: SpanInput | None,
    tops: list[SpanInput],
) -> TurnView:
    depth: dict[str, int] = {}
    stack = [(s, 0) for s in tops]
    while stack:
        current, level = stack.pop()
        if current.source_span_id in depth:
            continue
        depth[current.source_span_id] = level
        stack.extend((child, level + 1) for child in children.get(current.source_span_id, []))
    spans = [s for s in trace.spans if s.source_span_id in depth]
    ends = [s.ended_at for s in spans] + ([span.ended_at] if span else [])
    digest = hashlib.sha256("\n".join(s.source_span_id for s in spans).encode())
    if ends:
        digest.update(max(ends).isoformat().encode())
    return TurnView(
        index, ask if isinstance(ask, str) else None, span, spans, depth, digest.hexdigest()
    )
