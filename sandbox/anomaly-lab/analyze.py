#!/usr/bin/env python3
"""kNN novelty analysis over rendering embeddings, with a feature-vector
baseline. Answers:
  1. What does embedding-kNN novelty surface? (top outliers)
  2. Does the geometry just encode harness/benchmark? (neighbor purity)
  3. Does it differ from the boring feature baseline? (rank correlation)
  4. What does result-set-relative novelty (within benchmark) look like?

Writes data/novelty.json for the explain step.
Run: uv run --with numpy --python 3.12 analyze.py
"""

import json
from pathlib import Path

import numpy as np

DATA = Path(__file__).parent / "data"
K = 8


def knn_novelty(sim: np.ndarray, k: int = K) -> tuple[np.ndarray, np.ndarray]:
    """Mean cosine distance to k nearest neighbors + neighbor indices."""
    s = sim.copy()
    np.fill_diagonal(s, -np.inf)
    idx = np.argsort(-s, axis=1)[:, :k]
    dists = 1 - np.take_along_axis(s, idx, axis=1)
    return dists.mean(axis=1), idx


def zscore(x: np.ndarray) -> np.ndarray:
    med = np.median(x)
    mad = np.median(np.abs(x - med)) or 1.0
    return (x - med) / (1.4826 * mad)


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def main() -> None:
    recs = [json.loads(l) for l in (DATA / "renderings.jsonl").open()]
    emb = np.load(DATA / "embeddings.npy")
    emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
    sim = emb @ emb.T
    n = len(recs)

    novelty, nn_idx = knn_novelty(sim)

    # --- neighbor purity: does geometry encode metadata? ---
    harness = np.array([r["harness"] for r in recs])
    bench = np.array([r["benchmark"] for r in recs])
    model = np.array([str(r["models"]) for r in recs])
    for name, arr in [("harness", harness), ("benchmark", bench), ("model", model)]:
        same = np.mean([np.mean(arr[nn_idx[i]] == arr[i]) for i in range(n)])
        base = np.mean([np.mean(np.delete(arr, i) == arr[i]) for i in range(n)])
        print(f"kNN purity {name}: {same:.2f} (random baseline {base:.2f})")

    # --- feature baseline ---
    feats = np.column_stack([
        zscore(np.log1p(np.array([r["llm_calls"] for r in recs], float))),
        zscore(np.log1p(np.array([r["tool_calls"] for r in recs], float))),
        zscore(np.log1p(np.array([r["errors"] for r in recs], float))),
        zscore(np.log1p(np.array([r["total_tokens"] for r in recs], float))),
        zscore(np.array([r["n_tool_names"] for r in recs], float)),
    ])
    fdist = np.linalg.norm(feats[:, None, :] - feats[None, :, :], axis=2)
    fsim = -fdist
    fnov, _ = knn_novelty(fsim)

    print(f"\nspearman(embedding novelty, feature novelty) = {spearman(novelty, fnov):.2f}")
    top_e = set(np.argsort(-novelty)[:20])
    top_f = set(np.argsort(-fnov)[:20])
    print(f"top-20 overlap: {len(top_e & top_f)}/20")

    # --- within-benchmark (result-set-relative) novelty ---
    within = np.full(n, np.nan)
    for b in set(bench):
        ids = np.where(bench == b)[0]
        if len(ids) <= K:
            continue
        sub_nov, _ = knn_novelty(sim[np.ix_(ids, ids)], k=min(K, len(ids) - 1))
        within[ids] = sub_nov

    # --- dump top outliers ---
    def describe(i: int) -> dict:
        r = recs[i]
        return {
            "i": int(i),
            "session": r["session_id"],
            "harness": r["harness"],
            "benchmark": r["benchmark"],
            "model": r["models"],
            "llm_calls": r["llm_calls"],
            "tool_calls": r["tool_calls"],
            "errors": r["errors"],
            "novelty": round(float(novelty[i]), 4),
            "feature_novelty": round(float(fnov[i]), 4),
            "within_benchmark_novelty": None if np.isnan(within[i]) else round(float(within[i]), 4),
            "neighbors": [
                {"session": recs[j]["session_id"], "harness": recs[j]["harness"],
                 "benchmark": recs[j]["benchmark"], "sim": round(float(sim[i, j]), 3)}
                for j in nn_idx[i][:3]
            ],
        }

    order = np.argsort(-novelty)
    print("\n=== top 12 embedding outliers (global) ===")
    for i in order[:12]:
        d = describe(i)
        flag = "" if i in top_f else "  <-- NOT a feature outlier"
        print(f"{d['novelty']:.3f}  {d['harness']:>28} {d['benchmark']:>14} "
              f"llm={d['llm_calls']:<3} tools={d['tool_calls']:<3} err={d['errors']:<2} "
              f"{d['session']}{flag}")

    print("\n=== most typical (lowest novelty) ===")
    for i in order[-5:]:
        d = describe(i)
        print(f"{d['novelty']:.3f}  {d['harness']:>28} {d['benchmark']:>14} {d['session']}")

    w_order = np.argsort(-np.nan_to_num(within, nan=-1))
    print("\n=== top 8 within-benchmark outliers ===")
    for i in w_order[:8]:
        d = describe(i)
        print(f"{within[i]:.3f}  {d['harness']:>28} {d['benchmark']:>14} "
              f"llm={d['llm_calls']:<3} err={d['errors']:<2} {d['session']}")

    json.dump(
        {"global_top": [describe(int(i)) for i in order[:12]],
         "within_top": [describe(int(i)) for i in w_order[:8]],
         "novelty": novelty.tolist(), "nn_idx": nn_idx.tolist()},
        (DATA / "novelty.json").open("w"), indent=1,
    )
    print("\nwrote data/novelty.json")


if __name__ == "__main__":
    main()
