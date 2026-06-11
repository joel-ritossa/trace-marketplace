# Slice 1 — Raw Upload Loop

Spec: `docs/spec/stage-1/5_build-order.md` (Slice 1), `6_architecture.md` (reliability),
`3_api.md` (uploads endpoints), `2_data-model.md` (uploads, dead_letters, storage).

**Done when:** upload a fixture file, see it stored and listed, download the
identical bytes back; duplicates and invalid files are rejected with readable
reasons; a fault-injected transient failure retries to success, and an exhausted
job lands in `dead_letters` with the upload marked `failed`.

## Plan

### Migration

`00000000000002_uploads.sql`:

- `uploads` table per 2_data-model.md (id, owner_id, filename, size_bytes,
  sha256, storage_path, source_format, status, error_message, attempts,
  parse_warnings, created_at, processed_at). Unique `(owner_id, sha256)`.
  RLS: owner can select own rows (API uses service role; policy is the
  defense-in-depth mirror per the spec).
- `dead_letters` table per 2_data-model.md. RLS enabled with no policies —
  service-role only, operators read it with SQL.
- `raw-traces` private storage bucket created in the migration
  (`insert into storage.buckets`), so a fresh `db reset` provisions everything.

### Backend — upload path

- `app/storage.py`: thin async client for Supabase Storage's HTTP API (httpx,
  service-role key): `put(path, bytes)`, `get(path)`, `delete(path)`. New
  required setting `supabase_service_role_key` (and `supabase_storage_url`
  derived from `supabase_url`).
- `POST /v1/uploads` (`routers/uploads.py`): multipart with exactly one `file`
  part → 413 over `upload_max_bytes` (25MB default, env-configurable) → sha256
  → duplicate check `(owner_id, sha256)` → 409 `duplicate_upload` with existing
  `upload_id` in details → JSON parse → 422 `invalid_json` → envelope check
  (`resourceSpans` key ⇒ `otlp_json`) → 422 `unsupported_format` → store object
  at `raw/{owner_id}/{sha256}.json` → insert `uploads` row (`received`) →
  enqueue `ingest_upload(upload_id)` → 201.
- `GET /v1/uploads` — owner's uploads, newest first (id, filename, size,
  status, error_message, created_at, processed_at). **Spec gap:** 3_api.md
  doesn't define a list endpoint but the /upload page spec requires "a minimal
  uploads list"; amend 3_api.md.
- `GET /v1/uploads/{id}` — owner-only status for polling, per spec
  (`trace_ids` always `[]` this slice).
- `GET /v1/uploads/{id}/download` — owner-only, streams raw bytes back with
  original filename. **Spec gap:** build order requires "raw download of own
  uploads" but 3_api.md only has trace-level download (traces don't exist
  until Slice 2); amend 3_api.md.
- Queries in `app/queries/uploads.py`; response models in
  `app/schemas/upload.py`.

### Backend — reliability skeleton

- `ingest_upload(upload_id)` task (`worker/tasks.py`): set `processing` +
  increment `attempts` → fetch raw object → verify sha256 matches → set
  `complete` + `processed_at`. No parsing this slice. Idempotent by
  construction (status writes are absolute, no trace rows yet; the
  delete-and-rewrite invariant activates in Slice 2).
- Error classification (`worker/errors.py`): `PermanentIngestError` → mark
  upload `failed` with readable `error_message`, no retry. Anything else is
  transient → retry.
- Retries: taskiq retry middleware, max 5 attempts, exponential backoff with
  jitter (~2s → 60s cap). Custom small middleware (subclassing taskiq's
  `SimpleRetryMiddleware`) so exhaustion has a hook: write `dead_letters` row
  (attempts, last_error, traceback tail in `error_context`) + set upload
  `failed`.
- Stuck-upload sweep: taskiq scheduled task (every 60s) re-enqueues uploads in
  `received`/`processing` older than 10 minutes. Fired by a dedicated
  `scheduler` Compose service (same image as worker, `taskiq scheduler`
  entrypoint) — decided with the user; we'll likely hang more scheduled work
  off it later. Double-fires are harmless because the sweep re-enqueue is
  idempotent.
- Fault injection (for the done-when): dev-gated header `X-Fault` on
  `POST /v1/uploads` (`transient:N` = fail first N attempts, `permanent`,
  `exhaust`), honored only when `dev_routes` is on; stored in a transient
  marker the task reads. Exact mechanism may drift; the requirement is a
  deterministic way to demo retry-to-success and DLQ paths locally.
- Requeue: `make requeue UPLOAD=<id>` — Makefile target invoking a small
  module (`python -m app.cli.requeue`) that resets the upload to `received`,
  clears `error_message`, sets `dead_letters.requeued_at`, enqueues a fresh
  job.

### Backend — rate limiting

- `app/middleware/rate_limit.py`: token buckets in Redis (atomic Lua script),
  enforced as ASGI middleware ahead of routing. Buckets per 6_architecture.md:
  global 50 req/s burst 100; per-user 10 req/s burst 20; per-user
  `POST /v1/uploads` 10/min. Limits env-configurable with those defaults.
- Per-user key comes from the JWT `sub` claim parsed (not re-verified) in the
  middleware — rate limiting needs a cheap stable key, auth still happens in
  the dependency. Unauthenticated requests fall under the global bucket only.
- Exceeding any bucket → `429 rate_limited` with `Retry-After`, spec envelope.
- `/v1/health` is exempt (Compose healthcheck must not consume budget).

### Web

