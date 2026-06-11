# Judging / Analysis — Structure

How traces get analyzed, labeled, and scored. This doc owns the cross-cutting decisions (label model, storage, HIL routing, feedback loop, validation, exports); each analyzer family has its own doc to drill into.

## The three analyzer families

| # | Family | Doc | Engine | Output |
|---|---|---|---|---|
| 1 | Deterministic signals | [1_deterministic-signals.md](1_deterministic-signals.md) | Pure functions over normalized spans | Typed signals object; tier-1 filterable fields |
| 2 | Outcome judge | [2_outcome-judge.md](2_outcome-judge.md) | Custom LLM judge (zero-shot rubric; exemplar few-shot is an extension) | `outcome`, `failure_mode`, `task_category`, confidence |
| 3 | Quality metric evals | [3_quality-metrics.md](3_quality-metrics.md) | Owned critics (open-source-seeded prompts) + RAGAS collections for decomposed metrics | Per-metric 0–1 scores / boolean flags |

All three run as post-ingestion worker jobs, per trace, on the analysis plumbing (`infra.md` §6): results table with analyzer name + version + output jsonb + confidence; matching-relevant fields promoted into the `trace_analysis` side table (1:1 with `traces`).

## Label model (settled)

- **Outcome is ternary:** `success | failure | indeterminate`. No graded outcome scores — humans are reliable at binary, unreliable at "this trace is a 0.7". `indeterminate` exists because some traces genuinely can't be judged (and is a valid *human* answer too — "can't tell" is a resolution, not a failure of the review UI).
- On `failure`: a `failure_mode` from a closed taxonomy — **AgentRx's 10-category grounded taxonomy, adopted wholesale** (see [2_outcome-judge.md](2_outcome-judge.md)).
- **Provenance is per-field:** `outcome`, `failure_mode`, and `task_category` each carry `machine | human_confirmed | human`. A review may resolve outcome without touching category; provenance reflects that honestly (in practice they usually move together).
- **Owner-initiated relabel:** an owner can correct any label without waiting for a review item — same resolve path, self-created item, provenance `human`. Consumer label disputes are future work.
- **Confidence and provenance are filterable fields** (columns on `trace_analysis`) like any other derived field. Consumers exclude low-confidence or machine-only labels themselves (e.g. `outcome = success AND label_confidence >= 0.8`, or `provenance != machine`) — in search, subscriptions, and bounties alike.
- Quality metric scores (family 3) are **not labels** — graded derived fields for filtering, never human-adjudicated.

### Confidence formula

The stored scalar has defined semantics (consumers build queries on it):

- Base = **vote share from N sampled judge runs** (self-consistency — see [2_outcome-judge.md](2_outcome-judge.md); degrades to LLM self-report when N=1). Better calibrated than self-report, which is the documented weak point of LLM judges.
- **Hard-capped at 0.5 on disagreement** — family 1's `failure_suspected` is true while the judge says `success`.
- Set to **1.0 on human resolution** (provenance `human` / `human_confirmed`).

## Storage shape (settled)

