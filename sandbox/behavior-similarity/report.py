#!/usr/bin/env python3
"""Snapshot a run into results/<UTC timestamp>/ (anomaly-lab convention).

meta.json (tracked): params, headline metrics, LLM ledgers — so approach
iterations stay comparable across commits. summary.md: human-readable rollup.

Run: uv run --with numpy --python 3.12 report.py
"""

import json
import subprocess
import time

from common import DATA, LAB


def main() -> None:
    eval_ = json.loads((DATA / "eval.json").read_text())
    pairs = json.loads((DATA / "pair_eval.json").read_text())
    motifs = json.loads((DATA / "motifs.json").read_text())
    tags = json.loads((DATA / "tags.json").read_text())

    out = LAB / "results" / time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())
    out.mkdir(parents=True)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()

    meta = {
        "git_sha": sha,
        "corpus": "anomaly-lab 300-session sample of Exgentic/agent-llm-traces",
        "taxonomy": list(tags["taxonomy"]),
        "tag_counts": eval_["tag_counts"],
        "eval": {
            mode: {m: {k: v for k, v in r.items() if k != "per_tag_ap"}
                   for m, r in eval_[mode]["methods"].items()}
            for mode in ("in_corpus", "cross_benchmark")
        },
        "per_tag_ap_cross_benchmark": {
            m: r["per_tag_ap"] for m, r in eval_["cross_benchmark"]["methods"].items()
            if m != "random"
        },
        "pair_eval": pairs["summary"],
        "motifs": {
            "n_clusters": motifs["n_clusters"], "n_noise": motifs["n_noise"],
            "cross_benchmark_clusters": sum(1 for c in motifs["clusters"] if c["n_benchmarks"] >= 2),
            "named": [{k: c.get(k) for k in ("name", "kind", "n_traces", "n_benchmarks")}
                      for c in motifs["clusters"] if "name" in c],
        },
        "ledgers": {
            "closed_coding": tags["ledger"], "pair_judge": pairs["ledger"],
            "motif_naming": motifs["ledger"],
        },
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))

    lines = ["# Behavior-similarity run summary", ""]
    for mode in ("in_corpus", "cross_benchmark"):
        lines += [f"## {mode}", "", "| method | P@5 inf | mAP inf | mAP rare | bench@5 | harness@5 |",
                  "|---|---|---|---|---|---|"]
        for m, r in eval_[mode]["methods"].items():
            lines.append(f"| {m} | {r['p@5_informative']} | {r['map_informative']} | "
                         f"{r['map_rare']} | {r['bench@5']} | {r['harness@5']} |")
        lines.append("")
    lines += ["## Blind pairwise precision", "", "| selection | precision | n |", "|---|---|---|"]
    for k, v in pairs["summary"].items():
        lines.append(f"| {k} | {v['precision']} | {v['n']} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