- `/upload` page: drop zone + file picker (single JSON file), client-side size
  check, `POST /v1/uploads`, then poll `GET /v1/uploads/{id}` until terminal.
  States per 4_pages.md: idle, uploading, received/processing (spinner +
  status text), complete, failed (verbatim `error_message`), duplicate (links
  to the existing upload), 413/422 reasons rendered readably.
- Minimal uploads list on the same page: filename, size, status badge,
  created, raw-download action. Status palette from DESIGN.md.
- App shell nav gains an Upload link.
- `lib/api`: upload types, multipart upload helper, status poll helper,
  authenticated download (fetch blob with bearer token → object URL).

### Tests

Per AGENTS.md, integration-first:

- API integration tests (pytest, against the running local stack):
  upload-validate matrix (happy path, too large, invalid JSON, wrong envelope,
  duplicate), owner-only access on status/list/download, byte-identical
  download.
- Reliability integration test: fault-injected transient → retries → success;
  exhaustion → `dead_letters` row + upload `failed`; requeue resets and
  completes.
- Rate-limit test: burst past the upload bucket → 429 + `Retry-After`.

### Verification (done-when walkthrough)

1. Upload a fixture OTLP JSON via `/upload` → status reaches `complete`, file
   listed, raw download byte-identical (`diff`/sha).
2. Re-upload same file → duplicate rejection with link; upload garbage → 422
   with readable reason.
3. Fault-inject `transient:2` → attempts=3, ends `complete`.
4. Fault-inject `exhaust` → 5 attempts, `dead_letters` row, upload `failed`;
   `make requeue` recovers it.
5. Burst uploads → `429 rate_limited` with `Retry-After`.

## Drift

1. **Custom `RetryDlqMiddleware` instead of taskiq's `SmartRetryMiddleware`.**
   The Redis list broker has no delayed delivery, and SmartRetryMiddleware's
   alternative (schedule-source retries) quantizes delays to the scheduler's
   minute tick — useless for 2s backoff. It also has no exhaustion hook for
   the DLQ write. The custom middleware (~60 lines) re-kicks after an
   in-process `asyncio.sleep` (non-blocking; doesn't hold a worker slot) and
   dead-letters on exhaustion. A worker crash during the wait loses only that
   re-kick — exactly what the stuck-upload sweep recovers.
2. **Spec amended for two gaps** (approved): `GET /v1/uploads` (list) and
   `GET /v1/uploads/{id}/download` (owner raw download) added to 3_api.md;
   the build order required both but the API spec defined neither. The
   `scheduler` Compose service was added to 6_architecture.md topology.
3. **`error_response` exposed from `app/errors.py`.** The rate-limit
   middleware runs outside the exception-handler stack, so it needs to build
   the spec envelope (plus `Retry-After`) directly; the handlers now share the
   same helper.
4. **`DEV_ROUTES` moved into the shared compose backend env.** The worker
   honors X-Fault markers only when the flag is on, so it needs the same
   setting as the API, not an api-only override.
5. **asyncpg pool gained a jsonb codec** so `parse_warnings`/`error_context`
   round-trip as dicts instead of strings.
6. **Permanent failures are handled inside the task**, not the middleware:
   `ingest_upload` catches `PermanentIngestError`, marks the upload failed,
   and returns normally — so the retry middleware only ever sees transients.
   Same behavior as spec'd, simpler routing than the planned "task wrapper".
7. **Bug caught in verification:** the single-part multipart check compared
   against `fastapi.UploadFile`, but `request.form()` yields *starlette's*
   `UploadFile` — every valid upload was rejected as `invalid_request`. The
   integration suite caught it on first run; check now uses the starlette
   class.
8. **Worker concurrency pinned** with `--max-async-tasks 4` on the worker
   command, matching the architecture's per-worker cap.
9. **DLQ `task_name` is taskiq's canonical registered name**
   (`app.worker.tasks:ingest_upload`), not the bare `ingest_upload` — kept
   because it's unambiguous for operators.

## Outcome

Done-when verified on 2026-06-11 against the Compose stack (api, worker,
scheduler, redis, web + local Supabase), via the integration suite
(`uv run pytest tests/integration` — 10 passed) plus an in-browser pass:

1. **Roundtrip** — fixture upload reaches `complete`, appears in the list,
   and downloads byte-identical (asserted on raw bytes in
   `test_upload_roundtrip`; verified in-browser via the `/upload` page with
   success state and download actions).
2. **Readable rejections** — duplicate → `409 duplicate_upload` with the
   existing `upload_id` in details; garbage → `422 invalid_json`; wrong
   envelope → `422 unsupported_format`; >25MB → `413 file_too_large`; extra
   parts → `422 invalid_request`. UI renders each reason verbatim.
3. **Retry to success** — `X-Fault: transient:2` → upload completes with
   `attempts = 3`, no DLQ row.
4. **Exhaustion + requeue** — `X-Fault: exhaust` → 5 attempts, `dead_letters`
   row with readable `last_error` + traceback tail, upload `failed` with a
   readable message; requeue CLI resets it, sets `requeued_at`, and the upload
   completes.
5. **Rate limiting** — 11th upload in a burst → `429 rate_limited` with
   `Retry-After`.
6. Ownership: other users get `404` on status/download and never see foreign
   uploads in lists. Scheduler fires the sweep every 60s (worker logs).
7. `ruff check`/`format`, eslint, and `next build` all pass.

**Status: done**, audited in [001_audit.md](001_audit.md). Next: Slice 2 —
Ingestion and Inspection.
