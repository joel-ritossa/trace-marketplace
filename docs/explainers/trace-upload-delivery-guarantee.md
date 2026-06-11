# Trace Upload Delivery Guarantee

**At-least-once delivery with an idempotent consumer; Postgres — not Redis —
is the source of truth.** Once a client gets a 201, the upload cannot be
silently lost: it always terminates in `complete`, or in `failed` with a
`dead_letters` audit row.

## Mechanism

**1. Durability before acknowledgment.** `POST /v1/uploads`
(`routers/uploads.py`) writes the raw object to storage, commits the
`uploads` row (`status='received'`), and only then enqueues `ingest_upload`
and returns 201. A failure before the row commit returns an error to the
client; the sha256 dedupe makes the retry safe (worst case: an orphan
object, harmlessly keyed by content hash).

**2. The queue is a latency optimization, not the guarantee.** The Redis
list broker has no acks or visibility timeout: a Redis crash or a worker
crash mid-task loses the in-flight message. Retry backoff re-kicks are
in-process sleeps (`worker/retry_dlq.py`), lost the same way. We deliberately
don't harden the queue.

**3. The sweep is the guarantee.** Every 60s the scheduler fires
`sweep_stuck_uploads` (`worker/tasks/sweep.py`), which re-enqueues any upload
still `received`/`processing` whose last claim
(`coalesce(last_attempt_at, created_at)`, see `queries/uploads.py`) is older
than `SWEEP_STUCK_AFTER_MINUTES` (default 10). A lost message costs at most
~11 minutes of delay (window + cron tick), never the upload. Keying off
`last_attempt_at` bounds re-enqueues to once per window.

**4. Idempotency makes duplicates harmless.** Both the broker and the sweep
can double-deliver, so `ingest_upload` (`worker/tasks/ingest.py`) is
convergent: `complete` is a terminal no-op and re-running any other state
produces the same outcome. Delivery is at-least-once; the *effect* is
exactly-once.

**5. Bounded failure, never limbo.** Transient errors retry up to
`INGEST_MAX_ATTEMPTS` (default 5) with exponential backoff + jitter;
exhaustion writes a `dead_letters` row and marks the upload `failed`
(terminal — the sweep ignores it). Permanent errors (`PermanentIngestError`,
e.g. checksum mismatch) fail immediately with a readable reason, no retries.
Recovery from `failed` is an explicit operator action: `app.cli.requeue`.

## Caveats

- Not exactly-once *delivery* — only exactly-once effect via idempotency.
- Not real-time guaranteed: in the rare lost-message case the UI shows
  `received` until the sweep recovers it (≤ ~11 min at defaults).
- The trade (cheap Redis list + DB-backed sweep over an ack-based broker) is
  recorded in `docs/spec/stage-1/6_architecture.md`.
