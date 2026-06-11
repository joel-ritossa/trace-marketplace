"""Span content extraction with cross-convention fallback chains.

Mirrors the importer's `mapping.py` approach: OTel GenAI conventions first
(`gen_ai.input/output.messages`, tool call attributes), then OpenInference
(`input.value`/`output.value`), then Traceloop legacy (flattened
`gen_ai.prompt.N.*`, `traceloop.entity.*`), then span events. Fail open:
no extractable content returns None and the caller keeps the step skeleton.

Shared by the renderer (judge prompt surface) and the trace→sample adapter
(family 3 / RAGAS).
"""

import json
from typing import Any

from app.analysis.trace_input import SpanInput

_TOOL_INPUT_KEYS = ("gen_ai.tool.call.arguments", "traceloop.entity.input", "input.value")
_TOOL_OUTPUT_KEYS = ("gen_ai.tool.call.result", "traceloop.entity.output", "output.value")
_GENERIC_INPUT_KEYS = ("input.value", "traceloop.entity.input")
_GENERIC_OUTPUT_KEYS = ("output.value", "traceloop.entity.output")

# Attributes whose information already lives in the step skeleton, in
# extracted content, or in normalized span columns (provider/model/tokens)
# — excluded from the fallback attribute summary.
_SUMMARY_EXCLUDED_PREFIXES = (
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.provider.name",
    "gen_ai.system",
    "gen_ai.usage.",
    "gen_ai.tool.name",
    "llm.provider",
    "llm.model_name",
    "llm.system",
    "llm.token_count.",
    "tool.name",
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.prompt",
    "gen_ai.completion",
    "gen_ai.tool.call",
    "gen_ai.tool.definitions",
    "input.value",
    "output.value",
    "traceloop.entity.input",
    "traceloop.entity.output",
    "gen_ai.operation.name",
    "openinference.span.kind",
    "traceloop.span.kind",
)
_SUMMARY_MAX_ATTRS = 8
_SUMMARY_VALUE_CAP = 120
# Scan ceiling for flattened indexed attributes (gen_ai.prompt.N.*,
# retrieval.documents.N.*) — a guard against pathological payloads.
_MAX_INDEXED_ATTRS = 64


def _first_str(attributes: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = attributes.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _parse_json_messages(value: Any) -> list[dict[str, Any]] | None:
    """gen_ai.*.messages: a JSON string (or already-decoded list) of
    {role, parts|content} message objects."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if isinstance(value, list) and all(isinstance(m, dict) for m in value):
        return value
    return None


def _compact(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _part_text(part: Any) -> str | None:
    if isinstance(part, str):
        return part
    if not isinstance(part, dict):
        return None
    kind = part.get("type")
    if kind == "tool_call":
        name = part.get("name", "?")
        return f"[tool_call {name}({_compact(part.get('arguments'))})]"
    if kind == "tool_call_response":
        return f"[tool_result {_compact(part.get('response', part.get('result')))}]"
    content = part.get("content", part.get("text"))
    return _compact(content) if content is not None else None


def message_text(message: dict[str, Any]) -> str | None:
    """One message object → "role: content" (multi-part joined by newlines)."""
    parts = message.get("parts")
    if parts is None:
        parts = [message.get("content")] if message.get("content") is not None else []
    texts = [t for t in (_part_text(p) for p in parts) if t]
    if not texts:
        return None
    role = message.get("role", "unknown")
    return f"{role}: " + "\n".join(texts)


def _messages_text(value: Any) -> str | None:
    messages = _parse_json_messages(value)
    if not messages:
        return None
    lines = [t for t in (message_text(m) for m in messages) if t]
    return "\n".join(lines) if lines else None


def _flattened_messages_text(attributes: dict[str, Any], prefix: str) -> str | None:
    """Traceloop legacy: gen_ai.prompt.0.role / gen_ai.prompt.0.content …"""
    lines = []
    for i in range(_MAX_INDEXED_ATTRS):
        content = attributes.get(f"{prefix}.{i}.content")
        if not isinstance(content, str) or not content:
            break
        role = attributes.get(f"{prefix}.{i}.role", "unknown")
        lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else None


def _event_text(
    span: SpanInput, event_names: tuple[str, ...], attr_keys: tuple[str, ...]
) -> str | None:
    for event in span.events:
        if event.get("name") in event_names:
            text = _first_str(event.get("attributes", {}), attr_keys)
            if text:
                return _messages_text(text) or text
    return None


def input_text(span: SpanInput) -> str | None:
    """Best-effort input content for a span, per the fallback chain."""
    if span.kind == "tool":
        return _first_str(span.attributes, _TOOL_INPUT_KEYS)
    return (
        _messages_text(span.attributes.get("gen_ai.input.messages"))
        or _flattened_messages_text(span.attributes, "gen_ai.prompt")
        or _first_str(span.attributes, _GENERIC_INPUT_KEYS)
        or _event_text(span, ("gen_ai.content.prompt",), ("gen_ai.prompt",))
    )


def output_text(span: SpanInput) -> str | None:
    """Best-effort output content for a span, per the fallback chain."""
    if span.kind == "tool":
        return _first_str(span.attributes, _TOOL_OUTPUT_KEYS)
    return (
        _messages_text(span.attributes.get("gen_ai.output.messages"))
        or _flattened_messages_text(span.attributes, "gen_ai.completion")
        or _first_str(span.attributes, _GENERIC_OUTPUT_KEYS)
        or _event_text(span, ("gen_ai.content.completion", "gen_ai.choice"), ("gen_ai.completion",))
    )


def _user_text_from_messages(value: Any) -> str | None:
    messages = _parse_json_messages(value)
    if not messages:
        return None
    for message in messages:
        if message.get("role") == "user":
            text = message_text(message)
            if text:
                return text.removeprefix("user: ")
    return None


def first_user_message(spans: list[SpanInput]) -> str | None:
    """The earliest user-role message across LLM spans — a rendering must-have
    and the sample adapter's `user_input`."""
    for span in spans:
        if span.kind != "llm":
            continue
        text = _user_text_from_messages(span.attributes.get("gen_ai.input.messages"))
        if text:
            return text
        for i in range(_MAX_INDEXED_ATTRS):
            if span.attributes.get(f"gen_ai.prompt.{i}.role") == "user":
                content = span.attributes.get(f"gen_ai.prompt.{i}.content")
                if isinstance(content, str) and content:
                    return content
    return None


def attribute_summary(span: SpanInput) -> str | None:
    """Compact scalar-attribute summary for spans with no extractable
    input/output — keeps e.g. retrieval counts visible to the judge."""
    items = []
    for key in sorted(span.attributes):
        if any(key.startswith(prefix) for prefix in _SUMMARY_EXCLUDED_PREFIXES):
            continue
        value = span.attributes[key]
        if not isinstance(value, (str, int, float, bool)) or value == "":
            continue
        items.append(f"{key}={str(value)[:_SUMMARY_VALUE_CAP]}")
        if len(items) == _SUMMARY_MAX_ATTRS:
            break
    return "; ".join(items) if items else None


def retrieved_contexts(span: SpanInput) -> list[str]:
    """Document contents from a retriever span: OpenInference indexed
    documents, else the span's output text as one context."""
    contexts = []
    for i in range(_MAX_INDEXED_ATTRS):
        content = span.attributes.get(f"retrieval.documents.{i}.document.content")
        if not isinstance(content, str) or not content:
            break
        contexts.append(content)
    if contexts:
        return contexts
    text = output_text(span)
    return [text] if text else []
