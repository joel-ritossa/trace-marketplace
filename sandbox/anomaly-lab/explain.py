#!/usr/bin/env python3
"""Approach 3: contrastive LLM explanation of flagged outliers.

For each chosen outlier, send its rendering plus its 3 nearest neighbors'
renderings (by skeleton geometry) and ask what this trace does behaviorally
that the comparable ones don't.

Run: uv run --with numpy --python 3.12 explain.py
"""

import json
import urllib.request
from pathlib import Path

import numpy as np

from embed import load_key

DATA = Path(__file__).parent / "data"
MODEL = "gpt-5-mini"
PER_TRACE_CAP = 12000  # chars per rendering inside the prompt

# hand-picked from the analysis: 3 skeleton (behavioral) outliers of
# different shapes + 1 full-rendering (topical) outlier as contrast
TARGETS = [
    "066de3655406_9950c2db",  # zero-tool human-transfer conversation
    "e3bfdef4aca3_c0427304",  # swebench session dead after 2 calls
    "379733137f5d_3de2a4dc",  # 154 tool calls, 4 errors
    "15bb4bab2031_7f230c54",  # top full-rendering outlier (topical?)
]

PROMPT = """You are reviewing AI-agent execution traces from a trace marketplace.
One trace was statistically flagged as unusual relative to its nearest
neighbors (the most similar traces in the corpus). Below is the flagged
trace followed by {n} comparable traces.

Explain in 2-4 sentences what the FLAGGED trace does *behaviorally* that the
comparable traces do not. Focus on agent behavior (actions, strategy,
recovery, failure shape) — not the task topic. If the trace is not actually
behaviorally unusual, say so plainly.

## FLAGGED TRACE
{target}

{neighbors}"""


def cap(t: str, n: int = PER_TRACE_CAP) -> str:
    return t if len(t) <= n else t[: n // 2] + "\n[…elided…]\n" + t[-n // 2 :]


def chat(key: str, prompt: str) -> str:
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as res:
        return json.load(res)["choices"][0]["message"]["content"]


def main() -> None:
    key = load_key()
    recs = [json.loads(l) for l in (DATA / "renderings.jsonl").open()]
    by_id = {r["session_id"]: i for i, r in enumerate(recs)}

    emb = np.load(DATA / "skeleton_embeddings.npy")
    emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
    sim = emb @ emb.T
    np.fill_diagonal(sim, -np.inf)

    out = []
    for sid in TARGETS:
        i = by_id[sid]
        r = recs[i]
        nn = np.argsort(-sim[i])[:3]
        neighbors = "\n\n".join(
            f"## COMPARABLE TRACE {j + 1} ({recs[k]['harness']} / {recs[k]['benchmark']})\n"
            + cap(recs[k]["rendering"])
            for j, k in enumerate(nn)
        )
        prompt = PROMPT.format(n=3, target=cap(r["rendering"]), neighbors=neighbors)
        print(f"\n{'=' * 70}\n{sid} ({r['harness']} / {r['benchmark']}, "
              f"llm={r['llm_calls']} tools={r['tool_calls']} err={r['errors']})")
        answer = chat(key, prompt)
        print(answer)
        out.append({"session": sid, "neighbors": [recs[int(k)]["session_id"] for k in nn],
                    "explanation": answer})

    json.dump(out, (DATA / "explanations.json").open("w"), indent=1)
    print("\nwrote data/explanations.json")


if __name__ == "__main__":
    main()
