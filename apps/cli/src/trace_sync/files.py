"""Trace-file discovery and the watch-mode stability scan (5_cli.md)."""

import functools
import re
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import zstandard

from trace_sync.prune import prune_jsonl

SUFFIXES = (".json", ".jsonl", ".jsonl.zst")
SUBAGENTS = "subagents"
DEFAULT_QUIET_SECONDS = 300.0
_AGENT_ID = re.compile(rb'"agentId":\s*"([\w-]+)"')
_TIMESTAMP = re.compile(rb'"timestamp":\s*"([^"]+)"')
_TAIL_BYTES = 128 * 1024
_reported_stale: set[Path] = set()


def _is_trace(path: Path) -> bool:
    return path.name.lower().endswith(SUFFIXES)


def upload_name(path: Path) -> str:
    """Filename sent to the server: `.zst` dropped so a session keeps its name
    live and archived."""
    return path.name.removesuffix(".zst") if path.suffix.lower() == ".zst" else path.name


def discover(paths: list[Path], since_hours: float | None = None) -> list[Path]:
    """`*.json` / `*.jsonl` / `*.jsonl.zst` files (any case) under the given paths, recursive,
    sorted, deduped. `since_hours` keeps only files modified in the last N
    hours and whose last recorded activity (latest record `timestamp`) is
    within it too: a stale session with a fresh mtime is skipped. Files inside a
    session's companion directory (`X/` beside `X.jsonl`: subagent
    transcripts, title metadata) are skipped; subagents upload with `X`."""
    found: set[Path] = set()
    for path in paths:
        if path.is_file() and _is_trace(path):
            found.add(path)
        elif path.is_dir():
            found.update(p for p in path.rglob("*") if p.is_file() and _is_trace(p))
    found = {p for p in found if not _in_session_dir(p)}
    if since_hours is not None:
        cutoff = time.time() - since_hours * 3600
        found = {p for p in found if (_stat(p) or (0, -1.0))[1] >= cutoff}
        found = {p for p in found if _active_since(p, cutoff)}
    return sorted(found)


def _active_since(path: Path, cutoff: float) -> bool:
    """False when the file's last recorded activity predates `cutoff`; files
    without a readable timestamp stay (mtime already passed). Reports each
    skipped file once, not on every watch tick."""
    try:
        st = path.stat()
        last = _last_activity(path, st.st_size, st.st_mtime)
    except OSError:  # vanished or unreadable: leave it to the upload path
        return True
    if last is None or last >= cutoff:
        return True
    if path not in _reported_stale:
        _reported_stale.add(path)
        age_hours = (time.time() - last) / 3600
        print(f"{path} → skipped: last activity {age_hours:.0f}h ago", file=sys.stderr)
    return False


@functools.lru_cache(maxsize=4096)
def _last_activity(path: Path, size: int, mtime: float) -> float | None:
    """Latest record `timestamp` (epoch seconds) in the file's tail, keyed on
    its stat like `_agent_ids_at`. `.zst` streams can't seek, so they are
    decompressed and trimmed."""
    if path.suffix.lower() == ".zst":
        with path.open("rb") as f:
            reader = zstandard.ZstdDecompressor().stream_reader(f)
            tail = b""
            while chunk := reader.read(_TAIL_BYTES):
                tail = (tail + chunk)[-_TAIL_BYTES:]
    else:
        with path.open("rb") as f:
            f.seek(max(0, size - _TAIL_BYTES))
            tail = f.read()
    stamps = []
    for raw in _TIMESTAMP.findall(tail):
        try:
            stamps.append(datetime.fromisoformat(raw.decode()).timestamp())
        except ValueError:
            continue
    return max(stamps, default=None)


def _in_session_dir(path: Path) -> bool:
    return any(d.with_name(f"{d.name}.jsonl").is_file() for d in path.parents if d.name)


