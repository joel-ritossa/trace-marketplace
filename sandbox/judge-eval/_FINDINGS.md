# Judge Eval — Experiment Report

2026-06-11 · Outcome judge validated on [AgentRewardBench](https://huggingface.co/datasets/McGill-NLP/agent-reward-bench) (200-trace stratified slice of 1,408 expert outcome labels) · failure-mode judge on [microsoft/AgentRx](https://huggingface.co/datasets/microsoft/AgentRx) (all 73 annotated failed trajectories) · converters `tools/arb_to_otlp.py`, `tools/agentrx_to_otlp.py` · canonical record in `docs/buildlog/stage-2/B4/002_judge-iteration.md` (outcome) and `003_failure-mode-iteration.md` (failure mode).

## TL;DR

How good are the judge's labels, and what actually moves them?

1. **Outcome: 87.9% decided agreement** with expert annotators (0.5% abstention, gpt-5-mini, prompt V3). Prompt iteration found a real asymmetry (the judge is gullible about confident final answers) but the "fix" (V2, demand evidence) *regressed* to 83.6% — the rendering truncates the evidence agents are not required to show. V3 = skepticism narrowed to *positive contradiction only* restored baseline.
2. **Failure mode: 28.9% exact root-cause / 51.1% any-annotated-category** on the production path (was 17.4%/30.4%). Roughly doubled in one pass — and **the dominant lever was an evidence bug, not a prompt**: the converter's head-only content cap dropped the decisive text (`ResponsibleAIPolicyViolation`, CAPTCHA walls) from the tails of long tracebacks. Tail-preserving capping fixed the entire guardrails→system_failure confusion class (recall 2/9 → 7/9).
3. **Capability is not the bottleneck, twice.** gpt-5 ≈ gpt-5-mini on both tasks (outcome probe: no net gain on 33 problem traces; fm probe: 21.9/28.8 vs 19.2/31.5 on identical prompt+corpus). The residual is information the trace doesn't contain.
4. **The ceiling is structural.** Both benchmarks score against *hidden* ground truth (expected DB state, the real task instruction given to a simulated user). A confident, plausible, wrong answer is invisible in-trace; `underspecified_intent` is invisible *by definition*. Realistic in-trace ceilings: outcome ~90% here, exact root-cause low-30s.

## Setup

- Converted benchmark trajectories take the **shipped pipeline** — real importer, redaction, renderer, prompts — so the numbers measure the product, not a lab harness. Ground truth lives only in a labels sidecar; it never leaks into traces.
- `app.cli.analyze agreement` is the production-path harness (gated: fm only runs when the outcome call says failure). Per-trace verdicts cache atomically, version-stamped by `JUDGE_VERSION` — interrupted runs resume, prompt revs never reuse stale verdicts.
- `fm_eval.py` (this dir) is the **unconditional** fm harness: all 73 AgentRx traces are ground-truth failures, so it bypasses the outcome gate — n 46→73, and the classifier iterates in isolation. Caches per (prompt-hash, model).
- `errors.py` dumps disagreements for reading; `compare.py` diffs two agreement runs (headline deltas, per-benchmark, flipped traces).
- Annotator semantics were mined from AgentRx's `category_reason`/`step_reason` fields — the closest thing to official category definitions — and the fm prompt was rewritten in that language (their "plan adherence" = *executed wrong*; "intent_plan_misalignment" = *conceived wrong*).

## Result 1 — Outcome prompt ladder (ARB, 200 traces)

| prompt | decided agreement | note |
|---|---|---|
| V1 | 87.9% | baseline |
| V2 (demand supporting evidence) | 83.6% | overcorrection: fails correct answers whose evidence the rendering capped; 16 broken vs 4 fixed |
| **V3 (positive contradiction only)** | **87.9%** | absent evidence is not evidence of failure |

Disagreement taxonomy: dominated by confident-wrong-answer traces (in-trace invisible), not by rendering truncation (truncated traces had *lower* error rates).

## Result 2 — Failure-mode ladder (AgentRx, unconditional, n=73)

| corpus | prompt | root-cause | any-category |
|---|---|---|---|
| head-only cap | V2 | 20.5% | 26.0% |
| head-only cap | V3 (annotator language) | 19.2% | 31.5% |
| **tail-preserving cap** | V3 | **26.0%** | **43.8%** |
| tail-preserving cap | V4 (recovery-aware boundaries) | 24.7% | 43.8% |

V4 pinned despite flat measurement: boundary rules now apply only at the unrecovered derailment point (a CAPTCHA the agent worked past must not label the trace) — strictly safer on production traces. Pinned ensemble: outcome V3 + fm V4, `JUDGE_VERSION = "5"`.

## Result 3 — Where the remaining misses live

- **Same diagnosis, different drawer.** The largest confusion cell (`intent_plan_misalignment` → `plan_adherence_failure`) is the judge citing the *same step* as the annotator — whole order cancelled instead of one item — filed as "executed wrong" vs the human's "wrong belief in the plan".
- **In-trace invisibility.** ~⅓ of AgentRx failures judge as success: the agent delivered a confident answer whose wrongness exists only in the hidden reference. 8/73 root causes are `underspecified_intent` — the simulated user misconveyed the task, undetectable from the agent's side.
- **Practical recipe:** treat exact root-cause as a triage hint, not a verdict; any-category (51%) is the fair "is the label useful" read; outcome agreement (87.9%) is the headline accuracy; and route low-confidence verdicts to HIL — the measured safety net for exactly these misses.
