"""The one sync loop; watch only changes the exit condition (5_cli.md)."""

import sys
import time
from dataclasses import dataclass
from pathlib import Path

from trace_sync.client import FileOutcome, SyncClient
from trace_sync.files import StabilityScanner, discover

WATCH_INTERVAL_SECONDS = 2.0

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_UNRUNNABLE = 2


@dataclass
class Counts:
    synced: int = 0
    skipped: int = 0
    failed: int = 0

    def record(self, kind: str) -> None:
        if kind == "uploaded":
            self.synced += 1
        elif kind == "skipped":
            self.skipped += 1
        else:
            self.failed += 1

    def summary(self) -> str:
        return f"synced {self.synced} · skipped {self.skipped} · failed {self.failed}"

    def exit_code(self) -> int:
        return EXIT_FAILURES if self.failed else EXIT_OK


def _sync_file(client: SyncClient, path: Path, counts: Counts) -> FileOutcome:
    outcome = client.upload(path)
    counts.record(outcome.kind)
    print(f"{path} → {outcome.detail}")
    return outcome


def run_sync(client: SyncClient, paths: list[Path]) -> int:
    files = discover(paths)
    if not files:
        print("no .json files found under the given paths", file=sys.stderr)
        return EXIT_UNRUNNABLE
    counts = Counts()
    for path in files:
        _sync_file(client, path, counts)
    print(counts.summary())
    return counts.exit_code()


def _sync_and_mark(
    client: SyncClient, path: Path, counts: Counts, scanner: StabilityScanner
) -> None:
    # Transport failures stay unmarked so the scanner re-offers the file;
    # server rejections are marked — a permanently bad file must not loop.
    if not _sync_file(client, path, counts).retryable:
        scanner.mark_synced(path)


def run_watch(client: SyncClient, paths: list[Path]) -> int:
    """Initial sync pass, then upload files as they appear or change.
    Exits only on interrupt; the code reflects failures seen so far."""
    counts = Counts()
    scanner = StabilityScanner(paths)
    for path in discover(paths):
        _sync_and_mark(client, path, counts, scanner)
    print(f"watching {', '.join(str(p) for p in paths)} — Ctrl-C to stop")
    try:
        while True:
            time.sleep(WATCH_INTERVAL_SECONDS)
            for path in scanner.scan():
                _sync_and_mark(client, path, counts, scanner)
    except KeyboardInterrupt:
        print()  # newline past the ^C
        print(counts.summary())
        return counts.exit_code()
