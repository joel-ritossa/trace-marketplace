"""The judge agent's tools: compact text views over the in-memory trace.

Field caps reuse the renderer's: a full llm field is capped at
`conversation_cap_chars`, any other at `tool_field_cap_chars`.
"""

import json
from typing import Any

from app.analysis import content
from app.analysis.agent.turns import TurnView
from app.analysis.config import RendererConfig
from app.analysis.rendering import middle_out
from app.analysis.trace_input import SpanInput, TraceInput

READ_TURN_PAGE_SPANS = 25
PREVIEW_CHARS = 200
SEARCH_MAX_HITS = 20
# list_turns shows every turn, so its asks are short; read_turn has the full one.
LIST_ASK_CHARS = 100

SPECS: list[dict[str, Any]] = [
    {
        "name": "list_turns",
        "description": "Every turn: index, the user's ask, duration, span count, error count.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_turn",
        "description": (
            "One turn's spans in order, one row each: span_id, kind, name/tool, status, "
            "duration, input/output previews. Subagent spans are indented under the call "
            f"that spawned them. Paged, {READ_TURN_PAGE_SPANS} spans per page; the first "
            "page also lists the turn's error spans and subagents (size, errors) with their "
            "offsets. Pass `under` to page through one subagent's own spans."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "turn_index": {"type": "integer"},
                "offset": {"type": "integer", "description": "First span to show (default 0)."},
                "under": {
                    "type": "string",
                    "description": "A span_id: show only the spans nested under it.",
                },
            },
            "required": ["turn_index"],
        },
    },
    {
        "name": "read_span",
        "description": "One span's full input and output.",
        "parameters": {
            "type": "object",
            "properties": {"span_id": {"type": "string"}},
            "required": ["span_id"],
        },
    },
    {
        "name": "search",
        "description": (
            "Spans whose name, input or output contain the text (case-insensitive), "
            f"at most {SEARCH_MAX_HITS} hits."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "turn_index": {"type": "integer", "description": "Limit to one turn."},
            },
            "required": ["query"],
        },
    },
]


def list_turns(turns: list[TurnView]) -> str:
    rows = []
    for turn in turns:
        errors = sum(1 for s in turn.spans if s.status == "error")
        rows.append(
            f"turn {turn.index} ({turn.origin}): {_duration_ms(turn)}ms, {len(turn.spans)} spans, "
            f"{errors} errors | ask: {preview(turn.ask, LIST_ASK_CHARS)}"
        )
    return "\n".join(rows)


def read_turn(
    turns: list[TurnView],
    turn_index: int,
    config: RendererConfig,
    offset: int = 0,
    under: str | None = None,
) -> str:
    turn = _turn(turns, turn_index)
    nested = _nested(turn)
    if under is not None and under not in nested:
        raise ValueError(f"{under!r} is not a subagent call in turn {turn.index}")
    spans = turn.spans if under is None else nested[under]
    scope = f"turn {turn.index} ({turn.origin})" + (f" under {under}" if under else "")
    offset = max(offset, 0)
    if offset and offset >= len(spans):
        raise ValueError(f"{scope} has {len(spans)} spans; offset is past the end")
    page = spans[offset : offset + READ_TURN_PAGE_SPANS]
    lines = [f"{scope}: spans {offset}-{offset + len(page) - 1} of {len(spans)}"]
    if offset == 0:
        if under is None:
            ask = middle_out(turn.ask, config.conversation_cap_chars)[0] if turn.ask else None
            lines.append(f"ask: {ask or '(not recorded)'}")
        lines.extend(
            _index("error spans", [(i, s) for i, s in enumerate(spans) if s.status == "error"])
        )
        subagents = [(i, s) for i, s in enumerate(spans) if s.source_span_id in nested]
        lines.extend(_index("subagents", subagents, nested))
    for span in page:
        indent = "  " * turn.depth[span.source_span_id]
        lines.append(f"{indent}{_row(span)}{_size(nested.get(span.source_span_id))}")
        for label, text in (("in", content.input_text(span)), ("out", content.output_text(span))):
            if text:
                lines.append(f"{indent}  {label}: {preview(text)}")
    rest = len(spans) - offset - len(page)
    if rest > 0:
        more = f", under={under!r}" if under else ""
        lines.append(f"({rest} more: read_turn({turn.index}, offset={offset + len(page)}{more}))")
    return "\n".join(lines)


def read_span(trace: TraceInput, span_id: str, config: RendererConfig) -> str:
    span = next((s for s in trace.spans if s.source_span_id == span_id), None)
    if span is None:
        raise ValueError(f"no span {span_id!r}")
    cap = config.conversation_cap_chars if span.kind == "llm" else config.tool_field_cap_chars
    lines = [_row(span)]
    if span.status_message:
        lines.append(f"status message: {middle_out(span.status_message, cap)[0]}")
    fields = (("input", content.input_text(span)), ("output", content.output_text(span)))
    for label, text in fields:
        if text:
            lines.append(f"{label}: {middle_out(text, cap)[0]}")
    if not any(text for _, text in fields):
        lines.append(f"attrs: {content.attribute_summary(span) or '(none)'}")
    return "\n".join(lines)


