#!/usr/bin/env python3
"""Blind pairwise verification — the check that doesn't use our own tags.

For each method: its top-10 most-similar pairs overall and its top-10
cross-benchmark pairs. Each pair (plus random controls) is judged blind by an
LLM: do these two traces share a *distinctive* behavioral pattern — conduct,
not topic? Verdicts are cached per pair, so methods retrieving the same pair
share one judgment.

Writes data/pair_eval.json.
Run: uv run --with numpy,litellm --python 3.12 pair_eval.py
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from common import DATA, LAB, load_key, load_renderings, load_skeletons, truncate_text

load_key()
sys.path.insert(0, str(LAB.parent / "anomaly-lab"))
import llm  # noqa: E402

TOP_PAIRS = 10
N_CONTROL = 15
WORKERS = 8
TRANSCRIPT_BUDGET = 3500
SKELETON_BUDGET = 2500
SEED = 0

PROMPT = """You are a strict auditor comparing the BEHAVIOR of two AI agent execution traces.

For each trace you get an action skeleton (structure only: messages, tool \
calls, result sizes, error markers) and a truncated transcript excerpt.

Procedure:
1. For trace A, list its 1-3 most distinctive behavioral patterns (conduct, \
not topic): retry/recovery style, degenerate repetition, confirm-before-acting \
discipline, brute-force enumeration, escalation moves, verification habits, \
oscillation, giving up, etc.
2. Same for trace B.
3. Verdict on the overlap:
   - "specific": the two lists share a concrete, distinctive pattern — an \
analyst would say "this agent misbehaves/behaves the same particular way in \
both". You should expect this to be RARE for arbitrary pairs.
   - "generic": they only share conduct common to most agent traces (calls \
tools, iterates step by step, recovers from an occasional error, answers the \
user, finishes the task) or a same-topic/domain resemblance.
   - "none": no meaningful behavioral overlap.

Sharing a topic, domain, task, or toolset does NOT count. Be skeptical: \
default to "generic" or "none" unless the specific match would be surprising \
between two randomly chosen traces.

Return JSON: {{"a_patterns": [...], "b_patterns": [...], "verdict": \
"specific"|"generic"|"none", "pattern": "<one sentence: the shared specific \
conduct, or why there is none>"}}

=== TRACE A SKELETON ===
{skel_a}

=== TRACE A TRANSCRIPT ===
{tr_a}

=== TRACE B SKELETON ===
{skel_b}

=== TRACE B TRANSCRIPT ===
{tr_b}
"""


def top_pairs(sim: np.ndarray, benchmarks: list[str], cross_only: bool) -> list[tuple[int, int]]:
    s = sim.copy()
    iu = np.triu_indices_from(s, k=1)
    order = np.argsort(-s[iu])
    pairs = []
    for k in order:
        i, j = iu[0][k], iu[1][k]
        if cross_only and benchmarks[i] == benchmarks[j]:
            continue
        pairs.append((int(i), int(j)))
        if len(pairs) == TOP_PAIRS:
            break
    return pairs


def main() -> None:
    recs = load_renderings()
    skels = {s["session_id"]: s["skeleton"] for s in load_skeletons()}
    benchmarks = [r["benchmark"] for r in recs]
    sims = dict(np.load(DATA / "sims.npz"))

    wanted: dict[tuple[int, int], None] = {}
    selections: dict[str, list[tuple[int, int]]] = {}
    for name, s in sims.items():
        for mode, cross in (("all", False), ("cross", True)):
            pairs = top_pairs(s, benchmarks, cross)
            selections[f"{name}/{mode}"] = pairs
            wanted.update(dict.fromkeys(pairs))

    rng = np.random.default_rng(SEED)
    n = len(recs)
    controls = []
    while len(controls) < N_CONTROL:
        i, j = sorted(rng.integers(0, n, 2).tolist())
        if i != j and (i, j) not in controls:
            controls.append((i, j))
    selections["random/control"] = controls
    wanted.update(dict.fromkeys(controls))

    def judge(pair: tuple[int, int]) -> dict:
        i, j = pair
        a, b = recs[i], recs[j]
        prompt = PROMPT.format(
            skel_a=truncate_text(skels[a["session_id"]], SKELETON_BUDGET),
            tr_a=truncate_text(a["rendering"], TRANSCRIPT_BUDGET),
            skel_b=truncate_text(skels[b["session_id"]], SKELETON_BUDGET),
            tr_b=truncate_text(b["rendering"], TRANSCRIPT_BUDGET),
        )
        out = llm.parse_json(llm.chat(prompt, "pair_judge", json_mode=True))
        return {"verdict": out.get("verdict", "none"),
                "shared": out.get("verdict") == "specific",
                "pattern": out.get("pattern", "")}

    pairs = list(wanted)
    with ThreadPoolExecutor(WORKERS) as ex:
        verdicts = dict(zip(pairs, ex.map(judge, pairs)))

    summary = {}
    for key, sel in selections.items():
        prec = float(np.mean([verdicts[p]["shared"] for p in sel]))
        summary[key] = {"precision": round(prec, 3), "n": len(sel)}
        print(f"{key:24} precision={prec:.2f}  (n={len(sel)})")

    (DATA / "pair_eval.json").write_text(json.dumps({
        "summary": summary,
        "selections": {k: [[recs[i]["session_id"], recs[j]["session_id"]] for i, j in v]
                       for k, v in selections.items()},
        "verdicts": {f"{recs[i]['session_id']}|{recs[j]['session_id']}": v
                     for (i, j), v in verdicts.items()},
        "ledger": llm.ledger_summary(),
    }, indent=2))
    print("saved pair_eval.json;", llm.ledger_summary())


if __name__ == "__main__":
    main()
