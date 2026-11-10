"""Session-JSONL importers (8_session-ingestion.md): detection, one-trace-per-session
conversion, deterministic identity, and rejection — over synthetic fixtures."""

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


# --- session conversion --------------------------------------------------------


def test_codex_session_is_one_trace_with_turn_spans():
    result = import_fixture("codex-session.jsonl", "codex_jsonl")
    assert len(result.traces) == 1
    trace = result.traces[0]
    assert trace.name == "codex: Add a healthcheck endpoint"
    # Session root + 2 turn spans + (tool + llm) per turn.
    assert trace.span_count == 7
    assert trace.model == "gpt-5.3-codex"
    assert "shell" in trace.tool_names
    # Content-borne session id (session_meta.id) keys identity and grouping.
    root = next(s for s in trace.spans if s.source_parent_span_id is None)
    assert root.attributes["session.id"] == "sess-codex-demo"
    assert root.attributes["session.turn_count"] == 2
    turns = [s for s in trace.spans if s.source_parent_span_id == root.source_span_id]
    assert [t.name for t in turns] == [
        "turn 1: Add a healthcheck endpoint",
        "turn 2: Now add a test for it",
    ]
    assert [t.attributes["turn.index"] for t in turns] == [0, 1]
    assert turns[1].attributes["turn.user_message"] == "Now add a test for it"


def test_claude_session_carries_model_and_tokens():
    result = import_fixture("claude-session.jsonl", "anthropic_jsonl")
    assert len(result.traces) == 1
    trace = result.traces[0]
    assert trace.name == "claude: Rename the config module"
    assert trace.model == "claude-fable-5"
    # root + 2 turn spans + (llm + tool + llm) + llm.
    assert trace.span_count == 7
    assert trace.total_tokens >= 120 + 45 + 150 + 20


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
    (trace,) = result.traces
    by_id = {s.source_span_id: s for s in trace.spans}
    tool = next(s for s in trace.spans if s.tool_name == "Read")
    # The call stays under its own turn span; it never leaks into turn 2.
    assert by_id[tool.source_parent_span_id].attributes["turn.index"] == 0


def test_claude_harness_messages_do_not_open_turns():
    """Claude Code tags who produced each user record; task notifications are
    model input, not asks. Paste wrapper tags never reach titles."""
    records = [
        {
            "type": "user",
            "origin": {"kind": "human"},
            "message": {
                "content": 'deploy it <pasted_content id="a">log line</pasted_content id="a">'
            },
        },
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "started"}]}},
        {
            "type": "user",
            "origin": {"kind": "task-notification"},
            "message": {"content": "<task-notification>build done</task-notification>"},
        },
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "it is live"}]}},
    ]
    payload = sessions.convert("anthropic_jsonl", records, session_id="s", anchor=ANCHOR)
    (trace,) = otlp.import_payload(payload, redaction_salt=OFFLINE_SALT).traces
    (turn,) = [s for s in trace.spans if "turn.index" in s.attributes]
    assert turn.attributes["turn.user_message"] == "deploy it log line"
    llms = [s for s in trace.spans if s.kind == "llm"]
    assert len(llms) == 2
    assert "build done" in llms[1].attributes["input.value"]


def test_claude_subagent_nests_under_its_spawning_call():
    """Bundled `subagents/*.jsonl` records (isSidechain + agentId) nest under
    the Agent call whose result names that agentId; unlinked ones drop."""

    def rec(kind, ts, content, **extra):
        message = {"role": kind, "content": content}
        return {
            "type": kind,
            "timestamp": f"2026-01-01T00:00:{ts:02d}Z",
            "message": message,
            **extra,
        }

    spawn = {"type": "tool_use", "id": "t1", "name": "Agent", "input": {"prompt": "dig"}}
    result = {"type": "tool_result", "tool_use_id": "t1", "content": "launched"}
    records = [
        rec("user", 1, "investigate"),
        rec("assistant", 2, [spawn]),
        rec("user", 3, [result], toolUseResult={"agentId": "a1"}),
        rec("assistant", 9, [{"type": "text", "text": "summary"}]),
        rec("user", 4, "dig", isSidechain=True, agentId="a1"),
        rec("assistant", 5, [{"type": "text", "text": "found it"}], isSidechain=True, agentId="a1"),
        rec("user", 6, "orphan", isSidechain=True, agentId="zz"),
        rec("assistant", 7, [{"type": "text", "text": "lost"}], isSidechain=True, agentId="zz"),
    ]
    payload = sessions.convert("anthropic_jsonl", records, session_id="s", anchor=ANCHOR)
    (trace,) = otlp.import_payload(payload, redaction_salt=OFFLINE_SALT).traces
    by_id = {s.source_span_id: s for s in trace.spans}
    found = next(s for s in trace.spans if s.attributes.get("output.value") == "found it")
    assert by_id[found.source_parent_span_id].tool_name == "Agent"
    assert found.attributes["input.value"] == "dig"
    assert not any(s.attributes.get("output.value") == "lost" for s in trace.spans)
    assert len([s for s in trace.spans if "turn.index" in s.attributes]) == 1


