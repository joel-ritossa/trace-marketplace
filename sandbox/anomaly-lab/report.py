#!/usr/bin/env python3
"""Full method-comparison report with blind LLM evaluation.

1. Scores all methods (methods.py).
2. Blind eval panel: top-10 per method + random controls, each judged by an
   LLM (with its 3 skeleton-space neighbors as context, identical for every
   method) -> behavioral / topical precision@10.
3. Rare-but-clustered case study (the human-transfer traces).
4. Contrastive explanations for the combined method's top picks.
5. Writes results/<UTC timestamp>/ with meta (params, git sha, latency,
   cost), scores, eval, explanations, and a human-readable summary.

Run: uv run --with numpy,scikit-learn,litellm --python 3.12 report.py
"""

import json
import random
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from llm import chat, ledger_summary, parse_json
from methods import K, KMEANS_K, MIN_CLUSTER, SEED, compute

LAB = Path(__file__).parent
TOP_N = 10
N_CONTROLS = 10
EVAL_MODEL = "gpt-5-mini"
TARGET_CAP = 10000
NEIGHBOR_CAP = 5000
WORKERS = 6

JUDGE_PROMPT = """You are auditing AI-agent execution traces. Below is one trace plus its 3
most similar traces from the same corpus (by action structure). Judge the
TARGET trace relative to the comparables and the corpus at large.

Return JSON only:
{{
  "behaviorally_unusual": true|false,   // unusual agent CONDUCT: strategy, recovery, failure shape, tool usage pattern
  "topically_unusual": true|false,      // unusual task CONTENT/domain, but conduct is ordinary
  "note": "<one sentence>"
}}

## TARGET TRACE
{target}

{neighbors}"""

EXPLAIN_PROMPT = """One AI-agent trace was statistically flagged as behaviorally unusual
relative to its nearest neighbors (below). In 2-3 sentences, explain what the
FLAGGED trace does behaviorally that the comparables don't — actions,
strategy, recovery, failure shape, not topic. If it is not actually unusual,
say so plainly.

## FLAGGED TRACE
{target}

{neighbors}"""


