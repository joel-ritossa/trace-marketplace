from pathlib import Path

from trace_sync import run as run_mod
from trace_sync.client import FileOutcome
from trace_sync.run import EXIT_FAILURES, EXIT_OK, EXIT_UNRUNNABLE, run_sync, run_watch


class FakeClient:
    def __init__(self, outcomes: dict[str, FileOutcome]) -> None:
        self._outcomes = outcomes
        self.calls: list[str] = []

    def upload(self, path: Path) -> FileOutcome:
        self.calls.append(path.name)
        return self._outcomes[path.name]


def test_sync_lines_summary_and_exit_code(tmp_path, capsys):
    (tmp_path / "ok.json").write_text("{}")
    (tmp_path / "dup.json").write_text("{ }")
    (tmp_path / "bad.json").write_text("{  }")
    client = FakeClient(
        {
            "ok.json": FileOutcome("uploaded", "uploaded (complete, 1 trace)"),
            "dup.json": FileOutcome("skipped", "already synced"),
            "bad.json": FileOutcome("failed", "failed: No spans found."),
        }
    )

    assert run_sync(client, [tmp_path]) == EXIT_FAILURES
    out = capsys.readouterr().out
    assert f"{tmp_path / 'ok.json'} → uploaded (complete, 1 trace)" in out
    assert f"{tmp_path / 'dup.json'} → already synced" in out
    assert f"{tmp_path / 'bad.json'} → failed: No spans found." in out
    assert "synced 1 · skipped 1 · failed 1" in out


def test_sync_all_skipped_is_success(tmp_path, capsys):
    (tmp_path / "a.json").write_text("{}")
    client = FakeClient({"a.json": FileOutcome("skipped", "already synced")})
    assert run_sync(client, [tmp_path]) == EXIT_OK


def test_sync_no_files_is_unrunnable(tmp_path):
    assert run_sync(FakeClient({}), [tmp_path]) == EXIT_UNRUNNABLE


def test_watch_interrupt_prints_summary(tmp_path, capsys, monkeypatch):
    """Ctrl-C lands as KeyboardInterrupt in the scan sleep; watch must close
    with the summary and a code reflecting failures seen so far."""
    (tmp_path / "a.json").write_text("{}")
    client = FakeClient({"a.json": FileOutcome("failed", "failed: boom")})

    def interrupt(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(run_mod.time, "sleep", interrupt)
    assert run_watch(client, [tmp_path]) == EXIT_FAILURES
    out = capsys.readouterr().out
    assert "synced 0 · skipped 0 · failed 1" in out


def _interrupt_after(monkeypatch, ticks: int) -> None:
    """Let `ticks` watch-loop sleeps pass, then deliver the interrupt."""
    remaining = {"n": ticks}

    def sleep(_seconds: float) -> None:
        if remaining["n"] == 0:
            raise KeyboardInterrupt
        remaining["n"] -= 1

    monkeypatch.setattr(run_mod.time, "sleep", sleep)


def test_watch_retries_transport_failures(tmp_path, monkeypatch):
    """A transport failure (server never saw the bytes) is not marked synced:
    the scanner re-offers the file once its stats are stable again."""
    (tmp_path / "a.json").write_text("{}")
    client = FakeClient({"a.json": FileOutcome("failed", "failed: boom", retryable=True)})

    # Initial pass + two scan ticks: tick 1 marks pending, tick 2 re-offers.
    _interrupt_after(monkeypatch, ticks=2)
    assert run_watch(client, [tmp_path]) == EXIT_FAILURES
    assert client.calls == ["a.json", "a.json"]


def test_watch_does_not_retry_server_rejections(tmp_path, monkeypatch):
    """A server rejection marks the file synced; it is never offered again
    until its bytes change."""
    (tmp_path / "a.json").write_text("{}")
    client = FakeClient({"a.json": FileOutcome("failed", "failed: invalid JSON")})

    _interrupt_after(monkeypatch, ticks=3)
    assert run_watch(client, [tmp_path]) == EXIT_FAILURES
    assert client.calls == ["a.json"]
