"""Content extraction: per-convention fallback chains, fail-open behavior."""

import json

from app.analysis import content
from tests.unit.analysis_factories import make_span


def test_genai_messages_attribute_wins() -> None:
    span = make_span(
        0,
        kind="llm",
        attributes={
            "gen_ai.input.messages": json.dumps(
                [{"role": "user", "parts": [{"type": "text", "content": "hello"}]}]
            ),
            "input.value": "should not be used",
        },
    )
    assert content.input_text(span) == "user: hello"


def test_tool_call_parts_render_compactly() -> None:
    span = make_span(
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
                                "id": "c1",
                                "name": "search",
                                "arguments": {"q": "x"},
                            }
                        ],
                    }
                ]
            )
        },
    )
    assert content.output_text(span) == 'assistant: [tool_call search({"q": "x"})]'


def test_traceloop_flattened_prompt_fallback() -> None:
    span = make_span(
        0,
        kind="llm",
        attributes={
            "gen_ai.prompt.0.role": "system",
            "gen_ai.prompt.0.content": "be helpful",
            "gen_ai.prompt.1.role": "user",
            "gen_ai.prompt.1.content": "hi",
        },
    )
    assert content.input_text(span) == "system: be helpful\nuser: hi"


def test_openinference_value_fallback() -> None:
    span = make_span(0, kind="llm", attributes={"output.value": "raw response text"})
    assert content.output_text(span) == "raw response text"


def test_event_fallback() -> None:
    span = make_span(
        0,
        kind="llm",
        events=[{"name": "gen_ai.content.prompt", "attributes": {"gen_ai.prompt": "from event"}}],
    )
    assert content.input_text(span) == "from event"


def test_tool_span_uses_tool_call_attributes() -> None:
    span = make_span(
        0,
        kind="tool",
        attributes={
            "gen_ai.tool.call.arguments": '{"q": 1}',
            "gen_ai.tool.call.result": "result!",
        },
    )
    assert content.input_text(span) == '{"q": 1}'
    assert content.output_text(span) == "result!"


def test_no_content_fails_open_to_none() -> None:
    span = make_span(0, kind="llm")
    assert content.input_text(span) is None
    assert content.output_text(span) is None


def test_first_user_message_across_spans() -> None:
    spans = [
        make_span(0, kind="tool"),
        make_span(
            1,
            kind="llm",
            attributes={
                "gen_ai.input.messages": json.dumps(
                    [
                        {"role": "system", "parts": [{"type": "text", "content": "rules"}]},
                        {"role": "user", "parts": [{"type": "text", "content": "the goal"}]},
                    ]
                )
            },
        ),
    ]
    assert content.first_user_message(spans) == "the goal"
    assert content.first_user_message([make_span(0)]) is None


def test_attribute_summary_skips_noise_and_caps() -> None:
    span = make_span(
        0,
        attributes={
            "retrieval.documents": 3,
            "gen_ai.usage.input_tokens": 12,  # promoted column → excluded
            "session.id": "abc",
            "nested": {"not": "scalar"},  # non-scalar → excluded
        },
    )
    assert content.attribute_summary(span) == "retrieval.documents=3; session.id=abc"


def test_retrieved_contexts_indexed_documents_then_output() -> None:
    indexed = make_span(
        0,
        kind="retriever",
        attributes={
            "retrieval.documents.0.document.content": "doc a",
            "retrieval.documents.1.document.content": "doc b",
        },
    )
    assert content.retrieved_contexts(indexed) == ["doc a", "doc b"]

    plain = make_span(1, kind="retriever", attributes={"output.value": "one doc"})
    assert content.retrieved_contexts(plain) == ["one doc"]

    assert content.retrieved_contexts(make_span(2, kind="retriever")) == []
