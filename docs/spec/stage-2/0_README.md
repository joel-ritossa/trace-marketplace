# Stage 2 Spec

This directory is the normative spec for Stage 2. Every statement here is "the system does X." Shaping and rationale live in `.archive/stage-2-planning/` (historical, non-normative); if they disagree, this spec wins. Stage 2 layers on the stage-1 platform (`docs/spec/stage-1/`); stage-1 rules (error shape, rate limiting, RLS mirroring, ingestion idempotency, span-body privacy) carry over unchanged except where a delta is stated here.

## Stage 2 In One Sentence

Coding-agent sessions flow in passively through a local sync CLI (one trace per session), are judged server-side turn by turn into labels and filterable derived fields — owners relabel the turns the judge was unsure about — and consumers subscribe to saved queries and bulk-acquire matches.

## Demo Script

The literal click-through that defines done:

1. **Settings**: mint an API key — plaintext shown exactly once, with a ready-to-run CLI snippet.
2. Terminal: `sync` a directory of trace files; each file uploads and its terminal status prints. Re-running syncs nothing (server-side dedupe). `watch` stays alive and uploads a file dropped into the directory.
3. A bad file fails ingestion while nobody watches: the failure is visible on **/uploads** (status + reason verbatim) and as an `upload_failed` notification.
4. Open a synced session: the **Analysis** section shows the session verdict (goal, outcome, summary, categories, failure modes) and a verdict per turn, each failure mode citing the spans that show it (click to open the span), plus deterministic signals.
5. A session with an uncertain turn lands in **/review** (notification digested per upload). Relabel the turn: the machine's take is shown as context, never pre-selected; the turn becomes human-labeled and is never re-judged.
6. Multi-select synced traces on **My Traces** → "List N traces" → one batched-consent confirmation.
7. (As a consumer) filter the marketplace on label predicates (`outcome = failure`, `failure_mode = invalid_invocation`, `llm_call_count ≥ 50`) → **Save as subscription** with backfill preview.
8. A new matching trace is synced and listed → `subscription_match` notification → feed → multi-select → **bulk acquire** (itemized result).
9. **/library**: select acquired traces → "Download N" → zip of scrubbed payloads + `labels.jsonl` (owners downloading their own traces get raw).
10. Offline: `python -m app.cli.analyze run` judges a fixture session turn by turn and dumps the verdicts as JSON.

## Scope: In

- **Sync CLI** (`apps/cli`): one-shot `sync` + `watch` mode, API-key auth, stateless, raw bytes only.
- **API keys**: one scope (upload-only); dual JWT/API-key auth middleware.
- **Analysis pipeline**: worker job on the existing taskiq machinery, run per session turn ([9_session-analysis.md](9_session-analysis.md)); `turn_analysis` + `trace_labels` + `trace_analysis` (session roll-up, 1:1 with `traces`) + `analyzer_results` audit.
- **Two analyzer families**: deterministic signals (per turn); the agent judge — one OpenAI Agents SDK agent per turn that explores the trace through tools (`outcome` success/partial/failure/indeterminate, multi-select `task_category`, span-anchored AgentRx `failure_mode`s) plus a roll-up to the session verdict. No voting, no confidence, no quality metrics.
- **Human-in-the-loop**: one open review item per trace listing its uncertain turns; owners relabel any turn (human turns are never re-judged).
- **In-app notifications**: `review_request` (digested per upload), `subscription_match`, `upload_failed` (CLI uploads only).
- **Filter vocabulary extension**: analysis fields + numeric min-bound predicates; one filter language across search, subscriptions, and (later) bounties.
- **Subscriptions**: saved queries, event-driven matching, live-feed backfill, no auto-acquire.
- **Bulk actions**: acquire, list/unlist (batched consent), download (zip + `labels.jsonl`).
- **New pages**: `/review`, `/review/[itemId]`, `/notifications`, `/subscriptions`, `/subscriptions/[id]`, `/settings`, `/uploads`; deltas to existing pages.
- **Validation**: benchmark→OTLP converters (the agreement script was retired with the voted judge).
- **Redaction**: credential + pattern-PII scrubbing at ingestion; owner sees raw, every other surface (inspection, downloads, LLM analyzers) sees deterministic placeholders ([7_redaction.md](7_redaction.md)).

## Scope: Extensions (Not Base)

Designed-for but explicitly out of the base build: task bounties, desktop notifications, similar-trace subscriptions, on-demand enrichment, behavioral novelty scoring (rare-data discovery), few-shot exemplars / evaluator training, judge model selection, session stitching, `estimated_cost`, hierarchical task categories. SFT/trajectory/pairs export formats are future-work narrative only.

