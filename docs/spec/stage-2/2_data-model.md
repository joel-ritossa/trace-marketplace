# Data Model

New tables plus a minimal stage-1 contact surface. Same ground rules as stage 1: all tables in `public`, RLS enabled, schema changes only via new migrations in `supabase/migrations/`.

## New Tables

### api_keys

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `owner_id` | uuid | References `profiles.id`. |
| `name` | text | User-chosen label. |
| `key_hash` | text | SHA-256 of the full key; unique. Plaintext shown once at mint, never stored. |
| `key_display` | text | Prefix + last 4 (e.g. `tmk_ab…f3k9`) for list rendering. |
| `scope` | text | `upload` — the only scope in stage 2; column exists so more scopes are additive. |
| `created_at` | timestamptz | |
| `last_used_at` | timestamptz | Updated on authenticated use (best-effort, throttled). |
| `revoked_at` | timestamptz | Soft revoke; revoked keys fail auth but the row remains for history. |

### notifications

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid | References `profiles.id`. |
| `type` | text | `review_request \| subscription_match \| upload_failed`. App-validated; new types are additive. |
| `payload` | jsonb | Type-specific: `review_request` → upload_id + item count (digested per upload); `subscription_match` → subscription_id + name + match_count (digested per subscription; trace_id only while the count is 1, so a single match deep-links the trace); `upload_failed` → upload_id. Always enough to build the link target. |
| `created_at` | timestamptz | |
| `read_at` | timestamptz | Null = unread. |

Generated server-side only (worker jobs / API). `upload_failed` is emitted only for `uploads.source = 'cli'` (web failures fail in front of the user).

### review_items

Generic plumbing; the label model lives in the jsonb payloads so it can change without migration churn.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `trace_id` | uuid | References `traces.id`, cascade delete. |
| `question_type` | text | `verdict` in stage 2 (the composed outcome/failure_mode/category question). |
| `context` | jsonb | Machine verdict, per-field confidence, routing reasons in plain language. Empty reasons = owner-initiated relabel. |
| `answer` | jsonb | Null until resolved. Partial answers allowed (e.g. outcome only). |
| `status` | text | `open \| resolved \| superseded`. |
| `created_at` | timestamptz | |
| `resolved_at` | timestamptz | |
| `resolved_by` | uuid | References `profiles.id`. |

Constraint: at most one `open` item per trace (partial unique index on `trace_id` where `status = 'open'`). A re-run that routes again marks the existing open item `superseded` and creates a fresh one — never duplicates.

### subscriptions

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `owner_id` | uuid | References `profiles.id`. |
| `name` | text | |
| `query` | jsonb | The stored filter map — the same param vocabulary as `GET /v1/traces` ([3_api.md](3_api.md)), minus scope/sort/pagination. Scope is forced to listed traces. |
| `created_at` | timestamptz | |
| `last_seen_at` | timestamptz | Backs the feed's new-since-last-seen marker. |

The feed is the stored query executed live (backfill for free); no match rows are needed to render it.

### subscription_matches

First-match records, for notification dedupe only.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `subscription_id` | uuid | References `subscriptions.id`, cascade delete. |
| `trace_id` | uuid | References `traces.id`, cascade delete. |
| `matched_at` | timestamptz | |

Unique `(subscription_id, trace_id)` — a trace notifies a subscription at most once, ever, regardless of how many trigger events re-match it.

### analyzer_results

One row per analyzer run per trace. Audit + reproducibility layer; never queried by search.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `trace_id` | uuid | References `traces.id`, cascade delete. |
| `analyzer` | text | `signals \| judge \| metric:<name>`. |
| `analyzer_version` | text | Prompt/renderer/config changes bump it. |
| `model_id` | text | Null for deterministic analyzers. |
| `output` | jsonb | Full result model: signals object incl. `failure_suspected`; judge verdict incl. the N stored votes + reasoning + `rendering_truncated`; metric score/flag + reason. |
| `confidence` | numeric | Null where not applicable. |
| `created_at` | timestamptz | |

A re-run of `analyze_trace` deletes and rewrites the trace's rows (with `trace_analysis`, one transaction).

### span_raw

Owner-only raw copies of the scrubbed span content fields ([7_redaction.md](7_redaction.md)). After redaction lands, `spans.attributes` / `events` / `status_message` hold the scrubbed representation; this table is the only place original values exist in Postgres. Written in the same ingestion transaction as `spans`.

| Column | Type | Notes |
|---|---|---|
| `span_id` | uuid PK | References `spans.id`, cascade delete. |
| `attributes` | jsonb | Original OTLP attributes. |
| `events` | jsonb | Original OTLP events. |
| `status_message` | text | Original status message. |

### trace_analysis

The 1:1 side table holding everything filterable. **One writer:** the analysis job (and human resolution) own this table; ingestion owns `traces`. No row = not yet analyzed; within a row, null = the analyzer didn't produce the field. Null never matches any predicate.

