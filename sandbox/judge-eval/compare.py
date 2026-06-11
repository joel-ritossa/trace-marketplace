#!/usr/bin/env python3
"""Compare two agreement runs trace by trace: headline deltas, per-benchmark
breakdown, and the traces whose verdicts flipped. Scratch tooling.

Usage: python3 compare.py <out_dir_a> <out_dir_b>
"""

import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).parents[2]
LABELS = json.loads((BASE / "devdata/benchmarks/arb/labels.json").read_text())


def load(out_dir: Path) -> dict[str, dict]:
    rows = {}
    for path in sorted(out_dir.glob("*_route.json")):
        trace_id = path.stem[: -len("_route")].rsplit("_", 1)[-1]
        rows[trace_id] = json.loads(path.read_text())
    return rows


def verdict(report: dict) -> str:
    return report["verdict"]["outcome"] or "indeterminate"


def stats(rows: dict[str, dict]) -> dict:
    decided = matches = abst = 0
    by_bench: dict[str, list[int]] = {}
    for trace_id, report in rows.items():
        human = LABELS[trace_id]["outcome"]
        judged = verdict(report)
        bench = LABELS[trace_id]["benchmark"]
        if judged == "indeterminate":
            abst += 1
            by_bench.setdefault(bench, []).append(-1)
        else:
            decided += 1
            hit = int(judged == human)
            matches += hit
            by_bench.setdefault(bench, []).append(hit)
    return {
        "n": len(rows),
        "decided": decided,
        "matches": matches,
        "abstentions": abst,
        "by_bench": by_bench,
    }


def fmt(s: dict) -> str:
    decided_pct = s["matches"] / s["decided"] if s["decided"] else 0
    strict_pct = s["matches"] / s["n"]
    return (
        f"decided {decided_pct:.1%} ({s['matches']}/{s['decided']}), "
        f"strict {strict_pct:.1%}, abstentions {s['abstentions']}"
    )


def main() -> None:
    dir_a, dir_b = Path(sys.argv[1]), Path(sys.argv[2])
    a, b = load(dir_a), load(dir_b)
    shared = sorted(set(a) & set(b))
    print(f"{dir_a.name}: {fmt(stats(a))}")
    print(f"{dir_b.name}: {fmt(stats(b))}")
    print(f"\nshared traces: {len(shared)}")

    flips = Counter()
    fixed, broken = [], []
    for trace_id in shared:
        va, vb = verdict(a[trace_id]), verdict(b[trace_id])
        if va == vb:
            continue
        human = LABELS[trace_id]["outcome"]
        flips[(va, vb)] += 1
        was_right, is_right = va == human, vb == human
        if not was_right and is_right:
            fixed.append((trace_id, va, vb))
        elif was_right and not is_right:
            broken.append((trace_id, va, vb))
    print(f"verdict flips: {sum(flips.values())}")
    for (va, vb), n in flips.most_common():
        print(f"  {va} -> {vb}: {n}")
    print(f"\nfixed ({len(fixed)}):")
    for trace_id, va, vb in fixed:
        lbl = LABELS[trace_id]
        print(f"  {lbl['benchmark']}/{lbl['task_id']} [{lbl['agent']}] {va} -> {vb}")
    print(f"\nbroken ({len(broken)}):")
    for trace_id, va, vb in broken:
        lbl = LABELS[trace_id]
        print(f"  {lbl['benchmark']}/{lbl['task_id']} [{lbl['agent']}] {va} -> {vb}")

    print("\nper-benchmark strict agreement (a -> b):")
    sa, sb = stats(a), stats(b)
    for bench in sorted(sa["by_bench"]):
        xa = sa["by_bench"][bench]
        xb = sb["by_bench"].get(bench, [])
        pa = sum(1 for v in xa if v == 1) / len(xa)
        pb = sum(1 for v in xb if v == 1) / len(xb) if xb else 0
        print(f"  {bench:<18} {pa:.1%} -> {pb:.1%} (n={len(xa)})")


if __name__ == "__main__":
    main()
