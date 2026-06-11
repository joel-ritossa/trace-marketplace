"""Trace→sample adapter: the family-3 evaluation-sample shape."""

import json

from app.analysis import trace_to_sample
from tests.unit.analysis_factories import load_fixture_trace, make_span, make_trace


def test_full_sample_extraction() -> None:
    spans = [
        make_span(
            0,
            kind="llm",
            attributes={
                "gen_ai.input.messages": json.dumps(
                    [{"role": "user", "parts": [{"type": "text", "content": "weather in paris?"}]}]
                )
            },
        ),
        make_span(
            1,
            kind="retriever",
            attributes={"retrieval.documents.0.document.content": "paris docs"},
        ),
        make_span(
            2,
            kind="tool",
            tool_name="get_weather",
            attributes={
                "gen_ai.tool.call.arguments": '{"location": "Paris"}',
                "gen_ai.tool.call.result": '{"temp": 18}',
            },
        ),
        make_span(
            3,
            kind="llm",
            attributes={
                "gen_ai.output.messages": json.dumps(
                    [{"role": "assistant", "parts": [{"type": "text", "content": "18C, cloudy"}]}]
                )
            },
        ),
    ]
    sample = trace_to_sample(make_trace(spans))
    assert sample.user_input == "weather in paris?"
    assert sample.response == "assistant: 18C, cloudy"
    assert sample.retrieved_contexts == ["paris docs"]
    assert len(sample.tool_calls) == 1
    assert sample.tool_calls[0].name == "get_weather"
    assert sample.tool_calls[0].arguments == '{"location": "Paris"}'
    assert sample.tool_calls[0].result == '{"temp": 18}'


def test_response_comes_from_last_llm_span_with_output() -> None:
    spans = [
        make_span(0, kind="llm", attributes={"output.value": "draft"}),
        make_span(1, kind="llm", attributes={"output.value": "final"}),
        make_span(2, kind="llm"),  # no extractable output → skipped
    ]
    assert trace_to_sample(make_trace(spans)).response == "final"


def test_absent_fields_are_null_or_empty() -> None:
    sample = trace_to_sample(make_trace([make_span(0)]))
    assert sample.user_input is None
    assert sample.response is None
    assert sample.retrieved_contexts == []
    assert sample.tool_calls == []


def test_embedded_tool_calls_reach_the_sample() -> None:
    # Claude Code shape: no tool spans, calls embedded in LLM output messages.
    spans = [
        make_span(
            0,
            kind="llm",
            attributes={
                "gen_ai.output.messages": json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [
                                {
                                    "type": "tool_call",
                                    "id": "call_1",
                                    "name": "search",
                                    "arguments": {"q": "x"},
                                }
                            ],
                        }
                    ]
                )
            },
        ),
        make_span(
            1,
            kind="llm",
            attributes={
                "gen_ai.input.messages": json.dumps(
                    [
                        {
                            "role": "user",
                            "parts": [
                                {"type": "tool_call_response", "id": "call_1", "result": "hit"}
                            ],
                        }
                    ]
                )
            },
        ),
    ]
    sample = trace_to_sample(make_trace(spans))
    assert len(sample.tool_calls) == 1
    assert sample.tool_calls[0].name == "search"
    assert sample.tool_calls[0].arguments == '{"q": "x"}'
    assert sample.tool_calls[0].result == "hit"


def test_fixture_sample() -> None:
    sample = trace_to_sample(load_fixture_trace("agent-session"))
    assert sample.user_input == "What's the weather in Paris? Use the docs if needed."
    assert [t.name for t in sample.tool_calls] == ["get_weather"]
