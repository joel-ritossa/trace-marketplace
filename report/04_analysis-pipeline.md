# Analysis Pipeline

Every ingested trace is analyzed into labels and filterable derived fields by one worker job (`analyze_trace`, `services/api/app/worker/tasks/analyze.py`) that runs three analyzer families in sequence and persists everything in one delete-and-rewrite transaction — idempotent like ingestion, except that fields a human has touched are never machine-overwritten. Each analyzer is a pure async function `(trace rows, config) → typed result model`; the worker owns all persistence ([spec](../docs/spec/stage-2/1_analysis.md)).

## Label Model

The platform's thesis is that trace data is only worth discovering if the labels are trustworthy — so the label model is built around saying *how much* to trust each field, not just what it says:

- **`outcome` is ternary**: `success | failure | indeterminate`. `indeterminate` is a designed answer, valid from both the machine and a human — some traces genuinely can't be judged, and a forced binary would publish false consensus.
- **`failure_mode`** (on failure only) uses the AgentRx 10-category taxonomy adopted wholesale — which later lets validation compare against AgentRx's expert annotations with no mapping layer.
- **`task_category`** is a closed enum (50 values in 10 display groups, e.g. `coding`, `web_research`, `customer_ops`, `devops_infra`, `financial_analysis`, …, `other`). Closed vocabularies only, no free-form tags — a filter predicate must mean the same thing on every trace. Owners scope the judge to the categories they work in (`profiles.task_categories`, settings page): a fine-grained taxonomy is precise but invites vote splits on boundary tasks — measured at 23% low-confidence routing unscoped vs ~2% scoped — so the category prompt offers only the owner's selection plus `other`, while the marketplace filters keep the full enum.
- **Confidence and provenance are per-field and filterable.** Each label carries `machine | human_confirmed | human` provenance and a confidence with defined semantics: vote share from N judge runs, hard-capped at 0.5 when the deterministic signals disagree with the verdict, 1.0 on human resolution. Consumers exclude low-confidence or machine-only labels in their own queries; the system never gates on confidence.
- **Analyzers fail open.** Instrumentation that doesn't match expected conventions yields null, never a guess — and null never matches any filter predicate, so malformed traces drop out of subscription rules instead of polluting them. There is no `pending` placeholder value.

## Analyzer Families

### Deterministic Signals

Pure functions over the normalized spans — no model calls, run on every trace, free. The catalog: `has_retry_loop` (+ `loop_kind`: exact repeat, cycle, or stagnation — three rule-based strategies over `(tool_name, hash(args))` action signatures), `recovered_from_error`, `truncation_suspected`, `llm_call_count`, `tool_call_count`. One internal heuristic, `failure_suspected`, fires on strong structural negatives (unrecovered error ending, loop, truncation); it is never user-facing and never enters the judge prompt — its only job is to catch the judge saying `success` when the structure says otherwise (the disagreement routing trigger below).

### LLM Outcome Judge

One analyzer, three composed calls (`services/api/app/analysis/judge.py`):

1. **Outcome** — ternary verdict + reasoning from a rubric plus the full trace rendering. The clean-room call: deterministic signals are deliberately excluded, because an anchored judge can't disagree with the signals, and disagreement is what routes to human review.
2. **Failure mode** — only when the outcome is `failure`; this call *does* get deterministic evidence (loop kind, error spans), since anchoring matters for the verdict, not for diagnosing a declared failure.
3. **Task category** — over a minimal goal-focused rendering (first user message + tool names).

Each call runs N times at temperature > 0 (env-tunable, default 5 — measured: one defecting vote survives the 0.7 routing threshold at N=5 instead of routing, halving review-queue traffic for flat accuracy) and the votes fold by majority — split or abstention-majority becomes `indeterminate`, confidence = vote share, and the raw votes are stored with the result row as the audit artifact. Provider access goes through one litellm wrapper that records per-call latency, tokens, and cost into the result metadata; the judge model is an env var (default `openai/gpt-5-mini`, `services/api/app/analysis/config.py`).

