#!/usr/bin/env python3
"""Join an agreement run's cached RouteReports with the labels sidecar and
dump the disagreements for manual review. Scratch tooling, not product code.

Usage: python3 errors.py <out_dir> [--full]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).parents[2]
LABELS = BASE / "devdata" / "benchmarks" / "arb" / "labels.json"


def load(out_dir: Path) -> list[dict]:
    labels = json.loads(LABELS.read_text())
    rows = []
    for path in sorted(out_dir.glob("*_route.json")):
        report = json.loads(path.read_text())
        trace_id = path.stem.rsplit("_", 1)[-1].removesuffix("_route")
        # identifier is "<file-stem>_<source_trace_id>"; trace id is the last
        # 32-hex chunk before "_route".
        trace_id = path.stem[: -len("_route")].rsplit("_", 1)[-1]
        label = labels.get(trace_id)
        if label is None:
            print(f"no label for {path.name}", file=sys.stderr)
            continue
        rows.append({"file": path.name, "label": label, "report": report})
    return rows


def vote_split(verdict: dict) -> str:
    votes = [v["value"] for v in verdict["votes"] if v["call"] == "outcome"]
    return "/".join(f"{v}:{c}" for v, c in Counter(votes).items())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir")
    parser.add_argument("--full", action="store_true", help="print full reasoning")
    args = parser.parse_args()

    rows = load(Path(args.out_dir))
    wrong = []
    for row in rows:
        human = row["label"]["outcome"]
        verdict = row["report"]["verdict"]
        judge = verdict["outcome"] or "indeterminate"
        if judge != human:
            wrong.append((human, judge, row))

    print(f"{len(rows)} traces, {len(wrong)} disagreements\n")
    by_kind = Counter((h, j) for h, j, _ in wrong)
    for (h, j), n in by_kind.most_common():
        print(f"  human={h} judge={j}: {n}")
    by_bench = Counter(r["label"]["benchmark"] for _, _, r in wrong)
    print(f"\nby benchmark: {dict(by_bench)}")
    by_agent = Counter(r["label"]["agent"] for _, _, r in wrong)
    print(f"by agent: {dict(by_agent)}\n")

    for human, judge, row in sorted(wrong, key=lambda w: (w[0], w[1])):
        verdict = row["report"]["verdict"]
        signals = row["report"]["signals"]
        reasons = [r["code"] for r in row["report"]["routing_reasons"]]
        reasoning = verdict.get("reasoning") or "(none)"
        if not args.full:
            reasoning = reasoning[:400]
        print("=" * 100)
        print(f"{row['file']}")
        print(
            f"  human={human}  judge={judge} (conf {verdict['outcome_confidence']}, "
            f"votes {vote_split(verdict)})  truncated={verdict['rendering_truncated']}"
        )
        print(
            f"  benchmark={row['label']['benchmark']}  agent={row['label']['agent']}  "
            f"looping={row['label']['looping']}"
        )
        print(
            f"  signals: failure_suspected={signals['failure_suspected']} "
            f"loop={signals['loop_kind']} trunc={signals['truncation_suspected']}"
        )
        print(f"  routed: {reasons or 'NO'}")
        print(f"  reasoning: {reasoning}")


if __name__ == "__main__":
    main()
