"""Trace→sample adapter: the evaluation-sample shape consumed by family 3
(RAGAS collections + critics, B3). Extracted from `gen_ai.*` span content via
`content.py` — the renderer and this adapter are the one owned integration
surface (1_analysis.md Trace rendering)."""

from pydantic import BaseModel

from app.analysis import content
from app.analysis.trace_input import TraceInput


class ToolCall(BaseModel):
    name: str
    arguments: str | None = None
    result: str | None = None


class TraceSample(BaseModel):
    user_input: str | None
    response: str | None
    retrieved_contexts: list[str]
    tool_calls: list[ToolCall]


def trace_to_sample(trace: TraceInput) -> TraceSample:
    response = None
    for span in reversed(trace.spans):
        if span.kind == "llm":
            response = content.output_text(span)
            if response:
                break

    contexts: list[str] = []
    tool_calls: list[ToolCall] = []
    for span in trace.spans:
        if span.kind == "retriever":
            contexts.extend(content.retrieved_contexts(span))
        elif span.kind == "tool":
            tool_calls.append(
                ToolCall(
                    name=span.tool_name or span.name,
                    arguments=content.input_text(span),
                    result=content.output_text(span),
                )
            )

    return TraceSample(
        user_input=content.first_user_message(trace.spans),
        response=response,
        retrieved_contexts=contexts,
        tool_calls=tool_calls,
    )
