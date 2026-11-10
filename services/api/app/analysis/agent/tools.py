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
            f"that spawned them. Paged, {READ_TURN_PAGE_SPANS} spans per page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "turn_index": {"type": "integer"},
                "offset": {"type": "integer", "description": "First span to show (default 0)."},
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
            f"turn {turn.index}: {_duration_ms(turn)}ms, {len(turn.spans)} spans, "
            f"{errors} errors | ask: {preview(turn.ask)}"
        )
    return "\n".join(rows)


def read_turn(
    turns: list[TurnView], turn_index: int, config: RendererConfig, offset: int = 0
) -> str:
    turn = _turn(turns, turn_index)
    offset = max(offset, 0)
    page = turn.spans[offset : offset + READ_TURN_PAGE_SPANS]
    lines = [f"turn {turn.index}: spans {offset}-{offset + len(page) - 1} of {len(turn.spans)}"]
    if offset == 0 and turn.ask:
        lines.append(f"ask: {middle_out(turn.ask, config.conversation_cap_chars)[0]}")
    for span in page:
        indent = "  " * turn.depth[span.source_span_id]
        lines.append(f"{indent}{_row(span)}")
        for label, text in (("in", content.input_text(span)), ("out", content.output_text(span))):
            if text:
                lines.append(f"{indent}  {label}: {preview(text)}")
    rest = len(turn.spans) - offset - len(page)
    if rest > 0:
        lines.append(f"({rest} more: read_turn({turn.index}, offset={offset + len(page)}))")
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
            return read_turn(turns, int(args["turn_index"]), config, int(args.get("offset") or 0))
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


def preview(text: str | None) -> str:
    return middle_out(" ".join(text.split()), PREVIEW_CHARS)[0] if text else "-"


def _duration_ms(turn: TurnView) -> int:
    if turn.span is not None:
        return turn.span.duration_ms
    if not turn.spans:
        return 0
    end = max(s.ended_at for s in turn.spans)
    return int((end - turn.spans[0].started_at).total_seconds() * 1000)