Built this round on top of the base: similar-trace subscriptions, shipped as the similar-behavior extension (agreed 2026-06-11; design in [`docs/proposals/similar-behavior.md`](../../proposals/similar-behavior.md)) — per-trace embeddings on analysis, a similar-traces endpoint + modal, and behavior-anchored subscription matching.

## Locked Decisions

| Decision | Resolution |
|---|---|
| Capture | Separate sync CLI; watch mode is base scope, not an extension. Stateless — server-side sha256 dedupe is the source of truth. |
| Search & matching | Deterministic/rule-based everywhere. Non-determinism only in field *derivation*; rules match on derived fields like any column. No embedding search in the base build; the similar-behavior extension (agreed 2026-06-11) adds an explicit embedding-anchored subscription predicate and a similar-traces lookup — derivation stays non-deterministic, matching against a stored vector stays deterministic. |
| Rare data | Base mechanism: rarity is filterable — sparse label combinations (`task_category` × `failure_mode`, signals) are discoverable and subscribable like any query. *Behavioral* rarity is the designed-for extension ([behavioral novelty](../../extensions/behavioral-novelty.md)); it ranks within a result set and never changes matching. |
| Unit of judgment | The turn; the session verdict is a roll-up. Sessions are the unit of upload (one trace per session). ([9_session-analysis.md](9_session-analysis.md)) |
| Label model | `outcome` (`success \| partial \| failure \| indeterminate`); multi-select `task_category` (closed enum) and `failure_mode` (AgentRx taxonomy minus `inconclusive`), failure modes anchored to spans; per-turn provenance (`machine \| human`). No confidence scores. |
| Review | A trace with uncertain turns has one open review item. Uncertainty blocks nothing — machine labels are stored and filterable immediately; owners relabel turns. |
| Subscriptions | Saved queries over the shared filter language; event-driven matching; **no auto-acquire anywhere**. |
| Bulk listing | Batched consent: explicit selection only, one dialog naming the exact count, same affirmative ownership checkbox. Listing remains the consent act. |
| Notifications | In-app, routed page (no popover panel); generated server-side only. |
| Privacy | CLI uploads private by default; listing is the consent act; subscriptions match listed traces only. |
| Redaction | Scrub at ingestion, pure + versioned: `detect-secrets` for credentials, in-house pattern recognizers for PII (no NER). Owner sees raw (owner-only `span_raw` side table); all other surfaces see deterministic HMAC placeholders. Raw storage objects are never mutated. ([7_redaction.md](7_redaction.md)) |
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
- Redaction ([7_redaction.md](7_redaction.md)): scrub step inside the importer; `spans` content columns become scrubbed-by-default with raw copies in the new owner-only `span_raw` table; `uploads` gains `redaction_salt` / `redaction_version` / `redaction_counts`; ingestion materializes a scrubbed payload artifact served to non-owner downloads.

## Spec Documents

| Doc | Defines |
|---|---|
| [1_analysis.md](1_analysis.md) | The analyzer contract, deterministic signals, taxonomies, privacy (partly superseded by 9). |
| [2_data-model.md](2_data-model.md) | New tables, stage-1 deltas, access rules. |
| [3_api.md](3_api.md) | Auth change, new endpoints, filter-language extension, exports. |
| [4_pages.md](4_pages.md) | New routes, page responsibilities, deltas to stage-1 pages, required UI states. |
| [5_cli.md](5_cli.md) | Sync CLI behavior. |
| [6_build-order.md](6_build-order.md) | Two parallel build streams with merge points and done criteria. |
| [7_redaction.md](7_redaction.md) | Credential + PII scrubbing at ingestion: detection rules, placeholder scheme, storage model, access boundaries. |
| [8_session-ingestion.md](8_session-ingestion.md) | Native session-log ingestion: one trace per session, turns, nested subagents. |
| [9_session-analysis.md](9_session-analysis.md) | The agent judge: per-turn verdicts, roll-up, when analysis runs, review. Wins over 1_analysis.md. |

## Third-Party Services

Analysis workers call OpenAI (Agents SDK + OpenAI SDK; no other provider). This is a new external data flow: **trace content is sent to OpenAI** during judging (the agent reads spans on demand through its tools) and embedding. Analyzers read the scrubbed representation ([7_redaction.md](7_redaction.md)), so detected credentials and pattern-PII never reach the provider. It must be documented in the runbook/README; without a key the system degrades per the locked decision above. Contributors can exclude their **private** traces from this flow per account (the `/settings` toggle); listed traces are always analyzed. `OPENAI_API_KEY`, the judge model, agent step limit, turn concurrency and idle window are env vars with local-demo defaults in `.env.example`.
