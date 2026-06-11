#!/usr/bin/env python3
"""Convert Exgentic/agent-llm-traces sessions (HuggingFace) into OTLP JSON
files the uploader accepts.

Fetches rows from the HF datasets-server REST API (no HF login, no parquet
deps — stdlib only) and writes one OTLP file per session into devdata/,
which is git-ignored: real benchmark traces stay out of the repo per
AGENTS.md; committed fixtures live in fixtures/ and are synthetic.

The dataset is flattened, so conversion is not 1:1:
- trace_id is a session slug (e.g. "2a21e94e0687_1b28ad67"), not 32-hex —
  a valid traceId is derived from its sha256; the slug is preserved in the
  synthesized root's attributes as session.id.
- spans carry no parent ids — a root "invoke_agent" span is synthesized per
  session (marked exgentic.synthesized_root) and all real spans hang off it.
- timestamps are ISO strings (sometimes naive; treated as UTC) → nanos.

Usage:
    python3 tools/exgentic_to_otlp.py [--count 5] [--offset 0] [--min-spans 0] [--spread]
"""

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROWS_URL = "https://datasets-server.huggingface.co/rows"
DATASET = "Exgentic/agent-llm-traces"
PAGE_SIZE = 10  # rows average ~1.5 MB; keep responses manageable
# Dataset row count (static dataset; only --spread stride math uses this).
TOTAL_ROWS = 1781
# Rows are grouped by harness/benchmark, so --spread takes a few per strided
# page instead of a contiguous run — variety over locality.
SPREAD_PER_PAGE = 3
OUT_DIR = Path(__file__).parents[1] / "devdata"


def fetch_rows(offset: int, length: int) -> list[dict]:
    query = urllib.parse.urlencode(
        {"dataset": DATASET, "config": "default", "split": "train", "offset": offset, "length": length}
    )
    with urllib.request.urlopen(f"{ROWS_URL}?{query}", timeout=120) as res:
        return [r["row"] for r in json.load(res)["rows"]]


def to_nanos(iso: str) -> int:
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000_000)


def any_value(value) -> dict:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [any_value(v) for v in value]}}
    if isinstance(value, str):
        try:
            return {"intValue": str(int(value))} if value.lstrip("-").isdigit() else {"stringValue": value}
        except ValueError:
            return {"stringValue": value}
    return {"stringValue": str(value)}


def attr_list(attributes: dict) -> list[dict]:
    return [{"key": k, "value": any_value(v)} for k, v in attributes.items() if v is not None]


def convert_session(row: dict) -> dict:
    session_id = row["session_id"]
    trace_id = hashlib.sha256(session_id.encode()).hexdigest()[:32]
    root_span_id = hashlib.sha256(f"root:{session_id}".encode()).hexdigest()[:16]

    spans = row["spans"]
    starts = [to_nanos(s["start_time"]) for s in spans]
    ends = [to_nanos(s["end_time"]) for s in spans]

    otlp_spans = [
        {
            "traceId": trace_id,
            "spanId": root_span_id,
            "name": f"{row['harness']} {row['benchmark']} session",
            "kind": 1,
            "startTimeUnixNano": str(min(starts)),
            "endTimeUnixNano": str(max(ends)),
            "attributes": attr_list(
                {
                    "gen_ai.operation.name": "invoke_agent",
                    "gen_ai.agent.name": row["harness"],
                    "session.id": session_id,
                    "exgentic.benchmark": row["benchmark"],
                    "exgentic.synthesized_root": True,
                }
            ),
            "status": {"code": 1},
        }
    ]
    for span, start, end in zip(spans, starts, ends):
        status = span.get("status") or {}
        otlp_spans.append(
            {
                "traceId": trace_id,
                "spanId": span["span_id"],
                "parentSpanId": root_span_id,
                "name": span["name"],
                "kind": 3,
                "startTimeUnixNano": str(start),
                "endTimeUnixNano": str(end),
                "attributes": attr_list(
                    {**(span.get("attributes") or {}), "exgentic.span.type": span.get("type")}
                ),
                "status": {"code": status.get("code", 0), "message": status.get("message") or ""},
            }
        )

    resource_attrs = spans[0].get("resource_attributes") or {} if spans else {}
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": attr_list(resource_attrs)},
                "scopeSpans": [{"scope": {"name": "exgentic.converter"}, "spans": otlp_spans}],
            }
        ]
    }


def _offsets(args: argparse.Namespace) -> list[int]:
    """Page offsets to visit. Sequential by default; --spread strides across
    the dataset so the grouped harness/benchmark blocks all get sampled."""
    if not args.spread:
        last_page = max(args.offset, TOTAL_ROWS - PAGE_SIZE)
        return list(range(args.offset, last_page + PAGE_SIZE, PAGE_SIZE))
    n_pages = max(1, -(-args.count // SPREAD_PER_PAGE))  # ceil
    stride = max(PAGE_SIZE, (TOTAL_ROWS - PAGE_SIZE) // max(1, n_pages - 1))
    return [min(args.offset + i * stride, TOTAL_ROWS - PAGE_SIZE) for i in range(n_pages)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5, help="sessions to convert")
    parser.add_argument("--offset", type=int, default=0, help="dataset row offset to start at")
    parser.add_argument("--min-spans", type=int, default=0, help="skip sessions with fewer spans")
    parser.add_argument(
        "--spread",
        action="store_true",
        help="stride across the dataset for harness/benchmark variety",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    written = 0
    seen: set[str] = set()
    for offset in _offsets(args):
        if written >= args.count:
            break
        rows = fetch_rows(offset, PAGE_SIZE)
        if not rows:
            break
        taken_this_page = 0
        for row in rows:
            if written >= args.count:
                break
            if args.spread and taken_this_page >= SPREAD_PER_PAGE:
                break
            if len(row["spans"]) < args.min_spans or row["session_id"] in seen:
                continue
            seen.add(row["session_id"])
            otlp = convert_session(row)
            span_count = len(row["spans"]) + 1  # + synthesized root
            name = f"{row['harness']}-{row['benchmark']}-{row['session_id']}-{span_count}spans.json"
            path = OUT_DIR / name.replace("/", "_")
            path.write_text(json.dumps(otlp))
            print(f"wrote {path.relative_to(Path.cwd())} ({path.stat().st_size / 1e6:.1f} MB)")
            written += 1
            taken_this_page += 1
    if written < args.count:
        print(f"dataset exhausted; wrote {written} of {args.count}")


if __name__ == "__main__":
    main()
