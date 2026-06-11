"""Trace-file discovery and the watch-mode stability scan (5_cli.md)."""

from pathlib import Path


def discover(paths: list[Path]) -> list[Path]:
    """`*.json` files (any case) under the given paths, recursive, sorted, deduped."""
    found: set[Path] = set()
    for path in paths:
        if path.is_file() and path.suffix.lower() == ".json":
            found.add(path)
        elif path.is_dir():
            found.update(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() == ".json")
    return sorted(found)


class StabilityScanner:
    """Tracks (size, mtime) across scans so watch only uploads files that
    have stopped growing (the spec's debounce). In-process state only — the
    CLI stays stateless across runs; server dedupe is the source of truth.
    """

    def __init__(self, paths: list[Path]) -> None:
        self._paths = paths
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
        present = set(discover(self._paths))
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
