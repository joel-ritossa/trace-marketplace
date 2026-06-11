"""Family-1 signals: loop detection, action extraction, recovery,
truncation, failure_suspected, and fail-open nulls — all synthetic."""

import json
from typing import Any

from app.analysis.config import AnalysisSettings
from app.analysis.content import ToolAction, tool_actions
from app.analysis.signals import detect_loop, run_signals
from app.analysis.trace_input import SpanInput
from tests.unit.analysis_factories import load_fixture_trace, make_span, make_trace

SETTINGS = AnalysisSettings(loop_n=3)


def tool_span(i: int, tool: str, args: str, result: str | None = None) -> SpanInput:
    attributes: dict[str, Any] = {"gen_ai.tool.call.arguments": args}
    if result is not None:
        attributes["gen_ai.tool.call.result"] = result
    return make_span(i, kind="tool", tool_name=tool, attributes=attributes)


def llm_span(
    i: int,
    *,
    output_parts: list[dict[str, Any]] | None = None,
    input_parts: list[dict[str, Any]] | None = None,
    attributes: dict[str, Any] | None = None,
) -> SpanInput:
    attrs: dict[str, Any] = dict(attributes or {})
    if output_parts is not None:
        attrs["gen_ai.output.messages"] = json.dumps([{"role": "assistant", "parts": output_parts}])
    if input_parts is not None:
        attrs["gen_ai.input.messages"] = json.dumps([{"role": "user", "parts": input_parts}])
    return make_span(i, kind="llm", attributes=attrs)


def action(name: str, args: Any, result: str | None = None) -> ToolAction:
    return ToolAction(name, args, result)


# --- loop detection over actions ---


def test_exact_repeat_at_threshold() -> None:
    actions = [action("search", '{"q": "x"}')] * 3
    assert detect_loop(actions, 3) == "exact_repeat"


def test_exact_repeat_below_threshold_is_no_loop() -> None:
    actions = [action("search", '{"q": "x"}')] * 2
    assert detect_loop(actions, 3) is None


def test_repeats_must_be_consecutive() -> None:
    actions = [
        action("search", '{"q": "x"}'),
        action("search", '{"q": "x"}'),
        action("fetch", '{"url": "a"}'),
        action("search", '{"q": "x"}'),
    ]
    assert detect_loop(actions, 3) is None


def test_signature_invariant_to_json_key_order() -> None:
    actions = [
        action("search", '{"a": 1, "b": 2}'),
        action("search", '{"b": 2, "a": 1}'),
        action("search", {"b": 2, "a": 1}),  # already-decoded args hash the same
    ]
    assert detect_loop(actions, 3) == "exact_repeat"


def test_cycle_period_two() -> None:
    actions = [action("a", "1"), action("b", "2")] * 2
    assert detect_loop(actions, 3) == "cycle"


def test_cycle_period_four() -> None:
    cycle = [action(n, "1") for n in "abcd"]
    assert detect_loop(cycle * 2, 3) == "cycle"


def test_period_above_four_is_no_cycle() -> None:
    cycle = [action(n, "1") for n in "abcde"]
    assert detect_loop(cycle * 2, 3) is None


def test_uniform_run_below_repeat_threshold_is_not_a_cycle() -> None:
    actions = [action("a", "1", result=str(i)) for i in range(4)]
    assert detect_loop(actions, 5) is None


def test_stagnation_same_result_different_args() -> None:
    actions = [action("search", f'{{"q": "{i}"}}', result="no results") for i in range(3)]
    assert detect_loop(actions, 3) == "stagnation"


def test_stagnation_needs_results() -> None:
    actions = [action("search", f'{{"q": "{i}"}}') for i in range(3)]
    assert detect_loop(actions, 3) is None


# --- action extraction ---


def test_actions_from_tool_spans() -> None:
    spans = [tool_span(i, "search", '{"q": "x"}', result="hit") for i in range(2)]
    actions = tool_actions(spans)
    assert actions == [ToolAction("search", '{"q": "x"}', "hit")] * 2


