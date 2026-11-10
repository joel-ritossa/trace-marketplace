# Analysis & Judging

How traces get analyzed and labeled. This doc defines the analyzer contract (the seam that lets analysis logic and platform plumbing build in parallel — see [6_build-order.md](6_build-order.md)), the deterministic signals, the taxonomies, and the privacy rules.

> **Partly superseded by [9_session-analysis.md](9_session-analysis.md)** (owner decision, 2026-11-10); where the two disagree, 9 wins. Superseded and now one-line pointers below: the outcome judge (composed calls, voting, confidence formula), the ternary label model and per-field provenance, quality metric evals, the standalone listing-copy and behavior-summary calls, HIL routing and the feedback loop, trace rendering for the judge, the litellm provider layer, and the vote/metric/rendering env vars. Still current here: the analyzer contract, deterministic signals (now computed per turn), taxonomies, derived-field principles, privacy, validation.

## The Analyzer Contract

The boundary between analysis logic and platform infrastructure:

- An **analyzer is a pure async function**: `(trace rows, config) → typed result model`. Input is the normalized `traces` row plus its `spans` rows (columns + `attributes`/`events` jsonb) — never the raw storage object. Analyzers perform no database writes, no queue operations, no HTTP handling; the agent judge makes OpenAI calls and reads the in-memory trace through its tools, nothing else.
- Every analyzer's output is a **Pydantic result model**; the worker job persists results, never the analyzer itself.
- Analyzers live in an analysis package inside `services/api` (one codebase, per repo rules) with an **offline runner** (`python -m app.cli.analyze`): loads traces from the local DB or fixture files, runs the analyzers, and dumps result models as JSON. This is the analysis stream's dev/test surface; it requires no stage-2 infrastructure.

Persistence (worker side, defined in [2_data-model.md](2_data-model.md)): per-turn verdicts in `turn_analysis` + `trace_labels`, the session roll-up and promoted signal columns in the `trace_analysis` 1:1 side table, one `analyzer_results` audit row per LLM run (model, usage, tool-call counts). Analysis owns these tables; re-ingestion and re-analysis stay independent. Re-analysis is incremental (a turn is re-judged only when its fingerprint changes — [9_session-analysis.md](9_session-analysis.md)), not delete-and-rewrite.

## Analyzer Families

| # | Family | Engine | Output |
|---|---|---|---|
| 1 | Deterministic signals | Pure functions over normalized spans, per turn | Typed signals object; tier-1 filterable fields |
| 2 | Agent judge | One OpenAI Agents SDK agent per turn + a tool-less session roll-up | Per-turn verdicts, session verdict ([9_session-analysis.md](9_session-analysis.md)) |

Quality metric evals (the former family 3: critics + RAGAS) are retired; the `ragas` dependency and `metric_scores` are gone.

## Labels