def _subagent_files(path: Path, siblings: bool = True) -> list[Path]:
    """A Claude Code session `X.jsonl` bundles `X/subagents/*.jsonl`, plus the
    transcripts of agents it references (recursively) that live under a
    sibling session's `subagents/`: a resumed or forked session copies the
    earlier history into a new file but not its subagent transcripts."""
    if path.suffix.lower() != ".jsonl":
        return []
    files = sorted((path.with_suffix("") / SUBAGENTS).glob("*.jsonl"))
    if not siblings:
        return files
    included = {p.name for p in files}
    elsewhere: dict[str, Path] | None = None
    queue = [path, *files]
    while queue:
        for agent_id in _agent_ids(queue.pop(0)):
            name = f"agent-{agent_id}.jsonl"
            if name in included:
                continue
            if elsewhere is None:
                elsewhere = {p.name: p for p in sorted(path.parent.glob(f"*/{SUBAGENTS}/*.jsonl"))}
            if name in elsewhere:
                included.add(name)
                files.append(elsewhere[name])
                queue.append(elsewhere[name])
    return files


def _agent_ids(path: Path) -> list[str]:
    st = path.stat()
    return _agent_ids_at(path, st.st_size, st.st_mtime)


@functools.lru_cache(maxsize=4096)
def _agent_ids_at(path: Path, size: int, mtime: float) -> list[str]:
    """Agent ids a transcript mentions, in order; keyed on the file's stat so
    watch-mode ticks reread only changed files."""
    return list(dict.fromkeys(m.decode() for m in _AGENT_ID.findall(path.read_bytes())))


def sibling_transcripts(path: Path) -> int:
    """How many bundled subagent transcripts come from sibling sessions."""
    return len(_subagent_files(path)) - len(_subagent_files(path, siblings=False))


def upload_bytes(path: Path, siblings: bool = True) -> bytes:
    """File bytes plus the session's subagent transcripts (with `siblings`,
    also those from sibling sessions) appended as newline-separated JSONL;
    session logs are pruned to what the importers read (prune.py)."""
    if path.suffix.lower() == ".zst":
        with path.open("rb") as f:
            data = zstandard.ZstdDecompressor().stream_reader(f).read()
    else:
        data = path.read_bytes()
    for sub in _subagent_files(path, siblings):
        if not data.endswith(b"\n"):
            data += b"\n"
        data += sub.read_bytes()
    return prune_jsonl(data) if upload_name(path).lower().endswith(".jsonl") else data


def _stat(path: Path) -> tuple[int, float] | None:
    """(total size, max mtime) across the file and its subagent files."""
    try:
        stats = [p.stat() for p in [path, *_subagent_files(path)]]
    except OSError:  # vanished between listing and stat
        return None
    return (sum(st.st_size for st in stats), max(st.st_mtime for st in stats))


class QuietScanner:
    """Offers files whose combined mtime is at least `quiet_seconds` old and
    that differ from the last synced stat, so an active session uploads once
    it goes quiet. In-process state only — the CLI stays stateless across
    runs; server dedupe is the source of truth.
    """

    def __init__(
        self,
        paths: list[Path],
        since_hours: float | None = None,
        quiet_seconds: float = DEFAULT_QUIET_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._paths = paths
        self._since_hours = since_hours
        self._quiet = quiet_seconds
        self._clock = clock
        self._synced: dict[Path, tuple[int, float]] = {}

    def mark_synced(self, path: Path) -> None:
        """Record the just-uploaded state so the file isn't re-offered until
        it changes again."""
        stat = _stat(path)
        if stat is not None:
            self._synced[path] = stat

    def scan(self) -> list[Path]:
        """One tick: files changed since the synced mark and quiet long enough."""
        now = self._clock()
        present = set(discover(self._paths, self._since_hours))
        ready = []
        for path in present:
            stat = _stat(path)
            if stat is not None and self._synced.get(path) != stat and now - stat[1] >= self._quiet:
                ready.append(path)
        # Drop state for deleted files so a long watch doesn't grow forever.
        self._synced = {p: s for p, s in self._synced.items() if p in present}
        return sorted(ready)
