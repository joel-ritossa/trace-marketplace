# Slice 1 Audit

Post-implementation review of the raw upload loop, per the `code-audit` skill.
All axes walked (correctness, spec conformance, modularity, future-proofing,
security/auth, reliability invariants, consistency) plus extra passes on
DoS/abuse, test coverage, observability, and accessibility. All findings below
were fixed in this pass unless marked otherwise.

## Bugs

1. **Invalid `X-Fault` validated after side effects** (`routers/uploads.py`).
   A bad value 422'd *after* the object + row were created, leaving a
   stored-but-never-enqueued upload that 409'd on re-upload and silently
   completed later via the sweep. Fix: validate the header first, before any
   writes; arming still happens after the row exists. Regression test:
   `test_invalid_fault_rejected_without_side_effects`.
2. **`Content-Disposition` filename too lightly sanitized.** Only `"` was
   stripped; CR/LF or non-latin-1 in the client-supplied filename made the
   response header unencodable → 500 on a legitimate download. Fix: strip to
   printable ASCII with an `upload.json` fallback. Verified manually with a
   control-char + unicode filename.
3. **Unbounded body consumption without `Content-Length`.** The size
   pre-check only ran when the header was present; a chunked request let
   `request.form()` spool an arbitrarily large file part to disk before the
   25 MB check. Fix: `411 length_required` when the header is absent (every
   real client sends it). Spec amended. Verified manually with a chunked
   request.
4. **Delayed retry re-kicks failed unobservably** (`worker/middleware.py`).
   An exception in the detached `_kick_later` task (e.g. Redis down during
   the backoff window) was never logged. Fix: try/except with
   `logger.exception`; the sweep remains the recovery path.

## Spec amendments (implementation kept, spec corrected)

- `3_api.md` download: "streams" → "returns … buffered", honest under the
  25 MB cap. Revisit streaming when consumer trace downloads land.
- `3_api.md` conventions: `GET /v1/health` documented as rate-limit-exempt
  (Compose healthchecks poll it).
- `3_api.md` POST failure cases: added `411 length_required` (bug 3).
- `2_data-model.md` / `6_architecture.md`: `uploads.last_attempt_at` (below).

## Reliability

- **Sweep keyed off `created_at`** re-enqueued a legitimately long-running
  job every 60s for as long as it ran. Added `uploads.last_attempt_at`
  (stamped by `mark_processing`); `stuck_ids` uses
  `coalesce(last_attempt_at, created_at)`, so duplicates space out to once
  per timeout window. Matters for Slice 2 where parsing gets expensive.
  Migration edited in place (uncommitted) + `ALTER` applied to the live DB.
- **Noted, accepted:** enqueue failure after row creation → client 500,
  retry 409s, sweep ingests within 10 min (self-heals by design); repeated
  exhaust cycles can produce multiple `dead_letters` rows per upload
  (`mark_requeued` clears all open ones).

## Modularity / consistency

- Test signup extracted to `conftest.signup_token()`; the owner-scope test's
  inline duplicate removed.
- `upload-flow.tsx`: mount load reuses `refreshList` (promise-callback form —
  the `react-hooks/set-state-in-effect` rule traces setState through
  async/await but not `.then`); poll interval keyed on the upload id so it
  survives per-tick state updates; list failures keep stale data instead of
  blanking.
- Broker imports: app code imports `app.worker.broker` directly;
  `app.worker.__init__` is documented as the taskiq CLI entrypoint only
  (package attribute `broker` shadows the submodule name — known trap).
- `asyncpg.DataError` top-level access style; retry middleware reads the
  upload id from args *or* kwargs (was positional-only and would IndexError
  inside the error handler).

## Future-proofing

- Frontend 25 MB limit now has a single source (`UPLOAD_MAX_BYTES` in
  `lib/api/uploads.ts`) feeding both the pre-check and the dropzone copy,
  with a keep-in-sync note. A `/v1/config` endpoint stays deferred — one
  number doesn't justify an endpoint yet.
- Compose `DEV_ROUTES` is `${DEV_ROUTES:-true}` instead of hardcoded.
- `requeue` CLI now refuses uploads not in `failed` (was: reset anything,
  including `complete`).
- `api` got a Compose healthcheck (stdlib urllib; image has no curl); `web`
  waits on `service_healthy`.

## Security & auth

Clean: pinned JWT algorithms/audience/required claims, RLS mirrors the spec,
no payload bodies or secrets in logs, unverified-sub rate-limit key documented
with bounded blast radius. Forward note for Slice 2: `dead_letters.last_error`
stores `str(exception)` — importer exceptions must not embed payload content.

## Observability

API now logs one info line per created upload (id, filename, size, sha
prefix). Worker logging was already adequate.

## Test coverage added

`test_unknown_upload_ids_404` (random UUID + non-UUID `DataError` branch),
`test_unauthenticated_rejected`, `test_permanent_failure_fails_immediately`
(no retries, no DLQ row), `test_invalid_fault_rejected_without_side_effects`.
Sweep behavior remains untested (needs a 10-minute clock); accepted.

## Outcome

Verified against the rebuilt Compose stack on 2026-06-10:

- `ruff check`/`format`, `eslint --max-warnings 0`, `next build` pass.
- Integration suite: 14 passed (10 existing + 4 new), including retry/DLQ/
  requeue against the live stack.
- Manual probes: chunked POST → `411 length_required`; hostile filename
  uploads and downloads byte-identical with a safe header; `api` container
  reports healthy.
