# A3 — Audit Pass

Post-implementation review per `.cursor/skills/code-audit/SKILL.md`. Scope:
everything A3 touched — migration 9, `queries/notifications.py`,
`queries/review_items.py`, the `rewrite`/worker/faults/retry-DLQ routing
wiring, both new routers + schema modules, the traces query/router deltas,
and the eight frontend surfaces — read against `1_analysis.md`,
`2_data-model.md`, `3_api.md`, `4_pages.md`, and the ratified plan
(`000_implementation.md`).

## Findings

### Bugs

- **B1 — lock-order inversion between `resolve` and `rewrite`.**
  `resolve` locked the review item first, then `trace_analysis`; `rewrite`
  takes `trace_analysis` first, then updates the item (supersede) inside
  the same transaction. A resolve racing a re-analysis of the same trace
  could deadlock; Postgres aborts one side — a 500 to the user or a burned
  task retry. The docstring claimed the locks "serialize" the two sides,
  which only holds with a consistent acquisition order.
- **B2 — `POST /v1/notifications/read` 500s on a non-UUID id.** `mark_read`
  fed `ids` straight into `any($2::uuid[])`; a malformed id raised
  `asyncpg.DataError`, which this router — alone among all of them — did
  not catch.
- **B3 — resolve accepted an incoherent answer.**
  `{"outcome": "success", "failure_mode": …}` wrote a human-provenance
  failure_mode beside a human success outcome — the row shape the label
  model forbids (`1_analysis.md`: failure_mode accompanies `failure`). The
  UI prevents the combination; the API boundary didn't.

### Spec conformance — clean

API shapes, error envelope, ordering, digest flood control, supersede
semantics, owner-only review visibility, and the pages law all match. The
deviations (payload filenames, `open_review_item_id` on cards, resolve
`labels`, `409 item_superseded`) are additive and already recorded in
`000_implementation.md` Drift.

### Modularity

- **M1 (nit) — `review_items.open_item_id` was dead code.** The analysis
  endpoint reads the id from the trace-row subquery; nothing called it.

### Future-proofing — clean

Thresholds/limits env-backed; the fault grammar is `dev_routes`-gated end
to end; no deploy-hostile hardcoding.

### Security & auth — clean

New endpoints are JWT-only via `CurrentUser`; RLS policies are select-only
and mirror the API rules; realtime delivery rides the recipient-scoped
policy; non-owner cards verifiably get `false`/`null` (integration-tested);
no span bodies or payloads logged.

### Reliability invariants

Routing writes are atomic with the rewrite; both `upload_failed` sites are
best-effort-wrapped; mark-read and relabel-create are idempotent.

- **R1 (nit) — digest `item_count` counts routed events, not open items.**
  A re-run that routes again supersedes the item (open count unchanged) but
  still increments the digest; resolution never decrements. The UI copy
  ("N traces … need review") claimed a live count the counter doesn't
  track.

### Consistency

The B2 DataError outlier aside, patterns are uniform (param-builder
queries, count-over fallback, 404-not-403 comments, mirrored FE/BE types).

### Frontend nits

- **F1** — the `/review` filter chip fell back to the raw upload UUID when
  the filtered queue was empty.
- **F2** — the `/review/[itemId]` width-breakout uses `100vw` (includes the
  scrollbar gutter), which can produce a sliver of horizontal scroll on
  scrollbar-bearing platforms. Cosmetic; **not fixed** — accepted as is.

## Fixes (approved: "fix whatever you think makes sense")

- **B1** — `resolve` now locks in `rewrite`'s order: an unlocked probe
  (ownership + trace_id; resolved/superseded early-returns are safe — those
  states are terminal), then `trace_analysis for update`, then the item
  `for update` with a status re-check under the lock (a rewrite that held
  the `trace_analysis` lock may have superseded it while we waited).
- **B2** — the router catches `asyncpg.DataError` and no-ops: malformed ids
  behave like foreign ones, per the endpoint's idempotent semantics.
- **B3** — `ReviewResolveRequest` model validator rejects `failure_mode`
  when `outcome` is present and ≠ `failure`. failure_mode alone stays legal
  (refining a machine failure verdict without touching its outcome).
  `label_updates` keeps its standalone precedence rule as defense in depth.
- **M1** — `open_item_id` deleted.
- **R1** — copy-side fix: the digest line reads "N review requests from
  upload X" (events, which is what the counter tracks); demo doc updated to
  match.
- **F1** — empty filtered queue shows a truncated id (`9f3a2c1b…`), never
  the raw UUID.

Tests added: unit — the validator matrix (rejects non-failure +
failure_mode, allows failure_mode alone and with failure); integration —
the incoherent combos in the 422 matrix, and a malformed-id mark-read
asserting 204.

## Verification

- Backend: `ruff check` + `format` clean on touched files; unit suite 277
  passed.
- Integration: the six HIL tests covering the changed paths pass against
  the rebuilt compose stack (resolve validation, upload-failed/mark-read,
  confirm/null/supersede/relabel). The full integration run had 9 failures,
  all `KeyError: 'traces'` from `GET /v1/traces` — concurrent in-flight A4
  work on `routers/traces.py`/`queries/traces.py` in the same working tree
  was baked into the image by the rebuild; unrelated to A3 (the two HIL
  tests among them fail only at their trailing list-shape assertions).
  Re-run the full suite once A4's tree is consistent.
- Frontend: `tsc --noEmit` and eslint clean on the touched pages.
