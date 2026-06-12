# Analysis & Judging

How traces get analyzed, labeled, and scored. This doc defines the analyzer contract (the seam that lets analysis logic and platform plumbing build in parallel — see [6_build-order.md](6_build-order.md)), the label model, the three analyzer families, and HIL routing.

## The Analyzer Contract

The boundary between analysis logic and platform infrastructure:

- An **analyzer is a pure async function**: `(trace rows, config) → typed result model`. Input is the normalized `traces` row plus its `spans` rows (columns + `attributes`/`events` jsonb) — never the raw storage object. Analyzers perform no database writes, no queue operations, no HTTP handling; LLM analyzers make provider calls and nothing else.
- Every analyzer's output is a **Pydantic result model**; the worker job persists results, never the analyzer itself.
- The **routing decision is a pure function**: `(signals result, judge verdict) → list of routing reasons` (possibly empty). The worker turns reasons into review items + notifications.
- Analyzers live in an analysis package inside `services/api` (one codebase, per repo rules) with an **offline runner**: a CLI entrypoint that loads traces from the local DB or fixture files, runs any analyzer, and dumps result models as JSON. This is the analysis stream's dev/test surface; it requires no stage-2 infrastructure.

Persistence (worker side, defined in [2_data-model.md](2_data-model.md)): one `analyzer_results` row per analyzer run (analyzer name, version, output jsonb, confidence); matching-relevant fields promoted into the `trace_analysis` 1:1 side table. Analysis owns `trace_analysis` and delete-and-rewrites it per run, mirroring the ingestion invariant; re-ingestion and re-analysis stay independent.

## The Three Analyzer Families

| # | Family | Engine | Output |
|---|---|---|---|
| 1 | Deterministic signals | Pure functions over normalized spans | Typed signals object; tier-1 filterable fields |
| 2 | Outcome judge | Composed LLM calls (zero-shot rubric) | `outcome`, `failure_mode`, `task_category`, per-field confidence, reasoning |
| 3 | Quality metric evals | Owned critics + RAGAS collections | Per-metric 0–1 scores / boolean flags |

All three run in one post-ingestion `analyze_trace` worker job per trace, sequentially, writing results in one transaction at the end.

## Label Model

- **`outcome` is ternary:** `success | failure | indeterminate`. No graded outcome scores. `indeterminate` is a valid machine *and* human answer — some traces genuinely can't be judged.
- On `failure`: a **`failure_mode`** from the AgentRx 10-category taxonomy (below), adopted wholesale.
- **`task_category`**: closed enum, ~8–10 values (below).
- **Provenance is per-field:** `outcome`, `failure_mode`, `task_category` each carry `machine | human_confirmed | human`. A review may resolve outcome without touching category; provenance reflects that.
- **Confidence and provenance are filterable fields** like any other column — consumers exclude low-confidence or machine-only labels in their own queries.
- Metric scores (family 3) are **not labels** — graded derived fields, never human-adjudicated.
- **Owner-initiated relabel:** an owner corrects any label without waiting for a review item — same resolve path, self-created item, provenance `human`.

### Confidence formula

The stored scalar has defined semantics (consumers query on it):

1. Base = **vote share from N sampled judge runs** (degrades to LLM self-report at N=1).
2. **Hard-capped at 0.5 on disagreement** — family 1's `failure_suspected` true while the judge says `success`.
3. **1.0 on human resolution** (provenance `human` / `human_confirmed`).

## Derived-Field Principles

