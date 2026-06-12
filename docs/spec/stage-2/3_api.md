# API

Additions to the stage-1 API. Stage-1 conventions hold everywhere: `/v1` versioning, one error shape, Pydantic models / OpenAPI as the frontend contract, rate limits on everything but health, `404`-not-`403` for invisible objects, no span bodies in logs.

## Authentication

The `Authorization: Bearer` header accepts **either** a Supabase JWT **or** an API key (format `tmk_` + 32 random chars; matched by SHA-256 against `api_keys.key_hash`). This is the only modification to stage-1 code.

- **API-key principals reach exactly two endpoints:** `POST /v1/uploads` and `GET /v1/uploads/{id}` (upload-only scope). Everything else returns `401 unauthorized` for keys (stage-1's single auth error code; no new code).
- Revoked keys fail auth. Successful key auth updates `last_used_at` (throttled) and stamps `uploads.source = 'cli'` on created uploads.

## Filter-Language Extension on GET /v1/traces

The stage-1 params remain. New params, all backed by a single shared filter builder that joins `trace_analysis` once (1:1 PK join). **Null never matches**: any analysis predicate excludes not-yet-analyzed traces.

| Param | Meaning |
|---|---|
| `outcome`, `failure_mode`, `task_category`, `loop_kind` | Equality; comma-separated values OR within a field (`outcome=failure,indeterminate`). |
| `outcome_provenance`, `failure_mode_provenance`, `task_category_provenance` | Same; `human,human_confirmed` expresses "not machine-only". |
| `has_retry_loop`, `recovered_from_error`, `truncation_suspected` | `true`/`false`. |
| `outcome_confidence_gte`, `task_category_confidence_gte` | Numeric min-bound (`field >= x`) — the only range shape in stage 2. |
| `duration_ms_gte`, `total_tokens_gte`, `llm_call_count_gte`, `tool_call_count_gte` | Min-bound on numerics (stage-1 numerics get this for free). |
| `metric` | Repeatable; `metric=<name>:<min>` → `metric_scores-><name> >= min`. Boolean-flag metrics accept `metric=<name>:true`. |

This vocabulary **is** the subscription query language: `subscriptions.query` stores exactly this param map (minus `scope`/`sort`/`limit`/`offset`). Any field that becomes filterable is automatically subscribable.

Result cards gain: `outcome`, `outcome_confidence`, `outcome_provenance`, `analysis_state`, `has_open_review_item`.

## New And Changed Endpoints

### GET /v1/traces/{trace_id}/analysis

Owner or listed. The full analysis view for the trace-detail Analysis section:

```json
{
  "analysis_state": "complete",
  "labels": {
    "outcome":       { "value": "failure", "confidence": 0.8, "provenance": "machine" },
    "failure_mode":  { "value": "tool_output_misinterpretation", "confidence": 0.6, "provenance": "machine" },
    "task_category": { "value": "web_research", "confidence": 1.0, "provenance": "human" }
  },
  "summary": { "gist": "…", "steps": ["…"] },
  "reasoning": "…",
  "signals": { "has_retry_loop": true, "loop_kind": "cycle", "...": "…" },
  "metric_scores": { "faithfulness": 0.82, "hallucination": false },
  "open_review_item_id": "…",
  "audit": { "analyzers": [ { "analyzer": "judge", "analyzer_version": "…", "model_id": "…", "votes": ["…"], "rendering_truncated": false } ] }
}
```

`analysis_state` follows [2_data-model.md](2_data-model.md): `pending | complete | skipped | failed` (with the dead-letter reason verbatim on `failed`; `skipped` carries `skip_reason`: `not_configured | owner_opt_out`). `summary` is the behavior summary ([1_analysis.md](1_analysis.md)), read from the `summary` analyzer row; null when none exists.

### API keys (JWT only)

- `POST /v1/api-keys` — body `{ "name": "…" }`. Returns the key **plaintext exactly once** plus the row (`api_key_id`, `name`, `key_display`, `created_at`).
- `GET /v1/api-keys` — the caller's keys: `name`, `key_display`, `scope`, `created_at`, `last_used_at`, `revoked_at`.
- `DELETE /v1/api-keys/{id}` — soft revoke (sets `revoked_at`); idempotent.

### Profile

- `GET /v1/profile` / `PATCH /v1/profile` — read and update `display_name`, `allow_private_llm_analysis`, and `task_categories` (validated against the global enum, `other` rejected; deduplicated; empty array = unscoped).

### Notifications

- `GET /v1/notifications` — newest first, `limit`/`offset`, plus `unread_count` and `total`.
- `POST /v1/notifications/read` — body `{ "ids": ["…"] }` or `{ "all": true }`. Idempotent.

### Review items

- `GET /v1/review-items` — the caller's open items (own traces only), newest first, `limit`/`offset`; each row: trace summary, `question_type`, `context` (machine verdict + confidence + routing reasons), `created_at`, and the trace's `upload_id` (for per-upload grouping). `status` param to include resolved.
- `GET /v1/review-items/{id}` — one item; resolved items include `answer`, `resolved_at`, `resolved_by`.
- `POST /v1/review-items/{id}/resolve` — body is a partial answer: any of `outcome`, `failure_mode`, `task_category`. App-validates values against the taxonomies. Writes answered fields to `trace_analysis` with provenance `human` (or `human_confirmed` when matching the machine value) and confidence 1.0; marks the item `resolved`. `409 already_resolved` on a resolved item.
- `POST /v1/traces/{trace_id}/review-items` — owner-initiated relabel: creates (or returns the existing) open item with empty routing reasons. Owner only.

### Subscriptions (JWT only)

- `POST /v1/subscriptions` — body `{ "name": "…", "query": { …filter params… } }`. Query validated against the filter vocabulary; unknown params `422`.
- `GET /v1/subscriptions` — the caller's subscriptions with live match counts and last-match time.
- `PATCH /v1/subscriptions/{id}` — `name` and/or `query`.
- `DELETE /v1/subscriptions/{id}` — hard delete (matches cascade; library unaffected).
- `GET /v1/subscriptions/{id}/results` — executes the stored query live against listed traces (same shape as `GET /v1/traces`), each card annotated `new_since_last_seen`.
- `POST /v1/subscriptions/{id}/seen` — sets `last_seen_at` to now.

**Matching is event-driven, three triggers:** (a) a trace becomes listed; (b) `analyze_trace` completes on a listed trace; (c) a review-item resolve writes labels to a listed trace (a human relabel can newly satisfy a stored query — without this trigger the feed shows the trace but no match record or notification ever lands). On any trigger, the worker evaluates which subscriptions newly match, inserts `subscription_matches` rows (unique pair = dedupe), and upserts one **digested** `subscription_match` notification per subscription — at most one unread digest per (user, subscription), its match count incrementing as first-matches land (the flood-control law; same mechanics as the per-upload review digest). No cron sweep. Subscriptions never match private traces.

Listing a trace whose LLM analysis was skipped for `owner_opt_out` (single or bulk visibility change) also enqueues an `analyze_trace` re-run; the resulting fields reach subscriptions through trigger (b). Listing is the consent act and covers analysis ([1_analysis.md](1_analysis.md) Runtime).

### Bulk operations (JWT only)

All bulk endpoints take `trace_ids[]` (max 100 per call) and return itemized results — partial success is normal, never all-or-nothing.

- `POST /v1/traces/acquire` — bulk acquire; per-trace semantics identical to the stage-1 single acquire (idempotent, $0, listed-only, owners included). Itemized statuses: `acquired | already_acquired | not_listed | not_found`.
- `POST /v1/traces/visibility` — bulk list/unlist; owner-only per trace. Body: `{ "trace_ids": […], "visibility": "listed", "confirm_ownership": true }`; `confirm_ownership` required when listing (batched consent — one confirmation covering the named selection), `422 confirmation_required` otherwise. Itemized: `updated | not_found`.
- `POST /v1/traces/download` — bulk download; every trace must be owner-or-acquired, else `403 acquisition_required` listing the offending ids. Streams a zip: each payload under its original filename (suffixed with the storage-object hash on collision) plus one **`labels.jsonl`** — one line per trace: `trace_id`, `outcome`, `failure_mode`, `task_category` (each with confidence + provenance), `metric_scores`, promoted signals, `analyzer versions`. Unanalyzed traces get a line with `trace_id` and nulls. Works for a single id — this is also the labeled-download path for one trace. Payload selection per trace follows the redaction boundary ([7_redaction.md](7_redaction.md)): owner → raw object, acquirer → scrubbed artifact; the stage-1 single download applies the same rule.

## Conventions

- Notification, review-item, and match creation happen server-side in worker jobs / API logic — no client can create them.
- Subscription queries are validated at write time against the same filter vocabulary the API parses, so a stored query can never fail to execute later (taxonomy soft-retires keep old values matchable).
- Bulk endpoints sit behind the standard per-user rate bucket; the zip download streams and is capped by the existing upload size limit × selection cap.
