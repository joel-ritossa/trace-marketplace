import os

from trace_sync.files import StabilityScanner, discover, upload_bytes


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


def test_scanner_waits_for_stability(tmp_path):
    scanner = StabilityScanner([tmp_path])
    f = tmp_path / "grow.json"
    f.write_text("{")

    assert scanner.scan() == []  # first sighting: pending, not ready
    f.write_text('{"resourceSpans": []}')  # grew since last tick
    os.utime(f, (1, 1))  # force a distinct mtime
    assert scanner.scan() == []  # changed again: still pending
    assert scanner.scan() == [f]  # stable across two ticks: ready


def test_scanner_skips_synced_until_changed(tmp_path):
    scanner = StabilityScanner([tmp_path])
    f = tmp_path / "t.json"
    f.write_text("{}")
    scanner.mark_synced(f)

    assert scanner.scan() == []  # unchanged since upload
    f.write_text('{"changed": true}')
    os.utime(f, (2, 2))
    scanner.scan()  # pending tick
    assert scanner.scan() == [f]  # changed file re-offers once stable


def _session_with_subagents(tmp_path):
    (tmp_path / "s.jsonl").write_bytes(b'{"p":1}')
    subs = tmp_path / "s" / "subagents"
    subs.mkdir(parents=True)
    (subs / "agent-b.jsonl").write_bytes(b'{"b":1}\n')
    (subs / "agent-a.jsonl").write_bytes(b'{"a":1}')
    (subs / "agent-a.meta.json").write_text("{}")
    return subs


def test_discover_skips_subagents_dir(tmp_path):
    _session_with_subagents(tmp_path)
    assert discover([tmp_path]) == [tmp_path / "s.jsonl"]


def test_upload_bytes_bundles_sorted_subagents(tmp_path):
    _session_with_subagents(tmp_path)
    assert upload_bytes(tmp_path / "s.jsonl") == b'{"p":1}\n{"a":1}\n{"b":1}\n'
    plain = tmp_path / "plain.jsonl"
    plain.write_bytes(b"x")
    assert upload_bytes(plain) == b"x"


def test_stat_reflects_subagent_growth(tmp_path):
    subs = _session_with_subagents(tmp_path)
    scanner = StabilityScanner([tmp_path])
    scanner.mark_synced(tmp_path / "s.jsonl")
    assert scanner.scan() == []
    (subs / "agent-a.jsonl").write_bytes(b'{"a":1}\n{"a":2}\n')
    assert scanner.scan() == []  # changed: pending
    assert scanner.scan() == [tmp_path / "s.jsonl"]  # stable