def final_message(turn: TurnView, config: RendererConfig) -> str | None:
    """The output of the turn's last llm span: the agent's answer."""
    llm = [s for s in turn.spans if s.kind == "llm" and content.output_text(s)]
    return (
        middle_out(content.output_text(llm[-1]), config.conversation_cap_chars)[0] if llm else None
    )


def _nested(turn: TurnView) -> dict[str, list[SpanInput]]:
    """span_id -> every span nested under it, chronological, for the
    non-llm spans that have any (subagent calls; an llm span's own tool
    calls are not a subagent)."""
    by_id = {s.source_span_id: s for s in turn.spans}
    nested: dict[str, list[SpanInput]] = {}
    for span in turn.spans:
        parent = by_id.get(span.source_parent_span_id or "")
        while parent is not None:
            if parent.kind != "llm":
                nested.setdefault(parent.source_span_id, []).append(span)
            parent = by_id.get(parent.source_parent_span_id or "")
    return nested


def _size(spans: list[SpanInput] | None) -> str:
    if not spans:
        return ""
    llm = sum(1 for s in spans if s.kind == "llm")
    errors = sum(1 for s in spans if s.status == "error")
    return f" [subagent: {len(spans)} spans, {llm} llm, {errors} errors]"


def _index(
    title: str,
    hits: list[tuple[int, SpanInput]],
    nested: dict[str, list[SpanInput]] | None = None,
) -> list[str]:
    if not hits:
        return []
    shown = [
        f"  offset {i}: {_row(s)}{_size((nested or {}).get(s.source_span_id))}"
        for i, s in hits[:SEARCH_MAX_HITS]
    ]
    more = len(hits) - len(shown)
    return [f"{title} ({len(hits)}):", *shown] + ([f"  ({more} more)"] if more else [])


def search(turns: list[TurnView], query: str, turn_index: int | None = None) -> str:
    needle = query.lower()
    if not needle:
        raise ValueError("empty query")
    scope = [_turn(turns, turn_index)] if turn_index is not None else turns
    hits = []
    for turn in scope:
        for span in turn.spans:
            for text in (
                span.name,
                span.tool_name,
                content.input_text(span),
                content.output_text(span),
            ):
                at = text.lower().find(needle) if text else -1
                if at >= 0:
                    start = max(at - PREVIEW_CHARS // 2, 0)
                    snippet = " ".join(text[start : start + PREVIEW_CHARS].split())
                    hits.append(f"turn {turn.index} | {_row(span)} | …{snippet}…")
                    break
    if not hits:
        return "no matches"
    shown = hits[:SEARCH_MAX_HITS]
    more = len(hits) - len(shown)
    return "\n".join(shown + ([f"({more} more hits; narrow the query)"] if more else []))


def run(
    name: str, arguments: str, trace: TraceInput, turns: list[TurnView], config: RendererConfig
) -> str:
    """Dispatch one tool call. Bad calls come back as error text for the
    model to correct, never as exceptions."""
    try:
        args = json.loads(arguments or "{}")
        if name == "list_turns":
            return list_turns(turns)
        if name == "read_turn":
            under = args.get("under")
            return read_turn(
                turns,
                int(args["turn_index"]),
                config,
                int(args.get("offset") or 0),
                None if under is None else str(under),
            )
        if name == "read_span":
            return read_span(trace, str(args["span_id"]), config)
        if name == "search":
            index = args.get("turn_index")
            return search(turns, str(args["query"]), None if index is None else int(index))
        return f"error: unknown tool {name!r}"
    except (ValueError, KeyError, TypeError) as exc:
        return f"error: {exc}"


def _turn(turns: list[TurnView], turn_index: int) -> TurnView:
    for turn in turns:
        if turn.index == turn_index:
            return turn
    raise ValueError(f"no turn {turn_index}")


def _row(span: SpanInput) -> str:
    status = "ERROR" + (f" {span.error_type}" if span.error_type else "")
    status = status if span.status == "error" else span.status
    label = span.tool_name or span.name
    return f"{span.source_span_id} {span.kind} {label} [{status}] {span.duration_ms}ms"


def preview(text: str | None, chars: int = PREVIEW_CHARS) -> str:
    return middle_out(" ".join(text.split()), chars)[0] if text else "-"


def _duration_ms(turn: TurnView) -> int:
    if turn.span is not None:
        return turn.span.duration_ms
    if not turn.spans:
        return 0
    end = max(s.ended_at for s in turn.spans)
    return int((end - turn.spans[0].started_at).total_seconds() * 1000)
