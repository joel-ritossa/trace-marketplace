import json
import os
import time
from datetime import UTC, datetime

import zstandard

from trace_sync.files import QuietScanner, discover, upload_bytes, upload_name


def test_discover_recursive_json_and_jsonl(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "s.jsonl").write_text('{"type":"user"}\n')
    (tmp_path / "notes.txt").write_text("not a trace")
    nested = tmp_path / "deep" / "deeper"
    nested.mkdir(parents=True)
    (nested / "b.json").write_text("{}")

    found = discover([tmp_path])
    assert found == [tmp_path / "a.json", nested / "b.json", tmp_path / "s.jsonl"]


def test_discover_since_hours_filters_by_mtime(tmp_path):
    fresh = tmp_path / "fresh.jsonl"
    fresh.write_text("{}")
    stale = tmp_path / "stale.json"
    stale.write_text("{}")
    os.utime(stale, (1, 1))  # epoch-old

    assert discover([tmp_path], since_hours=1) == [fresh]
    assert discover([tmp_path]) == [fresh, stale]


def test_discover_since_hours_skips_stale_session_with_fresh_mtime(tmp_path, capsys):
    now = time.time()

    def session(name, age_hours, compress=False):
        stamp = datetime.fromtimestamp(now - age_hours * 3600, UTC).isoformat()
        raw = f'{{"type":"user","timestamp":"{stamp}"}}\n{{"type":"snapshot"}}\n'.encode()
        path = tmp_path / name
        path.write_bytes(zstandard.ZstdCompressor().compress(raw) if compress else raw)
        return path

    active = session("active.jsonl", 1)
    old = session("old.jsonl", 100)
    old_zst = session("old2.jsonl.zst", 100, compress=True)
    untimed = tmp_path / "untimed.jsonl"
    untimed.write_text('{"type":"user"}\n')

    assert discover([tmp_path], since_hours=24) == [active, untimed]
    assert discover([tmp_path], since_hours=24) == [active, untimed]
    err = capsys.readouterr().err
    assert err.count("old.jsonl → skipped") == 1 and err.count("old2.jsonl.zst → skipped") == 1
    assert old in discover([tmp_path]) and old_zst in discover([tmp_path])


def test_discover_accepts_explicit_file(tmp_path):
    f = tmp_path / "a.json"
    f.write_text("{}")
    assert discover([f]) == [f]
    assert discover([tmp_path / "missing"]) == []


def test_scanner_waits_for_quiet_period(tmp_path):
    f = tmp_path / "grow.json"
    f.write_text("{}")
    mtime = f.stat().st_mtime
    now = [mtime + 10]
    scanner = QuietScanner([tmp_path], quiet_seconds=60, clock=lambda: now[0])

    assert scanner.scan() == []  # modified 10s ago: still active
    now[0] = mtime + 60
    assert scanner.scan() == [f]  # quiet long enough


def test_scanner_skips_synced_until_changed(tmp_path):
    scanner = QuietScanner([tmp_path], quiet_seconds=0)
    f = tmp_path / "t.json"
    f.write_text("{}")
    scanner.mark_synced(f)

    assert scanner.scan() == []  # unchanged since upload
    f.write_text('{"changed": true}')
    os.utime(f, (2, 2))
    assert scanner.scan() == [f]


def _session_with_subagents(tmp_path):
    (tmp_path / "s.jsonl").write_bytes(b'{"p":1}')
    subs = tmp_path / "s" / "subagents"
    subs.mkdir(parents=True)
    (subs / "agent-b.jsonl").write_bytes(b'{"b":1}\n')
    (subs / "agent-a.jsonl").write_bytes(b'{"a":1}')
    (subs / "agent-a.meta.json").write_text("{}")
    return subs


def test_discover_skips_session_companion_dir(tmp_path):
    _session_with_subagents(tmp_path)
    (tmp_path / "s" / "custom-title.json").write_text("{}")
    assert discover([tmp_path]) == [tmp_path / "s.jsonl"]


