# Judging Post-v1 Candidates

Signals and analyzers cut from the stage-2 judging base (`.archive/stage-2-planning/spec-shaping/judging/`) — on merit they were close; on scope they lost. Revisit after v1 ships against real data.

**Gate for all of these: the hit-rate principle.** A promoted field earns its place only if it actually fires on real traces. Before promoting anything here (or anything marginal already in base), measure per-field hit rates on the dev dataset.

## Deferred signals (family 1)

| Candidate | What it is | Why deferred | What would change the call |
|---|---|---|---|
| `final_span_shape` | Enum for how the trace ends: `normal_completion \| error \| tool_call_unanswered \| empty_output` | Most instrumentation-dependent field in the catalog — likely low hit rate; its useful part (error-shaped endings) already feeds `failure_suspected` internally | Measured hit rate on real data turns out acceptable |
| Silent-failure continuation | Error/empty tool result followed by the agent proceeding as if nothing happened (TraceGuard's pattern) | Marginal filter value beyond existing `error_count`/`recovered_from_error`; definition needs real examples | A consumer query or failure-mode analysis that needs it |
| `context_pressure` | `max(input_tokens / model_context_window)` across LLM spans — structural precursor to the `context_overflow` failure mode | Needs a model→context-window lookup table (config maintenance). Max, not average — average washes out the moment that matters | Model-metadata table lands (shared dependency with `estimated_cost`) |
| `estimated_cost` | Tokens × per-model price table | Non-required; price table is config maintenance | Same model-metadata table as above; consumer demand for cost filtering |
| Semantic loop layer | Output-similarity confirmation for "hidden" cycles the signature-based strategies miss (per the unsupervised cycle-detection literature) | Requires embeddings — non-deterministic, against the rule-based base principle | Reframed as a derived-field analyzer (non-determinism is allowed in field *derivation*) with demonstrated misses from the deterministic strategies |
| Per-model breakdowns | Per-model token/latency aggregates within a trace | No identified consumer query | Demand |

## Deferred judge mechanics (family 2)

(Few-shot exemplars were originally tracked here; promoted to a scoped extension — [`docs/extensions/few-shot-exemplars.md`](../extensions/few-shot-exemplars.md).)

| Candidate | What it is | Why deferred | What would change the call |
|---|---|---|---|
| Hierarchical `task_category` drill-down | ~10 top-level categories + one subcategory level, classified top-down with iterative LLM calls (Clio's pattern — it classifies into 20k O*NET tasks exactly this way) | Each level multiplies calls and taxonomy maintenance; no proven demand for sub-category filters yet. The composed-call judge leaves the seam: the category call just gains a second hop | Subscriptions/bounties measurably blocked by flat categories being too coarse |
| Critical-step localization | Pinpoint the *first unrecoverable step* in a failed trace (AgentRx's core contribution: deterministic invariant checks feeding an LLM judge) | Beyond the label model — consumers filter on `failure_mode`, not step indices; invariant synthesis costs several LLM calls per trace | A consumer surface that needs step-level failure annotation (e.g. training-data exports with failure offsets) |
| Reasoning-consensus meta-judge | An extra LLM call comparing the N vote *reasonings*: flags unanimous-label / divergent-reasoning verdicts (right-answer-wrong-reason) that vote share scores as high-confidence | Split labels already route without it; the unanimous-but-wrong case it targets is unproven; +1 call per trace and the meta-judge's own reliability is uncalibrated. Self-consistency literature votes on answers and discards reasoning paths deliberately | Validation slice shows unanimous-but-wrong verdicts where the stored reasonings visibly diverge |

## Shared dependency note

`context_pressure` and `estimated_cost` both need a **model metadata table** (context window sizes, prices). Building it for either unlocks both — evaluate them together.
