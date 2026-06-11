#!/usr/bin/env python3
"""Embed renderings with OpenAI text-embedding-3-small and save vectors.

Reads data/renderings.jsonl, writes data/embeddings.npy (float32, row order
matches the jsonl) and data/ids.json. Renderings are truncated middle-out to
fit the embedding context window.

Run: uv run --with numpy embed.py   (needs OPENAI_API_KEY in ../.env.local)
"""

import json
import os
import urllib.request
from pathlib import Path

import numpy as np

DATA = Path(__file__).parent / "data"
CHAR_BUDGET = 18000  # JSON-dense text can dip under 3 chars/token; stay safe
BATCH = 16
MODEL = "text-embedding-3-small"


def load_key() -> str:
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    env = Path(__file__).parents[2] / ".env.local"
    for line in env.read_text().splitlines():
        if line.startswith("OPENAI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("no OPENAI_API_KEY")


def truncate(text: str) -> str:
    if len(text) <= CHAR_BUDGET:
        return text
    half = CHAR_BUDGET // 2
    return text[:half] + "\n[…middle elided…]\n" + text[-half:]


def embed_batch(key: str, texts: list[str]) -> list[list[float]]:
    body = json.dumps({"model": MODEL, "input": texts}).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as res:
            data = json.load(res)["data"]
    except urllib.error.HTTPError as e:
        raise SystemExit(f"embeddings API {e.code}: {e.read().decode()[:500]}")
    return [d["embedding"] for d in sorted(data, key=lambda d: d["index"])]


def main() -> None:
    key = load_key()
    records = [json.loads(l) for l in (DATA / "renderings.jsonl").open()]
    texts = [truncate(r["rendering"]) or "(empty trace)" for r in records]
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        vectors.extend(embed_batch(key, texts[i : i + BATCH]))
        print(f"embedded {min(i + BATCH, len(texts))}/{len(texts)}")
    arr = np.asarray(vectors, dtype=np.float32)
    np.save(DATA / "embeddings.npy", arr)
    (DATA / "ids.json").write_text(json.dumps([r["session_id"] for r in records]))
    print(f"saved {arr.shape} -> embeddings.npy")


if __name__ == "__main__":
    main()
