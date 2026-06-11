# Slice 2 Audit

Post-implementation review of ingestion and inspection, per the `code-audit`
skill. All axes walked (correctness, spec conformance, modularity,
future-proofing, security/auth, reliability invariants, consistency).
Modularity and consistency were clean. All findings below were fixed in this
pass.

## Bugs

1. **Out-of-range timestamps crashed the decoder as transient**
   (`importers/otlp/decode.py`). `_decode_time` only guarded the `int()`
   parse; `datetime.fromtimestamp` was outside the `try`, so one absurd
   `startTimeUnixNano` raised `OverflowError` past the whole importer — the
   upload retried 5 times and dead-lettered instead of skipping the span per
   the partial-success contract. Fix: catch
   `ValueError/OverflowError/OSError` → span skips and counts. Regression
   test: `test_out_of_range_timestamp_skips_span`.
2. **Concurrent ingest of the same upload could duplicate traces**
   (`worker/tasks/ingest.py`). Delete-and-reinsert is idempotent
   sequentially, but two simultaneous runs raced under READ COMMITTED:
   neither delete sees the other's uncommitted inserts, both commit, two
   sets of rows. Reachable via the 10-minute sweep re-enqueueing a
   legitimately slow run, and the spec requires `--scale worker=2`
   correctness. Fix: `uploads.lock()` — `select … for update` on the upload
   row as the first statement of the rewrite transaction, serializing runs
   per upload. Regression test runs the real task twice concurrently
   in-process: `test_simultaneous_ingest_runs_do_not_duplicate`.
3. **Traces beyond ~10k spans failed to load against our own rate limit**
   (`lib/api/traces.ts`). The span pager drains 500/page sequentially,
   faster than the 10 req/s per-user bucket; page ~21+ got `429` and the
   inspector landed in the error state. The 5,000-span demo (10 pages) fit
   inside the burst, which is why verification missed it. Fix:
   `listAllSpans` backs off ~1.1s and retries on 429 (bounded at 5
   consecutive), so big traces load slower instead of failing.

## Spec conformance

- **`GET /v1/traces` was missing `owner_display_name` and `acquired`** —
  3_api.md result cards include both; the slice deferred them silently.
  Implemented: list query joins `profiles`, `acquired` is `false` until
  Slice 3 (same pattern as the detail endpoint's relationship fields).
  `SORT_COLUMNS` qualified with the table alias since `profiles` also has
  `created_at`.
- **`3_api.md` trace download said "Streams"** — implementation is buffered,
  matching the slice-1 amendment to the uploads download. Spec line amended.

## Security & auth

- **Skip-sample messages embedded unbounded payload content**
  (`decode.py`). The invalid-ID skip reason interpolated the raw `spanId`
  value, which is attacker-controlled and flows into `error_message`, logs,
  and dead letters — the exact thing slice 1's forward note warned about.
  Fix: `_brief()` bounds interpolated values to 64 chars. Regression test:
  `test_skip_samples_truncate_payload_content`.

Otherwise clean: ownership on all four trace endpoints (404 never 403,
covered by tests), RLS mirrors, reused download-header hygiene, no
attributes/events in logs.

## Future-proofing

- `spans(trace_id)` index replaced with `spans(trace_id, started_at)` —
  the span-list query filters + orders on exactly that, so pages come off
  the index instead of sorting the full span set at 50k spans. Migration
  edited in place (uncommitted) + applied to the live DB.

## Nits fixed

- `flow-status.tsx` rendered `parse_warnings` by `String()`-ing every value
  (the samples array came out comma-mashed). Now shows a readable
  "N malformed spans skipped."; samples stay API-side detail.
- `trace-inspector.tsx`: failed download was an unhandled rejection with no
  feedback; now caught with an inline error message.
- `buildSpanTree` hardened against corrupt input: duplicate
  `source_span_id`s keep their own nodes (previously collapsed/duplicated),
  and parent-id cycles render at root level (previously vanished silently —
  and could have recursed infinitely if re-rooted naively).
- `MAX_INT32` defined once in `decode.py` instead of three copies across the
  importer package.
- `agent-prism/README.md` added: upstream source, version, MIT attribution,
  and the two local theme modifications.

## Outcome

Verified against the rebuilt Compose stack on 2026-06-10:

- 23 unit tests (2 new) + 23 integration tests (1 new, including the
  concurrent double-run) green against the live stack.
- `ruff check`/`format`, `eslint --max-warnings 0`, `tsc`, `next build` all
  pass; api/worker/scheduler/web images rebuilt.
- Live DB index swapped (`spans_trace_id_started_at_idx` in place).
