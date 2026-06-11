#!/usr/bin/env python3
"""Compare full-rendering novelty vs behavior-skeleton novelty.

Run: uv run --with numpy --python 3.12 compare.py
"""

import json
from pathlib import Path

import numpy as np

from analyze import knn_novelty, spearman

DATA = Path(__file__).parent / "data"
K = 8


def main() -> None:
    recs = [json.loads(l) for l in (DATA / "renderings.jsonl").open()]
    n = len(recs)
    bench = np.array([r["benchmark"] for r in recs])
    harness = np.array([r["harness"] for r in recs])

    results = {}
    for name, path in [("full", "embeddings.npy"), ("skeleton", "skeleton_embeddings.npy")]:
        emb = np.load(DATA / path)
        emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
        sim = emb @ emb.T
        nov, nn = knn_novelty(sim)
        results[name] = (nov, nn, sim)
        for label, arr in [("harness", harness), ("benchmark", bench)]:
            same = np.mean([np.mean(arr[nn[i]] == arr[i]) for i in range(n)])
            print(f"{name:9} kNN purity {label}: {same:.2f}")

    fn, sn = results["full"][0], results["skeleton"][0]
    print(f"\nspearman(full, skeleton) = {spearman(fn, sn):.2f}")
    tf = set(np.argsort(-fn)[:20])
    ts = set(np.argsort(-sn)[:20])
    print(f"top-20 overlap: {len(tf & ts)}/20")

    def line(i: int, nov: np.ndarray) -> str:
        r = recs[i]
        return (f"{nov[i]:.3f}  {r['harness']:>28} {r['benchmark']:>14} "
                f"llm={r['llm_calls']:<3} tools={r['tool_calls']:<3} err={r['errors']:<2} "
                f"{r['session_id']}")

    print("\n=== top 12 SKELETON outliers (behavioral novelty) ===")
    for i in np.argsort(-sn)[:12]:
        print(line(i, sn))

    # within-benchmark skeleton novelty
    sim_s = results["skeleton"][2]
    within = np.full(n, np.nan)
    for b in set(bench):
        ids = np.where(bench == b)[0]
        if len(ids) <= K:
            continue
        sub, _ = knn_novelty(sim_s[np.ix_(ids, ids)], k=min(K, len(ids) - 1))
        within[ids] = sub
    print("\n=== top 10 within-benchmark SKELETON outliers ===")
    for i in np.argsort(-np.nan_to_num(within, nan=-1))[:10]:
        print(f"{within[i]:.3f}  " + line(i, sn)[7:])

    json.dump(
        {"skeleton_novelty": sn.tolist(), "skeleton_nn": results["skeleton"][1].tolist(),
         "within_skeleton": [None if np.isnan(x) else x for x in within]},
        (DATA / "skeleton_novelty.json").open("w"),
    )
    print("\nwrote data/skeleton_novelty.json")


if __name__ == "__main__":
    main()
