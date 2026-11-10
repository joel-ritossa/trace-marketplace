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
| `outcome`, `loop_kind` | Equality; comma-separated values OR within a field (`outcome=failure,partial`). `outcome` is the session outcome. |
| `failure_mode`, `task_category` | Match when the session's array (`failure_modes` / `task_categories`, the union over turns) contains any requested value; comma-separated, OR. |
| `has_retry_loop`, `recovered_from_error`, `truncation_suspected` | `true`/`false`. |
| `duration_ms_gte`, `total_tokens_gte`, `llm_call_count_gte`, `tool_call_count_gte` | Min-bound on numerics (`field >= x`) — the only range shape in stage 2. |

Removed with the agent judge: the `*_provenance` and `*_confidence_gte` filters and the repeatable `metric` filter (and its `GET /v1/traces/metric-keys` enumeration). Stored subscription queries containing them were stripped by migration 17.
This vocabulary **is** the subscription query language: `subscriptions.query` stores exactly this param map (minus `scope`/`sort`/`limit`/`offset`). Any field that becomes filterable is automatically subscribable.

Result cards gain: `outcome`, `task_categories`, `failure_modes` (session level), `analysis_status` (`pending | in_progress | final | skipped`), `analysis_failed`, `has_open_review_item` / `open_review_item_id` (owner only).

## New And Changed Endpoints

### Analysis block on GET /v1/traces/{trace_id}

There is no separate `/analysis` endpoint. Owner or listed; the trace detail carries an `analysis` block for the trace-detail Analysis section ([9_session-analysis.md](9_session-analysis.md) API):

```json
{
  "session": {
    "status": "final",
    "turn_count": 12,
    "skip_reason": null,
    "goal": "…",
    "outcome": "partial",
    "summary": "…",
    "task_categories": ["debugging", "coding"],
    "failure_modes": ["invalid_invocation"],
    "analyzed_at": "…",
    "signals": { "has_retry_loop": true, "loop_kind": "cycle", "…": "…" }
  },
  "turns": [
    {
      "turn_index": 0, "outcome": "success", "summary": "…", "uncertain": null,
      "provenance": "machine", "signals": { "…": "…" },
      "labels": [
        { "field": "task_category", "value": "debugging", "span_ids": [], "reason": null },
        { "field": "failure_mode", "value": "invalid_invocation", "span_ids": ["…"], "reason": "…" }
      ]
    }
  ],
  "failed_reason": null,
  "open_review_item_id": "…"
}
```

`session.status` follows [2_data-model.md](2_data-model.md): `pending | in_progress | final | skipped` (`skipped` carries `skip_reason`: `not_configured | owner_opt_out`). `failed_reason` is the open analyze dead letter's error, verbatim. `open_review_item_id` and `turns[].uncertain` are owner-only (null for everyone else, here and in `labels.jsonl`). Cited `span_ids` are `source_span_id`s inside the turn. There is no confidence, votes, audit block, or metric scores; the behavior summary is `session.goal` + `session.summary`.

### POST /v1/traces/{trace_id}/analyze

Owner only. Finalizes now — the last turn and the roll-up are judged whatever the idle state ([9_session-analysis.md](9_session-analysis.md) When analysis runs). Returns `{ status, queued }`: `200` with `queued: false` when the trace is already `final` (nothing enqueued); otherwise `202` with `queued: true` — a run in flight gets the request noted (it finalizes after, attempt counter untouched), else a finalizing job is enqueued with a reset attempt counter.

### PUT /v1/traces/{trace_id}/turns/{turn_index}/labels

Owner only. Body: `outcome`, `task_categories` (≥ 1, known values, no duplicates), `failure_modes` (`[{ value, span_ids, reason }]`, one entry per value; `span_ids` (≤ 100, distinct) must be llm/tool spans inside the turn — the judge's citation rule — else `422`; `reason` ≤ 2000 chars) — the turn's full label set, replacing what was there. The turn becomes `provenance = human` and is never re-judged, `uncertain` clears, the session arrays are recomputed, the review item closes when no uncertain turn is left, and a finalizing run re-rolls the session verdict up. Returns the analysis block. `404` unknown turn, `409 analysis_pending` if the turn has not been judged yet. That finalizing run fires subscription matching on a listed trace (trigger c).

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

One open item per trace, listing its uncertain turns. Items are created and closed server-side only (analysis runs and relabels); there is no resolve endpoint and no client-created item.

- `GET /v1/review-items` — the caller's items (own traces only), newest first, `limit`/`offset`, optional `upload_id` (the digest link's filter); each row: trace summary, `context` (`{ turns: [{ turn_index, reason, summary }] }`), `status`, `created_at`, and the trace's `upload_id` / `upload_filename` (per-upload grouping). `status` param: `open` (default), `resolved`, `superseded`, or `all`.
- `GET /v1/review-items/{id}` — one item; resolved items include `resolved_at`, `resolved_by`.
- Relabelling happens on the turn: `PUT /v1/traces/{id}/turns/{turn_index}/labels` (above).

