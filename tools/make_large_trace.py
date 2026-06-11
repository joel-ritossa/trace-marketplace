#!/usr/bin/env python3
"""Generate a synthetic OTLP JSON trace with thousands of spans, for the
large-trace-handling demo (docs/demos/large-trace-handling.md). Deterministic for
a given span count; stdlib only.

Usage:
    python3 tools/make_large_trace.py [--spans 5000] [--out devdata/large-trace.json]
"""

import argparse
import hashlib
import json
from pathlib import Path

BASE_NANOS = 1768471200_000_000_000  # 2026-01-15T10:00:00Z
OPERATIONS = ["chat", "execute_tool", "invoke_agent", "retrieval", "embeddings"]


def span_id(i: int) -> str:
    return hashlib.sha256(f"large-span-{i}".encode()).hexdigest()[:16]


def make_span(i: int, parent: int | None, trace_id: str) -> dict:
    operation = OPERATIONS[i % len(OPERATIONS)]
    start = BASE_NANOS + i * 12_000_000
    duration = (50 + (i * 37) % 900) * 1_000_000
    attributes = {
        "gen_ai.operation.name": operation,
        "gen_ai.request.model": "gpt-5" if operation == "chat" else None,
        "gen_ai.tool.name": f"tool_{i % 7}" if operation == "execute_tool" else None,
        "gen_ai.usage.input_tokens": 1200 + i if operation == "chat" else None,
        "gen_ai.usage.output_tokens": 80 + i % 50 if operation == "chat" else None,
        "gen_ai.input.messages": json.dumps(
            [{"role": "user", "parts": [{"type": "text", "content": f"synthetic message {i} " * 30}]}]
        )
        if operation == "chat"
        else None,
        "demo.index": i,
    }
    return {
        "traceId": trace_id,
        "spanId": span_id(i),
        **({"parentSpanId": span_id(parent)} if parent is not None else {}),
        "name": f"{operation} #{i}",
        "kind": 3,
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(start + duration),
        "attributes": [
            {
                "key": k,
                "value": {"intValue": str(v)} if isinstance(v, int) else {"stringValue": v},
            }
            for k, v in attributes.items()
            if v is not None
        ],
        "status": {"code": 2, "message": "synthetic failure"} if i % 97 == 0 and i else {"code": 1},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spans", type=int, default=5000)
    parser.add_argument("--out", type=Path, default=Path("devdata/large-trace.json"))
    args = parser.parse_args()

    trace_id = hashlib.sha256(f"large-trace-{args.spans}".encode()).hexdigest()[:32]
    # Each span's parent is i // 8: a bushy tree ~4-5 levels deep at 5000 spans.
    spans = [make_span(i, (i - 1) // 8 if i else None, trace_id) for i in range(args.spans)]
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "large-trace-demo"}}
                    ]
                },
                "scopeSpans": [{"scope": {"name": "demo.generator"}, "spans": spans}],
            }
        ]
    }
    args.out.parent.mkdir(exist_ok=True)
    args.out.write_text(json.dumps(payload))
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB, {args.spans} spans)")


if __name__ == "__main__":
    main()
