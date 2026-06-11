# Family 3: Quality Metric Evals

Traditional LLM-as-judge eval metrics (LangChain-criteria / RAGAS-class), run as analyzers producing graded scores and boolean flags per trace. **Not labels, never HIL-routed** — these are filterable derived fields ("helpfulness ≥ 0.8 AND no hallucination flag").

## The hard constraint: reference-free only

Marketplace traces arrive with no ground truth — no reference answer, no expected tool calls, no reference topics. That filters the standard catalogs into:

| Bucket | Metrics | Usable? |
|---|---|---|
| Reference-free criteria | hallucination, conciseness, relevance, coherence, harmfulness, maliciousness, helpfulness, controversiality, misogyny, criminality, insensitivity (the LangChain `EVAL_TYPES` list) | Yes — boolean critic-style |
| Reference-free scored | Response Relevancy, Faithfulness (vs retrieved context *in the trace*), Agent Goal Accuracy (without-reference variant), Aspect Critic, Simple Criteria / Rubrics scoring | Yes |
| Reference-required | Context Recall/Entities Recall, Noise Sensitivity, Answer Accuracy, Factual Correctness, Tool Call Accuracy/F1, Topic Adherence, Semantic Similarity, BLEU/CHRF/ROUGE, Exact Match, String Presence, SQL equivalence, Summarization-vs-source | No — nothing to compare against on organic uploads |

Reference-required metrics are what benchmark harnesses use (which is why the candidate datasets arrive pre-labeled); they cannot run here.

## Applicability predicates

Every metric declares what trace shape it needs; inapplicable → no row, never a garbage score.

- Faithfulness → requires retrieval spans / retrieved-context attributes.
- Goal accuracy → requires a discernible user goal (an initial user message).
- Critic metrics → require at least one LLM response span.

## Library choice (settled: split by bucket)

The catalog hides two different kinds of work, and the library decision splits along that line:

- **Bucket 1 — critics** (hallucination, helpfulness, harmfulness, coherence, relevancy, the long-tail criteria): each is a single structured-output call — rendering + criterion definition → flag + reason. There is no algorithm; the metric *is* the prompt. **Owned, not imported — but the prompt text is sourced from open source.** Copy the proven wordings (openevals' MIT-licensed prebuilt prompts: `HALLUCINATION_PROMPT`, `CONCISENESS_PROMPT`, `TOXICITY_PROMPT`, `RAG_GROUNDEDNESS_PROMPT`, `RAG_HELPFULNESS_PROMPT`…; RAGAS `AspectCritic` definitions; LangChain's legacy criteria definitions for the long tail) into our own versioned prompt files, executed through the same structured-output call pattern as the family-2 judge. Best of both: battle-tested prompt text, our plumbing/versioning/output shape — strictly better than importing a library for a prompt template, or writing wordings from scratch.
- **Bucket 2 — decomposed metrics** (faithfulness, goal accuracy): genuinely non-trivial machinery worth borrowing — faithfulness is statement extraction → per-statement verification against in-trace retrieved context. **RAGAS v0.4 `collections` API**, pinned: reference-free variants survived the rewrite (`Faithfulness`, `AgentGoalAccuracyWithoutReference`), it works with a raw OpenAI client (no LangChain wrapper since v0.4), and `MetricResult` carries `.value` + `.reason` — matching our stored-row shape natively. Risk noted: v0.4 is mid-migration (legacy API removed in v1.0; repo ownership recently changed) — we use collections-only and pin.

Ruled out:

- **DeepEval** — broadest catalog, but it's a framework with import-time side effects (autoloads `.env`, registers a pytest plugin, telemetry on by default with process-level opt-out) and platform gravity toward Confident AI. Wrong shape to embed inside a taskiq worker.
- **openevals as a dependency** — it's call-pattern primitives, which we already have via the family-2 judge pattern; its value to us is the prompt *text*, which is MIT and copyable without the import. (This also closes family 2's open question: no openevals plumbing anywhere.)
- **RAGAS `ResponseRelevancy`** — its recipe needs an embeddings client (LLM generates questions from the answer, scores by cosine similarity vs the original question). That would be the only embeddings dependency in the system, for a metric expressible more reliably as a bucket-1 critic ("is this response relevant to the user's request"). Relevancy is a critic.

## The trace→sample adapter

The integration surface we own regardless of library: one function walking normalized spans to extract `(user_input, response, retrieved_contexts, tool_calls)` from `gen_ai.*` attributes. Two consumers: bucket-1 critics take the message-list rendering (shared with the family-2 judge); RAGAS collections metrics take the extracted fields as keyword arguments (the v0.4 API — no sample objects).

## Default set vs full catalog

Every metric is N model calls per trace; running the full catalog on every upload is real cost even at demo scale. Split:

- **Default-on (~5–6):** hallucination, helpfulness, harmfulness, coherence, relevancy (critics — always-applicable except per the predicates above); faithfulness + goal accuracy (RAGAS, when applicable).
- **Extended (config / enrichment):** the rest of the criteria list, rubric-based scoring, anything situational. Env-var tunable per `AGENTS.md`.

## Self-consistency on critics: knob exists, default off

The family-2 judge runs each classification call N times and uses vote share as confidence ([2_outcome-judge.md](2_outcome-judge.md)). Critics support the same knob (it's the same call pattern; RAGAS `strictness` is the same idea) but **default to N=1**: multiplying 5–6 critics × N on every trace is the cost-explosion spot, and critics never route to HIL, so calibrated confidence buys less here. If a graded 0–1 is ever wanted from a boolean critic, vote share provides it for free — turn the knob, no redesign. Decomposed RAGAS metrics don't need it (per-statement verification is their internal granularity).

## Output and storage

- One results row per metric run: `analyzer = "metric:<name>"`, version, score/flag in output jsonb. Reuses infra §6 plumbing unchanged.
- **Settled (README storage shape):** promoted to `trace_analysis` as one `metric_scores` jsonb map — no migration per metric; the metric set is where churn lives. Requires numeric range predicates in the shared filter vocabulary (infra delta noted in [README](README.md)).

## Extension: on-demand enrichment

Consumers can request the extended catalog on traces they care about:

- Trigger: explicit "enrich" action on a trace (or selection) → queues the non-default analyzers; results land in the same results table / promoted fields.
- Sketch-level open questions: who can trigger (acquirer? any consumer? owner?); listed-only?; are results trace-global (everyone benefits) or requester-scoped; rate/cost ceiling per user; does enrichment completion notify.
- Trace-global results are architecturally simpler (results table has no requester dimension) and make every enrichment improve the marketplace — leaning that way, unresolved.

## Open questions

- **Hands-on verification (follow-up): RAGAS collections metrics against our actual trace shapes.** Faithfulness/goal accuracy were designed for RAG conversations, not agent traces — does the adapter's `(user_input, response, retrieved_contexts)` extraction produce sane scores on real agent trajectories? Also verify cost hooks (per-metric model override, token usage exposure).
- Final default-on set and per-metric applicability rules.
- How `metric_scores` surfaces in the search UI (storage shape itself is settled: jsonb map).
- Enrichment scoping decisions above.

(Resolved: library choice — split by bucket above. Critic score semantics — ours to define since we own the critic prompts: boolean flag + reason.)
