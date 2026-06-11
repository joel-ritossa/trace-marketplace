#!/usr/bin/env python3
"""Tag-based retrieval evaluation of every similarity method.

For each query trace, rank the other 299 by similarity and score against the
closed-coding behavior tags:

  P@5 (informative)   share of top-5 neighbors sharing an informative tag
                      (prevalence <= 1/3 — the dominant tags would saturate)
  mAP (informative)   macro mean average precision per informative tag
  mAP (rare)          same, tags with 5..30 carriers — the marketplace case
  bench@5 / harness@5 topic-confound diagnostics (same benchmark/harness share)

Random baseline via Monte Carlo shuffled rankings. Also scores a hybrid grid:
rank-averaged pairs of base methods.

Writes data/eval.json.
Run: uv run --with numpy --python 3.12 evaluate.py
"""

import itertools
import json

import numpy as np

from common import DATA, load_renderings

K = 5
INFORMATIVE_MAX = 100  # tag prevalence cap (out of 300)
RARE_RANGE = (5, 30)
SHUFFLES = 100
SEED = 0


def rankings(sim: np.ndarray, benchmarks: list[str] | None = None) -> list[np.ndarray]:
    """Per-query neighbor ranking, best first. If benchmarks given, candidates
    from the query's own benchmark are excluded (cross-benchmark evaluation)."""
    s = sim.astype(np.float64).copy()
    np.fill_diagonal(s, -np.inf)
    out = []
    for q in range(len(s)):
        order = np.argsort(-s[q])[:-1]
        if benchmarks is not None:
            order = np.array([j for j in order if benchmarks[j] != benchmarks[q]])
        out.append(order)
    return out


def p_at_k(rank: list[np.ndarray], tag_sets: list[set], informative: set) -> float:
    hits = []
    for q in range(len(rank)):
        qt = tag_sets[q] & informative
        if not qt:
            continue
        hits.append(np.mean([bool(qt & tag_sets[j]) for j in rank[q][:K]]))
    return float(np.mean(hits))


def macro_map(rank: list[np.ndarray], tag_sets: list[set], tags: list[str]) -> dict[str, float]:
    out = {}
    for t in tags:
        carriers = {i for i, ts in enumerate(tag_sets) if t in ts}
        aps = []
        for q in carriers:
            rel = np.array([j in carriers for j in rank[q]])
            if not rel.any():
                continue
            prec = np.cumsum(rel) / np.arange(1, len(rel) + 1)
            aps.append(float(prec[rel].mean()))
        out[t] = float(np.mean(aps)) if aps else 0.0
    return out


def purity_at_k(rank: list[np.ndarray], labels: list[str]) -> float:
    arr = np.array(labels)
    return float(np.mean([np.mean(arr[rank[q][:K]] == arr[q]) for q in range(len(rank))]))


def evaluate(rank, tag_sets, informative, rare, benchmarks, harnesses) -> dict:
    m = macro_map(rank, tag_sets, sorted(informative))
    return {
        "p@5_informative": round(p_at_k(rank, tag_sets, informative), 4),
        "map_informative": round(float(np.mean(list(m.values()))), 4),
        "map_rare": round(float(np.mean([m[t] for t in rare])), 4),
        "per_tag_ap": {t: round(v, 4) for t, v in m.items()},
        "bench@5": round(purity_at_k(rank, benchmarks), 4),
        "harness@5": round(purity_at_k(rank, harnesses), 4),
    }


def hybrid_sim(sim_a: np.ndarray, sim_b: np.ndarray) -> np.ndarray:
    def row_ranks(s):
        s = s.astype(np.float64).copy()
        np.fill_diagonal(s, -np.inf)
        return np.argsort(np.argsort(s, axis=1), axis=1)  # higher sim = higher rank
    return (row_ranks(sim_a) + row_ranks(sim_b)).astype(np.float64)


def main() -> None:
    recs = load_renderings()
    n = len(recs)
    tags_data = json.loads((DATA / "tags.json").read_text())
    tag_of = {r["session_id"]: set(r["tags"]) for r in tags_data["results"]}
    tag_sets = [tag_of[r["session_id"]] for r in recs]
    benchmarks = [r["benchmark"] for r in recs]
    harnesses = [r["harness"] for r in recs]

    counts = {}
    for ts in tag_sets:
        for t in ts:
            counts[t] = counts.get(t, 0) + 1
    informative = {t for t, c in counts.items() if c <= INFORMATIVE_MAX}
    rare = sorted(t for t, c in counts.items() if RARE_RANGE[0] <= c <= RARE_RANGE[1])
    print(f"informative tags: {sorted(informative)}\nrare tags: {rare}\n")

    sims = dict(np.load(DATA / "sims.npz"))
    rng = np.random.default_rng(SEED)

    def table(restrict: list[str] | None) -> tuple[dict, dict]:
        res = {name: evaluate(rankings(s, restrict), tag_sets, informative, rare, benchmarks, harnesses)
               for name, s in sims.items()}
        rand_runs = [evaluate(rankings(rng.random((n, n)), restrict), tag_sets, informative,
                              rare, benchmarks, harnesses) for _ in range(SHUFFLES)]
        res["random"] = {k: round(float(np.mean([r[k] for r in rand_runs])), 4)
                         for k in rand_runs[0] if k != "per_tag_ap"}
        hyb = {f"{a}+{b}": evaluate(rankings(hybrid_sim(sims[a], sims[b]), restrict),
                                    tag_sets, informative, rare, benchmarks, harnesses)
               for a, b in itertools.combinations(sims, 2)}
        return res, hyb

    def show(title: str, res: dict, hyb: dict) -> None:
        print(f"\n=== {title} ===")
        print(f"{'method':28} {'P@5inf':>7} {'mAPinf':>7} {'mAPrare':>8} {'bench@5':>8} {'harn@5':>7}")
        for name, r in res.items():
            print(f"{name:28} {r['p@5_informative']:7.3f} {r['map_informative']:7.3f} "
                  f"{r['map_rare']:8.3f} {r['bench@5']:8.3f} {r['harness@5']:7.3f}")
        print("top hybrids by mAP rare:")
        for name, r in sorted(hyb.items(), key=lambda kv: -kv[1]["map_rare"])[:4]:
            print(f"{name:28} {r['p@5_informative']:7.3f} {r['map_informative']:7.3f} "
                  f"{r['map_rare']:8.3f} {r['bench@5']:8.3f} {r['harness@5']:7.3f}")

    results, hybrids = table(None)
    show("in-corpus retrieval", results, hybrids)
    # Behavior tags are confounded with benchmark (tau2 ⇒ confirmation conduct,
    # appworld ⇒ brute force). Cross-benchmark retrieval removes the shortcut:
    # a method only scores by finding the same conduct in a different domain.
    results_x, hybrids_x = table(benchmarks)
    show("cross-benchmark retrieval (topic shortcut removed)", results_x, hybrids_x)

    (DATA / "eval.json").write_text(json.dumps({
        "tag_counts": counts, "informative": sorted(informative), "rare": rare,
        "in_corpus": {"methods": results, "hybrids": hybrids},
        "cross_benchmark": {"methods": results_x, "hybrids": hybrids_x},
    }, indent=2))
    print("\nsaved eval.json")


if __name__ == "__main__":
    main()
