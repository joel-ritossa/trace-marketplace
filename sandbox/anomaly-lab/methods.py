#!/usr/bin/env python3
"""All anomaly-scoring methods over the 300-trace sample.

Pure local computation (no LLM calls). Returns per-method score arrays plus
clustering diagnostics; `report.py` runs the LLM evaluation on top.

Methods:
  feat_z        max |robust z| over numeric features (the classic dashboard alert)
  feat_knn      kNN distance in z-scored feature space
  full_knn      kNN distance over full-rendering embeddings
  full_kmeans   distance to own k-means centroid, full embeddings
  skel_knn      kNN distance over behavior-skeleton embeddings
  skel_kmeans   distance to own k-means centroid, skeleton embeddings
  skel_cluster_rarity   1/cluster_size from HDBSCAN over skeletons (noise = singleton)
  skel_combined rank-average of skel_knn and skel_cluster_rarity
                (the rare-but-clustered fix: distance OR tiny-cluster membership)
"""

import json
from pathlib import Path

import numpy as np
from sklearn.cluster import HDBSCAN, KMeans

DATA = Path(__file__).parent / "data"
K = 8
KMEANS_K = 20
MIN_CLUSTER = 3
SEED = 0


def knn_novelty(sim: np.ndarray, k: int = K) -> tuple[np.ndarray, np.ndarray]:
    s = sim.copy()
    np.fill_diagonal(s, -np.inf)
    idx = np.argsort(-s, axis=1)[:, :k]
    return (1 - np.take_along_axis(s, idx, axis=1)).mean(axis=1), idx


def robust_z(x: np.ndarray) -> np.ndarray:
    med = np.median(x)
    mad = np.median(np.abs(x - med)) or 1.0
    return (x - med) / (1.4826 * mad)


def rank_normalize(x: np.ndarray) -> np.ndarray:
    return np.argsort(np.argsort(x)) / (len(x) - 1)


def kmeans_score(emb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    km = KMeans(n_clusters=KMEANS_K, random_state=SEED, n_init=10).fit(emb)
    dist = np.linalg.norm(emb - km.cluster_centers_[km.labels_], axis=1)
    return dist, km.labels_


def load() -> tuple[list[dict], np.ndarray, np.ndarray]:
    recs = [json.loads(l) for l in (DATA / "renderings.jsonl").open()]
    full = np.load(DATA / "embeddings.npy")
    skel = np.load(DATA / "skeleton_embeddings.npy")
    full = full / np.linalg.norm(full, axis=1, keepdims=True)
    skel = skel / np.linalg.norm(skel, axis=1, keepdims=True)
    return recs, full, skel


def compute() -> dict:
    recs, full, skel = load()

    feats = np.column_stack([
        robust_z(np.log1p(np.array([r["llm_calls"] for r in recs], float))),
        robust_z(np.log1p(np.array([r["tool_calls"] for r in recs], float))),
        robust_z(np.log1p(np.array([r["errors"] for r in recs], float))),
        robust_z(np.log1p(np.array([r["total_tokens"] for r in recs], float))),
        robust_z(np.array([r["n_tool_names"] for r in recs], float)),
    ])

    scores: dict[str, np.ndarray] = {}
    scores["feat_z"] = np.abs(feats).max(axis=1)
    fsim = -np.linalg.norm(feats[:, None, :] - feats[None, :, :], axis=2)
    scores["feat_knn"], _ = knn_novelty(fsim)

    scores["full_knn"], _ = knn_novelty(full @ full.T)
    scores["full_kmeans"], _ = kmeans_score(full)
    scores["skel_knn"], skel_nn = knn_novelty(skel @ skel.T)
    scores["skel_kmeans"], _ = kmeans_score(skel)

    # HDBSCAN on L2-normalized skeleton vectors (euclidean ~ cosine)
    hdb = HDBSCAN(min_cluster_size=MIN_CLUSTER).fit(skel)
    labels = hdb.labels_
    sizes = np.array([1 if l == -1 else int(np.sum(labels == l)) for l in labels])
    scores["skel_cluster_rarity"] = 1.0 / sizes
    scores["skel_combined"] = (rank_normalize(scores["skel_knn"])
                               + rank_normalize(scores["skel_cluster_rarity"])) / 2

    diagnostics = {
        "hdbscan": {
            "n_clusters": int(labels.max() + 1),
            "n_noise": int(np.sum(labels == -1)),
            "cluster_sizes": sorted(np.bincount(labels[labels >= 0]).tolist(), reverse=True),
        },
        "labels": labels.tolist(),
        "skel_nn": skel_nn.tolist(),
    }
    return {"recs": recs, "scores": scores, "diagnostics": diagnostics}


if __name__ == "__main__":
    out = compute()
    for name, s in out["scores"].items():
        top = np.argsort(-s)[:5]
        print(f"{name:22}", [out['recs'][i]['session_id'] for i in top])
    print(out["diagnostics"]["hdbscan"])
