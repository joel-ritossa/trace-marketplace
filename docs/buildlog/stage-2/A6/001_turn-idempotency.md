# A6 — Pass 001: Turn-Trace Idempotency (Owner-Scoped Identity)

User call: "need idempotency on turn traces if we're converting right" —
the 000 caveat (re-syncing a grown session duplicates its earlier turns
under a new upload) is not acceptable; conversion implies the turns are
the *same logical traces* on every sync.

## Decision

Trace identity moves from `(upload_id, source_trace_id)` to
**`(owner_id, source_trace_id)`** — one rule for every format, not a
session-only special case. The ingest upsert **adopts** an existing row
into the newest upload (`upload_id = excluded.upload_id`), rewriting all
content under that upload's redaction salt. Since per-turn ids are
deterministic (`sha256(agent:session:turn)`), re-syncing a grown log
updates existing turns in place and appends new ones. `traces.id` is
stable across re-syncs, so acquisitions, labels, and review items survive
— the same property the A2 amendment bought for re-ingest, extended to
re-upload.

Consequences accepted:

- A superseded upload stays `complete` with zero traces — honest about
  owning none; raw download of any adopted trace serves the newest
  upload's payload (`get_visible_with_upload` joins through `upload_id`).
- An OTLP re-upload sharing a trace id now updates that trace instead of
  duplicating it — defensible: same owner + same source trace id *is* the
  same trace, and whole-file sha dedupe already catches byte-identical
  re-uploads.
- Ping-pong (an older upload re-claiming traces) can't happen unprompted:
  `complete` is terminal, so superseded uploads are never re-ingested.
- Concurrent overlapping ingests upsert in `started_at` order on both
  sides (no deadlock); last writer owns the rows and either outcome
  converges.

## Changes

- `supabase/migrations/00000000000011_owner_trace_identity.sql` — dedupe
  existing `(owner_id, source_trace_id)` collisions keeping the newest row,
  swap the unique constraint.
- `queries/traces.py:upsert` — conflict target + upload adoption.
- `worker/tasks/ingest.py` — docstring.
- Spec: `6_architecture.md` A6 amendment paragraph; `8_session-ingestion.md`
  caveat replaced with the idempotency rule + new done-when bullet.

## Outcome

- New integration test `test_grown_session_resync_is_idempotent`: session
  v1 (2 turns) → upload; v1 + one turn → second upload completes with 3
  trace ids, the original 2 ids unchanged (adopted), superseded upload
  reports `trace_ids: []`, owner total is exactly 3.
- 304 passed across unit + uploads/ingestion/session/CLI integration;
  redaction + machine-door suites green. Re-ingest delete-and-rewrite
  tests pass under the new constraint.
- Pre-existing failures in `test_filter_query.py` lint and earlier
  `GET /v1/traces` 422s belong to the parallel A4 `TraceListParams` work,
  out of scope here.
