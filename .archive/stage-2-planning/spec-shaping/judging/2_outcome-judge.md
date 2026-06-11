# Family 2: Outcome Judge

The custom LLM judge that produces the trace's labels: `outcome`, `failure_mode`, `task_category`. The one analyzer we own end-to-end rather than borrowing from a library, because disagreement routing and the label model *are* the product story. Base form is zero-shot (rubric only, no exemplars) on a cheap default model.

## Outputs

| Field | Values | Notes |
|---|---|---|
| `outcome` | `success \| failure \| indeterminate` | The label model (see [README](README.md)) |
| `failure_mode` | closed taxonomy, only on `failure` | AgentRx's 10-category taxonomy, adopted |
| `task_category` | closed enum | ~8–10 values |
| `confidence` | 0–1 | Vote share from N sampled runs (see Self-consistency voting), then the README formula |
| `reasoning` | short text | Stored with the result row; shown in review items and trace detail |

## Libraries: borrow conventions, own the judge

Surveyed the trajectory-judging landscape: **agentevals** (LangChain — `create_trajectory_llm_as_judge`, reference-free trajectory judge built on openevals' `create_llm_as_judge`), **DeepEval** (`TaskCompletionMetric` and friends), **RAGAS** (Agent Goal Accuracy, without-reference variant), **AgentRx** (Microsoft — see below), plus platform scorers (MLflow, Phoenix). Findings:

- **No library produces our label model.** Off-the-shelf trajectory judges emit a pass/fail or 0–1 score against a generic accuracy rubric. Nothing emits `outcome` + closed-taxonomy `failure_mode` + `task_category` + confidence as one structured verdict — that is a custom classification prompt no matter whose plumbing executes it. The "own it end-to-end" call survives contact with the ecosystem.
- **What we adopt are their conventions — and their prompt text.** Every library represents the trajectory as an **OpenAI-style chat message list** (user/assistant/tool messages, tool calls inline) — the de-facto interchange format for judge inputs. Our trace rendering targets that shape. Plumbing is settled (with [family 3](3_quality-metrics.md)): **no openevals dependency** — a direct structured-output call is the same code with one less import, and family 3's critics share the same call pattern. But prompt *wording* is sourced, not invented: each composed call seeds from the best published prompt for its job (see per-call notes below), copied into our own versioned prompt files.
- **AgentRx** (Microsoft, 2026) is the closest prior art to our whole layered design: it normalizes trajectories to an IR, runs deterministic invariant checks step-by-step, then an LLM judge classifies root cause into a grounded ~10-category failure taxonomy and localizes the critical failure step. Not adopted wholesale — it diagnoses *known-failed* trajectories (invariant synthesis costs several LLM calls per trace; localization is beyond our label model) — but we crib three things: its failure taxonomy (grounded across τ-bench/Flash/Magentic-One), its 115-trajectory annotated benchmark as validation material alongside AgentRewardBench/TRAIL, and its key structural lesson: **failure diagnosis conditioned on a known outcome is a separate problem from outcome detection** — which motivates the composed-call design below. Critical-step localization itself is a [follow-up candidate](../../../../follow-up/judging-post-v1-candidates.md).

So what's actually ours is the **composed label model** — the multi-field structured verdict (ternary outcome + closed-taxonomy failure_mode + category + per-field confidence) with routing semantics — because no published judge has a concept of it. Decomposed, nearly every piece is borrowed: the failure taxonomy and its judge prompt (AgentRx), the outcome rubric skeleton (openevals), the category shape (Clio), the trajectory format and rubric+CoT+structured-verdict pattern (everyone). The genuinely novel parts exist only because the product demands them: ternary outcome (indeterminate is what routes to HIL), the confidence formula (consumers query on it), and the composition wiring. No algorithm is reinvented.

## Composed judge, not one mega-call

The judge is a small pipeline of focused calls, not one prompt answering everything. This mirrors how the ecosystem composes (every library metric is its own call; Clio extracts each facet with its own prompt; AgentRx separates detection from diagnosis):

1. **Outcome call** — `outcome` + confidence + reasoning, from rubric + full trace rendering. The clean-room call: no family-1 signals (anchoring — see Judge inputs). *Prompt seed:* openevals' `TRAJECTORY_ACCURACY_PROMPT` / `TASK_COMPLETION_PROMPT` (MIT) — the closest published rubrics for "did this trajectory achieve its goal"; we keep the rubric structure and CoT framing, swap binary pass/fail for our ternary verdict + confidence.
2. **Failure-mode call** — runs only when outcome = `failure`: classifies `failure_mode` + confidence. Because the outcome is already fixed, this call **may include deterministic evidence** (`loop_kind`, error spans, retry counts) AgentRx-style — anchoring matters for the verdict, not for diagnosing an already-declared failure. Disagreement routing reads only the outcome call, so layer independence is preserved exactly where it matters. *Prompt seed:* AgentRx's own classification prompt (MIT, in its repo) — we adopted its taxonomy, so its prompt transfers near-verbatim.
3. **Category call** — `task_category` + confidence: a plain classification call over a goal-focused, much smaller rendering (first user message + tool names usually suffices). *Prompt seed:* Clio's facet-extraction prompt pattern (published in the paper appendix); thin classification, nothing to borrow beyond the pattern.

Why composed: per-field confidence falls out naturally (each call votes for its own field — see below; the README confidence formula applies to the outcome confidence); prompts stay small and single-purpose; cost is conditional (failure-mode call only on failures, category call on a fraction of the tokens). Operationally the three calls are one worker job and one results row — "the judge" remains one analyzer with one version.

## Self-consistency voting

Confidence is **vote share from N sampled runs, not self-report** — the standard better-calibrated estimator (the self-consistency pattern; RAGAS critics' `strictness` and G-Eval's logprob weighting are the same idea in other clothes). Per call:

- **Outcome call × N:** majority over a consensus threshold → the label; a split (e.g. 3-2) **or** an abstention-majority → `indeterminate`. Confidence = vote share.
- **Failure-mode call × N** (cost bounded — failures only): plurality → label; no plurality → `inconclusive`, the taxonomy's built-in abstention. Confidence = plurality share.
- **Category call × N** (cheapest call): plurality → label; a weak plurality is just a low vote share, which routes via the existing confidence knob.

**The ternary prompt stays — voting does not replace abstention.** A binary judge forced to verdict on a genuinely unjudgeable trace (cut off mid-run, no observable resolution) doesn't flip-flop; it picks its bias direction consistently — **false consensus**: 5-0 "failure", high vote share, on a trace whose honest label is "can't tell". Abstention ("the trace lacks evidence") and disagreement ("the trace is borderline") are different signals; both map to `indeterminate`, but only the prompt option captures the first.

Mechanics: N is env-var tunable (default ~3 — it multiplies the most expensive call; N=1 degrades to self-reported confidence). Sampling needs temperature > 0, so individual votes vary run-to-run — **votes are stored with the result row** as the reproducibility artifact (the verdict is auditable even though a re-run may sample differently). Family-3 critics support the same knob but default to N=1 (see [3_quality-metrics.md](3_quality-metrics.md)).

A meta-judge over the N *reasonings* (catching unanimous-label/divergent-reasoning verdicts that vote share scores as confident) is a [follow-up candidate](../../../../follow-up/judging-post-v1-candidates.md) — unproven catch rate, certain cost.

## Taxonomies

### failure_mode — settled: AgentRx's taxonomy, adopted

Grounded-theory derived across three domains (τ-bench, Flash, Magentic-One), MIT-licensed, and the most defensible published failure taxonomy. Adopting it wholesale also makes our labels directly comparable to its 115-trajectory annotated benchmark — validation for free:

| Value | AgentRx category | Meaning |
|---|---|---|
| `plan_adherence_failure` | Instruction/Plan Adherence Failure | Skips steps or adds unnecessary actions |
| `invention_of_information` | Invention of New Information | Fabricates or omits ungrounded facts |
| `invalid_invocation` | Invalid Invocation | Malformed tool call (wrong args/types/schema) |
| `tool_output_misinterpretation` | Misinterpretation of Tool Output | Incorrect reasoning about tool results |
| `intent_plan_misalignment` | Intent-Plan Misalignment | Pursues wrong objective |
| `underspecified_intent` | Underspecified User Intent | Missing information to proceed |
| `intent_not_supported` | Intent Not Supported | Action can't be performed with available tools |
| `guardrails_triggered` | Guardrails Triggered | Blocked by safety/RAI/access policies |
| `system_failure` | System Failure | Infra errors (timeouts, unreachable endpoints) |
| `inconclusive` | Inconclusive | Judged a failure, cause unattributable |

Adoption notes:

- `inconclusive` is **not** the same as outcome `indeterminate`: indeterminate = can't tell whether the trace succeeded; inconclusive = it failed, but the cause can't be attributed.
- Our earlier draft folds in cleanly: loops/repetition → `plan_adherence_failure` (family 1's `loop_kind` remains the dedicated filterable loop field, so nothing is lost); hallucinated actions → `invention_of_information`; gave_up/incomplete → `plan_adherence_failure` / `intent_plan_misalignment`; context overflow → `system_failure` (and `context_pressure` is a follow-up signal anyway).

### task_category — ours to lock (validated against the datasets)

**There is no industry-standard task-category taxonomy** at our granularity. The closest public reference is Anthropic's Clio work: its top-level usage categories (coding, writing, research/analysis, education, business ops) are the right *shape*, but its formal taxonomies — the O*NET mapping (~20k labor tasks) and the 630-cluster bottom-up set — are far too granular for rule-based filtering. Benchmark suites define domains ad hoc (web browsing, OS, DB, shopping…). Conclusion: lock our own ~8–10 values, informed by Clio's top-level split and validated against the candidate datasets.

**Clio is also the precedent for hierarchical drill-down:** it never classifies into 20k O*NET tasks directly — it builds a multi-level taxonomy and classifies top-down through the hierarchy with iterative LLM calls (the full set never fits in context). A two-level version of that (~10 top-level categories, one subcategory level, second call conditioned on the first) is the natural growth path if flat categories prove too coarse for subscriptions/bounties — deferred to [follow-up](../../../../follow-up/judging-post-v1-candidates.md), since each level multiplies calls and taxonomy maintenance, and base demand is unproven. The composed-call design already leaves the seam: the category call just gains a second hop.

Starting point — to be finalized against the actual datasets (the family-3 library gate is resolved and imposed no conventions):

- **task_category:** `web_research`, `customer_ops`, `coding`, `data_analysis`, `scheduling_planning`, `content_generation`, `retrieval_qa`, `other`.

## Judge inputs

1. **Compact trace rendering** — the spans→message-list serialization, token-budgeted (see below).
2. **Rubric** — the fixed instruction set defining each outcome/failure_mode/category, with chain-of-thought reasoning required before the verdict (standard practice: trajectory + structured rubric + CoT).

Base is zero-shot. Few-shot exemplars (static seed and dynamic pool from human resolutions) are an extension: [few-shot exemplars](../../../../extensions/few-shot-exemplars.md) — sourced via [evaluator training](../../../../extensions/evaluator-training.md).

**Family-1 signals are deliberately excluded from the outcome call.** Anchoring/prior leakage is a documented LLM-judge bias, and disagreement-based routing requires the deterministic layer and the outcome verdict to be independent — feed the judge our heuristic conclusions and agreement becomes self-fulfilling. The outcome call sees the trace itself (structure included via the rendering), never our conclusions about it. The failure-mode call is exempt (outcome already fixed; evidence aids diagnosis — see the composed-judge section).

Prompts are versioned; the analyzer-version column makes every verdict reproducible.

## Trace rendering and token budget

The rendering dominates judge quality; it is the integration surface we own regardless of library choice. On industry practice: the eval libraries themselves punt here (agentevals/DeepEval accept a message list and assume it fits; observability platforms leave truncation to the user) — the real guidance comes from the context-engineering literature (prioritized inclusion, middle-out truncation, compaction). So the design below is assembled from those patterns, not lifted from one tool.

- **Shape:** normalized spans → chronological OpenAI-style message list (the ecosystem convention), serialized into the prompt. Same spans→sample walk as family 3's trace adapter — one adapter, two consumers.
- **Scope: one trace = one judging unit.** Stage 1 defines a trace as one OTLP `trace_id`; there is no session/conversation aggregation across traces. In practice that means one agent run (root span + its tree) — if the instrumentation emits a whole multi-turn session as one trace, we judge the session; if it emits per-turn traces, we judge turns, with no visibility into sibling turns. The judge takes the trace as the unit and the rubric instructs accordingly ("judge whether *this execution* achieved its stated goal"). Cross-trace session stitching is an extension: [session stitching](../../../../extensions/session-stitching.md).
- **Token mass lives in tool outputs, not conversation.** In agent traces the dominant token cost is observations — retrieval results, file reads, API responses — not user/assistant turns. So per-step content caps on tool inputs/outputs are the highest-leverage control, applied before any step-dropping: tool blobs truncated middle-out (keep head + tail) at a per-field char cap. Conversation messages get a looser cap; the step *skeleton* (names, statuses, ordering) is cheap and never dropped.
- **Priority-tiered budget, not naive truncation.** Outcome judging is ending-heavy. Must-haves: the first user message (the goal), the final K steps (the resolution), all error spans. Optional: remaining middle steps, added newest-first until the budget is spent, with explicit elision markers ("[14 steps elided]"). Naive head/tail cutting is the documented anti-pattern (silently drops the goal or the ending).
- **Deterministic, not adaptive.** The renderer is a pure function of (trace, renderer version, config): same trace, same rendering, every run — consistent with the family-1 reproducibility principle. It *is* dynamic in the trivial sense that bigger traces get more elision, but there is no per-trace adaptive policy, no sampling, no LLM-driven selection. Config changes are version bumps.
- **Budget is env-var tunable** (per `AGENTS.md`), default sized to the cheap judge model's context with headroom.
- **`rendering_truncated` is stored with the verdict** — auditable, and a candidate confidence input if truncated verdicts measure less reliable.
- Summarization-based compaction (an LLM pre-pass over oversized traces) is the standard escalation in the context-engineering literature but adds model calls per trace and breaks rendering determinism — not base.

## Confidence and HIL routing

Routing to the review queue happens when any of:

- **Disagreement:** family 1's `failure_suspected` is true and the judge says `success`. (The heuristic is failure-only — `false` means "no opinion", so there is no disagreement check on the success side.)
- The outcome is `indeterminate` — whether from abstention or a split vote.
- Outcome confidence (vote share) falls below threshold. **Env-var tunable, default 0.7.**
- `task_category` confidence is low (wrong categories silently corrupt subscriptions; HIL covers categories too). Same 0.7 default knob.

The review item asks the human the same questions the judge answered (outcome, failure_mode if failure, category if uncertain) — answer payload is the jsonb shape from infra §4. Human answer overrides machine fields with provenance `human` (or `human_confirmed` when it matches the machine verdict).

## Model

Start cheap. The judge model is env-var tunable (per `AGENTS.md`); default is a cheap structured-output-capable model — we have OpenAI, Anthropic, and OpenRouter access, so any mini/haiku/flash-class model works and the choice is not architectural. Systematic model selection — per-model agreement vs human labels on the validation dataset, cost/latency tables, calibration, possible cheap-first escalation routing — is an extension: [judge model selection](../../../../extensions/judge-model-selection.md).

## Feedback loop

- Base: human resolutions correct the trace's labels (per-field provenance) — nothing more.
- **Extension:** resolved review items become few-shot exemplars for the judge — [evaluator training](../../../../extensions/evaluator-training.md).
- No fine-tuning, no retroactive re-judging of already-labeled traces in base.

## Validation

- Convert an AgentRewardBench slice, run the judge, report agreement vs expert labels.
- The AgentRx benchmark (115 annotated failed trajectories, each with a category from the taxonomy we adopted) validates `failure_mode` directly — same labels, no mapping layer.
- TRAIL provides span-level error annotations for additional failure_mode sanity-checking.
- The paper findings (rule-based evaluators underreport success; no single LLM judge wins everywhere) are the citable rationale for the layered design + HIL.

## Open questions

- Final `task_category` values — validate the starting set against the candidate datasets before locking. (`failure_mode` is settled: AgentRx taxonomy.)
- Voting build-time details: default N (3 vs 5), the consensus threshold for the outcome call (e.g. unanimity vs ⌈N/2⌉+1), sampling temperature.
- Rendering build-time details: K (final-step count), per-field char caps, elision marker format, default token budget; whether the category call's goal-focused rendering needs anything beyond first-message + tool names.

(Resolved: no openevals plumbing — judge calls and family-3 critics share our own structured-output pattern; prompt text is seeded from open source per the composed-call notes.)
