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

## Library choice (open — bake-off, not locked)

Default candidate is **RAGAS**: its `AspectCritic` expresses the entire LangChain criteria list as named definitions (LangChain's `evaluation` module is semi-legacy), and it natively has the reference-free scored metrics. One dependency covering both catalogs.

Not locked. Evaluate alternatives before committing — **DeepEval** (strong agent/tool metrics, conversational G-Eval), **openevals**, or thin custom critic prompts (the AspectCritic pattern is ~a prompt template; owning it avoids a heavyweight dependency for what we use).

Decision criteria: reference-free coverage, agent-trace fit, output shape (need score + version per metric), cost control hooks, maintenance health, dependency weight inside the worker.

## The trace→sample adapter

The integration surface we own regardless of library: one function walking normalized spans to extract `(user_input, response, retrieved_contexts, tool_calls)` from `gen_ai.*` attributes into the library's sample shape. Everything downstream is library code.

## Default set vs full catalog

Every metric is N model calls per trace; running the full catalog on every upload is real cost even at demo scale. Split:

- **Default-on (~5–6):** hallucination, helpfulness, harmfulness, coherence (critics); response relevancy (always-applicable); faithfulness + goal accuracy (when applicable).
- **Extended (config / enrichment):** the rest of the criteria list, rubric-based scoring, anything situational. Env-var tunable per `AGENTS.md`.

## Output and storage

- One results row per metric run: `analyzer = "metric:<name>"`, version, score/flag in output jsonb. Reuses infra §6 plumbing unchanged.
- **Settled (README storage shape):** promoted to `traces` as one `metric_scores` jsonb map — no migration per metric; the metric set is where churn lives. Requires numeric range predicates in the shared filter vocabulary (infra delta noted in [README](README.md)).

## Extension: on-demand enrichment

Consumers can request the extended catalog on traces they care about:

- Trigger: explicit "enrich" action on a trace (or selection) → queues the non-default analyzers; results land in the same results table / promoted fields.
- Sketch-level open questions: who can trigger (acquirer? any consumer? owner?); listed-only?; are results trace-global (everyone benefits) or requester-scoped; rate/cost ceiling per user; does enrichment completion notify.
- Trace-global results are architecturally simpler (results table has no requester dimension) and make every enrichment improve the marketplace — leaning that way, unresolved.

## Open questions

- Library bake-off outcome (RAGAS vs DeepEval vs thin custom critics).
- Final default-on set and per-metric applicability rules.
- How `metric_scores` surfaces in the search UI (storage shape itself is settled: jsonb map).
- Score semantics for critics: boolean flag vs 0–1 — match whatever the chosen library emits or normalize?
- Enrichment scoping decisions above.
