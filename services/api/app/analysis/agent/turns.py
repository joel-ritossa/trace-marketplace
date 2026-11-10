"""Split a session trace into turns, and a turn into its linked subagents:
the units the agent judges."""

import hashlib
from dataclasses import dataclass

from app.analysis.content import first_user_message, input_text, output_text
from app.analysis.trace_input import SpanInput, TraceInput
from app.redaction import unsalted


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
    # Stable across re-uploads of unchanged content: no timestamps (clockless
    # logs get synthesized ones) and no salted redaction digests; changes
    # when a span is added or its status or content changes.
    fingerprint: str
    # "human" (a person's ask) or "automated" (a CI, scheduled or peer
    # event that started the work cycle); from the turn span's `turn.origin`.
    origin: str = "human"
    # Set on a subagent's view (`subagents`): the spawn span's id. `span` is
    # then the spawn span, `ask` its brief and `spans` everything below it.
    under: str | None = None


def split(trace: TraceInput) -> list[TurnView]:
    children = _children(trace.spans)
    # First span per index wins; booleans are not indices.
    by_index: dict[int, SpanInput] = {}
    for s in trace.spans:
        index = s.attributes.get("turn.index")
        if isinstance(index, int) and not isinstance(index, bool):
            by_index.setdefault(index, s)
    turn_spans = list(by_index.values())
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


def subagents(trace: TraceInput, turn: TurnView) -> list[TurnView]:
    """The turn's linked subagents, each as the view of its own spans. Linked
    as in queries/spans.overview: a spawn span with `subagent.id` and at
    least one child."""
    children = _children(trace.spans)
    return [
        _view(
            trace, children, turn.index, input_text(s), s, children[s.source_span_id], subagent=True
        )
        for s in turn.spans
        if s.attributes.get("subagent.id") is not None and children.get(s.source_span_id)
    ]


def deepest_first(subagents: list[TurnView]) -> list[list[TurnView]]:
    """Subagents grouped by nesting depth, deepest level first: each comes
    after every subagent nested in it."""
    levels: dict[int, list[TurnView]] = {}
    for view in subagents:
        depth = sum(1 for other in subagents if view.under in other.depth)
        levels.setdefault(depth, []).append(view)
    return [levels[depth] for depth in sorted(levels, reverse=True)]


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
    subagent: bool = False,
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
    digest = hashlib.sha256()
    for s in ([span] if span else []) + spans:
        text = unsalted(f"{input_text(s) or ''}\0{output_text(s) or ''}")
        signal = hashlib.sha256(text.encode()).hexdigest()
        digest.update(f"{s.source_span_id} {s.status} {signal}\n".encode())
    origin = "automated" if span and span.attributes.get("turn.origin") == "automated" else "human"
    return TurnView(
        index,
        ask if isinstance(ask, str) else None,
        span,
        spans,
        depth,
        digest.hexdigest(),
        origin,
        span.source_span_id if subagent and span else None,
    )
