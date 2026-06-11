#!/usr/bin/env python3
"""Fetch a stratified sample of Exgentic/agent-llm-traces sessions and store
compacted versions (text bodies truncated) for local rendering/embedding
experiments. Writes data/traces.jsonl, one compact session per line.

Stdlib only. ~15 MB per page of 10 rows; strides across the dataset so all
harness/benchmark combos are represented.
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

ROWS_URL = "https://datasets-server.huggingface.co/rows"
DATASET = "Exgentic/agent-llm-traces"
PAGE_SIZE = 10
N_PAGES = 30          # 300 sessions
TOTAL_ROWS = 1781
TEXT_CAP = 2000       # per text part
ARG_CAP = 1000        # per tool-call arguments blob
OUT = Path(__file__).parent / "data" / "traces.jsonl"


def fetch_rows(offset: int, length: int) -> list[dict]:
    query = urllib.parse.urlencode(
        {"dataset": DATASET, "config": "default", "split": "train",
         "offset": offset, "length": length}
    )
    with urllib.request.urlopen(f"{ROWS_URL}?{query}", timeout=300) as res:
        return [r["row"] for r in json.load(res)["rows"]]


def cap(text: str, n: int) -> str:
    if not isinstance(text, str) or len(text) <= n:
        return text
    half = n // 2
    return text[:half] + f" …[{len(text) - n} chars elided]… " + text[-half:]


def compact_part(part: dict) -> dict:
    p = {"type": part.get("type")}
    if part.get("type") == "text":
        p["content"] = cap(part.get("content") or "", TEXT_CAP)
    elif part.get("type") == "tool_call":
        p["name"] = part.get("name")
        p["arguments"] = cap(json.dumps(part.get("arguments"), default=str), ARG_CAP)
    elif part.get("type") == "tool_call_response":
        p["name"] = part.get("name")
        p["response"] = cap(json.dumps(part.get("response") or part.get("result"), default=str), ARG_CAP)
    else:
        p["raw"] = cap(json.dumps({k: v for k, v in part.items() if k != "type"}, default=str), ARG_CAP)
    return p


def compact_messages(raw) -> list[dict]:
    if raw is None:
        return []
    msgs = json.loads(raw) if isinstance(raw, str) else raw
    out = []
    for m in msgs:
        out.append({
            "role": m.get("role"),
            "finish_reason": m.get("finish_reason"),
            "parts": [compact_part(p) for p in (m.get("parts") or [])],
        })
    return out


def compact_session(row: dict) -> dict:
    spans = []
    for s in sorted(row["spans"], key=lambda x: x["start_time"]):
        a = s.get("attributes") or {}
        spans.append({
            "type": s.get("type"),
            "name": s.get("name"),
            "start_time": s.get("start_time"),
            "status": s.get("status"),
            "model": a.get("gen_ai.request.model"),
            "finish_reasons": a.get("gen_ai.response.finish_reasons"),
            "input_tokens": a.get("gen_ai.usage.input_tokens"),
            "output_tokens": a.get("gen_ai.usage.output_tokens"),
            "input_messages": compact_messages(a.get("gen_ai.input.messages")),
            "output_messages": compact_messages(a.get("gen_ai.output.messages")),
            # non-LLM spans: keep their attrs compactly
            "other_attrs": cap(json.dumps({k: v for k, v in a.items()
                                           if not k.startswith("gen_ai.")}, default=str), ARG_CAP)
            if s.get("type") != "llm_call" else None,
        })
    return {
        "session_id": row["session_id"],
        "harness": row["harness"],
        "benchmark": row["benchmark"],
        "models": row["models"],
        "total_tokens": row["total_tokens"],
        "n_spans": len(row["spans"]),
        "spans": spans,
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    stride = max(1, (TOTAL_ROWS - PAGE_SIZE) // (N_PAGES - 1))
    seen: set[str] = set()
    with OUT.open("w") as f:
        for i in range(N_PAGES):
            offset = min(i * stride, TOTAL_ROWS - PAGE_SIZE)
            try:
                rows = fetch_rows(offset, PAGE_SIZE)
            except Exception as e:  # noqa: BLE001 - log and keep sampling
                print(f"page offset={offset} failed: {e}")
                continue
            for row in rows:
                if row["session_id"] in seen:
                    continue
                seen.add(row["session_id"])
                f.write(json.dumps(compact_session(row)) + "\n")
            print(f"page {i + 1}/{N_PAGES} (offset {offset}) -> {len(seen)} sessions")
    print(f"wrote {len(seen)} sessions to {OUT}")


if __name__ == "__main__":
    main()
