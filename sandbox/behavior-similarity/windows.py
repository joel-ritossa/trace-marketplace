#!/usr/bin/env python3
"""Sliding-window skeleton embeddings for locality-aware matching (RQ2).

Splits each behavior skeleton into overlapping windows of skeleton lines and
embeds each window. A window is a local stretch of conduct (e.g. one retry
cycle), so window-level matching can align behaviors that whole-trace
embeddings dilute.

Writes data/windows.jsonl + data/window_embeddings.npy.
Run: uv run --with numpy --python 3.12 windows.py
"""

import json
import math

import numpy as np

from common import DATA, LAB, load_key, load_skeletons

import sys

sys.path.insert(0, str(LAB.parent / "anomaly-lab"))
from embed import embed_batch  # noqa: E402

WINDOW = 12  # skeleton lines per window
STRIDE = 6
MAX_WINDOWS = 40  # per trace; stride widens beyond this


def windows_for(lines: list[str]) -> list[tuple[int, str]]:
    if len(lines) <= WINDOW:
        return [(0, "\n".join(lines))]
    stride = STRIDE
    n = math.ceil((len(lines) - WINDOW) / stride) + 1
    if n > MAX_WINDOWS:
        stride = math.ceil((len(lines) - WINDOW) / (MAX_WINDOWS - 1))
    out = []
    for start in range(0, len(lines) - WINDOW + stride, stride):
        chunk = lines[start : start + WINDOW]
        if chunk:
            out.append((start, "\n".join(chunk)))
        if start + WINDOW >= len(lines):
            break
    return out


def main() -> None:
    key = load_key()
    skels = load_skeletons()
    recs: list[dict] = []
    for s in skels:
        lines = [ln for ln in s["skeleton"].splitlines() if ln.strip()] or ["(empty)"]
        for start, text in windows_for(lines):
            recs.append({"session_id": s["session_id"], "start": start, "text": text})
    print(f"{len(recs)} windows from {len(skels)} traces")

    vectors: list[list[float]] = []
    texts = [r["text"][:6000] for r in recs]
    for i in range(0, len(texts), 64):
        vectors.extend(embed_batch(key, texts[i : i + 64]))
        if (i // 64) % 5 == 0:
            print(f"embedded {min(i + 64, len(texts))}/{len(texts)}")
    np.save(DATA / "window_embeddings.npy", np.asarray(vectors, dtype=np.float32))
    with (DATA / "windows.jsonl").open("w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    print("saved window embeddings")


if __name__ == "__main__":
    main()
