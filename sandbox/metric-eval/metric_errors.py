#!/usr/bin/env python3
"""Join a metrics-agreement run's cached per-trace results with the
HaluBench labels sidecar and dump the disagreements for manual review.
Scratch tooling, not product code.

Critic section: hallucination flag vs human label, with the critic's
reason. Score section: faithfulness scores on the wrong side of the
threshold (default 0.5).

Usage: python3 metric_errors.py <out_dir> [--full] [--threshold 0.5]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).parents[2]
LABELS = BASE / "devdata" / "benchmarks" / "halubench" / "labels.json"
RAW_ROWS = BASE / "devdata" / "benchmarks" / "halubench" / "raw_rows.jsonl"


def load(out_dir: Path) -> list[dict]:
    labels = json.loads(LABELS.read_text())
    rows = []
    for path in sorted(out_dir.glob("*_metrics.json")):
        report = json.loads(path.read_text())
        # identifier is "<file-stem>_<source_trace_id>"; trace id is the
        # last 32-hex chunk before "_metrics".
        trace_id = path.stem[: -len("_metrics")].rsplit("_", 1)[-1]
        label = labels.get(trace_id)
        if label is None:
            print(f"no label for {path.name}", file=sys.stderr)
            continue
        rows.append({"file": path.name, "label": label, "results": report["results"]})
    return rows


def raw_cases(case_ids: set[str]) -> dict[str, dict]:
    if not RAW_ROWS.exists():
        return {}
    cases = {}
    for line in RAW_ROWS.read_text().splitlines():
        row = json.loads(line)
        if row["id"] in case_ids:
            cases[row["id"]] = row
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir")
    parser.add_argument("--full", action="store_true", help="print question/answer/passage")
    parser.add_argument("--threshold", type=float, default=0.5, help="faithfulness cutoff")
    args = parser.parse_args()

    rows = load(Path(args.out_dir))

    critic_wrong = []
    score_wrong = []
    for row in rows:
        human = row["label"]["hallucinated"]
        critic = row["results"].get("hallucination")
        if critic is not None and bool(critic["value"]) != human:
            critic_wrong.append(row)
        score = row["results"].get("faithfulness")
        if score is not None:
            faithful_by_score = float(score["value"]) >= args.threshold
            if faithful_by_score == human:  # high score on a hallucinated answer or vice versa
                score_wrong.append(row)

    print(f"{len(rows)} traces")
    print(f"hallucination critic wrong: {len(critic_wrong)}")
    by_kind = Counter(
        (row["label"]["hallucinated"], bool(row["results"]["hallucination"]["value"]))
        for row in critic_wrong
    )
    for (human, critic), n in by_kind.most_common():
        print(f"  human={human} critic={critic}: {n}")
    by_source = Counter(row["label"]["source"] for row in critic_wrong)
    print(f"  by source: {dict(by_source)}")
    print(f"faithfulness on the wrong side of {args.threshold}: {len(score_wrong)}")
    by_source = Counter(row["label"]["source"] for row in score_wrong)
    print(f"  by source: {dict(by_source)}\n")

    cases = raw_cases({row["label"]["case_id"] for row in critic_wrong}) if args.full else {}
    for row in sorted(critic_wrong, key=lambda r: (r["label"]["source"], r["file"])):
        critic = row["results"]["hallucination"]
        score = row["results"].get("faithfulness")
        score_text = f"{float(score['value']):.2f}" if score else "n/a"
        print("=" * 100)
        print(row["file"])
        print(
            f"  human hallucinated={row['label']['hallucinated']}  "
            f"critic flag={critic['value']}  faithfulness={score_text}  "
            f"source={row['label']['source']}"
        )
        print(f"  critic reason: {critic.get('reason') or '(none)'}")
        case = cases.get(row["label"]["case_id"])
        if case:
            print(f"  question: {case['question'][:300]}")
            print(f"  answer: {case['answer'][:500]}")
            print(f"  passage: {case['passage'][:800]}")


if __name__ == "__main__":
    main()
