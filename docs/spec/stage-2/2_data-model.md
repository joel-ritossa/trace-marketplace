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
| `payload` | jsonb | Type-specific: `review_request` → upload_id + filename + item_count + uncertain_turns, and trace_id + trace_name while every item in the digest is on one trace (digested per upload; a new item only when a trace with no open item becomes uncertain); `subscription_match` → subscription_id + name + match_count (digested per subscription; trace_id only while the count is 1, so a single match deep-links the trace); `upload_failed` → upload_id. Always enough to build the link target. |
| `created_at` | timestamptz | |
| `read_at` | timestamptz | Null = unread. |

Generated server-side only (worker jobs / API). `upload_failed` is emitted only for `uploads.source = 'cli'` (web failures fail in front of the user).

### review_items

Generic plumbing; the question lives in the jsonb payload so it can change without migration churn. Since the agent judge ([9_session-analysis.md](9_session-analysis.md)) an item asks one thing: relabel this trace's uncertain turns.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `trace_id` | uuid | References `traces.id`, cascade delete. |
| `question_type` | text | `verdict` (column default; the only value). |
| `context` | jsonb | `{ turns: [{ turn_index, reason, summary }] }` — the trace's uncertain machine turns and why the agent could not judge them. |
| `answer` | jsonb | Unused since the agent judge (answers are turn relabels in `turn_analysis`); always null. |
| `status` | text | `open \| resolved \| superseded`. `resolved` when owner relabels leave no uncertain turn; `superseded` when a re-judge clears the uncertain set. |
| `created_at` | timestamptz | |
| `resolved_at` | timestamptz | |
| `resolved_by` | uuid | References `profiles.id`; set when the owner's relabels close the item. |

Constraint: at most one `open` item per trace (partial unique index on `trace_id` where `status = 'open'`). A changed uncertain-turn set updates the open item's context in place (analysis runs and owner relabels alike); an item is created only when none is open — never duplicates, no notification churn as a session grows.

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

One row per LLM analysis run per trace (appended, not rewritten). Audit layer; never queried by search.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `trace_id` | uuid | References `traces.id`, cascade delete. |
| `analyzer` | text | `agent` (the per-turn judge + roll-up run). |
| `analyzer_version` | text | Prompt/agent changes bump it (`fault:canned` for dev fault runs). |
| `model_id` | text | The judge model. |
| `output` | jsonb | Per judged turn and the roll-up: model, token usage, latency, tool-call counts. No verdicts (those live in `turn_analysis`), no votes. |
| `created_at` | timestamptz | |

Each run that judges something appends a row, in the same transaction as the `turn_analysis` / `trace_analysis` writes.

### span_raw

Owner-only raw copies of the scrubbed span content fields ([7_redaction.md](7_redaction.md)). After redaction lands, `spans.attributes` / `events` / `status_message` hold the scrubbed representation; this table is the only place original values exist in Postgres. Written in the same ingestion transaction as `spans`.

| Column | Type | Notes |
|---|---|---|
| `span_id` | uuid PK | References `spans.id`, cascade delete. |
| `attributes` | jsonb | Original OTLP attributes. |
| `events` | jsonb | Original OTLP events. |
| `status_message` | text | Original status message. |

### turn_analysis

One row per judged turn; PK `(trace_id, turn_index)`. A trace with no turn spans has one row at `turn_index` 0.

| Column | Type | Notes |
|---|---|---|
| `fingerprint` | text | Hash of the turn's span ids and end time; a changed fingerprint means re-judge. |
| `outcome` | text | `success \| partial \| failure \| indeterminate`; check-constrained. Null = not judged (LLM skipped); signals are always computed. |
| `summary` | text | One line: what was asked, what happened. |
| `uncertain` | text | Why the agent could not judge confidently; null otherwise. Drives the review item. |
| `signals` | jsonb | This turn's deterministic signals. |
| `provenance` | text | `machine \| human`. A `human` turn is never re-judged or overwritten. |
| `model`, `usage` | text, jsonb | Judge model and token/latency/tool-call usage. |
| `analyzed_at` | timestamptz | |

### trace_labels

One row per label, hung off a turn (`(trace_id, turn_index)` FK → `turn_analysis`, cascade delete); unique `(trace_id, turn_index, field, value)` — a value cited twice is one row with merged span ids.

| Column | Type | Notes |
|---|---|---|
| `field` | text | `task_category \| failure_mode`; check-constrained. |
| `value` | text | Taxonomy value; app-validated. |
| `span_ids` | text[] | `source_span_id`s that show the label. At least one for a machine `failure_mode`; empty for categories (and possibly for human labels). |
| `reason` | text | One sentence; null for categories. |

### trace_analysis

The 1:1 side table holding everything filterable at session level. **One writer:** the analysis job (and owner relabels) own this table; ingestion owns `traces`. No row = not yet analyzed; within a row, null = the analyzer didn't produce the field. Null never matches any predicate. The row exists as soon as any turn has been judged; the roll-up columns fill when the session is finalized.

