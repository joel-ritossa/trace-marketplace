# Slice 2 Reliability Sweep

Focused sweep of the delivery path — delivery guarantees, fault tolerance,
failure-mode classification — across API enqueue, broker, retry/DLQ
middleware, sweep, ingest transaction, storage client, and rate limiter.
Scoped to the local stack; deployment topology (replicas, managed Redis, etc.)
deferred to the infra pass. All five gaps below were fixed in this pass.

## What held up

- At-least-once delivery + idempotent consumer, with Postgres as the only
  state of record and Redis as a dumb pipe. No exactly-once machinery.
- The stuck-upload sweep doubles as a transactional-outbox substitute: every
  message-loss mode (Redis restart, worker crash mid-job or mid-backoff,
  failed enqueue) recovers from durable upload state via one mechanism.
- Object-first/row-second write ordering with sha-addressed objects; a crash
  between leaves a harmless orphan, never a dangling row.
- Checksum verification at consume time; typed permanent/transient routing;
  row-lock serialization of concurrent runs; bounded insert batches.

## Gaps fixed

1. **`complete` was not terminal** (`queries/uploads.py`,
   `worker/tasks/ingest.py`). A stale retry chain exhausting after a
   concurrent run succeeded would `mark_failed` over `complete` (DLQ row +
   `failed` status while the traces exist and are visible); `mark_processing`
   could likewise regress `complete` → `processing` and redo work. The state
   machine is now monotone at `complete`, enforced in SQL
   (`where status <> 'complete'`) rather than by the task's read-then-act
   check, which was a TOCTOU. The task now uses the atomic claim's `None`
   return as the drop signal. Test: `test_complete_is_terminal`.
2. **A failed enqueue failed an already-accepted request**
   (`routers/uploads.py`). The row commit is the acceptance of record; a
   broker blip after it now logs and still returns 201, with the sweep as the
   delivery guarantee. Previously: 500, then a confusing 409 on user retry.
3. **The retry cap rode on a volatile message label** (`worker/retry_dlq.py`).
   `_retries` reset to zero whenever the sweep re-enqueued a lost job, so
   total work per upload was unbounded and `dead_letters.attempts` lied. The
   cap is now enforced on `uploads.attempts` — the durable counter every claim
   already increments; the label is gone. The exhaust test now asserts
   `uploads.attempts == dead_letters.attempts`.
4. **Missing storage object classified transient**
   (`worker/tasks/ingest.py`). Supabase Storage returns 400/404 for a missing
   object; the fetch is immutable, so a 4xx can never succeed on retry —
   it burned 5 attempts and a DLQ row before failing. 4xx (except 429) now
   maps to `PermanentIngestError`; 429/5xx/network stay transient. Found
   empirically: the local stack returns **400**, not 404, for a missing key.
   Test: `test_missing_storage_object_fails_permanently`.
5. **Rate limiter failed closed on Redis loss**
   (`middleware/rate_limit.py`). Every request ran the Lua script unguarded;
   Redis down meant 500s on all routes, including Postgres-only trace reads.
   Rate-limit state is explicitly not state of record, so the limiter now
   fails open with a warning log.
   Test: `test_rate_limit_failopen.py` (unit, stubbed Redis).

## Noted and accepted (deliberate for local scope)

- In-process backoff sleep instead of broker-delayed delivery; loss window
  covered by the sweep. Revisit if the broker changes.
- Redis without persistence; worker SIGKILL drops the popped message — both
  recovered by the sweep, no ack/visibility machinery needed.
- DLQ-write failure with the DB down leaves the upload `processing` and the
  sweep looping until the DB returns — correct, since terminal states require
  the DB anyway.
- Trace-ID churn on re-ingest: known TODO in `ingest.py`; the terminal-state
  guards shrink the re-run-after-complete window to ~zero. Stable trace
  identity lands when derived analysis attaches to trace IDs.

## Spec amendments

`6_architecture.md`: enqueue is best-effort after the committed row;
storage 4xx classified permanent; `complete` documented as terminal with SQL
guards; retry budget defined as `uploads.attempts`; limiter documented as
fail-open.

## Verification

- Unit: 25 passed (new: rate-limit fail-open). Integration: 25 passed
  (new: `test_complete_is_terminal`,
  `test_missing_storage_object_fails_permanently`; strengthened exhaust test).
- Ruff lint + format clean; `api`, `worker`, `scheduler` images rebuilt and
  the suite re-run against the live stack.
