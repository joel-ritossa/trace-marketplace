"""Trace-file discovery and the watch-mode stability scan (5_cli.md)."""

import time
from pathlib import Path

SUFFIXES = (".json", ".jsonl")


def discover(paths: list[Path], since_hours: float | None = None) -> list[Path]:
    """`*.json` / `*.jsonl` files (any case) under the given paths, recursive,
    sorted, deduped. `since_hours` keeps only files modified in the last N
    hours — file selection only, never content interpretation."""
    found: set[Path] = set()
    for path in paths:
        if path.is_file() and path.suffix.lower() in SUFFIXES:
            found.add(path)
        elif path.is_dir():
            found.update(
                p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SUFFIXES
            )
    if since_hours is not None:
        cutoff = time.time() - since_hours * 3600
        found = {p for p in found if _mtime(p) >= cutoff}
    return sorted(found)


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:  # vanished between listing and stat
        return -1.0


class StabilityScanner:
    """Tracks (size, mtime) across scans so watch only uploads files that
    have stopped growing (the spec's debounce). In-process state only — the
    CLI stays stateless across runs; server dedupe is the source of truth.
    """

    def __init__(self, paths: list[Path], since_hours: float | None = None) -> None:
        self._paths = paths
        self._since_hours = since_hours
        self._pending: dict[Path, tuple[int, float]] = {}
        self._synced: dict[Path, tuple[int, float]] = {}

    def mark_synced(self, path: Path) -> None:
        """Record the just-uploaded state so the file isn't re-offered until
        it changes again."""
        stat = self._stat(path)
        if stat is not None:
            self._synced[path] = stat
            self._pending.pop(path, None)

    def scan(self) -> list[Path]:
        """One tick: files whose stats are new/changed vs the synced mark and
        unchanged since the previous tick (stable) are ready to upload."""
        ready: list[Path] = []
        present = set(discover(self._paths, self._since_hours))
        for path in present:
            stat = self._stat(path)
            if stat is None or self._synced.get(path) == stat:
                continue
            if self._pending.get(path) == stat:
                ready.append(path)
            else:
                self._pending[path] = stat
        # Drop state for deleted files so a long watch doesn't grow forever.
        self._pending = {p: s for p, s in self._pending.items() if p in present}
        self._synced = {p: s for p, s in self._synced.items() if p in present}
        return sorted(ready)

    @staticmethod
    def _stat(path: Path) -> tuple[int, float] | None:
        try:
            st = path.stat()
        except OSError:  # vanished between listing and stat
            return None
        return (st.st_size, st.st_mtime)
