# Pass 002 — pipelined sync (enqueue all, then drain)

## Why

First real-world prod sync (20 converted sessions against trace-mp.com) felt
slow: the CLI uploaded one file, then polled that upload to a terminal state
before touching the next. Ingestion already runs asynchronously on the
server's task queue, so serializing on it client-side bought nothing — N
files cost N full ingest waits.

## Change

Spec first: `5_cli.md` "Status feedback" became "Pipelined status feedback",
and the output section now allows outcome lines to land out of upload order.

- `client.py`: `upload()` split into `enqueue()` (POST; returns a terminal
  `FileOutcome` for skips/rejections/transport failures, else a
  `PendingUpload` carrying the upload id and its poll deadline) and
  `check()` (one status poll; outcome or `None` while processing).
- `run.py`: new `sync_batch()` enqueues every file, then drains the
  in-flight set on a 1 s tick, printing each outcome as it lands. `sync`
  and `watch` both run through it; watch's retryable/mark-synced logic is
  unchanged, applied per result after the batch drains.

Unchanged guarantees: statelessness, server-side dedupe, `Retry-After`
backoff (still inside `_request`, so polls self-throttle too), per-file
120 s poll timeout, exit codes, one outcome line per file.

## Verification

- `apps/cli`: 20 unit tests pass (client outcome mapping rewritten around
  enqueue/check, including a poll-deadline case; run tests' FakeClient now
  routes uploaded outcomes through the pending path).
- Integration `test_cli_sync.py` + `test_machine_door.py` (real stack):
  10 passed.

### Drift recorded

A first integration run failed with fixture 401s — leaked
`.env.production` exports from an earlier prod allowlist step in the same
shell, exactly the accident the allow-email skill warns about. The polluted
prod rows (11 `it-*@example.com` allowlist entries + auth users) were
deleted; tests pass in a clean environment.