| Column | Type | Notes |
|---|---|---|
| `trace_id` | uuid PK | References `traces.id`, cascade delete. |
| `outcome` | text | `success \| failure \| indeterminate`; check-constrained (stable set). |
| `outcome_confidence` | numeric | 0–1. |
| `outcome_provenance` | text | `machine \| human_confirmed \| human`; check-constrained. |
| `failure_mode` | text | AgentRx taxonomy; app-validated, no check constraint (taxonomy evolves). |
| `failure_mode_confidence` | numeric | |
| `failure_mode_provenance` | text | |
| `task_category` | text | App-validated. |
| `task_category_confidence` | numeric | |
| `task_category_provenance` | text | |
| `has_retry_loop` | boolean | Promoted family-1 signals; all nullable (fail open). |
| `loop_kind` | text | `exact_repeat \| cycle \| stagnation`. |
| `recovered_from_error` | boolean | |
| `truncation_suspected` | boolean | |
| `llm_call_count`, `tool_call_count` | integer | |
| `metric_scores` | jsonb | Map `metric name → number (0–1) or boolean flag`. Reasons stay in `analyzer_results`. |
| `llm_status` | text | `complete \| skipped` — whether LLM analyzers ran. |
| `llm_skip_reason` | text | Nullable; `not_configured \| owner_opt_out` when `llm_status = 'skipped'`, null otherwise. |
| `analyzed_at` | timestamptz | |

### Analysis state (derived, not stored)

The API derives the per-trace analysis state the UI requires ([4_pages.md](4_pages.md)):

| State | Condition |
|---|---|
| `pending` | Trace exists, no `trace_analysis` row, no `analyze_trace` dead letter. |
| `complete` | Row exists, `llm_status = 'complete'`. |
| `skipped` | Row exists, `llm_status = 'skipped'` (signals still present); `llm_skip_reason` says why. |
| `failed` | `dead_letters` row for `analyze_trace` on this trace. |

## Stage-1 Deltas

All additive, via new migrations:

- `uploads.source` text, `cli | web`, default `web`. Set by the API from auth type (API key → `cli`); clients never set it.
- `profiles.allow_private_llm_analysis` boolean not null default `true` — the per-account opt-out of LLM analysis for private traces ([1_analysis.md](1_analysis.md) Runtime). Editable only by the owner (existing profiles access rule).
- `profiles.task_categories` text[] not null default `'{}'` — the owner's task scope for the judge's category call ([1_analysis.md](1_analysis.md) Taxonomies): values from the global `task_category` enum (never `other`); empty = unscoped. Editable only by the owner (existing profiles access rule).
- `traces.total_tokens` integer nullable — ingestion-derived sum of span tokens (importer addition; like `duration_ms`).
- `dead_letters.trace_id` uuid nullable — analysis tasks are trace-scoped; ingestion rows leave it null.
- Importer check (not a schema change): trace `name` derivation must produce scannable names (root-span name, falling back to source filename), never a bare id — CLI sync makes this visible at volume.
- `uploads.redaction_salt` text — random hex set at upload creation, immutable; keys the deterministic placeholder HMAC ([7_redaction.md](7_redaction.md)).
- `uploads.redaction_version` text nullable, `uploads.redaction_counts` jsonb nullable — ruleset version and per-type replacement counts from the last ingestion; rewritten on re-ingest.
- `spans.attributes` / `events` / `status_message` and trace/span `name` become scrubbed-by-default once redaction lands; raw copies move to `span_raw` (no column changes — a semantic delta plus the new table).
- Storage: ingestion materializes a scrubbed payload artifact at `scrubbed/{owner_id}/{sha256}.json` in the `raw-traces` bucket, overwritten idempotently per ingest; non-owner downloads serve it.

## Indexes

`api_keys(key_hash)` unique; `notifications(user_id, created_at desc)` + partial on unread; `review_items(trace_id)` with the partial-unique open constraint, partial index on `status = 'open'`; `subscriptions(owner_id)`; unique `(subscription_id, trace_id)` on subscription_matches; `analyzer_results(trace_id)`; `trace_analysis` is PK-joined only (no secondary indexes until query evidence demands them).

## Access Rules

Enforced in API queries; mirrored as RLS policies (stage-1 rule).

| Object | Rule |
|---|---|
| `api_keys` | Owner only, all operations. Plaintext never readable after mint. |
| `notifications` | Recipient only; mark-read is the only mutation. |
| `review_items` | Owner of the referenced trace only (read + resolve). |
| `subscriptions`, `subscription_matches` | Owner only. |
| `analyzer_results` | Mirrors the referenced trace (owner, or anyone if listed). |
| `trace_analysis` | Mirrors `traces` exactly: owner, or any authenticated user when the trace is listed. |
| `span_raw` | Owner of the referenced trace only — never readable by non-owners regardless of visibility. |
| Download (delta to stage 1) | Owner gets the raw storage object; an acquirer gets the scrubbed artifact. |

API-key principals are scoped to upload endpoints only ([3_api.md](3_api.md)) regardless of row-level access.
