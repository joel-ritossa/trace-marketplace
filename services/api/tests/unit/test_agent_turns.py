from datetime import timedelta

from app.analysis.agent.turns import split
from app.redaction import scrub_text
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


def test_fingerprint_ignores_timestamps_and_tracks_changes() -> None:
    before = [t.fingerprint for t in split(session())]
    shifted = session()
    shifted.spans[:] = [
        s.model_copy(
            update={
                "started_at": s.started_at + timedelta(days=1),
                "ended_at": s.ended_at + timedelta(days=1),
            }
        )
        for s in shifted.spans
    ]
    assert [t.fingerprint for t in split(shifted)] == before

    grown = session()
    grown.spans.append(_span(8, 6, kind="llm"))
    assert [t.fingerprint for t in split(grown)][1] != before[1]
    failed = session()
    failed.spans[2] = failed.spans[2].model_copy(update={"status": "error"})
    assert [t.fingerprint == b for t, b in zip(split(failed), before, strict=True)] == [False, True]


def test_split_ignores_bool_and_duplicate_indices_and_reads_origin() -> None:
    trace = session()
    automated = trace.spans[6].model_copy(
        update={"attributes": {**trace.spans[6].attributes, "turn.origin": "automated"}}
    )
    trace.spans[6] = automated
    trace.spans.append(_span(9, 0, kind="agent", attributes={"turn.index": 1}))
    trace.spans.append(_span(10, 0, kind="agent", attributes={"turn.index": True}))
    turns = split(trace)
    assert [(t.index, t.origin) for t in turns] == [(0, "human"), (1, "automated")]
    assert turns[1].span.source_span_id == f"{6:016x}"


def _with_output(text: str):
    trace = session()
    span = trace.spans[7]
    trace.spans[7] = span.model_copy(update={"attributes": {"gen_ai.tool.call.result": text}})
    return split(trace)[1].fingerprint


def test_fingerprint_ignores_the_upload_salt_but_not_content() -> None:
    raw = "mailed jane@example.com the key"
    one, two = scrub_text(raw, "salt-a")[0], scrub_text(raw, "salt-b")[0]
    assert one != two
    assert _with_output(one) == _with_output(two)
    assert _with_output(one) != _with_output(scrub_text(raw + " twice", "salt-a")[0])


def test_read_turn_sizes_subagents_and_pages_under_one() -> None:
    from app.analysis.agent import tools
    from app.analysis.config import AnalysisSettings, RendererConfig

    turns, config = split(session()), RendererConfig.from_settings(AnalysisSettings())
    page = tools.read_turn(turns, 0, config)
    assert "subagents (1):" in page and "[subagent: 2 spans, 1 llm, 0 errors]" in page
    nested = tools.read_turn(turns, 0, config, under=f"{3:016x}")
    assert "spans 0-1 of 2" in nested and f"{2:016x}" not in nested
