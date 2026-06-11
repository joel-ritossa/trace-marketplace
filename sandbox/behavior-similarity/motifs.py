#!/usr/bin/env python3
"""RQ3 — unsupervised discovery of recurring behavioral motifs.

Clusters the window embeddings (local stretches of conduct) with HDBSCAN.
A cluster whose windows span many traces and several benchmarks is a
candidate recurring motif. An LLM names each candidate from sample windows —
with an explicit out to call it boilerplate or a harness artifact.

Writes data/motifs.json.
Run: uv run --with numpy,scikit-learn,litellm --python 3.12 motifs.py
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from sklearn.cluster import HDBSCAN

from common import DATA, LAB, load_key, load_renderings

load_key()
sys.path.insert(0, str(LAB.parent / "anomaly-lab"))
import llm  # noqa: E402

MIN_CLUSTER = 8
TOP_CLUSTERS = 15
SAMPLES_PER_CLUSTER = 5
WORKERS = 8

PROMPT = """Below are {n} window excerpts from DIFFERENT AI-agent execution traces. Each
is an action skeleton: roles, tool calls, result sizes, error markers — content
stripped. They were clustered together as a candidate recurring behavior.

Name the recurring behavioral MOTIF these windows share, focusing on conduct
(how the agent acts), not topic. If the commonality is just harness boilerplate
(same tool framework), a benchmark's scripted structure, or too generic to be
a behavior ("agent calls tools"), say so via kind.

Return JSON: {{"kind": "behavior"|"boilerplate"|"generic", "name": "<3-6 word
motif name>", "description": "<one sentence>"}}

{windows}
"""


def main() -> None:
    recs = load_renderings()
    meta = {r["session_id"]: r for r in recs}
    wins = [json.loads(line) for line in (DATA / "windows.jsonl").open()]
    emb = np.load(DATA / "window_embeddings.npy")
    emb = emb / np.maximum(np.linalg.norm(emb, axis=1, keepdims=True), 1e-9)

    labels = HDBSCAN(min_cluster_size=MIN_CLUSTER).fit(emb).labels_
    n_clusters = labels.max() + 1
    print(f"{n_clusters} clusters, {(labels == -1).sum()} noise windows of {len(wins)}")

    clusters = []
    for c in range(n_clusters):
        idx = np.where(labels == c)[0]
        sids = [wins[i]["session_id"] for i in idx]
        benches = {meta[s]["benchmark"] for s in sids}
        harns = {meta[s]["harness"] for s in sids}
        centroid = emb[idx].mean(axis=0)
        order = idx[np.argsort(-emb[idx] @ centroid)]
        # sample windows from distinct traces, nearest-to-centroid first
        seen, sample = set(), []
        for i in order:
            if wins[i]["session_id"] not in seen:
                seen.add(wins[i]["session_id"])
                sample.append(int(i))
            if len(sample) == SAMPLES_PER_CLUSTER:
                break
        clusters.append({
            "cluster": c, "n_windows": len(idx), "n_traces": len(set(sids)),
            "n_benchmarks": len(benches), "benchmarks": sorted(benches),
            "n_harnesses": len(harns), "sample_idx": sample,
        })

    clusters.sort(key=lambda x: -x["n_traces"])
    to_name = clusters[:TOP_CLUSTERS]

    def name(cl: dict) -> dict:
        blocks = "\n\n".join(
            f"--- window {k + 1} ---\n{wins[i]['text'][:1500]}"
            for k, i in enumerate(cl["sample_idx"]))
        out = llm.parse_json(llm.chat(
            PROMPT.format(n=len(cl["sample_idx"]), windows=blocks), "motif_naming", json_mode=True))
        return {k: out.get(k, "") for k in ("kind", "name", "description")}

    with ThreadPoolExecutor(WORKERS) as ex:
        for cl, named in zip(to_name, ex.map(name, to_name)):
            cl.update(named)

    for cl in to_name:
        print(f"[{cl['kind']:11}] {cl['name']:42} traces={cl['n_traces']:3} "
              f"windows={cl['n_windows']:3} benchmarks={cl['n_benchmarks']}")

    (DATA / "motifs.json").write_text(json.dumps({
        "params": {"min_cluster_size": MIN_CLUSTER},
        "n_clusters": int(n_clusters), "n_noise": int((labels == -1).sum()),
        "clusters": [{k: v for k, v in cl.items() if k != "sample_idx"} for cl in clusters],
        "ledger": llm.ledger_summary(),
    }, indent=2))
    print("saved motifs.json")


if __name__ == "__main__":
    main()
