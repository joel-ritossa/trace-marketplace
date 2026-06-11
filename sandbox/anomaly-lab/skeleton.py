#!/usr/bin/env python3
"""Render content-stripped 'behavior skeletons' and embed them.

The skeleton keeps action structure only: roles, tool names, argument keys,
result sizes, error markers, finish reasons. No natural-language content —
if novelty over these embeddings surfaces odd traces, the signal is
behavioral, not topical.

Writes data/skeletons.jsonl + data/skeleton_embeddings.npy.
Run: uv run --with numpy --python 3.12 skeleton.py
"""

import json
from pathlib import Path

import numpy as np

from embed import embed_batch, load_key, truncate

DATA = Path(__file__).parent / "data"


def part_skeleton(part: dict) -> str | None:
    t = part.get("type")
    if t == "text":
        c = part.get("content") or ""
        return f"text({len(c)}ch)" if c.strip() else None
    if t == "tool_call":
        try:
            keys = sorted(json.loads(part.get("arguments") or "{}").keys())
        except Exception:  # noqa: BLE001 - truncated json
            keys = ["?"]
        return f"CALL {part.get('name')}({','.join(keys)})"
    if t == "tool_call_response":
        r = part.get("response") or ""
        err = " ERRORISH" if any(w in r[:200].lower() for w in ("error", "exception", "traceback", "failed")) else ""
        return f"RESULT({len(r)}ch){err}"
    return f"[{t}]"


def skeleton(sess: dict) -> str:
    out: list[str] = []
    prev = 0
    for span in sess["spans"]:
        if span["type"] != "llm_call":
            out.append(f"[{span['type']}] {span.get('name')}")
            continue
        inputs = span.get("input_messages") or []
        new = inputs if prev == 0 else inputs[prev:]
        prev = len(inputs)
        for m in new:
            parts = [p for p in (part_skeleton(p) for p in m.get("parts") or []) if p]
            if parts:
                out.append(f"{(m.get('role') or '?').upper()}: " + " | ".join(parts))
        for m in span.get("output_messages") or []:
            parts = [p for p in (part_skeleton(p) for p in m.get("parts") or []) if p]
            if parts:
                out.append("ASSISTANT: " + " | ".join(parts))
            prev += 1
        fr = span.get("finish_reasons")
        if fr and "length" in str(fr):
            out.append("[finish=length]")
        status = span.get("status") or {}
        if status.get("code") == 2:
            out.append("[SPAN ERROR]")
    return "\n".join(out)


def main() -> None:
    sessions = [json.loads(l) for l in (DATA / "traces.jsonl").open()]
    recs = []
    for s in sessions:
        recs.append({"session_id": s["session_id"], "skeleton": skeleton(s)})
    with (DATA / "skeletons.jsonl").open("w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")

    key = load_key()
    texts = [truncate(r["skeleton"]) or "(empty)" for r in recs]
    vectors: list[list[float]] = []
    for i in range(0, len(texts), 16):
        vectors.extend(embed_batch(key, texts[i : i + 16]))
        print(f"embedded {min(i + 16, len(texts))}/{len(texts)}")
    np.save(DATA / "skeleton_embeddings.npy", np.asarray(vectors, dtype=np.float32))
    print("saved skeleton embeddings")


if __name__ == "__main__":
    main()
