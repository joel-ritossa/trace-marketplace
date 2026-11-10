from datetime import timedelta

from app.analysis.agent.turns import split
from tests.unit.analysis_factories import make_span, make_trace


def _span(i: int, parent: int | None, **kwargs):
    span = make_span(i, **kwargs)
    return span.model_copy(
        update={"source_parent_span_id": None if parent is None else f"{parent:016x}"}
    )


def _turn(i: int, index: int, ask: str):
    return _span(i, 0, kind="agent", attributes={"turn.index": index, "turn.user_message": ask})


def session():
    return make_trace(
        [
            _span(0, None, kind="agent"),
            _turn(1, 0, "first ask"),
            _span(2, 1, kind="llm"),
            _span(3, 1, kind="tool", tool_name="Agent"),
            _span(4, 3, kind="llm"),
            _span(5, 4, kind="tool", tool_name="Bash"),
            _turn(6, 1, "second ask"),
            _span(7, 6, kind="tool", status="error"),
        ]
    )


def test_splits_turns_with_nested_subagent_spans() -> None:
    first, second = split(session())
    assert (first.index, first.ask, first.span.source_span_id) == (0, "first ask", f"{1:016x}")
    assert [s.source_span_id for s in first.spans] == [f"{i:016x}" for i in (2, 3, 4, 5)]
    assert [first.depth[s.source_span_id] for s in first.spans] == [0, 0, 1, 2]
    assert second.index == 1 and [s.source_span_id for s in second.spans] == [f"{7:016x}"]


def test_turnless_trace_is_one_turn_with_every_span() -> None:
    trace = make_trace([_span(0, None, kind="agent"), _span(1, 0, kind="llm"), _span(2, None)])
    (turn,) = split(trace)
    assert turn.index == 0 and turn.span is None
    assert len(turn.spans) == 3
    assert turn.depth == {f"{0:016x}": 0, f"{1:016x}": 1, f"{2:016x}": 0}


def test_fingerprint_is_stable_and_tracks_growth() -> None:
    before = split(session())
    assert [t.fingerprint for t in split(session())] == [t.fingerprint for t in before]

    grown = session()
    late = _span(8, 6, kind="llm")
    grown.spans.append(late.model_copy(update={"ended_at": late.ended_at + timedelta(hours=1)}))
    after = split(grown)
    assert after[0].fingerprint == before[0].fingerprint
    assert after[1].fingerprint != before[1].fingerprint
