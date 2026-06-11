#!/usr/bin/env python3
"""Convert a HaluBench slice (PatronusAI/HaluBench, HF, open access) into
OTLP JSON files plus a metric ground-truth labels sidecar — the family-3
(quality metrics) validation corpus.

HaluBench is 14,900 single-turn RAG QA rows (passage, question, answer)
with human-verified PASS/FAIL hallucination labels, aggregated from six
sources (RAGTruth, FinanceBench, PubMedQA, CovidQA, DROP, halueval). One
row maps 1:1 onto the repo's single-turn RAG trace shape
(fixtures/retrieval-qa.json): a synthesized invoke_agent root, one
RETRIEVER span carrying the passage as an indexed document (the sample
adapter's `retrieved_contexts`), and one chat LLM span whose input
messages carry the passage as RAG system context plus the question as the
user message, and whose output message is the answer — so the renderer
shows the critic the same evidence the answering model saw.

Ground truth never leaks into the trace: PASS/FAIL exists only in the
sidecar (labels.json maps trace_id → {hallucinated, source, case_id}).
Rows with a passage longer than the cap are skipped, not truncated —
cutting evidence would invalidate the label. Timestamps are synthetic and
deterministic (the ARB convention), so re-runs are byte-identical.

Rows come from the HF datasets-server rows API (paged; a token from
HF_TOKEN / .env.local lifts the anonymous rate limit) and cache raw in
OUT_DIR/raw_rows.jsonl, so re-slicing never re-fetches. The slice is
stratified: even across sources, balanced PASS/FAIL within each.

Output layout: OUT_DIR/traces/*.json + OUT_DIR/labels.json.

Usage:
    python3 tools/halubench_to_otlp.py [--count 300] [--source RAGTruth] [--seed 0]
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _otlp import attr_list

DATASET = "PatronusAI/HaluBench"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
TOTAL_ROWS = 14_900
PAGE_SIZE = 100
OUT_DIR = Path(__file__).parents[1] / "devdata" / "benchmarks" / "halubench"

BASE_NANOS = 1_767_225_600_000_000_000  # 2026-01-01T00:00:00Z, ARB convention
RETRIEVE_NANOS = 500_000_000
CHAT_START_NANOS = 1_000_000_000
CHAT_END_NANOS = 3_000_000_000

# Skip-not-truncate: evidence cuts would invalidate the hallucination label.
# 6000 chars keeps the rendered chat input inside the renderer's default
# 8000-char conversation cap (passage + question + scaffolding).
PASSAGE_CAP_CHARS = 6000
ANSWER_CAP_CHARS = 4000

SYSTEM_PREFIX = "Answer the question using only the provided context.\n\nContext:\n"


def _hf_token() -> str | None:
    token = os.environ.get("HF_TOKEN")
    if not token:
        env_local = Path(__file__).parents[1] / ".env.local"
        if env_local.exists():
            for line in env_local.read_text().splitlines():
                if line.startswith("HF_TOKEN="):
                    token = line.split("=", 1)[1].strip()
    return token or None


def _hex_id(seed: str, length: int) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:length]


def _fetch_page(offset: int, headers: dict) -> list[dict]:
    query = urllib.parse.urlencode(
        {"dataset": DATASET, "config": "default", "split": "test",
         "offset": offset, "length": PAGE_SIZE}
    )
    request = urllib.request.Request(f"{ROWS_URL}?{query}", headers=headers)
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=120) as res:
                return [r["row"] for r in json.load(res)["rows"]]
        except urllib.error.HTTPError as err:
            if err.code != 429 or attempt == 5:
                raise SystemExit(f"rows API failed at offset {offset}: {err}") from err
            time.sleep(20 * (attempt + 1))  # rate-limit windows need real waits
        except (urllib.error.URLError, OSError, TimeoutError) as err:
            if attempt == 5:
                raise SystemExit(f"rows API failed at offset {offset}: {err}") from err
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def fetch_rows(token: str | None) -> list[dict]:
    """All rows via the datasets-server rows API, cached page-by-page as
    JSONL so a rate-limited pull resumes and a re-slice never re-fetches."""
    cache = OUT_DIR / "raw_rows.jsonl"
    rows: list[dict] = []
    if cache.exists():
        rows = [json.loads(line) for line in cache.read_text().splitlines() if line.strip()]
        if len(rows) >= TOTAL_ROWS:
            return rows
        rows = rows[: len(rows) - len(rows) % PAGE_SIZE]  # resume on a page boundary
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with cache.open("w" if not rows else "r+") as out:
        if rows:
            out.writelines(json.dumps(r) + "\n" for r in rows)
            out.truncate()
        for offset in range(len(rows), TOTAL_ROWS, PAGE_SIZE):
            page = _fetch_page(offset, headers)
            rows.extend(page)
            out.writelines(json.dumps(r) + "\n" for r in page)
            out.flush()
            if offset and offset % 2000 == 0:
                print(f"…fetched {len(rows)} rows", file=sys.stderr)
    return rows


def usable(row: dict) -> bool:
    """A convertible row: complete fields, binary label, passage within the
    skip cap (truncation would invalidate the ground truth)."""
    return bool(
        row.get("id")
        and row.get("passage")
        and row.get("question")
        and row.get("answer")
        and row.get("label") in ("PASS", "FAIL")
        and len(row["passage"]) <= PASSAGE_CAP_CHARS
        and len(row["answer"]) <= ANSWER_CAP_CHARS
    )


def stratify(rows: list[dict], count: int, seed: int) -> list[dict]:
    """Even across sources; within each, balanced PASS/FAIL."""
    rng = random.Random(seed)
    pools: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        pools.setdefault((row["source_ds"], row["label"]), []).append(row)
    for pool in pools.values():
        pool.sort(key=lambda r: r["id"])
        rng.shuffle(pool)
    sources = sorted({s for s, _ in pools})
    per_source = -(-count // len(sources))  # ceil
    selected: list[dict] = []
    for source in sources:
        source_pools = [pools.get((source, label), []) for label in ("PASS", "FAIL")]
        taken = 0
        while taken < per_source and any(source_pools):
            for pool in source_pools:
                if pool and taken < per_source:
                    selected.append(pool.pop())
                    taken += 1
    return selected[:count]


def convert(row: dict) -> dict:
    identity = f"halubench:{row['id']}"
    trace_id = _hex_id(identity, 32)
    root_span_id = _hex_id(f"root:{identity}", 16)

    input_messages = [
        {"role": "system", "parts": [{"type": "text", "content": SYSTEM_PREFIX + row["passage"]}]},
        {"role": "user", "parts": [{"type": "text", "content": row["question"]}]},
    ]
    output_messages = [
        {
            "role": "assistant",
            "finish_reason": "stop",
            "parts": [{"type": "text", "content": row["answer"]}],
        }
    ]

    root = {
        "traceId": trace_id,
        "spanId": root_span_id,
        "name": f"halubench {row['source_ds']} {row['id'][:8]}",
        "kind": 1,
        "startTimeUnixNano": str(BASE_NANOS),
        "endTimeUnixNano": str(BASE_NANOS + CHAT_END_NANOS),
        "attributes": attr_list(
            {
                "gen_ai.operation.name": "invoke_agent",
                "halubench.source": row["source_ds"],
                "halubench.id": row["id"],
                "halubench.synthesized_root": True,
            }
        ),
        "status": {"code": 1},
    }
    retriever = {
        "traceId": trace_id,
        "spanId": _hex_id(f"retrieve:{identity}", 16),
        "parentSpanId": root_span_id,
        "name": "context_lookup",
        "kind": 1,
        "startTimeUnixNano": str(BASE_NANOS),
        "endTimeUnixNano": str(BASE_NANOS + RETRIEVE_NANOS),
        "attributes": attr_list(
            {
                "openinference.span.kind": "RETRIEVER",
                "retrieval.documents.0.document.content": row["passage"],
            }
        ),
        "status": {"code": 1},
    }
    chat = {
        "traceId": trace_id,
        "spanId": _hex_id(f"chat:{identity}", 16),
        "parentSpanId": root_span_id,
        "name": "chat rag-answerer",
        "kind": 3,
        "startTimeUnixNano": str(BASE_NANOS + CHAT_START_NANOS),
        "endTimeUnixNano": str(BASE_NANOS + CHAT_END_NANOS),
        "attributes": attr_list(
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.input.messages": json.dumps(input_messages),
                "gen_ai.output.messages": json.dumps(output_messages),
            }
        ),
        "status": {"code": 1},
    }

    return {
        "resourceSpans": [
            {
                "resource": {"attributes": attr_list({"service.name": "halubench-rag"})},
                "scopeSpans": [
                    {"scope": {"name": "halubench.converter"}, "spans": [root, retriever, chat]}
                ],
            }
        ]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=300, help="rows to convert")
    parser.add_argument("--source", help="restrict to one source dataset")
    parser.add_argument("--seed", type=int, default=0, help="sampling seed")
    args = parser.parse_args()

    rows = [r for r in fetch_rows(_hf_token()) if usable(r)]
    if args.source:
        rows = [r for r in rows if r["source_ds"] == args.source]
    selected = stratify(rows, args.count, args.seed)
    print(f"{len(rows)} usable rows; converting {len(selected)}")

    traces_dir = OUT_DIR / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    labels_path = OUT_DIR / "labels.json"
    labels: dict[str, dict] = json.loads(labels_path.read_text()) if labels_path.exists() else {}
    for row in selected:
        otlp = convert(row)
        trace_id = otlp["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
        # Filename keys on the (collision-free) trace id — raw row ids share
        # prefixes within some sources, so no slug of them is safe.
        (traces_dir / f"{row['source_ds']}-{trace_id[:12]}.json").write_text(json.dumps(otlp))
        labels[trace_id] = {
            "dataset": "halubench",
            "hallucinated": row["label"] == "FAIL",
            "source": row["source_ds"],
            "case_id": row["id"],
        }
    labels_path.write_text(json.dumps(labels, indent=2) + "\n")
    print(f"wrote {len(selected)} OTLP files + labels.json to {OUT_DIR.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
