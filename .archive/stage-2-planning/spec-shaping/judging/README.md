# Judging / Analysis — Structure

How traces get analyzed, labeled, and scored. This doc owns the cross-cutting decisions (label model, storage, HIL routing, feedback loop, validation, exports); each analyzer family has its own doc to drill into.

## The three analyzer families

| # | Family | Doc | Engine | Output |
|---|---|---|---|---|
| 1 | Deterministic signals | [1_deterministic-signals.md](1_deterministic-signals.md) | Pure functions over normalized spans | Typed signals object; tier-1 filterable fields |
| 2 | Outcome judge | [2_outcome-judge.md](2_outcome-judge.md) | Custom LLM judge (zero-shot rubric; exemplar few-shot is an extension) | `outcome`, `failure_mode`, `task_category`, confidence |
| 3 | Quality metric evals | [3_quality-metrics.md](3_quality-metrics.md) | Open-source eval library (RAGAS-class) | Per-metric 0–1 scores / boolean flags |

All three run as post-ingestion worker jobs, per trace, on the analysis plumbing (`infra.md` §6): results table with analyzer name + version + output jsonb + confidence; matching-relevant fields promoted onto `traces`.

## Label model (settled)

- **Outcome is ternary:** `success | failure | indeterminate`. No graded outcome scores — humans are reliable at binary, unreliable at "this trace is a 0.7". `indeterminate` exists because some traces genuinely can't be judged (and is a valid *human* answer too — "can't tell" is a resolution, not a failure of the review UI).
- On `failure`: a `failure_mode` from a small closed taxonomy (~6–8 values, cribbed from TRAIL/AgentRx — see [2_outcome-judge.md](2_outcome-judge.md)).
- **Provenance is per-field:** `outcome`, `failure_mode`, and `task_category` each carry `machine | human_confirmed | human`. A review may resolve outcome without touching category; provenance reflects that honestly (in practice they usually move together).
- **Owner-initiated relabel:** an owner can correct any label without waiting for a review item — same resolve path, self-created item, provenance `human`. Consumer label disputes are future work.
- **Confidence and provenance are filterable columns** like any other derived field. Consumers exclude low-confidence or machine-only labels themselves (e.g. `outcome = success AND label_confidence >= 0.8`, or `provenance != machine`) — in search, subscriptions, and bounties alike.
- Quality metric scores (family 3) are **not labels** — graded derived fields for filtering, never human-adjudicated.

### Confidence formula

The stored scalar has defined semantics (consumers build queries on it):

- Base = LLM self-reported confidence.
- **Hard-capped at 0.5 when the family-1 heuristic prior disagrees** with the LLM verdict.
- Set to **1.0 on human resolution** (provenance `human` / `human_confirmed`).

## Storage shape (settled)