def user(content, **extra) -> dict:
    return {"type": "user", "message": {"role": "user", "content": content}, **extra}


def reply(text: str) -> dict:
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


HUMAN = {"origin": {"kind": "human"}}


def turn_asks(records: list[dict], source_format: str = "anthropic_jsonl") -> list[tuple]:
    payload = sessions.convert(source_format, records, session_id="s", anchor=ANCHOR)
    (trace,) = otlp.import_payload(payload, redaction_salt=OFFLINE_SALT).traces
    turns = sorted(
        (s for s in trace.spans if "turn.index" in s.attributes),
        key=lambda s: s.attributes["turn.index"],
    )
    return [(t.attributes.get("turn.user_message"), t.attributes.get("turn.origin")) for t in turns]


def test_wrappers_read_as_typed():
    """Skill slash commands read as `/name args`; harness context blocks
    prepended to a human ask are dropped."""
    command = (
        "<command-message>search</command-message>\n<command-name>/search</command-name>\n"
        "<command-args>find calls</command-args>"
    )
    reminder = "<system-reminder>Linked sessions now: a</system-reminder>\n\nship it"
    records = [user(command, **HUMAN), reply("a"), user(reminder, **HUMAN), reply("b")]
    assert turn_asks(records) == [("/search find calls", "human"), ("ship it", "human")]


def test_outside_events_open_automated_turns():
    """Untagged records in an origin-tagged log and peer messages from other
    sessions open `automated` turns; subagent hand-backs and side-session
    reports (the agent's own delegated work) only feed the model."""
    records = [
        user("fix the build", **HUMAN),
        reply("on it"),
        user("<ci-monitor-event>PR #1 failed lint</ci-monitor-event>"),
        reply("fixed lint"),
        user(
            "Another Claude session sent a message:\n<agent-message>report</agent-message>",
            isMeta=True,
            origin={"kind": "peer"},
        ),
        reply("noted"),
        user(
            "<system-reminder>The session you started finished.</system-reminder>\n"
            "<side-sessions-event>Sessions idle.</side-sessions-event>"
        ),
        reply("reported"),
        user(
            '<cross-session-message from="x">merge it</cross-session-message>',
            isMeta=True,
            origin={"kind": "peer"},
        ),
        reply("merged"),
    ]
    assert turn_asks(records) == [
        ("fix the build", "human"),
        ("CI event: PR #1 failed lint", "automated"),
        ("Session message: merge it", "automated"),
    ]


def test_non_asks_never_open_turns():
    """Interrupt markers and local slash commands never open or title a turn."""
    records = [
        user("first", **HUMAN),
        reply("working"),
        user("[Request interrupted by user]"),
        user("<command-name>/model</command-name>\n<command-args>m</command-args>"),
        user("<local-command-stdout>Set model to m</local-command-stdout>"),
        user("please", **HUMAN),
        reply("done"),
    ]
    assert turn_asks(records) == [("first", "human"), ("please", "human")]


def test_resumed_log_takes_the_first_prompt():
    """A log that resumes after compaction starts with activity; the summary
    is not an ask, so the first prompt that follows titles that turn."""
    records = [
        user("Summary of the earlier conversation", isCompactSummary=True),
        reply("earlier answer"),
        user("continue", **HUMAN),
        reply("continuing"),
    ]
    assert turn_asks(records) == [("continue", "human")]


def test_codex_item_asks_and_agent_tasks():
    """Newer rollouts carry the ask only as a UserMessage item; a task from a
    parent agent opens an automated turn, a child's report does not."""

    def item(text):
        content = [{"type": "text", "text": text}]
        return {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {"type": "UserMessage", "content": content},
            },
        }

    def agent(author, recipient, text):
        content = [{"type": "input_text", "text": text}]
        payload = {
            "type": "agent_message",
            "author": author,
            "recipient": recipient,
            "content": content,
        }
        return {"type": "response_item", "payload": payload}

    def answer(text):
        content = [{"type": "output_text", "text": text}]
        return {
            "type": "response_item",
            "payload": {"type": "message", "role": "assistant", "content": content},
        }

    records = [
        agent("/root", "/root/worker", "review the diff"),
        answer("reviewing"),
        agent("/root/worker/helper", "/root/worker", "helper done"),
        answer("reviewed"),
        item("thanks, now merge"),
        answer("merged"),
    ]
    assert turn_asks(records, "codex_jsonl") == [
        ("review the diff", "automated"),
        ("thanks, now merge", "human"),
    ]


