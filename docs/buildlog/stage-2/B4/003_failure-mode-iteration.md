# B4 pass 3 — failure-mode category iteration (AgentRx)

Goal: improve the judge's failure-mode *category* specifically, after pass 2
established the corpus and a first prompt rev (fm V2, root-cause 17.4% /
any-category 30.4% on judge-called failures). Experiment-report version of
this pass (with the outcome work) in `sandbox/judge-eval/_FINDINGS.md`.

## Method changes

- **Unconditional fm-eval** (`sandbox/judge-eval/fm_eval.py`): ground truth
  says all 73 AgentRx traces are failures, so the harness runs the
  failure_mode call directly (production input path: rendering + evidence
  block) without the outcome gate. n goes 46 → 73 and the classifier under
  iteration is isolated from outcome-call drift. Caches per
  (prompt-hash, model).
- **Annotator-language mining**: the AgentRx annotations carry
  `category_reason`/`step_reason` per failure — the closest thing to
  official category definitions. Mined per category to write definitions in
  the annotators' own semantics (e.g. their "plan adherence" is
  *executed wrong* — skipped confirmations, ignored stated constraints —
  while "intent_plan_misalignment" is *conceived wrong* — a plan built on a
  false assumption about what policy allows).

## The decisive find: an evidence bug, not a prompt problem

gpt-5 (capability probe) still classified 5/9 guardrails traces as
`system_failure` despite an explicit boundary rule. Reading the raw traces:
the annotators' root cause (`ResponsibleAIPolicyViolation`, CAPTCHA text)
sits at the *tail* of long final tracebacks, and the converter's head-only
4000-char cap dropped it — the judge saw a generic openai-client stack and
answered defensibly wrong. The app renderer middle-out caps (head + tail),
so the loss was purely `tools/agentrx_to_otlp.py`; its cap is now
head+tail (last 1000 chars preserved). `tools/arb_to_otlp.py` keeps its
head-only cap deliberately: it caps accessibility trees (head is the
informative part) and 1000-char error strings, and regenerating would
invalidate the pass-2 outcome measurement history.

## Measurements (unconditional fm-eval, n=73, gpt-5-mini unless noted)

| corpus | prompt | root-cause | any-category |
|---|---|---|---|
| head-only cap | fm V2 | 20.5% | 26.0% |
| head-only cap | fm V3 | 19.2% | 31.5% |
| head-only cap | fm V3 (gpt-5) | 21.9% | 28.8% |
| tail-preserving | fm V3 | **26.0%** | **43.8%** |
| tail-preserving | fm V4 | 24.7% | 43.8% |

- **fm V3**: definitions rewritten in annotator language, multi-agent
  framing (a worker's reply is a tool output), three discrimination rules
  for the measured confusion boundaries. Moves any-category (+5.5pts on the
  old corpus); root-cause flat.
- **Evidence fix** is the dominant lever (+7/+12 pts): guardrails recall
  went 2/9 → 7/9 and the system_failure over-prediction collapsed.
- **fm V4**: V3's absolute guardrails rule over-triggered once the evidence
  became visible (policy errors the agent recovered from still pulled
  votes). V4 subordinates all boundary rules to the
  earliest-unrecovered-derailment rule. Measured flat (±1 trace) but
  strictly more correct for production traces — a recovered CAPTCHA must
  not label the whole trace — so V4 is pinned. `JUDGE_VERSION = "5"`.
- **Capability probe**: gpt-5 ≈ gpt-5-mini (21.9/28.8 vs 19.2/31.5, same
  prompt/corpus). The residual is not model capability.

## Full pipeline (production path, `out/agentrx-judge5`)

| | pass 2 (judge v4) | pass 3 (judge v5, fixed corpus) |
|---|---|---|
| root-cause match | 17.4% (8/46) | **28.9% (13/45)** |
| any-category match | 30.4% (14/46) | **51.1% (23/45)** |
| outcome decided agreement | 63.9% | 62.5% (noise; outcome prompt untouched) |

## Residual, honestly

The remaining confusion mass sits on boundaries where judge and annotator
describe the *same mistake* with different labels: cancelled the whole
order instead of one item → judge says executed-wrong
(plan_adherence), annotator says conceived-wrong (false belief that partial
cancellation works → intent_plan_misalignment). Verified by reading the
diagonal: the judge's step citations match the annotators' step_reasons.
Plus the structural information limit: `underspecified_intent` requires
knowing the hidden task instruction the simulated user failed to convey —
invisible in-trace by definition. Further prompt iteration churns within
noise (V4 vs V3 demonstrated); the honest ceiling for in-trace root-cause
attribution on this corpus is likely in the low-30s.
