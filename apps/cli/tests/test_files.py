import os

from trace_sync.files import StabilityScanner, discover


def test_discover_recursive_json_only(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "notes.txt").write_text("not a trace")
    nested = tmp_path / "deep" / "deeper"
    nested.mkdir(parents=True)
    (nested / "b.json").write_text("{}")

    found = discover([tmp_path])
    assert found == [tmp_path / "a.json", nested / "b.json"]


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
