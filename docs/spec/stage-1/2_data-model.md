# Data Model

Supabase Postgres. All tables in `public`, RLS enabled. Supabase auth owns identities; `auth.users` is referenced, not duplicated.

## Tables

### profiles

One row per auth user.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | References `auth.users.id`. |
| `display_name` | text | Shown as contributor name on listings. |
| `created_at` | timestamptz | |

### uploads

One submitted file. Immutable after ingestion finishes.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `owner_id` | uuid | References `profiles.id`. |
| `filename` | text | Original filename. |
| `size_bytes` | bigint | |
| `sha256` | text | Unique per owner; duplicate detection. |
| `storage_path` | text | Supabase Storage object path (see Storage). |
| `source_format` | text | `otlp_json` for Stage 1. |
| `status` | text | `received` → `processing` → `complete` \| `failed`. |
| `error_message` | text | Readable reason when `failed`. |
| `attempts` | integer | Ingestion attempts so far; incremented by the worker. |
| `parse_warnings` | jsonb | Count + samples of skipped malformed spans. |
| `last_attempt_at` | timestamptz | Set when a worker claims the job; the stuck-upload sweep keys off this. |
| `created_at`, `processed_at` | timestamptz | |

`uploads.status` is the state of record for ingestion. Redis holds in-flight job messages only; if Redis loses a job, a sweep re-enqueues uploads stuck in `received`/`processing` past a timeout (see [6_architecture.md](6_architecture.md)).

### traces

One user-visible trace derived from an upload. One upload may produce many traces.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `upload_id` | uuid | References `uploads.id`. |
| `owner_id` | uuid | Denormalized from upload for access checks. |
| `source_trace_id` | text | Original OTLP trace ID. |
| `name` | text | |
| `status` | text | `ok` \| `error`. |
| `started_at`, `ended_at` | timestamptz | |
| `duration_ms` | integer | |
| `span_count`, `error_count` | integer | |
| `provider`, `model`, `service_name` | text | Dominant values. |
| `tool_names` | text[] | |
| `error_types` | text[] | |
| `tags` | text[] | Contributor-editable. |
| `description` | text | Contributor-editable; shown on listing. |
| `visibility` | text | `private` (default) \| `listed`. |
| `listed_at` | timestamptz | Set when first listed. |
| `source_format`, `importer_version` | text | Provenance. |
| `search_tsv` | tsvector | Generated column; see Search. |
| `created_at` | timestamptz | |

### spans

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `trace_id` | uuid | References `traces.id`, cascade delete. |
| `source_span_id`, `source_parent_span_id` | text | Tree reconstruction. |
| `name` | text | |
| `kind` | text | `llm` \| `agent` \| `tool` \| `chain` \| `retriever` \| `embedding` \| `other`. |
| `started_at`, `ended_at` | timestamptz | |
| `duration_ms` | integer | |
| `status`, `status_message`, `error_type` | text | |
| `provider`, `model`, `tool_name` | text | |
| `input_tokens`, `output_tokens`, `total_tokens` | integer | Nullable. |
| `attributes` | jsonb | Full raw OTLP attributes. May contain prompt/output text. |
| `events` | jsonb | Raw OTLP events array. |

### acquisitions

One row per consumer-trace entitlement. The "purchase" object: in Stage 1 every acquisition is free, but the record is what grants download access and populates the consumer's library. Pricing/payment attach here later without changing access semantics.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `consumer_id` | uuid | References `profiles.id`. |
| `trace_id` | uuid | References `traces.id`. |
| `price_usd` | numeric | Always `0` in Stage 1; column exists so the shape is honest. |
| `acquired_at` | timestamptz | |

Constraints: unique `(consumer_id, trace_id)` — acquiring is idempotent. Owners do not acquire their own traces (API rejects; ownership already grants access). `trace_id` references `traces.id` with `on delete cascade`: deleting a trace deletes its acquisitions. For $0 acquisitions orphaned entitlement rows are dead weight; retention gets revisited when licensing becomes real. Unlisting keeps acquisition rows but the trace no longer resolves for non-owners (`404`, downloads included) — visibility is the contributor's kill switch over sensitive data. Relisting restores access to existing acquirers.

### dead_letters

One row per ingestion job that exhausted its retries. The DLQ lives in Postgres, not Redis, so it is durable and inspectable with SQL.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `upload_id` | uuid | References `uploads.id`. |
| `task_name` | text | `ingest_upload` in Stage 1. |
| `attempts` | integer | Total attempts made. |
| `last_error` | text | Final exception, readable. |
| `error_context` | jsonb | Traceback tail, timing per attempt. No raw payload content. |
| `failed_at` | timestamptz | |
| `requeued_at` | timestamptz | Set when an operator re-enqueues; null otherwise. |

Writing a `dead_letters` row also sets the upload to `failed` with a readable `error_message`. Requeue is a small CLI command (`make requeue UPLOAD=…`) that resets the upload and enqueues a fresh job.

Indexes: `spans(trace_id, started_at)`, `traces(owner_id)`, `traces(upload_id)`, `traces(visibility) where visibility = 'listed'`, GIN on `traces.search_tsv`, unique `(owner_id, sha256)` on uploads, unique `(consumer_id, trace_id)` plus `acquisitions(consumer_id)` and `acquisitions(trace_id)` on acquisitions, `dead_letters(upload_id)`.

## Storage

One private Supabase Storage bucket `raw-traces`. Object path: `raw/{owner_id}/{sha256}.json`. Objects are written once at upload and never mutated. No public URLs; downloads are served through the API after an access check.

## Search

`traces.search_tsv` is a generated tsvector over: `name`, `description`, `provider`, `model`, `service_name`, `tool_names`, `error_types`, `tags`. Span `attributes` and `events` are never included. Structured filters operate directly on trace columns.

## Access Rules

Enforced in the API; mirrored as RLS policies for defense in depth.

| Action | Rule |
|---|---|
| Read upload, private trace, its spans | Owner only. |
| Read listed trace and its spans (inspection) | Any authenticated user. |
| Download raw payload | Owner, or consumer with an acquisition for the trace. |
| Acquire a trace | Any authenticated non-owner, trace must be `listed`. |
| Read own acquisitions / library | Consumer only. |
| Search / marketplace results | Own traces + listed traces. |
| Create upload | Any authenticated user. |
| Change visibility, tags, description | Owner only. |
| Delete trace | Owner only; spans and acquisitions cascade. When no other trace references the upload, the upload row and its storage object are deleted too — every surviving upload stays downloadable, no half-dead state. |

Inspection is deliberately open for listed traces: consumers evaluate quality before acquiring. Acquisition gates download (the deliverable) and builds the library. When real pricing exists, pre-acquisition span visibility becomes a preview/redaction decision — out of scope here.

The API connects with the service role and applies these rules in queries; RLS policies express the same rules so a future direct-from-frontend Supabase read cannot bypass them.