def test_missing_end_stays_inside_its_turn():
    """A response's synthesized end runs to the next event of its own turn,
    never across an idle gap to the next ask."""

    def rec(kind, ts, text):
        return {"type": kind, "timestamp": ts, "message": {"role": kind, "content": text}}

    records = [
        rec("user", "2026-01-01T00:00:00Z", "first"),
        rec("assistant", "2026-01-01T00:00:05Z", "answer"),
        rec("user", "2026-01-04T00:00:00Z", "three days later"),
        rec("assistant", "2026-01-04T00:00:02Z", "again"),
    ]
    payload = sessions.convert("anthropic_jsonl", records, session_id="s", anchor=ANCHOR)
    (trace,) = otlp.import_payload(payload, redaction_salt=OFFLINE_SALT).traces
    first = next(s for s in trace.spans if s.attributes.get("output.value") == "answer")
    assert first.duration_ms <= 1000


# --- golden-corpus semantics (fixtures/golden/, real-log shapes) ----------------


def golden_fixture(name: str) -> otlp.ImportResult:
    from tests.unit.test_session_golden import convert_session

    return convert_session(name)


def turn_spans(trace, turn_index: int) -> tuple[object, list]:
    """The turn span and its event spans, in order."""
    turn = next(s for s in trace.spans if s.attributes.get("turn.index") == turn_index)
    return turn, [s for s in trace.spans if s.source_parent_span_id == turn.source_span_id]


def test_claude_skips_sidechains_and_meta_records():
    """Sub-agent transcripts (`isSidechain`) and meta/compaction records
    interleave in real Claude Code session files; none of them are turns."""
    result = golden_fixture("claude-code")
    (trace,) = result.traces
    assert trace.name == "claude: Refactor the auth module to use the new session store"
    assert [s.name for s in trace.spans if "turn.index" in s.attributes] == [
        "turn 1: Refactor the auth module to use the new session store",
        "turn 2: Now run the tests",
    ]
    # The sidechain's haiku model must not leak into the main-line trace.
    assert trace.model == "claude-fable-5"


def test_claude_groups_responses_and_counts_cache_tokens():
    result = golden_fixture("claude-code")
    first, events = turn_spans(result.traces[0], 0)
    llm_spans = [s for s in events if s.kind == "llm"]
    # Three API responses (one split across 3 records, one tool-only) →
    # three llm spans, none duplicated, tool-only response included.
    assert len(llm_spans) == 3
    # input = input_tokens + cache_read + cache_creation, per response:
    # (4+220+1500=1724/85) + (6+1800=1806/60) + (5+1900=1905/30) = 5610.
    assert [s.total_tokens for s in llm_spans] == [1809, 1866, 1935]
    assert sum(s.total_tokens for s in llm_spans) == 5610
    # thinking block lands on its response's llm span.
    assert llm_spans[0].attributes["gen_ai.reasoning"].startswith("The auth module")


def test_codex_turn_usage_reasoning_and_generic_tools():
    result = golden_fixture("codex")
    trace = result.traces[0]
    (first, first_events), (second, second_events) = (turn_spans(trace, i) for i in (0, 1))
    # token_count events sum per turn onto the turn span: 900+1100+300 etc.
    assert (first.input_tokens, first.output_tokens, first.total_tokens) == (2300, 220, 2520)
    assert second.total_tokens == 550
    # The root carries no usage, so trace totals count each turn once.
    assert trace.total_tokens == 2520 + 550
    # Reasoning summaries attach to the assistant message that follows them.
    llm = next(s for s in first_events if s.kind == "llm")
    assert "exponential backoff" in llm.attributes["gen_ai.reasoning"]
    # The typed ask wins over the preamble-laden response_item echo.
    assert llm.attributes["input.value"] == "Add retry logic to the fetch client"
    # tool_search_call pairs via call_id; the output-less trailing call and
    # the id-less web_search_call still emit.
    assert [s.tool_name for s in first_events if s.kind == "tool"] == ["shell", "tool_search"]
    assert sorted({s.tool_name for s in second_events if s.kind == "tool"}) == [
        "shell",
        "web_search",
    ]
    assert sum(1 for s in second_events if s.tool_name == "shell") == 2


def test_cursor_multi_block_records_emit_in_order():
    result = golden_fixture("cursor")
    (trace,) = result.traces
    assert trace.name == "cursor: Fix the failing CI build"
    first, events = turn_spans(trace, 0)
    # text + 2 idless tool_use in one record, a tool-only record, a closing
    # text record → llm, Read, Grep, Shell, llm in synthesized-clock order.
    assert [(s.kind, s.name) for s in events] == [
        ("llm", "assistant turn"),
        ("tool", "Read"),
        ("tool", "Grep"),
        ("tool", "Shell"),
        ("llm", "assistant turn"),
    ]
    assert trace.total_tokens is None


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