### Subscriptions (JWT only)

- `POST /v1/subscriptions` — body `{ "name": "…", "query": { …filter params… } }`. Query validated against the filter vocabulary; unknown params `422`.
- `GET /v1/subscriptions` — the caller's subscriptions with live match counts and last-match time.
- `PATCH /v1/subscriptions/{id}` — `name` and/or `query`.
- `DELETE /v1/subscriptions/{id}` — hard delete (matches cascade; library unaffected).
- `GET /v1/subscriptions/{id}/results` — executes the stored query live against listed traces (same shape as `GET /v1/traces`), each card annotated `new_since_last_seen`.
- `POST /v1/subscriptions/{id}/seen` — sets `last_seen_at` to now.

**Matching is event-driven, three triggers:** (a) a trace becomes listed; (b) `analyze_trace` writes labels on a listed trace; (c) a turn relabel writes labels to a listed trace (a human relabel can newly satisfy a stored query — without this trigger the feed shows the trace but no match record or notification ever lands). On any trigger, the worker evaluates which subscriptions newly match, inserts `subscription_matches` rows (unique pair = dedupe), and upserts one **digested** `subscription_match` notification per subscription — at most one unread digest per (user, subscription), its match count incrementing as first-matches land (the flood-control law; same mechanics as the per-upload review digest). No cron sweep. Subscriptions never match private traces.

Listing a trace that is not final — or whose LLM analysis was skipped for `owner_opt_out` (single or bulk visibility change) — enqueues a finalizing `analyze_trace` run; the resulting fields reach subscriptions through trigger (b). Listing is the consent act and covers analysis ([1_analysis.md](1_analysis.md) Runtime).

### Bulk operations (JWT only)

All bulk endpoints take `trace_ids[]` (max 100 per call) and return itemized results — partial success is normal, never all-or-nothing.

- `POST /v1/traces/acquire` — bulk acquire; per-trace semantics identical to the stage-1 single acquire (idempotent, $0, listed-only, owners included). Itemized statuses: `acquired | already_acquired | not_listed | not_found`.
- `POST /v1/traces/visibility` — bulk list/unlist; owner-only per trace. Body: `{ "trace_ids": […], "visibility": "listed", "confirm_ownership": true }`; `confirm_ownership` required when listing (batched consent — one confirmation covering the named selection), `422 confirmation_required` otherwise. Itemized: `updated | not_found`.
- `POST /v1/traces/download` — bulk download; every trace must be owner-or-acquired, else `403 acquisition_required` listing the offending ids. Streams a zip: each payload under its original filename (suffixed with the storage-object hash on collision) plus one **`labels.jsonl`** — one line per trace: `trace_id`, the `session` block (outcome, goal, summary, `task_categories`, `failure_modes`, status, session signals) and `turns[]` (per-turn outcome, labels with cited `span_ids` and reasons, provenance, signals) — the same shapes as the detail's analysis block. Unanalyzed traces get a `pending` session and no turns. Works for a single id — this is also the labeled-download path for one trace. Payload selection per trace follows the redaction boundary ([7_redaction.md](7_redaction.md)): owner → raw object, acquirer → scrubbed artifact; the stage-1 single download applies the same rule.

## Conventions

- Notification, review-item, and match creation happen server-side in worker jobs / API logic — no client can create them.
- Subscription queries are validated at write time against the same filter vocabulary the API parses, so a stored query can never fail to execute later (taxonomy soft-retires keep old values matchable).
- Bulk endpoints sit behind the standard per-user rate bucket; the zip download streams and is capped by the existing upload size limit × selection cap.
