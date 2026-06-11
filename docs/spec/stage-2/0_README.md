# Stage 2 Spec

This directory is the normative spec for Stage 2. Every statement here is "the system does X." Shaping and rationale live in `.archive/stage-2-planning/` (historical, non-normative); if they disagree, this spec wins. Stage 2 layers on the stage-1 platform (`docs/spec/stage-1/`); stage-1 rules (error shape, rate limiting, RLS mirroring, ingestion idempotency, span-body privacy) carry over unchanged except where a delta is stated here.

## Stage 2 In One Sentence

Traces flow in passively through a local sync CLI, are analyzed server-side into labels and filterable derived fields — humans resolve uncertain verdicts in a review queue — and consumers subscribe to saved queries and bulk-acquire matches.

## Demo Script

The literal click-through that defines done:

1. **Settings**: mint an API key — plaintext shown exactly once, with a ready-to-run CLI snippet.
2. Terminal: `sync` a directory of trace files; each file uploads and its terminal status prints. Re-running syncs nothing (server-side dedupe). `watch` stays alive and uploads a file dropped into the directory.
3. A bad file fails ingestion while nobody watches: the failure is visible on **/uploads** (status + reason verbatim) and as an `upload_failed` notification.
4. Open a synced trace: the **Analysis** section shows `outcome` / `failure_mode` / `task_category` with per-field confidence and provenance, judge reasoning, deterministic signals, and metric scores; audit details (analyzer versions, model id, stored votes) behind a disclosure.
5. An uncertain verdict lands in **/review** (notification digested per upload). Resolve it: the machine's take is shown as context, never pre-selected; labels update with `human` provenance and confidence 1.0.
6. Multi-select synced traces on **My Traces** → "List N traces" → one batched-consent confirmation.
7. (As a consumer) filter the marketplace on label + metric predicates (`outcome = failure`, `confidence ≥ 0.8`, `faithfulness ≥ 0.8`) → **Save as subscription** with backfill preview.
8. A new matching trace is synced and listed → `subscription_match` notification → feed → multi-select → **bulk acquire** (itemized result).
9. **/library**: select acquired traces → "Download N" → zip of raw payloads + `labels.jsonl`.
10. Offline: the validation script reports judge agreement against expert labels on a converted benchmark slice — the headline demo claim.

## Scope: In

- **Sync CLI** (`apps/cli`): one-shot `sync` + `watch` mode, API-key auth, stateless, raw bytes only.
- **API keys**: one scope (upload-only); dual JWT/API-key auth middleware.
- **Analysis pipeline**: post-ingestion worker job on the existing taskiq machinery; `analyzer_results` table + `trace_analysis` side table (1:1 with `traces`).
- **Three analyzer families**: deterministic signals; composed LLM outcome judge (ternary label model, AgentRx failure taxonomy, task category, self-consistency voting); quality metric evals (owned critics + RAGAS collections).
- **Human-in-the-loop**: review items routed on uncertainty/disagreement; resolve UI with per-field provenance; owner-initiated relabel.
- **In-app notifications**: `review_request` (digested per upload), `subscription_match`, `upload_failed` (CLI uploads only).
- **Filter vocabulary extension**: analysis fields + numeric min-bound predicates; one filter language across search, subscriptions, and (later) bounties.
- **Subscriptions**: saved queries, event-driven matching, live-feed backfill, no auto-acquire.
- **Bulk actions**: acquire, list/unlist (batched consent), download (zip + `labels.jsonl`).
- **New pages**: `/review`, `/review/[itemId]`, `/notifications`, `/subscriptions`, `/subscriptions/[id]`, `/settings`, `/uploads`; deltas to existing pages.
- **Validation**: benchmark→OTLP converter + offline judge-agreement script.

## Scope: Extensions (Not Base)

Designed-for but explicitly out of the base build: task bounties, desktop notifications, similar-trace subscriptions, on-demand enrichment, few-shot exemplars / evaluator training, judge model selection, session stitching, `estimated_cost`, meta-judge over vote reasonings, hierarchical task categories. SFT/trajectory/pairs export formats are future-work narrative only.

## Locked Decisions

| Decision | Resolution |
|---|---|
| Capture | Separate sync CLI; watch mode is base scope, not an extension. Stateless — server-side sha256 dedupe is the source of truth. |
| Search & matching | Deterministic/rule-based everywhere. Non-determinism only in field *derivation*; rules match on derived fields like any column. No embedding search. |
| Label model | Ternary `outcome` (`success \| failure \| indeterminate`); `failure_mode` from the AgentRx 10-category taxonomy; `task_category` closed enum; per-field confidence + provenance. |
| Confidence | Vote share from N sampled judge runs; capped at 0.5 on signals/judge disagreement; 1.0 on human resolution. |
| HIL routing | Only the outcome judge routes to review. Low confidence blocks nothing — machine labels are stored and filterable immediately. |
| Subscriptions | Saved queries over the shared filter language; event-driven matching; **no auto-acquire anywhere**. |
| Bulk listing | Batched consent: explicit selection only, one dialog naming the exact count, same affirmative ownership checkbox. Listing remains the consent act. |
| Notifications | In-app, routed page (no popover panel); generated server-side only. |
| Privacy | Unchanged from stage 1: CLI uploads private by default; listing is the consent act; subscriptions match listed traces only. |
| Private-trace LLM analysis | **Per-account opt-out** (`profiles.allow_private_llm_analysis`, default on): when off, LLM analyzers skip the account's private traces (deterministic signals still run). Listed traces are always analyzed — listing is the consent act and covers analysis. |
| Analyzers without an LLM key | Degrade explicitly: signals run, LLM analyzers skip with a recorded reason, fields stay null. Never a fake "pending". |

## Stage-1 Contact Surface

Deliberately minimal; everything else in stage 2 is additive (new tables, endpoints, jobs, pages):

- Auth middleware accepts an API key on the same `Authorization` header (the one code modification).
- `uploads.source` column (`cli | web`, inferred from auth type).
- `profiles.allow_private_llm_analysis` column (the per-account LLM-analysis opt-out for private traces).
- `traces.total_tokens` (ingestion-derived, small importer addition + migration).
- `dead_letters.trace_id` nullable column (analysis tasks are trace-scoped, not upload-scoped).
- Trace-name derivation check: CLI-synced traces must get scannable names (root-span name or filename), never bare ids.

## Spec Documents

| Doc | Defines |
|---|---|
| [1_analysis.md](1_analysis.md) | The analyzer contract, label model, three analyzer families, rendering, HIL routing, validation. |
| [2_data-model.md](2_data-model.md) | New tables, stage-1 deltas, access rules. |
| [3_api.md](3_api.md) | Auth change, new endpoints, filter-language extension, exports. |
| [4_pages.md](4_pages.md) | New routes, page responsibilities, deltas to stage-1 pages, required UI states. |
| [5_cli.md](5_cli.md) | Sync CLI behavior. |
| [6_build-order.md](6_build-order.md) | Two parallel build streams with merge points and done criteria. |

## Third-Party Services

Analysis workers call an LLM provider (OpenAI / Anthropic / OpenRouter — env-configured). This is a new external data flow: **trace content is sent to the configured provider** during judging and metric evaluation. It must be documented in the runbook/README; without a key the system degrades per the locked decision above. Contributors can exclude their **private** traces from this flow per account (the `/settings` toggle); listed traces are always analyzed. Provider key, judge model, vote count N, confidence thresholds, rendering token budget, and the default metric set are all env vars with local-demo defaults in `.env.example`.