- **Closed vocabularies only; no free-form tags** — for derived *filter* fields. Taxonomies are fixed in this spec. Evolution policy: values are text with app-level validation (no Postgres enums); additive change is free, rename is one UPDATE migration, removal is soft-retire. No analyzer re-runs for taxonomy changes. (Generated listing copy is owner-editable prose, not a filter field — see [Listing Copy](#listing-copy-tags--description).)
- **Analyzers fail open.** Instrumentation that doesn't match expected conventions yields null — never a guess. **Null never matches any predicate**, so malformed traces drop out of rules instead of polluting them. No `pending` placeholder value exists; `indeterminate` already covers judged-but-unknowable.
- **One filter language across tiers:** deterministic fields (stage-1 columns, signals) and LLM-derived fields (labels, metric scores) compose in the same query.

## Family 1: Deterministic Signals

Pure functions over normalized rows. No model calls. Runs on every trace. New fields only — never duplicates stage-1 trace columns (`status`, `error_count`, `error_types`, `duration_ms`, `tool_names` stay where they are).

### Catalog

| Signal | Type | Definition |
|---|---|---|
| `has_retry_loop` | bool | Loop detection below |
| `loop_kind` | text, nullable | `exact_repeat \| cycle \| stagnation` |
| `recovered_from_error` | bool | Error span followed by successful retry then normal completion |
| `truncation_suspected` | bool | Final LLM span finish_reason `length` / output cut at max tokens |
| `llm_call_count` | int | llm-kind span count |
| `tool_call_count` | int | Tool actions: tool-kind spans, or message-embedded tool calls when the trace has none (see loop detection) |

All nullable (fail open). **Promotion is hit-rate gated:** per-field hit rates are measured on the dev dataset before the promotion list is locked at build; low-hit-rate fields are dropped, not kept as schema noise.

### Loop detection

Per tool action — tool-kind spans when the trace has any, else `tool_call` parts embedded in LLM output messages (results paired back by call id; the shape real Claude Code traces ship) — compute an action signature `(tool_name, hash(normalized_args))` and a result hash; run three strategies:

1. **Exact repeat** — same signature ≥ N consecutive times.
2. **Cycle** — repeating n-gram of signatures, period ≤ 4, ≥ 2 repetitions.
3. **Stagnation** — same tool returning an identical result hash ≥ N times.

Thresholds env-var tunable, N = 3 default. No embedding-based similarity (rule-based principle).

### Heuristic verdict: `failure_suspected`

One boolean, true on strong negatives (unrecovered error ending, loop detected, truncation), false otherwise. `false` means "no opinion", not "success" — structure can prove failure but never success. Stored on the signals result row (routing must be auditable) but **never promoted, never user-facing, never in the judge prompt**.

## Family 2: Outcome Judge

The composed LLM judge producing the trace's labels. Zero-shot (rubric only) on a cheap env-configured model; few-shot exemplars are an extension.

### Composed calls, not one mega-call

1. **Outcome call** — `outcome` + confidence + reasoning, from rubric + full trace rendering. The clean-room call: **family-1 signals are never in this prompt** (anchoring breaks disagreement-based routing). Prompt seeded from openevals' trajectory-accuracy rubrics, adapted to the ternary verdict.
2. **Failure-mode call** — only when outcome = `failure`: classifies `failure_mode`. May include deterministic evidence (`loop_kind`, error spans) — anchoring matters for the verdict, not for diagnosing a declared failure. Prompt seeded from AgentRx's classification prompt.
3. **Category call** — `task_category` over a goal-focused minimal rendering (first user message + tool names). Clio-style facet classification. The prompt's vocabulary is the owner's task scope (see Taxonomies below): the scoped values + `other`, built per trace from a versioned prompt template.

Prompt text lives in versioned prompt files; the three calls are one worker step and one results row — "the judge" is one analyzer with one version.

### Self-consistency voting

Each call runs N times (env-var, default 5, temperature > 0 — at the 0.7 routing threshold a single defecting vote routes at N=3 (2/3 = 0.67) but survives at N=5 (4/5 = 0.8), which measured as half the routing rate for the same accuracy; see the task-scope buildlog):

- **Outcome:** majority over a consensus threshold → label; a split or abstention-majority → `indeterminate`. Confidence = vote share.
- **Failure-mode:** plurality → label; none → `inconclusive` (the taxonomy's built-in abstention).
- **Category:** plurality → label; weak plurality = low vote share, routed by the confidence knob.

The ternary prompt option stays — voting does not replace abstention (a forced binary judge gives false consensus on unjudgeable traces). **The N votes are stored with the result row** as the audit artifact; the model id rides in result metadata. N=1 degrades to self-reported confidence.

### Taxonomies

**`failure_mode`** — AgentRx's taxonomy, adopted wholesale:

| Value | Meaning |
|---|---|
| `plan_adherence_failure` | Skips steps or adds unnecessary actions (incl. loops/repetition) |
| `invention_of_information` | Fabricates or omits ungrounded facts |
| `invalid_invocation` | Malformed tool call (wrong args/types/schema) |
| `tool_output_misinterpretation` | Incorrect reasoning about tool results |
| `intent_plan_misalignment` | Pursues wrong objective |
| `underspecified_intent` | Missing information to proceed |
| `intent_not_supported` | Action can't be performed with available tools |
| `guardrails_triggered` | Blocked by safety/access policies |
| `system_failure` | Infra errors (timeouts, unreachable endpoints) |
| `inconclusive` | Failed, cause unattributable (≠ outcome `indeterminate`) |

**`task_category`** — closed enum, ~50 values grouped for UI display (canonical values + one-line descriptions live in `app/analysis/models.py`; the web/desktop taxonomy files mirror it). A strict superset of the original 8-value set, so existing labels stay valid:

| Group | Values |
|---|---|
| Software engineering | `coding`, `debugging`, `code_review`, `testing_qa`, `devops_infra`, `ci_cd`, `database_admin`, `security_engineering`, `ml_engineering` |
| Data | `data_analysis`, `data_engineering`, `data_visualization`, `reporting_bi`, `financial_analysis` |
| Web & research | `web_research`, `web_automation`, `web_scraping`, `market_research`, `competitive_analysis`, `academic_research` |
| Knowledge & QA | `retrieval_qa`, `summarization`, `translation` |
| Content | `content_generation`, `technical_writing`, `copywriting`, `editing_proofreading`, `social_media` |
| Business operations | `customer_ops`, `customer_support`, `sales_outreach`, `crm_ops`, `hr_recruiting`, `legal_review`, `compliance`, `procurement`, `invoicing_billing` |
| Personal & coordination | `scheduling_planning`, `email_management`, `travel_planning`, `task_management`, `personal_assistant` |
| Operations & monitoring | `monitoring_alerting`, `incident_response`, `file_management`, `document_processing` |
| Specialized | `education_tutoring`, `design_assets`, `game_playing` |
| — | `other` |

**Owner task scope (hard scoping).** A taxonomy this size invites vote splits on boundary tasks, so owners scope it: `profiles.task_categories` holds the categories an account works in (settings page; empty = unscoped). The category call's vocabulary is the owner's selection **plus `other`** (the permanent escape hatch — it can never be deselected); empty selection means the full taxonomy. A vote outside the scoped vocabulary is a malformed vote, exactly like an out-of-enum value. Scoping constrains only the judge on *your* traces — the global enum stays the marketplace's filter vocabulary, and human resolution may pick any global value. Changing the scope is not retroactive (no automatic re-judging, consistent with the HIL rule).

### Trace rendering

The renderer is the integration surface we own; one adapter serves the judge and family 3.

- **Shape:** normalized spans → chronological OpenAI-style message list (the ecosystem convention).
- **Unit:** one trace = one judging unit (one OTLP `trace_id`; no session aggregation — extension).
- **Per-step content caps first:** tool inputs/outputs truncated middle-out at a per-field char cap (token mass lives in observations); conversation gets a looser cap; the step skeleton (names, statuses, ordering) is never dropped.
- **Priority-tiered budget:** must-haves are the first user message, the final K steps, all error spans; remaining middle steps fill the budget newest-first with explicit elision markers. When must-haves alone exceed the budget, per-step caps shrink toward a skeleton-only floor and then pre-final-K error spans are elided oldest-first (marked, never silent); the first user message and the final K steps are never dropped.
- **Deterministic:** a pure function of (trace, renderer version, config). Config changes are version bumps. Budget env-var tunable.
- **`rendering_truncated` is stored with the verdict.**

## Family 3: Quality Metric Evals

Graded scores and boolean flags per trace — filterable derived fields, **never HIL-routed**.

- **Hard constraint: reference-free only.** Marketplace traces have no ground truth; reference-required metrics (recall, answer accuracy, tool-call F1, BLEU…) cannot run here.
- **Applicability predicates:** every metric declares the trace shape it needs (faithfulness → retrieval spans; goal accuracy → discernible user goal; critics → ≥1 LLM response span). Inapplicable → no row, never a garbage score.
- **Bucket 1 — critics** (hallucination, helpfulness, harmfulness, coherence, relevancy, long-tail criteria): one structured-output call each — **owned, prompt text sourced** from openevals/RAGAS/LangChain criteria into our versioned prompt files. Output: boolean flag + reason. Same call pattern as the judge. No openevals/DeepEval dependency.
- **Bucket 2 — decomposed metrics** (faithfulness, goal accuracy): **RAGAS v0.4 `collections` API, pinned**; reference-free variants only; fed by the trace→sample adapter (`user_input`, `response`, `retrieved_contexts`, `tool_calls` extracted from `gen_ai.*` attributes).
- **Default-on set (~5–6):** hallucination, helpfulness, harmfulness, coherence, relevancy + faithfulness and goal accuracy when applicable. The extended catalog is env-config (and the on-demand-enrichment extension later).
- **Self-consistency knob exists, default N=1** for critics (cost; critics never route to HIL).
- Storage: one results row per metric run (`analyzer = "metric:<name>"`); promoted into the `metric_scores` jsonb map on `trace_analysis` — no migration per metric.

## Listing Copy (Tags + Description)

The `listing` analyzer drafts the marketplace listing's owner-editable copy — `traces.tags` and `traces.description` — so freshly ingested traces don't list bare. One LLM call over the judge rendering (judge model, no voting), run inside `analyze_trace`; never in ingestion itself, which stays a deterministic function of the raw payload.

Rules:

- **Fill-if-empty, never overwrite.** Generated copy is written only into empty fields (no tags / null description), enforced atomically in SQL so a concurrent owner edit always wins. Once set — by the owner or a previous run — re-analysis never regenerates it.
- **Copy, not labels.** Free-form prose and tags with no closed vocabulary, no confidence, no provenance columns, no HIL routing. The closed-vocabulary principle above is untouched: subscriptions and filters match on the derived label fields, never on generated copy semantics.
- **Gated like the judge:** skipped keyless and for private traces of opted-out owners. A malformed response fails open — no copy beats junk copy. One `analyzer_results` row (`analyzer = "listing"`) carries the audit output and call cost.

### Caveats (why this is copy, not data)

- **Non-deterministic.** The call samples at temperature > 0, and there is no voting fold: the same trace can yield different tags and phrasing on different runs. This is why generated tags can never be filter vocabulary — a predicate like `tag = "retry-loop"` would silently depend on which run a trace happened to get. Fill-if-empty makes the copy stable *once written*, but two identical traces may still carry different copy.
- **Search-visible.** Tags and description feed `search_tsv` (tags at A weight), so generated copy shifts full-text relevance. Acceptable for listing copy; one more reason regeneration is off.
- **Owner-attributable.** The copy lands in fields the marketplace presents as the contributor's own words. The owner can edit or clear it at any time from the trace detail page; nothing marks it as machine-written in the UI (the `listing` audit row is the provenance record).

## Behavior Summary (Gist + Steps)

The `summary` analyzer describes what the agent did — a 1-2 sentence gist plus a 3-8 bullet chronological step walkthrough — so a reviewer or prospective consumer can grasp the behavior without reading the full evidence. One LLM call over the judge rendering (judge model, no voting), run inside `analyze_trace`.

Rules:

- **Description, not a verdict.** The prompt forbids judging success; outcome stays the judge's job. Like listing copy it is prose, never a label: no closed vocabulary, no confidence, no HIL routing, no filter semantics.
- **Machine-owned, regenerated every run.** Unlike listing copy it is never owner-editable and never presented as the contributor's words, so the delete-and-rewrite regenerates it with the rest of the analysis. Non-determinism across runs is acceptable for display prose.
- **No promoted columns.** It lives in its `analyzer_results` row (`analyzer = "summary"`, which also carries call cost); `GET /v1/traces/{id}/analysis` reads it from there — no `trace_analysis` migration.
- **Gated like the judge:** skipped keyless and for private traces of opted-out owners. A malformed or empty response fails open — no summary beats junk. Not search-visible: it feeds nothing but the two display surfaces (trace-detail Analysis section, review resolve view).

## HIL Routing

**Only the outcome judge creates review items.** Routing triggers, evaluated by the pure routing function:

1. **Disagreement:** `failure_suspected` true + judge `success`.
2. Outcome `indeterminate` (abstention or split vote).
3. Outcome confidence below threshold (env-var, default 0.7).
4. `task_category` confidence below threshold (same default knob; wrong categories silently corrupt subscriptions).

Routing semantics:

- **Low confidence blocks nothing.** The machine verdict is stored and filterable immediately; the review item exists alongside; the human answer overwrites with human provenance. No system-level gating on subscription matching — consumers add confidence/provenance predicates themselves.
- The review item asks the human the same questions the judge answered; the routing reason is recorded in plain terms on the item.
- **Flood control:** review items stay per-trace; `review_request` notifications digest per upload.
- **Supersede, never duplicate:** at most one open review item per trace; a re-run supersedes the open item. Human-provenance fields are never overwritten by a machine re-run. No automatic re-judging on analyzer version bumps.

## Feedback Loop (Base)

Human resolutions are stored with provenance and immediately correct the trace's own labels — that is the whole base loop. No fine-tuning, no retroactive re-judging, no exemplar pool (extension).

## Runtime, Config, Degradation

- `analyze_trace` runs on the existing taskiq machinery: same retry/backoff/DLQ rules as ingestion ([stage-1 6_architecture.md](../stage-1/6_architecture.md)). Provider errors classify as transient (retry) unless structurally permanent; exhaustion dead-letters with the trace marked analysis-`failed`.
- **Provider layer is litellm** (pinned in `services/api`), wrapped by one client module in the analysis package — the only place LLM calls happen; provider SDKs are never imported directly. Model strings are env-config (OpenAI / Anthropic / OpenRouter all route through the same call). The wrapper records per-call latency, token usage, and cost (litellm's price map) into the analyzer's result metadata — the audit row carries what each verdict cost.
- Re-running `analyze_trace` delete-and-rewrites that trace's `analyzer_results` and `trace_analysis` rows in one transaction — idempotent by construction. Exception: fields with human provenance are preserved, never machine-overwritten.
- **No LLM key configured:** signals run; the judge and metrics skip (`llm_status = 'skipped'`, `llm_skip_reason = 'not_configured'`); fields stay null. The UI states this honestly ([4_pages.md](4_pages.md)).
- **Owner opt-out:** when the trace is **private** and its owner has `allow_private_llm_analysis = false`, the judge and metrics skip the same way (`llm_skip_reason = 'owner_opt_out'`); signals still run. Listing such a trace enqueues an `analyze_trace` re-run — listing is the consent act and covers analysis — so subscriptions only ever match fully-analyzed listed traces via the analysis-complete trigger. Flipping the setting is not retroactive: it applies to subsequent analysis runs, never triggers a sweep.
- Env vars (local-demo defaults, in `.env.example`): provider key(s), judge model, vote count N, consensus/confidence thresholds, rendering token budget + caps, loop-detection N, default metric set.

## Privacy

- Analyzers read span `attributes` — fine — but trace bodies never leak into logs. Judge/critic prompts and raw LLM outputs are never logged; only structured results are stored (the recorded votes are labels + reasoning snippets, not trace content).
- Analysis sends trace content to the configured third-party LLM provider — documented per [0_README.md](0_README.md) Third-Party Services.
- **Per-account opt-out for private traces** (`profiles.allow_private_llm_analysis`): the only trace content that reaches the provider is private traces of accounts that allow it (the default) and listed traces. The operator-level control (no key configured) remains the zero-external-flow mode.

## Validation

Offline script + reported number, not a platform feature:

- **Benchmark→OTLP converter** (a real build item): converts an AgentRewardBench slice and the AgentRx benchmark (115 annotated failed trajectories) into OTLP JSON that ingests through the stage-1 pipeline.
- **Agreement script:** runs the judge over the converted slice, reports outcome agreement vs expert labels and `failure_mode` agreement vs AgentRx (same taxonomy, no mapping layer). AgentRewardBench's human looping annotations double as a sanity check on the deterministic loop signals. (TRAIL was originally slated for span-level sanity checks but is HF-gated as of 2026-06; dropped at B4.)
- **Quality-metrics validation (B5):** the same pattern for family 3 — a HaluBench slice (single-turn RAG QA, human PASS/FAIL hallucination labels, open access) converts to the single-turn RAG trace shape and grounds both the hallucination critic (confusion matrix, balanced accuracy) and RAGAS faithfulness (AUC vs the binary label). Critic prompt iteration runs against this slice under the per-metric versioning convention.
- The headline demo claim: "our judge agrees with human annotators X%, and disagreement routes to review."

## Finalized At Build (Parameters, Not Decisions)

These are tunables and measurements, not open design questions: final `task_category` values (validated against datasets), the signal promotion list (hit-rate gated), default N and consensus threshold, rendering K / char caps / token budget, arg-normalization details for action signatures, the final default-on metric set and per-metric applicability rules, RAGAS sanity verification against our trace shapes.