def test_embedded_actions_from_output_messages_with_paired_results() -> None:
    call = {"type": "tool_call", "id": "call_1", "name": "search", "arguments": {"q": "x"}}
    response = {"type": "tool_call_response", "id": "call_1", "result": "no results"}
    spans = [llm_span(0, output_parts=[call]), llm_span(1, input_parts=[response])]
    assert tool_actions(spans) == [ToolAction("search", {"q": "x"}, "no results")]


def test_input_message_tool_calls_are_history_not_actions() -> None:
    call = {"type": "tool_call", "id": "call_1", "name": "search", "arguments": {}}
    spans = [llm_span(0, input_parts=[call])]
    assert tool_actions(spans) == []


def test_tool_spans_win_over_embedded_calls() -> None:
    call = {"type": "tool_call", "id": "call_1", "name": "search", "arguments": {}}
    spans = [llm_span(0, output_parts=[call]), tool_span(1, "fetch", '{"url": "a"}')]
    assert [a.name for a in tool_actions(spans)] == ["fetch"]


def test_flattened_traceloop_tool_calls() -> None:
    attrs = {
        "gen_ai.completion.0.role": "assistant",
        "gen_ai.completion.0.tool_calls.0.name": "search",
        "gen_ai.completion.0.tool_calls.0.arguments": '{"q": "x"}',
    }
    spans = [llm_span(0, attributes=attrs)]
    assert tool_actions(spans) == [ToolAction("search", '{"q": "x"}', None)]


def test_structured_calls_suppress_flattened_duplicates() -> None:
    # One span encoding the same call both ways must count it once.
    call = {"type": "tool_call", "id": "call_1", "name": "search", "arguments": {"q": "x"}}
    attrs = {
        "gen_ai.completion.0.tool_calls.0.name": "search",
        "gen_ai.completion.0.tool_calls.0.arguments": '{"q": "x"}',
    }
    spans = [llm_span(0, output_parts=[call], attributes=attrs)]
    assert len(tool_actions(spans)) == 1


def test_payloadless_responses_have_no_result_and_no_stagnation() -> None:
    spans = []
    for i in range(3):
        call = {"type": "tool_call", "id": f"call_{i}", "name": "ack", "arguments": {"n": i}}
        response = {"type": "tool_call_response", "id": f"call_{i}"}
        spans.append(llm_span(2 * i, output_parts=[call]))
        spans.append(llm_span(2 * i + 1, input_parts=[response]))
    actions = tool_actions(spans)
    assert all(a.result is None for a in actions)
    assert detect_loop(actions, 3) is None


# --- recovered_from_error ---


async def test_recovered_error_retried_tool_then_normal_end() -> None:
    spans = [
        tool_span(0, "fetch", '{"url": "a"}'),
        make_span(
            1,
            kind="tool",
            tool_name="fetch",
            status="error",
            attributes={"gen_ai.tool.call.arguments": '{"url": "b"}'},
        ),
        tool_span(2, "fetch", '{"url": "b"}'),
        make_span(3, kind="llm"),
    ]
    result = await run_signals(make_trace(spans), SETTINGS)
    assert result.recovered_from_error is True
    # Recovered, no loop, no truncation evidence: no failure opinion even
    # though the trace status is error.
    assert result.failure_suspected is False


async def test_error_without_retry_is_not_recovered() -> None:
    spans = [make_span(0, kind="llm", status="error"), make_span(1, kind="llm", name="other")]
    result = await run_signals(make_trace(spans), SETTINGS)
    assert result.recovered_from_error is False
    assert result.failure_suspected is True


async def test_error_at_trace_end_is_not_recovered() -> None:
    spans = [make_span(0, name="step"), make_span(1, name="step", status="error")]
    result = await run_signals(make_trace(spans), SETTINGS)
    assert result.recovered_from_error is False


async def test_no_errors_means_no_recovery_opinion() -> None:
    result = await run_signals(make_trace([make_span(0)]), SETTINGS)
    assert result.recovered_from_error is None


async def test_recovered_llm_error_by_same_name_retry() -> None:
    spans = [
        make_span(0, kind="llm", name="chat", status="error"),
        make_span(1, kind="llm", name="chat"),
    ]
    result = await run_signals(make_trace(spans), SETTINGS)
    assert result.recovered_from_error is True


# --- truncation_suspected ---