def cap(t: str, n: int) -> str:
    return t if len(t) <= n else t[: n // 2] + "\n[…elided…]\n" + t[-n // 2 :]


def neighbor_block(recs: list[dict], nn: list[int]) -> str:
    return "\n\n".join(
        f"## COMPARABLE TRACE {j + 1} ({recs[k]['harness']} / {recs[k]['benchmark']})\n"
        + cap(recs[k]["rendering"], NEIGHBOR_CAP)
        for j, k in enumerate(nn[:3])
    )


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=LAB,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> None:
    t0 = time.perf_counter()
    out_dir = LAB / "results" / datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    out_dir.mkdir(parents=True)

    bundle = compute()
    recs, scores, diag = bundle["recs"], bundle["scores"], bundle["diagnostics"]
    n = len(recs)
    skel_nn = diag["skel_nn"]

    tops = {m: np.argsort(-s)[:TOP_N].tolist() for m, s in scores.items()}
    in_any_top = set().union(*tops.values())
    rng = random.Random(SEED)
    controls = rng.sample(sorted(set(range(n)) - in_any_top), N_CONTROLS)
    panel = sorted(in_any_top | set(controls))
    print(f"eval panel: {len(panel)} traces ({len(in_any_top)} flagged + {N_CONTROLS} controls)")

    def judge(i: int) -> tuple[int, dict]:
        prompt = JUDGE_PROMPT.format(target=cap(recs[i]["rendering"], TARGET_CAP),
                                     neighbors=neighbor_block(recs, skel_nn[i]))
        for attempt in range(2):
            try:
                return i, parse_json(chat(prompt, "eval", EVAL_MODEL, json_mode=True))
            except Exception as e:  # noqa: BLE001 - retry once, then record failure
                if attempt:
                    return i, {"behaviorally_unusual": None, "topically_unusual": None,
                               "note": f"judge failed: {e}"}
        raise AssertionError

    with ThreadPoolExecutor(WORKERS) as ex:
        verdicts = dict(ex.map(judge, panel))
    print(f"judged {len(verdicts)} traces")

    def rate(ids: list[int], key: str) -> float:
        vals = [verdicts[i][key] for i in ids if verdicts[i][key] is not None]
        return round(float(np.mean(vals)), 2) if vals else float("nan")

    eval_rows = {m: {"behavioral_precision_at_10": rate(ids, "behaviorally_unusual"),
                     "topical_rate_at_10": rate(ids, "topically_unusual")}
                 for m, ids in tops.items()}
    eval_rows["random_controls"] = {"behavioral_precision_at_10": rate(controls, "behaviorally_unusual"),
                                    "topical_rate_at_10": rate(controls, "topically_unusual")}

    # --- rare-but-clustered case study: the human-transfer traces ---
    transfers = [i for i, r in enumerate(recs)
                 if r["session_id"] in ("066de3655406_9950c2db", "18efd0e196b7_947c3c53")]
    labels = diag["labels"]
    case = []
    for i in transfers:
        ranks = {m: int(np.argsort(np.argsort(-s))[i]) + 1 for m, s in scores.items()}
        size = 1 if labels[i] == -1 else labels.count(labels[i])
        case.append({"session": recs[i]["session_id"], "hdbscan_cluster_size": size,
                     "rank_by_method": ranks,
                     "judged": verdicts.get(i, {}).get("note", "(not in panel)")})

    # --- contrastive explanations for the combined method's top 3 ---
    explanations = []
    for i in tops["skel_combined"][:3]:
        ans = chat(EXPLAIN_PROMPT.format(target=cap(recs[i]["rendering"], TARGET_CAP),
                                         neighbors=neighbor_block(recs, skel_nn[i])),
                   "explain", EVAL_MODEL)
        explanations.append({"session": recs[i]["session_id"],
                             "harness": recs[i]["harness"], "benchmark": recs[i]["benchmark"],
                             "explanation": ans})

    ledger = ledger_summary()
    meta = {
        "timestamp": out_dir.name,
        "git_sha": git_sha(),
        "dataset": {"source": "Exgentic/agent-llm-traces", "n": n,
                    "sampling": "30 pages of 10, even stride over 1781 rows"},
        "params": {"k": K, "kmeans_k": KMEANS_K, "hdbscan_min_cluster_size": MIN_CLUSTER,
                   "top_n": TOP_N, "n_controls": N_CONTROLS, "seed": SEED,
                   "embedding_model": "text-embedding-3-small", "eval_model": EVAL_MODEL,
                   "target_cap_chars": TARGET_CAP, "neighbor_cap_chars": NEIGHBOR_CAP},
        "eval_design": "blind judge; neighbor context = skeleton-space kNN for every method",
        "llm_usage": ledger,
        "wall_time_s": round(time.perf_counter() - t0, 1),
        "hdbscan": diag["hdbscan"],
    }

    sessions = [r["session_id"] for r in recs]
    json.dump(meta, (out_dir / "meta.json").open("w"), indent=1)
    json.dump({"sessions": sessions, "scores": {m: s.tolist() for m, s in scores.items()},
               "top10": {m: [sessions[i] for i in ids] for m, ids in tops.items()}},
              (out_dir / "scores.json").open("w"), indent=1)
    json.dump({"per_method": eval_rows,
               "verdicts": {sessions[i]: v for i, v in verdicts.items()},
               "rare_but_clustered_case": case},
              (out_dir / "eval.json").open("w"), indent=1)
    json.dump(explanations, (out_dir / "explanations.json").open("w"), indent=1)

    lines = [f"# Run {out_dir.name}", "",
             "| Method | behavioral P@10 | topical rate@10 |", "|---|---|---|"]
    for m, row in eval_rows.items():
        lines.append(f"| {m} | {row['behavioral_precision_at_10']} | {row['topical_rate_at_10']} |")
    lines += ["", "## Rare-but-clustered (human-transfer traces)", ""]
    for c in case:
        lines.append(f"- `{c['session']}` cluster_size={c['hdbscan_cluster_size']} "
                     f"ranks: " + ", ".join(f"{m}={r}" for m, r in c["rank_by_method"].items()))
        lines.append(f"  - judge: {c['judged']}")
    lines += ["", "## Cost / latency", "", "```json", json.dumps(ledger, indent=1), "```"]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")

    print("\n=== precision@10 (behavioral | topical) ===")
    for m, row in eval_rows.items():
        print(f"{m:22} {row['behavioral_precision_at_10']!s:>5} | {row['topical_rate_at_10']}")
    print("\n=== rare-but-clustered ===")
    for c in case:
        print(json.dumps(c, indent=1))
    print(f"\nLLM usage: {json.dumps(ledger)}")
    print(f"results -> {out_dir.relative_to(LAB)}")


if __name__ == "__main__":
    main()
