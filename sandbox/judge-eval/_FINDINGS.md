# Judge Eval — Experiment Report

2026-06-11 · Outcome judge validated on [AgentRewardBench](https://huggingface.co/datasets/McGill-NLP/agent-reward-bench) (200-trace stratified slice of 1,408 expert outcome labels) · failure-mode judge on [microsoft/AgentRx](https://huggingface.co/datasets/microsoft/AgentRx) (all 73 annotated failed trajectories) · task-category call on both corpora + golden session fixtures (`cat_eval.py`) · converters `tools/arb_to_otlp.py`, `tools/agentrx_to_otlp.py` · canonical record in `docs/buildlog/stage-2/B4/002_judge-iteration.md` (outcome), `003_failure-mode-iteration.md` (failure mode), and `004_task-category-iteration.md` (task category).

## TL;DR

How good are the judge's labels, and what actually moves them?

1. **Outcome: 87.9% decided agreement** with expert annotators (0.5% abstention, gpt-5-mini, prompt V3). Prompt iteration found a real asymmetry (the judge is gullible about confident final answers) but the "fix" (V2, demand evidence) *regressed* to 83.6% — the rendering truncates the evidence agents are not required to show. V3 = skepticism narrowed to *positive contradiction only* restored baseline.
2. **Failure mode: 28.9% exact root-cause / 51.1% any-annotated-category** on the production path (was 17.4%/30.4%). Roughly doubled in one pass — and **the dominant lever was an evidence bug, not a prompt**: the converter's head-only content cap dropped the decisive text (`ResponsibleAIPolicyViolation`, CAPTCHA walls) from the tails of long tracebacks. Tail-preserving capping fixed the entire guardrails→system_failure confusion class (recall 2/9 → 7/9).
3. **Task category: 86.8% on the labelable subset, 10.4% routing rate** — and the production review-queue flood (~35% of open items were category-only routes) was, for the third time, **an evidence bug, not a prompt problem**: `first_user_message` never implemented the OpenInference `input.value` fallback its own module promises, so session-ingested traces (Codex/Claude/Cursor) judged with *no user ask at all* and split coding-vs-other. The fallback fix took the session slice from 50% → 100% accuracy and 3/6 → 0/6 routed; prompt V1 survives unchanged.
4. **Taxonomy size is a routing knob, and hard scoping pays for it.** Expanding to the 50-value taxonomy (task-scope slice) *unscoped* doubled routing to 23.3% — all near-synonym boundaries (`customer_ops`↔`customer_support`, `web_research`↔`data_analysis`/`financial_analysis`). Scoping the prompt to an owner's declared categories + `other` (V2 builder) took routing to **1.8%** with finer, fully-correct session labels (6/6) and confident `other` on out-of-scope work. Record: `docs/buildlog/stage-2/task-scope/`.
5. **Capability is not the bottleneck, twice.** gpt-5 ≈ gpt-5-mini on both tasks (outcome probe: no net gain on 33 problem traces; fm probe: 21.9/28.8 vs 19.2/31.5 on identical prompt+corpus). The residual is information the trace doesn't contain.
6. **The ceiling is structural.** Both benchmarks score against *hidden* ground truth (expected DB state, the real task instruction given to a simulated user). A confident, plausible, wrong answer is invisible in-trace; `underspecified_intent` is invisible *by definition*. Realistic in-trace ceilings: outcome ~90% here, exact root-cause low-30s.

## Setup

- Converted benchmark trajectories take the **shipped pipeline** — real importer, redaction, renderer, prompts — so the numbers measure the product, not a lab harness. Ground truth lives only in a labels sidecar; it never leaks into traces.
- `app.cli.analyze agreement` is the production-path harness (gated: fm only runs when the outcome call says failure). Per-trace verdicts cache atomically, version-stamped by `JUDGE_VERSION` — interrupted runs resume, prompt revs never reuse stale verdicts.
- `fm_eval.py` (this dir) is the **unconditional** fm harness: all 73 AgentRx traces are ground-truth failures, so it bypasses the outcome gate — n 46→73, and the classifier iterates in isolation. Caches per (prompt-hash, model).
- `cat_eval.py` (this dir) is the task-category harness: the exact production category input (`first_user_message` + tool names) over arb + agentrx + golden session fixtures, cached per (prompt, model, input-text) so content-extraction changes invalidate exactly the traces they alter; `--pre-fix` reproduces the pre-pass-4 evidence bug; `--scope a,b,c` runs the owner-scoped prompt (task-scope slice). Ground truth is acceptable-category *sets* per corpus — at 50-value granularity single labels are wrong, not just coarse ("now run the tests" *is* `testing_qa`).
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

## Result 3 — Task category (cat_eval, 279 traces)

First independent measurement of the category call (the spec's "finalize
against datasets" item, done late). Ground truth only where wholesale
benchmark mappings are defensible: tau_retail → customer_ops, magentic_one
/ assistantbench → web_research, session fixtures → coding; webarena /
visualwebarena / workarena are task-level mixed and stay unlabeled
(they still count toward routing rate).

| corpus state | routing rate | labeled accuracy | sessions |
|---|---|---|---|
| pre-fix (shipped V1) | 11.5% | 84.5% | 50% acc, 3/6 routed |
| `input.value` fallback | **10.4%** | **86.8%** | **100% acc, 0/6 routed** |

- With 3 votes and a 0.7 threshold, one dissenting vote routes (2/3 =
  0.67) — so the judge's rational uncertainty about *invisible* asks was
  flooding the review queue: on the live stack ~35% of open items were
  category-only routes, ~all session traces, every dissent reasoning "no
  user request was recorded".
- Residual routing concentrates in webarena (13/50) — genuinely mixed
  tasks — and the web_research→data_analysis boundary (11/129: questions
  like "how likely is a >95°F day, given 2020-2023 data" that are honestly
  both). Routing those is the knob working as designed.
- Prompt V1 unchanged; no iteration warranted by the data.

## Result 4 — Taxonomy size × owner scoping (task-scope slice)

Same corpus, same model, after expanding the taxonomy 8 → 50 values
(superset; ground truth upgraded to acceptable-category sets — see Setup):

| configuration | routing rate | labeled accuracy | sessions |
|---|---|---|---|
| 8-value (pass-4 shipped) | 10.4% | 86.8% | 100% acc, 0/6 routed |
| 50-value, unscoped | 23.3% | 82.9% | 100% acc, 0/6 routed |
| 50-value, dev scope (7 cats) | **1.8%** | — (out-of-scope → `other`) | **100% acc (finer), 0/6 routed** |

- Granularity alone is a routing tax: every new near-synonym boundary
  (`customer_ops`↔`customer_support`, `web_research`↔`data_analysis`↔
  `financial_analysis`) is a fresh place for one of three votes to defect.
  No prompt fixes that — the boundaries are real.
- Hard scoping (prompt offers the owner's categories + `other` only,
  out-of-scope votes are malformed) deletes those boundaries instead of
  arguing about them: routing 23.3% → 1.8%, and in-scope labels get *finer*
  (the session that runs tests labels `testing_qa`, not a flat `coding`).
- Out-of-scope corpora under the dev scope fold to `other` confidently —
  correct by construction, and the reason scoped accuracy isn't comparable
  to the unscoped row.

**Vote-count probe (N=5, unscoped 50-value, same corpus).** With 3 votes a
single defector routes (2/3 = 0.67 < 0.7); with 5, one defector survives
(4/5 = 0.8) — so N=5 halves routing 23.3% → 13.3% at the same threshold,
accuracy flat (82.9% → 83.7%), labels mostly stable (20/279 flips), cost
+69% (still ~$0.004/trace). Accepting bare 3/5 pluralities (threshold 0.6)
would cut routing to 2.9%, but the 0.6-share band is only 5/8 correct vs
94/109 at unanimity — the confidence ladder is well-calibrated (1.0 → 86%,
0.8 → 75%, 0.6 → 63%), so 0.7 stays the right floor. N=5 is a pure
runtime knob (`JUDGE_VOTES`); scoped accounts barely need it (1.8% at N=3).
**Adopted: N=5 is now the stack default** (`config.py` + `.env.example`).

## Result 5 — Where the remaining misses live

- **Same diagnosis, different drawer.** The largest confusion cell (`intent_plan_misalignment` → `plan_adherence_failure`) is the judge citing the *same step* as the annotator — whole order cancelled instead of one item — filed as "executed wrong" vs the human's "wrong belief in the plan".
- **In-trace invisibility.** ~⅓ of AgentRx failures judge as success: the agent delivered a confident answer whose wrongness exists only in the hidden reference. 8/73 root causes are `underspecified_intent` — the simulated user misconveyed the task, undetectable from the agent's side.
- **Practical recipe:** treat exact root-cause as a triage hint, not a verdict; any-category (51%) is the fair "is the label useful" read; outcome agreement (87.9%) is the headline accuracy; and route low-confidence verdicts to HIL — the measured safety net for exactly these misses.