What the judge sees is itself a deterministic, versioned artifact: the renderer converts spans into a chronological message list under a priority-tiered character budget — first user message, error spans, and the final K steps survive first; every cut is visibly marked; `rendering_truncated` is stored with the verdict. Mechanism and caveats: [trace-rendering explainer](../docs/explainers/trace-rendering.md).

### Quality Metrics

Graded 0–1 scores and boolean flags — filterable derived fields, never labels, never human-adjudicated. Two buckets: owned critics (hallucination, helpfulness, harmfulness, coherence, relevancy — one structured-output call each, prompt text versioned in-repo) and RAGAS v0.4 decomposed metrics (faithfulness, goal accuracy), pinned and fed by a trace→sample adapter. Two constraints shape the family: **reference-free only** (marketplace traces have no ground truth, so reference-required metrics like recall or tool-call F1 can't run here), and **applicability predicates** (faithfulness needs retrieval spans; a metric that doesn't apply produces no row, never a garbage score). Applicable metrics for a trace run concurrently; scores promote into a `metric_scores` jsonb map on `trace_analysis`, so adding a metric never needs a migration.

A fourth, smaller analyzer drafts the marketplace listing's owner-editable tags and description (fill-if-empty, never regenerated) — it produces copy, not labels, and is covered with listing in [05](05_marketplace.md).

## Degradation Without a Key

With no LLM key configured, the system degrades honestly: signals still run, the judge and metrics skip with `llm_status = 'skipped'` and a recorded reason (`not_configured`), LLM-derived fields stay null, and the UI says so — never a fake "pending". The same gate handles consent: private traces of owners who set `allow_private_llm_analysis = false` skip with `owner_opt_out` (listing the trace re-runs analysis — listing is the consent act; see [06](06_privacy-and-redaction.md)). The whole HIL loop below is exercisable on a keyless stack via a canned-verdict dev fault, which is how `tests/integration/test_hil.py` runs it in CI.

## Behavior Embeddings (Similarity)

The analysis run also embeds each trace's judge rendering into a 1536-dim vector (`openai/text-embedding-3-small` via the same litellm wrapper), stored in a pgvector table with an HNSW cosine index ([proposal](../docs/proposals/similar-behavior.md), `docs/buildlog/stage-2/similar-behavior/`). The representation wasn't guessed: a research pass (`sandbox/behavior-similarity/_FINDINGS.md`) compared whole-transcript embeddings against structural representations and window matching, and the judge rendering won (blind pairwise precision 1.0 in-corpus, 0.6 cross-benchmark vs a 0.13 base rate).

Three properties keep it inside the pipeline's rules:

- **Gated exactly like the judge** — skipped keyless and for opted-out private traces, because an embedding call sends trace content to the provider just like a judge call. A gated or permanently-failed run deletes any existing vector, keeping the table a pure function of (payload, gates).
- **An enhancement, never a blocker.** Embedding failure is logged and absorbed — labels are the product; the next analyze run retries the vector.
- **Vectors are derived sensitive data**: RLS mirrors trace visibility.

What the vectors power — the similar-traces lookup on the trace page and behavior-anchored subscriptions (a `similar_to_trace_id` + threshold predicate that ANDs with the filter query) — lives on the marketplace side, in [05](05_marketplace.md).

## Human-in-the-Loop Review

A label the judge wasn't sure about is a data-quality liability, but human attention is expensive — so only the outcome judge routes, only on recorded reasons, and each question is asked once. The four triggers (a pure function, `(signals, verdict) → reasons`): signals/judge disagreement, an `indeterminate` outcome, outcome confidence below threshold (default 0.7), and task-category confidence below the same threshold (wrong categories silently corrupt subscriptions).

Routing semantics worth knowing ([demo](../docs/demos/hil-loop.md) walks all of them live):

- **Low confidence blocks nothing.** The machine verdict is stored and filterable immediately; the review item exists alongside it.
- **The review item asks the human the same questions the judge answered**, with the machine's take shown as context — never pre-selected — beside the same span-tree evidence components as the trace page. Resolving writes `human` provenance (or `human_confirmed` when the human matches the machine) at confidence 1.0.
- **Supersede, never duplicate**: at most one open item per trace, enforced by a partial unique index, with the item written in the same transaction as the analysis rewrite — labels never commit without the item that routed them. A re-run that resolves the uncertainty supersedes the stale item without opening a new one.
- **Flood control**: `review_request` notifications digest per upload — a bulk sync produces one bell ping, not one per trace.
- **Owner relabel**: an owner corrects any label without waiting for a review item — same resolve path, self-created item, `human` provenance.

