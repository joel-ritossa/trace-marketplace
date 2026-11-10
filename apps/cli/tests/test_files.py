import json
import os

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
            "toolUseResult": {"agentId": "a", "out": "big"},
        },
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {}}},
    ]
    path = tmp_path / "s.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines))
    assert [json.loads(line) for line in upload_bytes(path).splitlines()] == [
        {
            "type": "assistant",
            "timestamp": "t",
            "message": {"content": [{"type": "thinking", "thinking": "hm"}]},
        },
        {"type": "user", "message": {"content": "hi"}, "toolUseResult": {"agentId": "a"}},
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