async def test_truncation_from_finish_reason_length() -> None:
    spans = [llm_span(0, attributes={"gen_ai.response.finish_reasons": ["length"]})]
    result = await run_signals(make_trace(spans), SETTINGS)
    assert result.truncation_suspected is True
    assert result.failure_suspected is True


async def test_benign_finish_reason_is_not_truncation() -> None:
    spans = [llm_span(0, attributes={"gen_ai.response.finish_reasons": ["tool_calls"]})]
    result = await run_signals(make_trace(spans), SETTINGS)
    assert result.truncation_suspected is False


async def test_json_encoded_finish_reasons_decode() -> None:
    spans = [llm_span(0, attributes={"gen_ai.response.finish_reasons": '["MAX_TOKENS"]'})]
    result = await run_signals(make_trace(spans), SETTINGS)
    assert result.truncation_suspected is True


async def test_only_final_llm_span_counts_for_truncation() -> None:
    spans = [
        llm_span(0, attributes={"gen_ai.response.finish_reasons": ["length"]}),
        llm_span(1, attributes={"gen_ai.response.finish_reasons": ["stop"]}),
    ]
    result = await run_signals(make_trace(spans), SETTINGS)
    assert result.truncation_suspected is False


async def test_output_at_max_tokens_is_truncation() -> None:
    span = llm_span(0, attributes={"gen_ai.request.max_tokens": 100})
    span = span.model_copy(update={"output_tokens": 100})
    result = await run_signals(make_trace([span]), SETTINGS)
    assert result.truncation_suspected is True


async def test_no_finish_evidence_is_null() -> None:
    result = await run_signals(make_trace([llm_span(0)]), SETTINGS)
    assert result.truncation_suspected is None


async def test_boolean_max_tokens_is_not_a_limit() -> None:
    span = llm_span(0, attributes={"gen_ai.request.max_tokens": True})
    span = span.model_copy(update={"output_tokens": 100})
    result = await run_signals(make_trace([span]), SETTINGS)
    assert result.truncation_suspected is None


async def test_flattened_finish_reason_on_later_completion() -> None:
    attrs = {
        "gen_ai.completion.0.content": "partial",  # no finish_reason on 0
        "gen_ai.completion.1.finish_reason": "length",
    }
    result = await run_signals(make_trace([llm_span(0, attributes=attrs)]), SETTINGS)
    assert result.truncation_suspected is True


# --- the analyzer as a whole ---


async def test_loop_sets_failure_suspected_even_on_ok_trace() -> None:
    spans = [tool_span(i, "search", '{"q": "x"}') for i in range(3)]
    result = await run_signals(make_trace(spans), SETTINGS)
    assert result.has_retry_loop is True
    assert result.loop_kind == "exact_repeat"
    assert result.failure_suspected is True


async def test_no_actions_fails_open() -> None:
    result = await run_signals(make_trace([make_span(0)]), SETTINGS)
    assert result.has_retry_loop is None
    assert result.loop_kind is None
    assert result.tool_call_count == 0
    assert result.llm_call_count == 0
    assert result.failure_suspected is False


async def test_counts_embedded_calls_as_tool_calls() -> None:
    calls = [
        {"type": "tool_call", "id": f"call_{i}", "name": "search", "arguments": {"q": i}}
        for i in range(2)
    ]
    spans = [llm_span(0, output_parts=calls), llm_span(1)]
    result = await run_signals(make_trace(spans), SETTINGS)
    assert result.llm_call_count == 2
    assert result.tool_call_count == 2
    assert result.has_retry_loop is False


async def test_loop_n_is_tunable() -> None:
    spans = [tool_span(i, "search", '{"q": "x"}') for i in range(2)]
    relaxed = await run_signals(make_trace(spans), AnalysisSettings(loop_n=2))
    strict = await run_signals(make_trace(spans), AnalysisSettings(loop_n=3))
    assert relaxed.has_retry_loop is True
    assert strict.has_retry_loop is False


async def test_signals_are_deterministic() -> None:
    trace = load_fixture_trace("agent-session")
    first = await run_signals(trace, SETTINGS)
    second = await run_signals(trace, SETTINGS)
    assert first.model_dump_json() == second.model_dump_json()
