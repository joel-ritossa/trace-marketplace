#!/usr/bin/env python3
"""Compute all pairwise trace-similarity matrices (pure local computation).

Six methods, one 300x300 matrix each (higher = more similar):

  feat_cos     -euclidean over robust-z numeric features (magnitude baseline)
  full_emb     cosine over whole-transcript embeddings (topic baseline)
  skel_emb     cosine over whole-skeleton embeddings
  ngram_tfidf  cosine over TF-IDF of action-token n-grams (1-3)
  seq_align    normalized indel similarity over action-token sequences
  win_chamfer  symmetric chamfer over window embeddings (locality-aware)

Writes data/sims.npz.
Run: uv run --with numpy,scikit-learn,rapidfuzz --python 3.12 methods.py
"""

import json

import numpy as np
from rapidfuzz.distance import Indel
from rapidfuzz.process import cdist
from sklearn.feature_extraction.text import TfidfVectorizer

from common import ANOMALY_DATA, DATA, cap_sequence, load_renderings, load_skeletons, skeleton_tokens


def robust_z(x: np.ndarray) -> np.ndarray:
    med = np.median(x)
    mad = np.median(np.abs(x - med)) or 1.0
    return (x - med) / (1.4826 * mad)


def normalize(emb: np.ndarray) -> np.ndarray:
    return emb / np.maximum(np.linalg.norm(emb, axis=1, keepdims=True), 1e-9)


def chamfer(win_emb: np.ndarray, owner: np.ndarray, n: int) -> np.ndarray:
    """Symmetric mean-of-best-window-match similarity between traces."""
    cross = win_emb @ win_emb.T  # 2020x2020, fine in memory
    bounds = np.searchsorted(owner, np.arange(n + 1))  # owner is sorted by trace
    sim = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        si, ei = bounds[i], bounds[i + 1]
        block_i = cross[si:ei]
        for j in range(i, n):
            sj, ej = bounds[j], bounds[j + 1]
            b = block_i[:, sj:ej]
            s = 0.5 * (b.max(axis=1).mean() + b.max(axis=0).mean())
            sim[i, j] = sim[j, i] = s
    return sim


def main() -> None:
    recs = load_renderings()
    skels = load_skeletons()
    ids = [r["session_id"] for r in recs]
    assert ids == [s["session_id"] for s in skels], "ordering mismatch"
    n = len(recs)

    feats = np.column_stack([
        robust_z(np.log1p(np.array([r["llm_calls"] for r in recs], float))),
        robust_z(np.log1p(np.array([r["tool_calls"] for r in recs], float))),
        robust_z(np.log1p(np.array([r["errors"] for r in recs], float))),
        robust_z(np.log1p(np.array([r["total_tokens"] for r in recs], float))),
        robust_z(np.array([r["n_tool_names"] for r in recs], float)),
    ])
    feat_cos = -np.linalg.norm(feats[:, None, :] - feats[None, :, :], axis=2)

    full = normalize(np.load(ANOMALY_DATA / "embeddings.npy"))
    skel = normalize(np.load(ANOMALY_DATA / "skeleton_embeddings.npy"))

    token_seqs = [skeleton_tokens(s["skeleton"]) for s in skels]

    docs = []
    for toks in token_seqs:
        grams = list(toks)
        for k in (2, 3):
            grams += ["_".join(toks[i : i + k]) for i in range(len(toks) - k + 1)]
        docs.append(grams)
    tfidf = TfidfVectorizer(analyzer=lambda d: d, sublinear_tf=True).fit_transform(docs)
    ngram_sim = np.asarray((tfidf @ tfidf.T).todense(), dtype=np.float32)

    vocab = {t: i for i, t in enumerate({t for s in token_seqs for t in s})}
    int_seqs = [cap_sequence([str(vocab[t]) for t in toks]) for toks in token_seqs]
    seq_sim = cdist(int_seqs, int_seqs, scorer=Indel.normalized_similarity, workers=-1).astype(np.float32)

    win_recs = [json.loads(line) for line in (DATA / "windows.jsonl").open()]
    win_emb = normalize(np.load(DATA / "window_embeddings.npy"))
    idx_of = {sid: i for i, sid in enumerate(ids)}
    owner = np.array([idx_of[r["session_id"]] for r in win_recs])
    assert (np.diff(owner) >= 0).all(), "windows not grouped by trace order"
    win_sim = chamfer(win_emb, owner, n)

    np.savez_compressed(
        DATA / "sims.npz",
        feat_cos=feat_cos.astype(np.float32),
        full_emb=(full @ full.T).astype(np.float32),
        skel_emb=(skel @ skel.T).astype(np.float32),
        ngram_tfidf=ngram_sim,
        seq_align=seq_sim,
        win_chamfer=win_sim,
    )
    print("saved sims.npz:", {k: "300x300" for k in
          ["feat_cos", "full_emb", "skel_emb", "ngram_tfidf", "seq_align", "win_chamfer"]})


if __name__ == "__main__":
    main()
