# API

FastAPI, versioned under `/v1`. All endpoints require a Supabase JWT in `Authorization: Bearer`, verified server-side. The frontend consumes this API only — no direct Supabase data access from the browser (auth excepted).

Errors use one shape everywhere:

```json
{ "error": { "code": "duplicate_upload", "message": "You already uploaded this file.", "details": {} } }
```

## Endpoints

### POST /v1/uploads

Multipart file upload. Validates (size, JSON parse, envelope, duplicate hash), stores the raw payload, creates the `uploads` row with status `received`, and enqueues an `ingest_upload` job on Redis. Returns `201` immediately; the worker does the rest (see [6_architecture.md](6_architecture.md)).

Request contract — `multipart/form-data` with exactly one part:

| Part | Type | Notes |
|---|---|---|
| `file` | file | The trace payload, verbatim bytes. Part `filename` becomes `uploads.filename`; part content type is ignored. |

No other fields. There is no upload-time name/tags/description (trace-level, set post-ingestion via `PATCH /v1/traces/{id}`), and no client-supplied hash or format hint — the server computes `sha256` and detects `source_format` from the bytes. The stored object is byte-identical to the uploaded part. Missing or extra parts: `422 invalid_request`.

```json
{ "upload_id": "…", "status": "received", "sha256": "…" }
```

Failure cases: `411 length_required` (no `Content-Length`; required so the size check runs before the body is consumed), `413 file_too_large` (limit 25 MB, env-configurable), `422 invalid_request` (missing/extra parts), `422 invalid_json`, `422 unsupported_format`, `409 duplicate_upload` (details include the existing `upload_id`), `429 rate_limited`.

### GET /v1/uploads

The caller's own uploads, newest first. Backs the uploads list on `/upload`.
Returns upload rows (no payload content): `upload_id`, `filename`,
`size_bytes`, `status`, `error_message`, `created_at`, `processed_at` — plus
`total`. `limit`/`offset` pagination, max limit 100.

### GET /v1/uploads/{upload_id}

Owner only. Upload status for polling from the upload page.

```json
{
  "upload_id": "…", "filename": "…", "status": "complete",
  "error_message": null, "parse_warnings": { "skipped_spans": 2 },
  "trace_ids": ["…"], "created_at": "…", "processed_at": "…"
}
```

### GET /v1/uploads/{upload_id}/download

Owner only. Returns the raw uploaded payload byte-identical
(`Content-Disposition` attachment, original filename; buffered — fine under
the 25 MB upload cap). This is the
contributor's own-file download; consumer download is trace-level
(`GET /v1/traces/{trace_id}/download`).

### GET /v1/traces

Lists traces visible to the caller. Query params:

| Param | Meaning |
|---|---|
| `scope` | `mine` (default), `marketplace` (listed traces only), or `acquired` (the caller's library). |
| `q` | Full-text query against `search_tsv`. |
| `provider`, `model`, `tool` | Exact-match filters. |
| `has_errors` | `true` filters to `error_count > 0`. |
| `from`, `to` | `started_at` date range. |
| `sort` | `created_at` (default), `duration_ms`, `span_count`. |
| `limit`, `offset` | Pagination, max limit 100. |

Returns result cards: trace metadata columns only (no spans, no attributes), plus `owner_display_name`, `acquired` (boolean for the caller), and `total` count.

### GET /v1/traces/{trace_id}

Owner or listed. Full trace metadata row including description, tags, visibility, provenance, plus the caller's relationship to it: `is_owner`, `acquired`, `can_download`.

### GET /v1/traces/{trace_id}/spans

Owner or listed. All spans for the trace ordered by `started_at`, returning the light fields only: ids, name, kind, timing, status fields, provider/model/tool, token counts — no `attributes` or `events` (a trace's span attributes can total tens of MB; the tree never needs them). The frontend reconstructs the tree from `source_parent_span_id`. Paginated at 500 spans per page.

### GET /v1/traces/{trace_id}/spans/{span_id}

Owner or listed. One span with full `attributes` and `events` JSONB. Fetched when a span is selected in the detail panel, so payload cost scales with what the user inspects, not with trace size.

### POST /v1/traces/{trace_id}/acquire

Consumer "purchase" without exchange logic. Creates an acquisition for the caller at `price_usd: 0` and returns it. Idempotent: acquiring an already-acquired trace returns the existing record with `200`.

```json
{ "acquisition_id": "…", "trace_id": "…", "price_usd": 0, "acquired_at": "…" }
```

Failure cases: `404` (trace not visible to caller), `409 own_trace` (owners don't acquire their own traces), `409 not_listed` (trace is private).

### GET /v1/traces/{trace_id}/download

Owner or acquirer only. Returns the original raw uploaded payload (`Content-Disposition` attachment, original filename; buffered — fine under the 25 MB upload cap, same as the uploads download). A listed-but-not-acquired trace returns `403 acquisition_required` with a readable message pointing at the acquire action.

### PATCH /v1/traces/{trace_id}

Owner only. Mutable fields: `visibility`, `tags`, `description`. Setting `visibility: "listed"` requires `"confirm_ownership": true` in the body (the UI checkbox); otherwise `422 confirmation_required`.

### DELETE /v1/traces/{trace_id}

Owner only. Cascades per data-model rules.

### GET /v1/health

Unauthenticated liveness check used by Docker Compose and the smoke script.

## Conventions

- Pydantic models define every request/response; OpenAPI is the contract for frontend types.
- All endpoints sit behind global and per-user rate limits (Redis token bucket; limits in [6_architecture.md](6_architecture.md)), except `GET /v1/health`, which Compose healthchecks poll. Exceeding either returns `429 rate_limited` with `Retry-After`.
- No endpoint ever returns another user's private trace, even by ID probe (`404`, not `403`, for traces the caller cannot see exist).
- Logs include IDs and statuses, never span `attributes`, `events`, or raw payload bodies.
