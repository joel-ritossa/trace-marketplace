"""Session-JSONL importers (8_session-ingestion.md): detection, per-turn
splitting, deterministic identity, and rejection — over synthetic fixtures."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import importers
from app.importers import otlp, sessions
from app.importers.errors import PermanentIngestError
from app.redaction import OFFLINE_SALT

FIXTURES_DIR = Path(__file__).parents[4] / "fixtures"
ANCHOR = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def import_fixture(name: str, source_format: str) -> otlp.ImportResult:
    records = sessions.parse_records(fixture_bytes(name))
    payload = sessions.convert(source_format, records, session_id=Path(name).stem, anchor=ANCHOR)
    return otlp.import_payload(payload, redaction_salt=OFFLINE_SALT)


# --- detection ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("codex-session.jsonl", "codex_jsonl"),
        ("claude-session.jsonl", "anthropic_jsonl"),
        ("cursor-session.jsonl", "anthropic_jsonl"),
        ("minimal.json", "otlp_json"),
        ("unsupported-log.jsonl", None),
    ],
)
def test_sniff_format(name: str, expected: str | None):
    assert importers.sniff_format(fixture_bytes(name)) == expected


def test_sniff_garbage_is_none():
    assert importers.sniff_format(b"not json at all") is None
    assert importers.sniff_format(b"") is None


# --- per-turn conversion --------------------------------------------------------


def test_codex_splits_turns():
    result = import_fixture("codex-session.jsonl", "codex_jsonl")
    assert len(result.traces) == 2
    first, second = result.traces
    assert first.name == "codex: Add a healthcheck endpoint"
    assert second.name == "codex: Now add a test for it"
    # Each turn: synthetic root + tool + llm.
    assert first.span_count == 3
    assert second.span_count == 3
    assert first.model == "gpt-5.3-codex"
    assert "shell" in first.tool_names
    # Content-borne session id (session_meta.id) keys identity and grouping.
    roots = [s for s in first.spans if s.source_parent_span_id is None]
    assert roots[0].attributes["session.id"] == "sess-codex-demo"
    assert roots[0].attributes["turn.index"] == 0


def test_claude_turns_carry_model_and_tokens():
    result = import_fixture("claude-session.jsonl", "anthropic_jsonl")
    assert len(result.traces) == 2
    first, second = result.traces
    assert first.name == "claude: Rename the config module"
    assert first.model == "claude-fable-5"
    # llm + tool + llm under the root.
    assert first.span_count == 4
    assert first.total_tokens == 120 + 45 + 150 + 20
    assert second.span_count == 2


def test_cursor_synthesizes_timestamps_and_strips_harness_tags():
    result = import_fixture("cursor-session.jsonl", "anthropic_jsonl")
    assert len(result.traces) == 1
    trace = result.traces[0]
    assert trace.name == "cursor: Fix the flaky test"
    root = next(s for s in trace.spans if s.source_parent_span_id is None)
    assert root.attributes["converted.synthesized_timestamps"] is True
    # Synthesized clocks walk back from the anchor: everything lands before it.
    assert trace.ended_at <= ANCHOR


def test_idless_tool_use_emits_in_place():
    """Real Cursor transcripts carry tool_use blocks with no ids and never a
    tool_result: each call must land as a tool span in its own turn, not pool
    at the end of the session."""
    records = [
        {"type": "user", "message": {"role": "user", "content": "first ask"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "reading the file"},
                    {"type": "tool_use", "name": "Read", "input": {"path": "a.py"}},
                ],
            },
        },
        {"type": "user", "message": {"role": "user", "content": "second ask"}},
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
        },
    ]
    assert sessions.detect(records) == "anthropic_jsonl"
    payload = sessions.convert("anthropic_jsonl", records, session_id="s", anchor=ANCHOR)
    result = otlp.import_payload(payload, redaction_salt=OFFLINE_SALT)
    assert len(result.traces) == 2
    first, second = result.traces
    # root + llm + tool in the first turn; the call never leaks into turn 2.
    assert first.span_count == 3
    assert "Read" in first.tool_names
    assert second.span_count == 2
    assert second.tool_names == []


# --- golden-corpus semantics (fixtures/golden/, real-log shapes) ----------------


def golden_fixture(name: str) -> otlp.ImportResult:
    from tests.unit.test_session_golden import convert_session

    return convert_session(name)


def test_claude_skips_sidechains_and_meta_records():
    """Sub-agent transcripts (`isSidechain`) and meta/compaction records
    interleave in real Claude Code session files; none of them are turns."""
    result = golden_fixture("claude-code")
    assert [t.name for t in result.traces] == [
        "claude: Refactor the auth module to use the new session store",
        "claude: Now run the tests",
    ]
    # The sidechain's haiku model must not leak into the main-line traces.
    assert all(t.model == "claude-fable-5" for t in result.traces)


def test_claude_groups_responses_and_counts_cache_tokens():
    result = golden_fixture("claude-code")
    first = result.traces[0]
    llm_spans = [s for s in first.spans if s.kind == "llm"]
    # Three API responses (one split across 3 records, one tool-only) →
    # three llm spans, none duplicated, tool-only response included.
    assert len(llm_spans) == 3
    # input = input_tokens + cache_read + cache_creation, per response:
    # (4+220+1500=1724/85) + (6+1800=1806/60) + (5+1900=1905/30) = 5610.
    assert [s.total_tokens for s in llm_spans] == [1809, 1866, 1935]
    assert first.total_tokens == 5610
    # thinking block lands on its response's llm span.
    assert llm_spans[0].attributes["gen_ai.reasoning"].startswith("The auth module")


def test_codex_turn_usage_reasoning_and_generic_tools():
    result = golden_fixture("codex")
    first, second = result.traces
    # token_count events sum per turn onto the root span: 900+1100+300 etc.
    root = next(s for s in first.spans if s.source_parent_span_id is None)
    assert (root.input_tokens, root.output_tokens, root.total_tokens) == (2300, 220, 2520)
    assert first.total_tokens == 2520
    assert second.total_tokens == 550
    # Reasoning summaries attach to the assistant message that follows them.
    llm = next(s for s in first.spans if s.kind == "llm")
    assert "exponential backoff" in llm.attributes["gen_ai.reasoning"]
    # The typed ask wins over the preamble-laden response_item echo.
    assert llm.attributes["input.value"] == "Add retry logic to the fetch client"
    # tool_search_call pairs via call_id; the output-less trailing call and
    # the id-less web_search_call still emit.
    assert first.tool_names == ["shell", "tool_search"]
    assert second.tool_names == ["shell", "web_search"]
    assert sum(1 for s in second.spans if s.tool_name == "shell") == 2


def test_cursor_multi_block_records_emit_in_order():
    result = golden_fixture("cursor")
    assert [t.name for t in result.traces] == [
        "cursor: Fix the failing CI build",
        "cursor: Also update the README badge",
    ]
    first = result.traces[0]
    # text + 2 idless tool_use in one record, a tool-only record, a closing
    # text record → llm, Read, Grep, Shell, llm in synthesized-clock order.
    assert [(s.kind, s.name) for s in first.spans if s.source_parent_span_id] == [
        ("llm", "assistant turn"),
        ("tool", "Read"),
        ("tool", "Grep"),
        ("tool", "Shell"),
        ("llm", "assistant turn"),
    ]
    assert first.total_tokens is None


def test_conversion_is_deterministic():
    records = sessions.parse_records(fixture_bytes("cursor-session.jsonl"))
    a = sessions.convert("anthropic_jsonl", records, session_id="s", anchor=ANCHOR)
    b = sessions.convert("anthropic_jsonl", records, session_id="s", anchor=ANCHOR)
    assert a == b


# --- rejection ------------------------------------------------------------------


def test_detected_but_empty_session_is_permanent():
    records = [{"type": "session_meta", "payload": {"id": "s", "cwd": "/"}}]
    assert sessions.detect(records) == "codex_jsonl"
    with pytest.raises(PermanentIngestError, match="no convertible turns"):
        sessions.convert("codex_jsonl", records, session_id="s", anchor=ANCHOR)


def test_unsupported_records_detect_none():
    records = sessions.parse_records(fixture_bytes("unsupported-log.jsonl"))
    assert records  # parseable JSONL…
    assert sessions.detect(records) is None  # …but no known schema
