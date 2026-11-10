"""Skill uses and the subagent tree from the span skeleton
(queries/spans)."""

from datetime import UTC, datetime, timedelta

from app.queries.spans import overview, subagent_summary


def skill_uses(spans):
    return overview(spans)[0]


def subagent_tree(spans):
    return overview(spans)[1]


T0 = datetime(2026, 1, 1, tzinfo=UTC)


def span(span_id, parent=None, turn=None, skill=None, source=None, **extra) -> dict:
    return {
        "span_id": span_id,
        "parent_id": parent,
        "turn_index": turn,
        "skill_name": skill,
        "skill_source": source,
        "kind": "other",
        "status": "ok",
        "started_at": T0,
        "ended_at": T0,
        "input_tokens": None,
        "output_tokens": None,
        "subagent_id": None,
        "description": None,
        "type": None,
        "model": None,
        "background": None,
        **extra,
    }


def test_skill_uses_resolve_their_turn() -> None:
    spans = [
        span("root"),
        span("t0", "root", turn=0, skill="review", source="user"),  # slash command
        span("llm", "t0"),
        span("tool", "llm", skill="pdf", source="agent"),  # Skill tool, nested
        span("t1", "root", turn=1),
        span("sub", "t1"),
        span("tool2", "sub", skill="pdf", source="agent"),
        span("orphan", "root", skill="x"),  # outside any turn
    ]
    assert skill_uses(spans) == [
        {"name": "review", "source": "user", "turn_index": 0, "span_id": "t0"},
        {"name": "pdf", "source": "agent", "turn_index": 0, "span_id": "tool"},
        {"name": "pdf", "source": "agent", "turn_index": 1, "span_id": "tool2"},
        {"name": "x", "source": None, "turn_index": None, "span_id": "orphan"},
    ]


def test_turnless_trace_is_turn_zero() -> None:
    spans = [span("a"), span("b", "a", skill="pdf", source="agent")]
    assert skill_uses(spans)[0]["turn_index"] == 0


def test_parent_cycle_terminates() -> None:
    spans = [span("t", turn=0), span("a", "b", skill="s"), span("b", "a")]
    assert skill_uses(spans)[0]["turn_index"] is None


def test_subagent_tree_totals_and_nesting() -> None:
    later = T0 + timedelta(seconds=9)
    spans = [
        span("t0", turn=0),
        span(
            "spawn", "t0", kind="tool", subagent_id="a1", description="explore", background="true"
        ),
        span("llm", "spawn", kind="llm", input_tokens=10, output_tokens=2),
        span("inner", "spawn", kind="tool", subagent_id="a2", type="general"),
        span("deep", "inner", kind="llm", status="error", ended_at=later, input_tokens=5),
        span("t1", turn=1),
        span("lost", "t1", kind="tool", description="no transcript"),
    ]
    outer, nested, lost = subagent_tree(spans)
    assert (outer["span_id"], outer["parent_span_id"], outer["depth"]) == ("spawn", None, 0)
    assert (outer["turn_index"], outer["background"], outer["linked"]) == (0, True, True)
    # Everything under it, nested subagent included; own stream excludes it.
    assert (outer["span_count"], outer["own_span_count"]) == (3, 2)
    assert (outer["llm_calls"], outer["tool_calls"], outer["error_count"]) == (2, 1, 1)
    assert (outer["input_tokens"], outer["output_tokens"], outer["ended_at"]) == (15, 2, later)
    assert (nested["parent_span_id"], nested["depth"], nested["span_count"]) == ("spawn", 1, 1)
    assert (lost["linked"], lost["turn_index"], lost["background"]) == (False, 1, None)
    assert subagent_summary([outer, nested, lost]) == {"count": 3, "turns": 2, "max_depth": 1}
    assert subagent_summary([]) == {"count": 0, "turns": 0, "max_depth": 0}
