"""Renderer behavior: budget tiering, per-field caps, elision, must-haves."""

import json

from app.analysis import RendererConfig, render_trace
from app.analysis.rendering import _middle_out
from tests.unit.analysis_factories import make_span, make_trace


def _llm_attrs(user_text: str, assistant_text: str) -> dict:
    return {
        "gen_ai.input.messages": json.dumps(
            [{"role": "user", "parts": [{"type": "text", "content": user_text}]}]
        ),
        "gen_ai.output.messages": json.dumps(
            [{"role": "assistant", "parts": [{"type": "text", "content": assistant_text}]}]
        ),
    }


def _busy_trace(n: int = 40):
    """n spans with chunky content; an LLM opener and one mid-trace error."""
    spans = [make_span(0, kind="llm", attributes=_llm_attrs("find the answer", "ok " * 200))]
    for i in range(1, n - 1):
        status = "error" if i == 5 else "ok"
        spans.append(
            make_span(
                i,
                kind="tool",
                status=status,
                tool_name=f"tool_{i}",
                attributes={
                    "gen_ai.tool.call.arguments": f'{{"q": "{i}"}}',
                    "gen_ai.tool.call.result": "x" * 500,
                },
            )
        )
    spans.append(make_span(n - 1, kind="llm", attributes=_llm_attrs("", "final answer")))
    return make_trace(spans)


TIGHT = RendererConfig(
    budget_chars=4_000, final_steps=4, tool_field_cap_chars=200, conversation_cap_chars=400
)


def test_tight_budget_keeps_must_haves_and_stays_within_budget() -> None:
    trace = _busy_trace()
    rendered = render_trace(trace, TIGHT)

    assert rendered.total_chars <= TIGHT.budget_chars
    assert rendered.rendering_truncated
    assert rendered.elided_step_count > 0

    contents = [m.content for m in rendered.messages]
    # First user message survives as a dedicated user message.
    assert any(m.role == "user" and "find the answer" in m.content for m in rendered.messages)
    # The error span (step 6) and the final K steps are never elided.
    assert any("[step 6/40]" in c and "error, BoomError" in c for c in contents)
    for index in range(37, 41):
        assert any(f"[step {index}/40]" in c for c in contents)
    # Elided runs are explicitly marked.
    assert any("elided (" in c for c in contents)


def test_loose_budget_renders_everything_unmarked() -> None:
    trace = _busy_trace(n=6)
    config = RendererConfig(
        budget_chars=100_000,
        final_steps=8,
        tool_field_cap_chars=2_000,
        conversation_cap_chars=8_000,
    )
    rendered = render_trace(trace, config)
    assert not rendered.rendering_truncated
    assert rendered.elided_step_count == 0
    assert rendered.step_count == 6


def test_per_field_cap_truncates_middle_out() -> None:
    rendered = render_trace(_busy_trace(n=6), TIGHT)
    tool_steps = [m.content for m in rendered.messages if m.role == "tool"]
    capped = [c for c in tool_steps if "chars truncated" in c]
    assert capped  # the 500-char tool results exceed the 200-char field cap
    # Middle-out: head and tail of the original content both survive.
    assert any(c.count("x") > 0 and "…[" in c for c in capped)


def test_skeleton_floor_when_must_haves_exceed_budget() -> None:
    # Every span is an error → all mandatory; tiny budget forces cap halvings
    # down to the skeleton-only floor, then trims oldest steps to fit.
    spans = [
        make_span(
            i,
            kind="tool",
            status="error",
            attributes={"gen_ai.tool.call.result": "y" * 1000},
        )
        for i in range(50)
    ]
    config = RendererConfig(
        budget_chars=2_000,
        final_steps=4,
        tool_field_cap_chars=500,
        conversation_cap_chars=500,
    )
    rendered = render_trace(make_trace(spans), config)
    assert rendered.total_chars <= config.budget_chars
    assert rendered.rendering_truncated
    contents = [m.content for m in rendered.messages]
    # The final K steps always survive.
    for index in range(47, 51):
        assert any(f"[step {index}/50]" in c for c in contents)


def test_middle_out_marker_counts_removed_chars() -> None:
    text = "a" * 100 + "b" * 100
    capped, cut = _middle_out(text, 100)
    assert cut
    assert len(capped) <= 100
    assert capped.startswith("a") and capped.endswith("b")
    assert "chars truncated" in capped
    same, uncut = _middle_out("short", 100)
    assert same == "short" and not uncut