Defined in [9_session-analysis.md](9_session-analysis.md): `outcome` is `success | partial | failure | indeterminate` (`indeterminate` is a valid answer — some turns genuinely can't be judged); `task_category` and `failure_mode` are multi-select sets, per turn and (as the union) per session; every `failure_mode` cites the spans that show it. Provenance is per turn (`machine | human`). There are no confidence scores.

## Derived-Field Principles

- **Closed vocabularies only; no free-form tags** — for derived *filter* fields. Taxonomies are fixed in this spec. Evolution policy: values are text with app-level validation (no Postgres enums); additive change is free, rename is one UPDATE migration, removal is soft-retire. No analyzer re-runs for taxonomy changes. (Generated listing copy is owner-editable prose, not a filter field — see [Listing Copy](#listing-copy-tags--description).)
- **Analyzers fail open.** Instrumentation that doesn't match expected conventions yields null — never a guess. **Null never matches any predicate**, so malformed traces drop out of rules instead of polluting them. No `pending` placeholder value exists; `indeterminate` already covers judged-but-unknowable.
- **One filter language across tiers:** deterministic fields (stage-1 columns, signals) and LLM-derived fields (outcome, categories, failure modes) compose in the same query.

## Family 1: Deterministic Signals

Pure functions over normalized rows. No model calls. Computed **per turn** over that turn's spans only (so a repeat across turns is not a loop); the session-level signal columns are the aggregate (flags: any turn; counts: sums; first loop kind found). A trace with no turn spans is one turn. New fields only — never duplicates stage-1 trace columns (`status`, `error_count`, `error_types`, `duration_ms`, `tool_names` stay where they are).

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

The former heuristic verdict `failure_suspected` (and the judge/signals disagreement routing it fed) is removed. Signals are never in the judge's prompt or tools.

## Agent Judge

The outcome judge (three composed calls, N-vote self-consistency, confidence formula) is replaced by the per-turn agent in [9_session-analysis.md](9_session-analysis.md): tools, verdict shapes, validation, step limit, persistence, and when it runs are defined there.

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

**Owner task scope (hard scoping).** A taxonomy this size invites inconsistent picks on boundary tasks, so owners scope it: `profiles.task_categories` holds the categories an account works in (settings page; empty = unscoped). The agent's category vocabulary is the owner's selection **plus `other`** (the permanent escape hatch — it can never be deselected); empty selection means the full taxonomy. A category outside the scoped vocabulary is a validation violation, like an out-of-enum value. Scoping constrains only the judge on *your* traces — the global enum stays the marketplace's filter vocabulary, and a human relabel may pick any global value. Changing the scope is not retroactive (turns are not re-judged).

`failure_mode`'s `inconclusive` is not offered to the agent: an empty set already says "none identified". Failure modes are allowed on any outcome (a turn can succeed after an `invalid_invocation`).

## Listing Copy and Behavior Summary

The standalone `listing` and `summary` calls are removed. Listing copy (`traces.tags`, `traces.description`) now comes from the session roll-up, with the same **fill-if-empty, never overwrite** rule (enforced atomically in SQL, so a concurrent owner edit wins), and the behavior summary is the roll-up's `goal` + `summary` ([9_session-analysis.md](9_session-analysis.md)). The copy stays prose, not a filter field.

Caveats (why this is copy, not data):

- **Non-deterministic.** Sampled at temperature > 0: the same trace can yield different tags and phrasing on different runs. This is why generated tags can never be filter vocabulary. Fill-if-empty makes the copy stable *once written*.
- **Search-visible.** Tags and description feed `search_tsv` (tags at A weight), so generated copy shifts full-text relevance.
- **Owner-attributable.** The copy lands in fields the marketplace presents as the contributor's own words; the owner can edit or clear it any time.

## Review and Feedback

Confidence-based routing and the resolve loop are replaced: a trace with uncertain turns gets one open review item, and owners relabel turns directly ([9_session-analysis.md](9_session-analysis.md) Review). There is no fine-tuning, no retroactive re-judging, no exemplar pool (extension).

## Runtime, Config, Degradation

- `analyze_trace` runs on the existing taskiq machinery: same retry/backoff/DLQ rules as ingestion ([stage-1 6_architecture.md](../stage-1/6_architecture.md)). Provider errors classify as transient (retry) unless structurally permanent; exhaustion dead-letters with the trace marked analysis-`failed`. A turn that fails does not lose the others: what succeeded is written, then the error is raised so the retry judges only the rest.
- **LLM access is OpenAI only** (OpenAI Agents SDK + OpenAI SDK, pinned in `services/api`), wrapped by one client module (`app/analysis/llm.py`) — the only place LLM calls happen. SDK tracing export is disabled. The wrapper records per-call latency and token usage into the audit row.
- **No LLM key configured:** signals run; the judge skips (`llm_status = 'skipped'`, `llm_skip_reason = 'not_configured'`); LLM fields stay null. The UI states this honestly ([4_pages.md](4_pages.md)).
- **Owner opt-out:** when the trace is **private** and its owner has `allow_private_llm_analysis = false`, the judge skips the same way (`llm_skip_reason = 'owner_opt_out'`); signals still run. Listing such a trace finalizes it — listing is the consent act and covers analysis — so subscriptions only ever match fully-analyzed listed traces via the analysis-complete trigger. Flipping the setting is not retroactive: it applies to subsequent analysis runs, never triggers a sweep.
- Env vars (local-demo defaults, in `.env.example`): `OPENAI_API_KEY`, `ANALYSIS_JUDGE_MODEL`, `ANALYSIS_AGENT_MAX_STEPS`, `ANALYSIS_TURN_CONCURRENCY`, `ANALYSIS_IDLE_SECONDS`, the tool-field caps (`ANALYSIS_RENDER_TOOL_FIELD_CAP_CHARS`, `ANALYSIS_RENDER_CONVERSATION_CAP_CHARS`), loop-detection N, embedding model/budget. Removed: judge vote count, consensus/confidence thresholds, metric set, litellm provider keys.

Trace rendering for the judge (the budgeted message list) is no longer on the judging path: the agent reads spans on demand through its tools. `render_trace` survives only as the offline runner's `render` command and for `middle_out` truncation.

## Privacy

- Analyzers read span `attributes` — fine — but trace bodies never leak into logs. Prompts, tool results and raw LLM outputs are never logged; only structured results are stored (labels, reasons, one-line summaries, usage).
- Analysis sends trace content to OpenAI — documented per [0_README.md](0_README.md) Third-Party Services. The judge sees the redacted representation ([7_redaction.md](7_redaction.md)).
- **Per-account opt-out for private traces** (`profiles.allow_private_llm_analysis`): the only trace content that reaches the provider is private traces of accounts that allow it (the default) and listed traces. The operator-level control (no key configured) remains the zero-external-flow mode.

## Validation

The agreement harness (`app.cli.analyze agreement`, `app/analysis/validation.py`) and the HaluBench metric validation belonged to the retired voted judge and metrics and no longer exist; their results are recorded in the B4/B5 buildlogs as history. What remains: the benchmark→OTLP converters (`tools/arb_to_otlp.py`, `tools/agentrx_to_otlp.py`), which produce ordinary OTLP that ingests through the stage-1 pipeline (one turn per trace) and can be run through `python -m app.cli.analyze run`. Re-measuring the per-turn agent against expert labels is not built.

## Finalized At Build (Parameters, Not Decisions)

Tunables and measurements, not open design questions: final `task_category` values (validated against datasets), the signal promotion list (hit-rate gated), tool-field caps, agent step limit, arg-normalization details for action signatures.
