#!/usr/bin/env python3
"""Render compacted sessions into chronological behavior transcripts.

Approximates the spec's deterministic renderer (1_analysis.md): normalized
spans -> chronological message list. Input messages in this dataset are
cumulative per LLM call, so each span renders only its *delta*: input
messages beyond the previous span's count, then its output messages.

Writes data/renderings.jsonl: {session_id, harness, benchmark, models,
n_spans, total_tokens, features..., rendering}.
"""

import json
from pathlib import Path

DATA = Path(__file__).parent / "data"
PART_CAP = 700  # chars per rendered part; keeps transcripts embedding-sized


def cap(text: str, n: int = PART_CAP) -> str:
    text = text or ""
    if len(text) <= n:
        return text
    half = n // 2
    return text[:half] + " […] " + text[-half:]


def render_part(part: dict) -> str | None:
    t = part.get("type")
    if t == "text":
        c = (part.get("content") or "").strip()
        return cap(c) if c else None
    if t == "tool_call":
        return f"CALL {part.get('name')}({cap(part.get('arguments') or '', 400)})"
    if t == "tool_call_response":
        return f"RESULT {part.get('name') or ''}: {cap(part.get('response') or '', 400)}"
    return f"[{t}] {cap(part.get('raw') or '', 200)}"


def render_message(m: dict) -> str | None:
    lines = [p for p in (render_part(p) for p in m.get("parts") or []) if p]
    if not lines:
        return None
    role = (m.get("role") or "?").upper()
    return f"{role}: " + "\n".join(lines)


def render_session(sess: dict) -> str:
    out: list[str] = []
    prev_input_count = 0
    for span in sess["spans"]:
        if span["type"] == "llm_call":
            inputs = span.get("input_messages") or []
            # First span: include the task setup (system + first user msg).
            # Later spans: only the delta (tool results, new user turns).
            new = inputs if prev_input_count == 0 else inputs[prev_input_count:]
            for m in new:
                r = render_message(m)
                if r:
                    out.append(r)
            prev_input_count = len(inputs)
            for m in span.get("output_messages") or []:
                r = render_message(m)
                if r:
                    out.append(r)
                prev_input_count += 1  # outputs join the next call's history
            fr = span.get("finish_reasons")
            if fr and "length" in str(fr):
                out.append("[finish_reason=length — output truncated]")
        else:
            out.append(f"[{span['type']}] {span.get('name')} {cap(span.get('other_attrs') or '', 300)}")
        status = span.get("status") or {}
        if status.get("code") == 2 or status.get("message"):
            out.append(f"[span status: ERROR {status.get('message') or ''}]")
    return "\n\n".join(out)


def features(sess: dict) -> dict:
    """The boring feature vector — the baseline the embedding has to beat."""
    tool_calls = 0
    tool_names: set[str] = set()
    errors = 0
    for span in sess["spans"]:
        status = span.get("status") or {}
        if status.get("code") == 2:
            errors += 1
        for m in span.get("output_messages") or []:
            for p in m.get("parts") or []:
                if p.get("type") == "tool_call":
                    tool_calls += 1
                    if p.get("name"):
                        tool_names.add(p["name"])
    return {
        "llm_calls": sum(1 for s in sess["spans"] if s["type"] == "llm_call"),
        "tool_calls": tool_calls,
        "n_tool_names": len(tool_names),
        "tool_names": sorted(tool_names),
        "errors": errors,
        "total_tokens": sess.get("total_tokens") or 0,
        "n_spans": sess["n_spans"],
    }


def main() -> None:
    out_path = DATA / "renderings.jsonl"
    n = 0
    with (DATA / "traces.jsonl").open() as f, out_path.open("w") as out:
        for line in f:
            sess = json.loads(line)
            rec = {
                "session_id": sess["session_id"],
                "harness": sess["harness"],
                "benchmark": sess["benchmark"],
                "models": sess["models"],
                **features(sess),
                "rendering": render_session(sess),
            }
            out.write(json.dumps(rec) + "\n")
            n += 1
    print(f"rendered {n} sessions -> {out_path}")


if __name__ == "__main__":
    main()