- **All derived fields live in `trace_analysis`** — a 1:1 side table keyed by `trace_id`, not new columns on `traces`. One writer per table: ingestion owns `traces`, analysis (and human resolution) owns `trace_analysis`; re-ingestion and re-analysis stay independent. Stage-1 schema untouched; one PK join in the shared filter builder; RLS mirrors `traces`. (Detailed in `infra.md` §6.)
- **Hybrid within the table.** The label core (`outcome`, `failure_mode`, `task_category`, per-field confidence/provenance) + promoted family-1 signals = real columns — stable, check-constrained, clean SQL. Metric scores = one `metric_scores` jsonb map — that's where churn lives (library bake-off, default-set changes, enrichment); no migration per metric.
- **Null semantics are structural:** no `trace_analysis` row = not yet analyzed; within a row, NULL = that analyzer hasn't produced the field. Either way, **NULL never matches any predicate**. No `pending` enum value — `indeterminate` already covers judged-but-unknowable, and the analysis-complete trigger (infra §5) keeps subscriptions from seeing half-analyzed traces.
- **Taxonomy evolution:** values stored as text with app-level validation, *not* Postgres enums. Additive = free. Rename = one UPDATE migration. Removal = soft-retire (value leaves the judge's assignable set; historical rows keep it or remap in the same migration). No analyzer re-run for any of these — re-runs are only for re-bucketing old traces into categories that didn't exist when they were judged.

## Derived-field principles

- **Closed vocabularies only. No free-form tags.** Open tag sets make rule matching mushy and bounties undefineable. Taxonomies are fixed in the spec; changing one follows the evolution policy above.
- Tier 1 = deterministic (tool names, counts, errors, duration, tokens — duration/token totals already exist from stage 1). `estimated_cost` (tokens × per-model price table) is a non-required addition / potential extension, not base. Tier 2 = LLM-derived (outcome, failure_mode, task_category, behavioral flags, metric scores).
- **Rules compose across tiers:** one filter language; `has_retry_loop = true AND duration_ms > 300000` mixes an LLM-era flag with a stage-1 aggregate.
- **Analyzers fail open.** When a trace's instrumentation doesn't match expected schema/conventions, the field is null — never a guess. Combined with "NULL never matches a predicate", malformed traces silently drop out of rules instead of polluting them.
- **Infra delta:** metric scores and confidence require numeric range predicates (`field >= x`) in the shared filter language (search, subscriptions, bounties). Added to `infra.md` §5.

## HIL routing

- **Only the outcome judge routes to HIL.** Nobody human-reviews a conciseness score; metric evals never create review items.
- Routing triggers: **disagreement** (family 1's `failure_suspected` + LLM `success` — the heuristic is failure-only and never fed into the judge prompt; layers stay independent and compose only here); outcome is `indeterminate` (abstention or split vote); outcome confidence (vote share) below threshold; low-confidence `task_category` (a wrong category silently corrupts subscriptions, so the queue covers categories too). **Thresholds: env-var tunable, default 0.7** (one knob for outcome and category floors unless build-time evidence demands splitting).
- **Low confidence blocks nothing.** Machine verdict stored and filterable immediately; review item exists alongside; human answer overwrites with human provenance; unresolved items just leave the trace machine-labeled at low confidence.
- **No system-level gating on subscription/bounty matching.** Consumers who care add confidence/provenance predicates to their own queries. Feeds self-correct since stored queries execute live.
- **Flood control:** analysis is per-trace at ingestion, so a large first sync can produce many uncertain traces at once. Review items stay per-trace; `review_request` notifications digest per upload ("12 traces need review from upload X").
- **Re-runs:** no automatic re-judging on analyzer version bumps (base). Consideration for when a trace *is* manually re-run: supersede its open review item, never duplicate. Human-provenance fields are never overwritten by a machine re-run.

## Feedback loop

Base is minimal: human resolutions are stored with provenance and immediately correct the trace's own labels — that is the whole base loop. The judge runs zero-shot on rubric + trace rendering (family-1 signals stay out of the prompt). **Using human labels to improve the judge (the exemplar pool) is an extension** — see Extensions below.

No retroactive re-judging of already-labeled traces in base. Analyzer versioning (infra §6) keeps every verdict auditable.

## Validation (base scope)

Run the judge over a converted [AgentRewardBench](../../candidate-datasets.md) slice and report agreement with the expert labels; TRAIL serves the same role at span level. "Our judge agrees with human annotators X%, and disagreement routes to review" is the headline demo claim.

- Validation is an offline script + reported number, not a platform feature. The AgentRx benchmark (115 annotated failed trajectories) joins the validation material — adopting its taxonomy makes our failure_mode labels directly comparable.
- The trajectory→OTLP **converter is a real build item** (gates validation *and* demo data) — must appear in the stage-2 build order.

## Exports

Bulk acquire gains a `labels.jsonl` (trace id, outcome, failure_mode, provenance, confidence, metric scores, analyzer versions) alongside raw payloads. Single acquire gets the same artifact (same code path). SFT/trajectory/pairs formatting is future-work narrative, not stage 2.

## Extensions

- **Few-shot exemplars.** Exemplars in the judge prompt — static seed phase + dynamic pool phase: [`extensions/few-shot-exemplars.md`](../../../../extensions/few-shot-exemplars.md).
- **Evaluator training.** The feedback loop sourcing the dynamic pool from human resolutions; listed traces only (listing is the consent act): [`extensions/evaluator-training.md`](../../../../extensions/evaluator-training.md).
- **Judge model selection.** Base ships a cheap env-var-tunable default; systematic per-model agreement/cost/calibration evaluation (and possible escalation routing) is its own extension: [`extensions/judge-model-selection.md`](../../../../extensions/judge-model-selection.md).
- **Session stitching.** Sessions as a first-class grouping over per-turn traces (stage 1 has no session concept; affects judging unit, search, exports): [`extensions/session-stitching.md`](../../../../extensions/session-stitching.md).
- **On-demand enrichment.** The default metric set is deliberately small (cost); enrichment lets a consumer trigger the extended catalog on traces they care about, results landing in the same results table / `metric_scores`. Open scoping questions (trigger rights, listed-only?, trace-global vs requester-scoped, cost ceiling) in [3_quality-metrics.md](3_quality-metrics.md).
- **Judge observability.** Human-agreement rate over time (cheap: `human_confirmed` vs `human` ratio on resolutions), per-category accuracy, queue throughput. Belongs to a future observability/improvement surface; not base.
- **`estimated_cost` derived field.** Tokens × per-model price table; non-required, only if it earns its keep.

## Privacy

- **Hard rule now (`AGENTS.md`):** analyzers read span `attributes` — fine — but trace bodies never leak into logs. LLM judge/eval prompts and raw outputs are never logged; only structured results are stored.
- **Deferred, must address before promote/ship:** analysis sends trace content to a third-party LLM provider — a new external data flow stage 1 didn't have. Needs explicit documentation (configured provider, env-var model) per the third-party-services rule. Parked for now.

## Open questions

Index only — each lives in its owning doc:

- Default metric set, `metric_scores` filter-language details, and the hands-on RAGAS-vs-our-trace-shapes verification — [family 3](3_quality-metrics.md). (Library choice is settled: critics owned with open-source-seeded prompts, RAGAS collections for faithfulness/goal accuracy; no openevals dependency anywhere.)
- Final `task_category` values (dataset validation only — no library gate) and rendering build-time details — [family 2](2_outcome-judge.md).
- Enrichment scoping — extension, settled if/when picked up.
- Exemplar-pool and judge-model-selection scoping — [`extensions/`](../../../../extensions/README.md), settled if/when picked up.
