#!/usr/bin/env python3
"""LLM behavioral coding of the 300-trace corpus (the evaluation ground truth).

Two phases, mirroring qualitative open/closed coding:

  tag.py open    free-describe the conduct of a 60-trace stratified sample
                 -> data/open_codes.json (input to taxonomy design)
  tag.py closed  apply the fixed TAXONOMY below to all 300 traces
                 -> data/tags.json

The taxonomy is consolidated by hand from the open codes; rationale lives in
_FINDINGS.md. Retrieval methods never see these tags — they are reference
labels only.

Run: uv run --with litellm --python 3.12 tag.py open|closed
"""

import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from common import DATA, LAB, load_key, load_renderings, load_skeletons, truncate_text

load_key()  # must precede llm import (it reads the env)
sys.path.insert(0, str(LAB.parent / "anomaly-lab"))
import llm  # noqa: E402

SAMPLE = 60
WORKERS = 8
SKELETON_BUDGET = 7000
TRANSCRIPT_BUDGET = 6000

OPEN_PROMPT = """You are auditing the BEHAVIOR of an AI agent's execution trace.

Below are (1) an action skeleton — the structural sequence of messages, tool \
calls, result sizes, and error markers, with all content stripped — and (2) a \
truncated transcript excerpt for context.

Describe the behaviorally distinctive patterns of CONDUCT in this trace: how \
the agent acts. Examples of the kind of thing that counts: repeated identical \
or near-identical calls, retry/recovery after errors, oscillating between \
approaches, brute-force enumeration, giving up early, escalating to a human, \
verifying its own work (or never verifying), long monologues without action, \
efficient linear execution, dead/stub sessions. Do NOT describe the task \
domain or topic.

Return JSON: {{"codes": ["<short phrase>", ...]}} — 1 to 4 phrases, each at \
most 8 words, lowercase, conduct-focused.

=== ACTION SKELETON ===
{skeleton}

=== TRANSCRIPT EXCERPT ===
{transcript}
"""

# Consolidated by hand from data/open_codes.json (60-trace open coding) —
# rationale in _FINDINGS.md.
TAXONOMY: dict[str, str] = {
    "clean_linear": "executes the task in an efficient, mostly linear sequence without notable friction",
    "repeated_calls": "repeats identical or near-identical calls/queries hoping for a different result",
    "error_recovery": "hits tool/validation errors and adapts its approach to recover",
    "error_persistence": "hits the same error repeatedly without changing approach",
    "brute_force": "enumerates or sweeps many candidates/ids/parameters instead of targeted action",
    "oscillation": "alternates between approaches/services/tools without converging",
    "self_verification": "explicitly checks its own work, re-tests, or re-reads state after acting",
    "no_verification": "commits answers or state changes without any checking step",
    "early_termination": "stops, concedes, or answers well before the work is plausibly complete",
    "human_escalation": "hands off to a human agent or asks the user to take over",
    "policy_refusal": "refuses a request citing policy/capability limits, possibly resisting user pressure",
    "confirm_before_action": "asks for explicit confirmation before state-changing actions",
    "plan_tracking": "maintains explicit plans/todo bookkeeping during execution",
    "parallel_calls": "batches multiple tool calls simultaneously for efficiency",
    "degenerate_loop": "stuck repeating a cycle that makes no progress (beyond simple repeats)",
    "stub_session": "trace is empty, dead after a couple of spans, or structurally broken",
}

CLOSED_PROMPT = """You are labeling the BEHAVIOR of an AI agent's execution trace with a fixed taxonomy.

Below are (1) an action skeleton — the structural sequence of messages, tool \
calls, result sizes, and error markers, content stripped — and (2) a truncated \
transcript excerpt for context.

Apply every tag that clearly fits the agent's CONDUCT (not the task topic). \
Most traces get 1-3 tags; use more only when clearly warranted. If nothing \
distinctive applies and execution is unremarkable, use ["clean_linear"].

Taxonomy:
{taxonomy}

Return JSON: {{"tags": ["<tag>", ...]}} using only taxonomy keys.

=== ACTION SKELETON ===
{skeleton}

=== TRANSCRIPT EXCERPT ===
{transcript}
"""


def stratified_sample(recs: list[dict], n: int) -> list[int]:
    by_group: dict[tuple, list[int]] = defaultdict(list)
    for i, r in enumerate(recs):
        by_group[(r["benchmark"], r["harness"])].append(i)
    picked: list[int] = []
    groups = sorted(by_group.values(), key=len, reverse=True)
    while len(picked) < n and any(groups):
        for g in groups:
            if g and len(picked) < n:
                picked.append(g.pop(0))
    return sorted(picked)


def build_prompt(template: str, skeleton: str, rendering: str, **kw) -> str:
    return template.format(
        skeleton=truncate_text(skeleton, SKELETON_BUDGET) or "(empty)",
        transcript=truncate_text(rendering, TRANSCRIPT_BUDGET) or "(empty)",
        **kw,
    )


def run_open() -> None:
    recs = load_renderings()
    skels = {s["session_id"]: s["skeleton"] for s in load_skeletons()}
    idxs = stratified_sample(recs, SAMPLE)

    def one(i: int) -> dict:
        r = recs[i]
        prompt = build_prompt(OPEN_PROMPT, skels[r["session_id"]], r["rendering"])
        out = llm.parse_json(llm.chat(prompt, "open_coding", json_mode=True))
        return {"session_id": r["session_id"], "benchmark": r["benchmark"],
                "harness": r["harness"], "codes": out.get("codes", [])}

    with ThreadPoolExecutor(WORKERS) as ex:
        results = list(ex.map(one, idxs))
    (DATA / "open_codes.json").write_text(json.dumps(
        {"results": results, "ledger": llm.ledger_summary()}, indent=2))
    for r in results:
        print(f"{r['benchmark'][:18]:18} {r['harness'][:12]:12} {r['codes']}")


def run_closed() -> None:
    recs = load_renderings()
    skels = {s["session_id"]: s["skeleton"] for s in load_skeletons()}
    tax = "\n".join(f"- {k}: {v}" for k, v in TAXONOMY.items())

    def one(r: dict) -> dict:
        prompt = build_prompt(CLOSED_PROMPT, skels[r["session_id"]], r["rendering"], taxonomy=tax)
        out = llm.parse_json(llm.chat(prompt, "closed_coding", json_mode=True))
        tags = [t for t in out.get("tags", []) if t in TAXONOMY] or ["clean_linear"]
        return {"session_id": r["session_id"], "tags": tags}

    with ThreadPoolExecutor(WORKERS) as ex:
        results = list(ex.map(one, recs))
    (DATA / "tags.json").write_text(json.dumps(
        {"taxonomy": TAXONOMY, "results": results, "ledger": llm.ledger_summary()}, indent=2))
    from collections import Counter
    counts = Counter(t for r in results for t in r["tags"])
    for t, c in counts.most_common():
        print(f"{t:20} {c}")
    print("ledger:", llm.ledger_summary())


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "open"
    {"open": run_open, "closed": run_closed}[phase]()