| Column | Type | Notes |
|---|---|---|
| `trace_id` | uuid PK | References `traces.id`, cascade delete. |
| `outcome` | text | Session outcome: `success \| partial \| failure \| indeterminate`; check-constrained. Roll-up; null until finalized. |
| `goal`, `summary` | text | Roll-up: what the user was trying to get done; short paragraph. |
| `task_categories` | text[] | Union over turn labels, recomputed on every write; GIN-indexed. |
| `failure_modes` | text[] | Same. |
| `has_retry_loop` | boolean | Session aggregate of the per-turn signals (any turn); all nullable (fail open). |
| `loop_kind` | text | `exact_repeat \| cycle \| stagnation`; first found. |
| `recovered_from_error` | boolean | Any turn. |
| `truncation_suspected` | boolean | Any turn. |
| `llm_call_count`, `tool_call_count` | integer | Sums over turns. |
| `llm_status` | text | `complete \| skipped` — whether the LLM judge ran. |
| `llm_skip_reason` | text | Nullable; `not_configured \| owner_opt_out` when `llm_status = 'skipped'`, null otherwise. |
| `analyzed_at` | timestamptz | Roll-up time; null until finalized, and reset when a turn is rewritten after it (the roll-up is then stale). |

The scalar `failure_mode` / `task_category`, every `*_confidence` / `*_provenance` column, and `metric_scores` are gone.

### Analysis state (derived, not stored)

The run lease lives on `traces`: `analysis_lease_until` (one analyze run per trace; heartbeat-extended) and `analysis_rerun` (`incremental | finalize`, the mode a run that found the lease held asked for; its holder enqueues it on release).

The API derives the session analysis status the UI requires ([4_pages.md](4_pages.md)) from `trace_analysis`, `traces.analysis_attempts` and the dead-letter table (`queries/analysis.py:derive_status`):

| Status | Condition |
|---|---|
| `pending` | No `trace_analysis` row (nothing judged yet). |
| `in_progress` | Row exists, `llm_status = 'complete'`, and the roll-up is not current (`analyzed_at` null, or the trace was re-ingested since). Some turns may already be judged. |
| `final` | Every turn judged and the roll-up current. |
| `skipped` | `llm_status = 'skipped'` (signals still present); `llm_skip_reason` says why. |

Separately, an open `analyze_trace` dead letter surfaces as a failure (`failed_reason` / `analysis_failed`), independent of the status above.

## Stage-1 Deltas

All additive, via new migrations:

- `uploads.source` text, `cli | web`, default `web`. Set by the API from auth type (API key → `cli`); clients never set it.
- `profiles.allow_private_llm_analysis` boolean not null default `true` — the per-account opt-out of LLM analysis for private traces ([1_analysis.md](1_analysis.md) Runtime). Editable only by the owner (existing profiles access rule).
- `profiles.task_categories` text[] not null default `'{}'` — the owner's task scope for the judge's category vocabulary ([1_analysis.md](1_analysis.md) Taxonomies): values from the global `task_category` enum (never `other`); empty = unscoped. Editable only by the owner (existing profiles access rule).
- `traces.total_tokens` integer nullable — ingestion-derived sum of span tokens (importer addition; like `duration_ms`).
- `dead_letters.trace_id` uuid nullable — analysis tasks are trace-scoped; ingestion rows leave it null.
- Importer check (not a schema change): trace `name` derivation must produce scannable names (root-span name, falling back to source filename), never a bare id — CLI sync makes this visible at volume.
- `uploads.redaction_salt` text — random hex set at upload creation, immutable; keys the deterministic placeholder HMAC ([7_redaction.md](7_redaction.md)).
- `uploads.redaction_version` text nullable, `uploads.redaction_counts` jsonb nullable — ruleset version and per-type replacement counts from the last ingestion; rewritten on re-ingest.
- `spans.attributes` / `events` / `status_message` and trace/span `name` become scrubbed-by-default once redaction lands; raw copies move to `span_raw` (no column changes — a semantic delta plus the new table).
- Storage: ingestion materializes a scrubbed payload artifact at `scrubbed/{owner_id}/{sha256}.json` in the `raw-traces` bucket, overwritten idempotently per ingest; non-owner downloads serve it.

## Indexes

`api_keys(key_hash)` unique; `notifications(user_id, created_at desc)` + partial on unread; `review_items(trace_id)` with the partial-unique open constraint, partial index on `status = 'open'`; `subscriptions(owner_id)`; unique `(subscription_id, trace_id)` on subscription_matches; `analyzer_results(trace_id)`; unique `trace_labels(trace_id, turn_index, field, value)`; GIN on `trace_analysis(task_categories)` and `(failure_modes)` (the filters are array overlap); `trace_analysis` and `turn_analysis` are otherwise PK-joined.

## Access Rules

Enforced in API queries; mirrored as RLS policies (stage-1 rule).

| Object | Rule |
|---|---|
| `api_keys` | Owner only, all operations. Plaintext never readable after mint. |
| `notifications` | Recipient only; mark-read is the only mutation. |
| `review_items` | Owner of the referenced trace only (read; closed by turn relabels). |
| `subscriptions`, `subscription_matches` | Owner only. |
| `analyzer_results` | Mirrors the referenced trace (owner, or anyone if listed). |
| `trace_analysis`, `turn_analysis`, `trace_labels` | Mirror `traces` exactly: owner, or any authenticated user when the trace is listed. Read-only for clients; turn relabels go through the API. Direct `turn_analysis` reads are column-limited for every client (owners included) to `trace_id, turn_index, outcome, summary, signals, provenance, analyzed_at`: `uncertain` is owner-only review content and `model` / `usage` / `fingerprint` are internal — the API serves them, owner-scoped. |
| `span_raw` | Owner of the referenced trace only — never readable by non-owners regardless of visibility. |
| Download (delta to stage 1) | Owner gets the raw storage object; an acquirer gets the scrubbed artifact. |

API-key principals are scoped to upload endpoints only ([3_api.md](3_api.md)) regardless of row-level access.
