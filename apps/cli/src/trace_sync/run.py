"""The one sync loop; watch only changes the exit condition (5_cli.md)."""

import sys
import time
from dataclasses import dataclass
from pathlib import Path

from trace_sync.client import FileOutcome, PendingUpload, SyncClient
from trace_sync.files import StabilityScanner, discover

WATCH_INTERVAL_SECONDS = 2.0
DRAIN_INTERVAL_SECONDS = 1.0

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


def _print_outcome(path: Path, outcome: FileOutcome, counts: Counts) -> None:
    counts.record(outcome.kind)
    print(f"{path} → {outcome.detail}")


def sync_batch(client: SyncClient, files: list[Path], counts: Counts) -> list[tuple[Path, bool]]:
    """Enqueue every file, then drain the in-flight set (5_cli.md: pipelined).
    Ingestion runs concurrently on the server's queue; we only serialize the
    quick POSTs. Returns (path, retryable) per file for watch's re-offer logic."""
    results: list[tuple[Path, bool]] = []
    pending: list[PendingUpload] = []
    for path in files:
        enqueued = client.enqueue(path)
        if isinstance(enqueued, PendingUpload):
            pending.append(enqueued)
        else:
            _print_outcome(path, enqueued, counts)
            results.append((path, enqueued.retryable))

    while pending:
        still_pending: list[PendingUpload] = []
        for upload in pending:
            outcome = client.check(upload)
            if outcome is None:
                still_pending.append(upload)
            else:
                _print_outcome(upload.path, outcome, counts)
                results.append((upload.path, outcome.retryable))
        pending = still_pending
        if pending:
            time.sleep(DRAIN_INTERVAL_SECONDS)
    return results


def run_sync(client: SyncClient, paths: list[Path], since_hours: float | None = None) -> int:
    files = discover(paths, since_hours)
    if not files:
        print("no .json/.jsonl files found under the given paths", file=sys.stderr)
        return EXIT_UNRUNNABLE
    counts = Counts()
    sync_batch(client, files, counts)
    print(counts.summary())
    return counts.exit_code()


def _sync_and_mark(
    client: SyncClient, files: list[Path], counts: Counts, scanner: StabilityScanner
) -> None:
    # Transport failures stay unmarked so the scanner re-offers the file;
    # server rejections are marked — a permanently bad file must not loop.
    for path, retryable in sync_batch(client, files, counts):
        if not retryable:
            scanner.mark_synced(path)


def run_watch(client: SyncClient, paths: list[Path], since_hours: float | None = None) -> int:
    """Initial sync pass, then upload files as they appear or change.
    Exits only on interrupt; the code reflects failures seen so far."""
    counts = Counts()
    scanner = StabilityScanner(paths, since_hours)
    _sync_and_mark(client, discover(paths, since_hours), counts, scanner)
    print(f"watching {', '.join(str(p) for p in paths)} — Ctrl-C to stop")
    try:
        while True:
            time.sleep(WATCH_INTERVAL_SECONDS)
            _sync_and_mark(client, scanner.scan(), counts, scanner)
    except KeyboardInterrupt:
        print()  # newline past the ^C
        print(counts.summary())
        return counts.exit_code()
