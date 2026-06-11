"""Inventory the field structure of real local session logs (no content printed).

For each harness, scan recent files and report: record types, key sets per
type, payload/message sub-types, content block types, and usage keys —
so we can diff against what app/importers/sessions/ actually extracts.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HOME = Path.home()


def recent_files(root: Path, limit: int = 8) -> list[Path]:
    files = [p for p in root.rglob("*.jsonl") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def scan(files: list[Path]):
    rec_types: Counter = Counter()
    keys_by_type: dict[str, Counter] = defaultdict(Counter)
    payload_types: Counter = Counter()
    payload_keys: dict[str, Counter] = defaultdict(Counter)
    msg_keys: Counter = Counter()
    block_types: Counter = Counter()
    block_keys: dict[str, Counter] = defaultdict(Counter)
    usage_keys: Counter = Counter()
    for f in files:
        for line in f.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict):
                continue
            t = str(r.get("type") or r.get("role") or "?")
            rec_types[t] += 1
            keys_by_type[t].update(r.keys())
            p = r.get("payload")
            if isinstance(p, dict):
                pt = str(p.get("type") or "?")
                payload_types[f"{t}/{pt}"] += 1
                payload_keys[f"{t}/{pt}"].update(p.keys())
            m = r.get("message")
            if isinstance(m, dict):
                msg_keys.update(m.keys())
                u = m.get("usage")
                if isinstance(u, dict):
                    usage_keys.update(u.keys())
                c = m.get("content")
                if isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict):
                            bt = str(b.get("type") or "?")
                            block_types[bt] += 1
                            block_keys[bt].update(b.keys())
    return {
        "record_types": rec_types,
        "keys_by_type": keys_by_type,
        "payload_types": payload_types,
        "payload_keys": payload_keys,
        "message_keys": msg_keys,
        "block_types": block_types,
        "block_keys": block_keys,
        "usage_keys": usage_keys,
    }


def show(name: str, root: Path):
    files = recent_files(root)
    print(f"\n{'=' * 70}\n{name}: {len(files)} recent files")
    if not files:
        return
    r = scan(files)
    print(f"record types: {dict(r['record_types'].most_common())}")
    for t, keys in sorted(r["keys_by_type"].items()):
        print(f"  [{t}] keys: {dict(keys.most_common())}")
    if r["payload_types"]:
        print(f"payload types: {dict(r['payload_types'].most_common(30))}")
        for pt, keys in sorted(r["payload_keys"].items()):
            print(f"  [{pt}] keys: {sorted(keys)}")
    if r["message_keys"]:
        print(f"message keys: {dict(r['message_keys'].most_common())}")
    if r["block_types"]:
        print(f"content block types: {dict(r['block_types'].most_common())}")
        for bt, keys in sorted(r["block_keys"].items()):
            print(f"  [{bt}] keys: {sorted(keys)}")
    if r["usage_keys"]:
        print(f"usage keys: {dict(r['usage_keys'].most_common())}")


if __name__ == "__main__":
    show("codex", HOME / ".codex/sessions")
    show("claude", HOME / ".claude/projects")
    show("cursor", HOME / ".cursor/projects")
    sys.stdout.flush()