def test_upload_bytes_bundles_sorted_subagents(tmp_path):
    _session_with_subagents(tmp_path)
    assert upload_bytes(tmp_path / "s.jsonl") == b'{"p":1}\n{"a":1}\n{"b":1}\n'
    plain = tmp_path / "plain.jsonl"
    plain.write_bytes(b"x")
    assert upload_bytes(plain) == b"x"


def test_forked_session_bundles_agents_from_sibling_sessions(tmp_path):
    """A forked session references agents whose transcripts stayed under the
    original session's dir (one nested); each is bundled once, and a change
    to one re-triggers the fork."""
    old = tmp_path / "old" / "subagents"
    old.mkdir(parents=True)
    (tmp_path / "old.jsonl").write_bytes(b'{"o":1}\n')
    (old / "agent-x.jsonl").write_bytes(b'{"toolUseResult":{"agentId":"y"}}\n')
    (old / "agent-y.jsonl").write_bytes(b'{"y":1}\n')
    (old / "agent-z.jsonl").write_bytes(b'{"z":1}\n')  # not referenced
    fork = tmp_path / "fork.jsonl"
    fork.write_bytes(b'{"toolUseResult":{"agentId":"x"}}\n{"toolUseResult":{"agentId":"x"}}\n')

    assert upload_bytes(fork).splitlines()[2:] == [
        b'{"toolUseResult":{"agentId":"y"}}',
        b'{"y":1}',
    ]
    scanner = QuietScanner([fork], quiet_seconds=0)
    scanner.mark_synced(fork)
    (old / "agent-y.jsonl").write_bytes(b'{"y":1}\n{"y":2}\n')
    assert scanner.scan() == [fork]


def test_stat_reflects_subagent_growth(tmp_path):
    subs = _session_with_subagents(tmp_path)
    scanner = QuietScanner([tmp_path], quiet_seconds=0)
    scanner.mark_synced(tmp_path / "s.jsonl")
    assert scanner.scan() == []
    (subs / "agent-a.jsonl").write_bytes(b'{"a":1}\n{"a":2}\n')
    assert scanner.scan() == [tmp_path / "s.jsonl"]


def test_upload_bytes_prunes_session_bookkeeping(tmp_path):
    lines = [
        {"type": "attachment", "attachment": {"type": "skill_listing"}},
        {
            "type": "assistant",
            "timestamp": "t",
            "cwd": "/x",
            "message": {"content": [{"type": "thinking", "thinking": "hm", "signature": "s"}]},
        },
        {
            "type": "user",
            "message": {"content": "hi"},
            "toolUseResult": {"agentId": "a", "isAsync": True, "out": "big"},
            "turnOrigin": "scheduled",
        },
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {}}},
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {
                    "type": "UserMessage",
                    "id": "u",
                    "content": [{"type": "text", "text": "go"}],
                },
            },
        },
    ]
    path = tmp_path / "s.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines))
    assert [json.loads(line) for line in upload_bytes(path).splitlines()] == [
        {
            "type": "assistant",
            "timestamp": "t",
            "message": {"content": [{"type": "thinking", "thinking": "hm"}]},
        },
        {
            "type": "user",
            "message": {"content": "hi"},
            "turnOrigin": "scheduled",
            "toolUseResult": {"agentId": "a", "isAsync": True},
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {"type": "UserMessage", "content": [{"type": "text", "text": "go"}]},
            },
        },
    ]
    other = tmp_path / "other.jsonl"
    other.write_bytes(b'{"kind": "metric"}\n')
    assert upload_bytes(other) == b'{"kind": "metric"}\n'


def test_zst_matches_plain_twin(tmp_path):
    raw = b'{"type":"user","message":{"content":"hi"}}\n'
    plain = tmp_path / "rollout.jsonl"
    plain.write_bytes(raw)
    archived = tmp_path / "archived" / "rollout.jsonl.zst"
    archived.parent.mkdir()
    archived.write_bytes(zstandard.ZstdCompressor().compress(raw))

    assert archived in discover([archived.parent])
    assert upload_bytes(archived) == upload_bytes(plain)
    assert upload_name(archived) == plain.name