- **Hybrid.** The label core (`outcome`, `failure_mode`, `task_category`, per-field confidence/provenance) = real columns on `traces` — stable, check-constrained, clean SQL. Metric scores = one `metric_scores` jsonb map — that's where churn lives (library bake-off, default-set changes, enrichment); no migration per metric.
- **Null semantics:** NULL = not-yet-analyzed, and **NULL never matches any predicate**. No `pending` enum value — `indeterminate` already covers judged-but-unknowable, and the analysis-complete trigger (infra §5) keeps subscriptions from seeing half-analyzed traces.
- **Taxonomy evolution:** values stored as text with app-level validation, *not* Postgres enums. Additive = free. Rename = one UPDATE migration. Removal = soft-retire (value leaves the judge's assignable set; historical rows keep it or remap in the same migration). No analyzer re-run for any of these — re-runs are only for re-bucketing old traces into categories that didn't exist when they were judged.

## Derived-field principles

- **Closed vocabularies only. No free-form tags.** Open tag sets make rule matching mushy and bounties undefineable. Taxonomies are fixed in the spec; changing one follows the evolution policy above.
- Tier 1 = deterministic (tool names, counts, errors, duration, tokens — duration/token totals already exist from stage 1). `estimated_cost` (tokens × per-model price table) is a non-required addition / potential extension, not base. Tier 2 = LLM-derived (outcome, failure_mode, task_category, behavioral flags, metric scores).
- **Rules compose across tiers:** one filter language; `has_retry_loop = true AND duration_ms > 300000` mixes an LLM-era flag with a stage-1 aggregate.
- **Infra delta:** metric scores and confidence require numeric range predicates (`field >= x`) in the shared filter language (search, subscriptions, bounties). To be added to `infra.md` §5 when promoted.

## HIL routing

- **Only the outcome judge routes to HIL.** Nobody human-reviews a conciseness score; metric evals never create review items.
- Routing triggers: family-1 prior and LLM verdict **disagree**; LLM outputs `indeterminate`; LLM confidence below threshold; low-confidence `task_category` (a wrong category silently corrupts subscriptions, so the queue covers categories too). **Thresholds: env-var tunable, default 0.7** (one knob for outcome and category floors unless build-time evidence demands splitting).
- **Low confidence blocks nothing.** Machine verdict stored and filterable immediately; review item exists alongside; human answer overwrites with human provenance; unresolved items just leave the trace machine-labeled at low confidence.
- **No system-level gating on subscription/bounty matching.** Consumers who care add confidence/provenance predicates to their own queries. Feeds self-correct since stored queries execute live.
- **Flood control:** analysis is per-trace at ingestion, so a large first sync can produce many uncertain traces at once. Review items stay per-trace; `review_request` notifications digest per upload ("12 traces need review from upload X").
- **Re-runs:** no automatic re-judging on analyzer version bumps (base). Consideration for when a trace *is* manually re-run: supersede its open review item, never duplicate. Human-provenance fields are never overwritten by a machine re-run.

## Feedback loop

Base is minimal: human resolutions are stored with provenance and immediately correct the trace's own labels — that is the whole base loop. The judge runs zero-shot on rubric + signals. **Using human labels to improve the judge (the exemplar pool) is an extension** — see Extensions below.

No retroactive re-judging of already-labeled traces in base. Analyzer versioning (infra §6) keeps every verdict auditable.

## Validation (base scope)

Run the judge over a converted [AgentRewardBench](../../candidate-datasets.md) slice and report agreement with the expert labels; TRAIL serves the same role at span level. "Our judge agrees with human annotators X%, and disagreement routes to review" is the headline demo claim.

- Validation is an offline script + reported number, not a platform feature.
- The trajectory→OTLP **converter is a real build item** (gates validation *and* demo data) — must appear in the stage-2 build order.
- Dataset licenses still need verification before use.

## Exports

Bulk acquire gains a `labels.jsonl` (trace id, outcome, failure_mode, provenance, confidence, metric scores, analyzer versions) alongside raw payloads. Single acquire gets the same artifact (same code path). SFT/trajectory/pairs formatting is future-work narrative, not stage 2.

## Extensions

- **Evaluator training (exemplar pool).** Human-resolved traces become few-shot exemplars for the judge: an exemplar is the trace's compact rendering plus the human's verdict; the pool is a query — traces with human provenance, **listed traces only** (exemplars inject trace content into prompts judging *other users'* traces; listing is the consent act, so private uploads never become exemplars). Loop: labels → exemplars in judge prompts (same task_category preferred) → verdicts align with marketplace standards → less disagreement → fewer reviews. No training infra. Selection policy (N, recency vs diversity, minimum pool size) settled if/when picked up.
- **On-demand enrichment.** The default metric set is deliberately small (cost); enrichment lets a consumer trigger the extended catalog on traces they care about, results landing in the same results table / `metric_scores`. Open scoping questions (trigger rights, listed-only?, trace-global vs requester-scoped, cost ceiling) in [3_quality-metrics.md](3_quality-metrics.md).
- **Judge observability.** Human-agreement rate over time (cheap: `human_confirmed` vs `human` ratio on resolutions), per-category accuracy, queue throughput. Belongs to a future observability/improvement surface; not base.
- **`estimated_cost` derived field.** Tokens × per-model price table; non-required, only if it earns its keep.

## Privacy

- **Hard rule now (`AGENTS.md`):** analyzers read span `attributes` — fine — but trace bodies never leak into logs. LLM judge/eval prompts and raw outputs are never logged; only structured results are stored.
- **Deferred, must address before promote/ship:** analysis sends trace content to a third-party LLM provider — a new external data flow stage 1 didn't have. Needs explicit documentation (configured provider, env-var model) per the third-party-services rule. Parked for now.

## Open questions

Index only — each lives in its owning doc:

- Library bake-off, default metric set, `metric_scores` filter-language details — [family 3](3_quality-metrics.md).
- Enrichment and exemplar-pool scoping — extensions, settled if/when picked up.
