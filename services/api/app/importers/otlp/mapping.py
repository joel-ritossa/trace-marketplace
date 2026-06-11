"""Semantic-convention extraction per 1_trace-format.md.

Fallback chains, in spec order: OTel GenAI → OpenInference → legacy aliases
(OpenLLMetry/traceloop). Constants are pinned here rather than imported from
`opentelemetry-semantic-conventions`, whose gen_ai names live in a private
`_incubating` module with an unstable import path.
"""

from __future__ import annotations

from typing import Any

from app.importers.otlp.decode import MAX_INT32, DecodedSpan

# gen_ai.operation.name → our span kind (well-known values from the GenAI
# semconv registry; see .archive/planning_docs/research/trace-source-schemas.md).
_OPERATION_KINDS = {
    "chat": "llm",
    "text_completion": "llm",
    "generate_content": "llm",
    "execute_tool": "tool",
    "invoke_agent": "agent",
    "create_agent": "agent",
    "invoke_workflow": "chain",
    "embeddings": "embedding",
    "retrieval": "retriever",
}

# openinference.span.kind (uppercase) → our span kind.
_OPENINFERENCE_KINDS = {
    "LLM": "llm",
    "AGENT": "agent",
    "TOOL": "tool",
    "CHAIN": "chain",
    "RETRIEVER": "retriever",
    "EMBEDDING": "embedding",
}

# traceloop.span.kind → our span kind.
_TRACELOOP_KINDS = {
    "llm": "llm",
    "agent": "agent",
    "tool": "tool",
    "workflow": "chain",
    "task": "chain",
}

_PROVIDER_KEYS = ("gen_ai.provider.name", "llm.provider", "llm.system", "gen_ai.system")
_MODEL_KEYS = (
    "gen_ai.request.model",
    "gen_ai.response.model",
    "llm.model_name",
)
_TOOL_NAME_KEYS = ("gen_ai.tool.name", "tool.name")
_INPUT_TOKEN_KEYS = (
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.prompt_tokens",
    "llm.token_count.prompt",
)
_OUTPUT_TOKEN_KEYS = (
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.completion_tokens",
    "llm.token_count.completion",
)
_TOTAL_TOKEN_KEYS = ("gen_ai.usage.total_tokens", "llm.token_count.total")
_ERROR_TYPE_KEYS = ("error.type", "exception.type")


def _first_str(attributes: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = attributes.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _first_int(attributes: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = attributes.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and 0 <= value <= MAX_INT32:
            return int(value)
    return None


def span_kind(attributes: dict[str, Any]) -> str:
    """Normalized AI kind via gen_ai.operation.name → openinference → traceloop."""
    operation = attributes.get("gen_ai.operation.name")
    if isinstance(operation, str) and operation in _OPERATION_KINDS:
        return _OPERATION_KINDS[operation]
    openinference = attributes.get("openinference.span.kind")
    if isinstance(openinference, str) and openinference.upper() in _OPENINFERENCE_KINDS:
        return _OPENINFERENCE_KINDS[openinference.upper()]
    traceloop = attributes.get("traceloop.span.kind")
    if isinstance(traceloop, str) and traceloop.lower() in _TRACELOOP_KINDS:
        return _TRACELOOP_KINDS[traceloop.lower()]
    return "other"


def provider(attributes: dict[str, Any]) -> str | None:
    return _first_str(attributes, _PROVIDER_KEYS)


def model(attributes: dict[str, Any]) -> str | None:
    return _first_str(attributes, _MODEL_KEYS)


def tool_name(attributes: dict[str, Any]) -> str | None:
    return _first_str(attributes, _TOOL_NAME_KEYS)


def token_counts(attributes: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    input_tokens = _first_int(attributes, _INPUT_TOKEN_KEYS)
    output_tokens = _first_int(attributes, _OUTPUT_TOKEN_KEYS)
    total_tokens = _first_int(attributes, _TOTAL_TOKEN_KEYS)
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = min(input_tokens + output_tokens, MAX_INT32)
    return input_tokens, output_tokens, total_tokens


def error_type(span: DecodedSpan) -> str | None:
    """error.type/exception.type from span attributes, else exception events."""
    direct = _first_str(span.attributes, _ERROR_TYPE_KEYS)
    if direct:
        return direct
    for event in span.events:
        from_event = _first_str(event.get("attributes", {}), _ERROR_TYPE_KEYS)
        if from_event:
            return from_event
    return None


def service_name(resource_attributes: dict[str, Any]) -> str | None:
    value = resource_attributes.get("service.name")
    return value if isinstance(value, str) and value else None
