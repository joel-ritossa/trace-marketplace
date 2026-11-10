"""Trace-file discovery and the watch-mode stability scan (5_cli.md)."""

import time
from pathlib import Path

from trace_sync.prune import prune_jsonl

SUFFIXES = (".json", ".jsonl")
SUBAGENTS = "subagents"


def discover(paths: list[Path], since_hours: float | None = None) -> list[Path]:
    """`*.json` / `*.jsonl` files (any case) under the given paths, recursive,
    sorted, deduped. `since_hours` keeps only files modified in the last N
    hours — file selection only, never content interpretation. Files inside a
    session's companion directory (`X/` beside `X.jsonl`: subagent
    transcripts, title metadata) are skipped; subagents upload with `X`."""
    found: set[Path] = set()
    for path in paths:
        if path.is_file() and path.suffix.lower() in SUFFIXES:
            found.add(path)
        elif path.is_dir():
            found.update(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SUFFIXES)
    found = {p for p in found if not _in_session_dir(p)}
    if since_hours is not None:
        cutoff = time.time() - since_hours * 3600
        found = {p for p in found if (_stat(p) or (0, -1.0))[1] >= cutoff}
    return sorted(found)


def _in_session_dir(path: Path) -> bool:
    return any(d.with_name(f"{d.name}.jsonl").is_file() for d in path.parents if d.name)


def _subagent_files(path: Path) -> list[Path]:
    """A Claude Code session `X.jsonl` bundles `X/subagents/*.jsonl`."""
    if path.suffix.lower() != ".jsonl":
        return []
    return sorted((path.with_suffix("") / SUBAGENTS).glob("*.jsonl"))


def upload_bytes(path: Path) -> bytes:
    """File bytes plus the session's subagent transcripts appended as
    newline-separated JSONL; session logs are pruned to what the importers
    read (prune.py)."""
    data = path.read_bytes()
    for sub in _subagent_files(path):
        if not data.endswith(b"\n"):
            data += b"\n"
        data += sub.read_bytes()
    return prune_jsonl(data) if path.suffix.lower() == ".jsonl" else data


def _stat(path: Path) -> tuple[int, float] | None:
    """(total size, max mtime) across the file and its subagent files."""
    try:
        stats = [p.stat() for p in [path, *_subagent_files(path)]]
    except OSError:  # vanished between listing and stat
        return None
    return (sum(st.st_size for st in stats), max(st.st_mtime for st in stats))


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
        stat = _stat(path)
        if stat is not None:
            self._synced[path] = stat
            self._pending.pop(path, None)

    def scan(self) -> list[Path]:
        """One tick: files whose stats are new/changed vs the synced mark and
        unchanged since the previous tick (stable) are ready to upload."""
        ready: list[Path] = []
        present = set(discover(self._paths, self._since_hours))
        for path in present:
            stat = _stat(path)
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