## Feedback Loops

### The Base Loop

Human resolutions are stored with provenance and immediately correct the trace's own labels — that is the whole base loop, deliberately. One subtlety makes it compound: on re-analysis, the routing-reason filter drops any reason whose target field already carries human provenance, so humans are never re-asked a question they've answered (`services/api/app/queries/analysis.py`).

### What Feedback Never Does (By Design)

No fine-tuning, no retroactive re-judging of old traces, no exemplar pool in the base system. Human-provenance fields are never overwritten by a machine re-run, and analyzer version bumps don't trigger automatic re-judging. These lines are drawn because each crossing trades auditability for accuracy that hasn't been demonstrated: a label whose history can't be explained is worse for a marketplace than a slightly staler one.

### Feedback as Validation Signal

The routing reasons double as a live read on judge quality: the agreement report (below) computes what share of judge-wrong traces carried routing reasons — i.e., how often the safety net catches the misses. Mining resolution outcomes systematically (which routing reasons most often end in a human overrule) is deferred; the data for it accumulates from day one.

### Designed-For Extensions

Two written-up designs turn accumulated human labels into judge improvement: [few-shot exemplars](../docs/extensions/few-shot-exemplars.md) (resolved traces as prompt exemplars, with budget and reproducibility mechanics) and [evaluator training](../docs/extensions/evaluator-training.md) (the pool's lifecycle, listed traces only). The schema already supports both — resolutions carry provenance, the votes and reasons are stored — so they are extensions of the prompt layer, not the data model.

## Validation

The judge produces labels consumers filter and pay on, so its quality is measured, not asserted — and measured through the *shipped* importer, renderer, and prompts, not a lab harness. Benchmark→OTLP converters (`tools/arb_to_otlp.py`, `tools/agentrx_to_otlp.py`, `tools/halubench_to_otlp.py`) turn expert-annotated benchmark trajectories into ordinary traces; offline agreement scripts run the production analyzers over them and fold verdicts against the human labels (the fold is a pure, unit-tested function — the LLM run and the arithmetic can't contaminate each other).

The numbers ([judge demo](../docs/demos/judge-agreement.md), [metrics demo](../docs/demos/metric-agreement.md) — both reproducible with one command per slice):

| What | Result | Corpus |
|---|---|---|
| Outcome agreement (decided traces) | 87.9% (0.5% abstention) | 200-trajectory AgentRewardBench slice, gpt-5-mini |
| Failure-mode category match (judge-flagged failures) | 51% any annotated category, 29% root cause exact | 73-trajectory AgentRx corpus |
| Hallucination critic vs human PASS/FAIL | 88.8% agreement, 90.4% precision | 294-trace HaluBench slice (six sources) |
| RAGAS faithfulness class separation | AUC 0.77 | same HaluBench slice |
| Task-category accuracy / routing rate | 86.8% on the 129 defensibly-labelable traces; 10.4% routed | 279 traces (ARB + AgentRx + session fixtures) |

The agreement reports also sanity-check the deterministic loop signal against AgentRewardBench's human looping annotations, and report the share of judge-wrong traces that carried HIL routing reasons. The measurement history — prompt iterations, error taxonomies, the honest ceilings (e.g. HaluBench label semantics plateau the critic near 88–89%) — is in the buildlogs: `docs/buildlog/stage-2/B4/` (judge, failure mode, task category) and `B5/` (metrics). Iteration there repeatedly found evidence bugs, not prompt problems — e.g. the task-category fix was making the session importers' first user message visible to the renderer, which took session-turn category accuracy from 50% to 100% on the six golden fixture turns and cleared 32 of 38 stale review items on the live stack (`docs/buildlog/stage-2/B4/004_task-category-iteration.md`).
