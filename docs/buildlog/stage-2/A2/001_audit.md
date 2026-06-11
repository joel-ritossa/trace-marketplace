# A2 — Audit Pass

**Status: done (2026-06-11)** — findings reported, all fixes approved
("fix all"), implemented, re-verified.

Scope read in full: migration 8, the worker path (`analyze.py`, `ingest.py`,
`retry_dlq.py`, `sweep.py`, `faults.py`, `requeue.py`), queries (`analysis`,
`traces`, `spans`, `dead_letters`, `uploads`), the analysis package surface
the worker consumes (`registry`, `judge`, `routing`, `llm`), API
(`routers/traces.py`, `schemas/analysis.py`, `schemas/trace.py`), frontend
(`traces.ts`, `badges.tsx`, `analysis-section.tsx`, `trace-inspector.tsx`,
table/cards, `use-trace-list.ts`), tests (`test_analysis.py`,
`test_analysis_state.py`, `test_reliability.py`), infra/docs diffs (compose,
`.env.example`, Makefile, README), and the governing specs (2/3/6) plus the
A2 plan.

## Findings → resolutions

### Correctness / reliability

- **B1 (bug, fixed)** — a successful re-analysis didn't close an open
  analyze dead letter, so `failed` (which wins in `derive_state`) survived
  any recovery that bypassed `requeue trace` — concretely, operator
  re-ingest of the upload: the fresh run succeeded and rewrote
  `trace_analysis`, but every surface kept showing `failed`. Fixed in
  `analysis_q.rewrite`: the rewrite transaction now closes the trace's open
  dead letters (`mark_requeued_for_trace`, widened to take a connection) —
  a successful run is newer truth than any old failure, the mirror of
  `derive_state`'s failed-beats-stale-row rule. Regression:
  `test_reingest_clears_failed_state`.
- **B2 (bug, fixed)** — the sweep couldn't recover a lost *re*-analysis
  kick: `stale_pending_ids` required no `trace_analysis` row, but a
  re-ingested trace keeps its prior row, so a lost best-effort kick left
  analysis permanently stale against the rewritten content — contradicting
  the plan's "the sweep recovers lost kicks" drift note. Fixed: the
  ingest-time budget reset is a clean marker, so the predicate now also
  matches `analysis_attempts = 0` beside an existing row (the claim
  immediately sets it to 1, ending the window).
- **B3 (bug, fixed)** — eternal `pending` when the worker crashed on the
  final budgeted attempt: attempts = max, no row, no dead letter, and the
  sweep's `attempts < max` filter excluded it forever — exactly the fake
  pending the done-when forbids. Fixed by dropping the budget filter,
  matching ingestion's `stuck_ids` semantics: the sweep re-kicks, and the
  budget is enforced by the middleware *on failure* (attempt ≥ max →
  dead letter), so every path converges to a row or a dead letter.
  B2+B3 regression: `test_sweep_predicate_recovers_lost_kicks`.
- **B4 (bug, cosmetic, fixed)** — `fetch_results` ordered by
  `(created_at, id)` claiming insertion order, but `created_at` is the
  transaction timestamp — identical for every row of a rewrite — so the
  audit disclosure ordered by random uuid. Now an explicit rank
  (signals → judge → metrics by name) with an honest docstring.

### Spec conformance

- **S1 (example amended)** — `3_api.md`'s audit example said `"version"`;
  the implementation (and FE mirror) ship `analyzer_version`, matching the
  DB column. Spec example amended to `analyzer_version` — the implemented
  name is more precise and already mirrored everywhere.
- Clean otherwise: the four derived states match `2_data-model.md` (with
  failed-beats-stale-row as the consistent extension), skip reasons +
  ratified precedence, RLS mirrors traces exactly on both tables,
  `failure_suspected` stored but never in the API, 404-not-403,
  `failed_reason` verbatim. Filter extension is A4; `has_open_review_item`
  deferral was ratified (plan decision 11).

### Consistency

- **C1 (dead code, fixed)** — the worker's post-judge `finalize_verdict` +
  envelope `model_copy` was a no-op with stale comments: B2 moved the cap
  *inside* `run_judge` ("applied before the verdict leaves the analyzer"),
  so the envelope already carried the capped output/confidence. Block
  removed; the worker validates the verdict once for promotion. This
  supersedes plan decision 8's "the worker applies `finalize_verdict`" —
  the cap's one home is the judge, per the registry's own comment.
- **C2 (nit, fixed)** — `assert signals_run is not None` in a production
  path (stripped under `-O`); now an explicit raise.
- **C3 (nit, fixed)** — the trace-scope dead-letter path silently dropped
  when the trace vanished mid-failure; now logs like every other drop path.
- **C4 (nit, fixed)** — `rewrite()` mutated the caller's `promoted` dict
  during human-label carryover; now copies first.

### UX

- **U1 (fixed)** — the detail Analysis section hid the labels grid entirely
  when `skipped`, but human-provenance labels survive a machine rewrite even
  when the LLM skipped (relabel → re-ingest on a keyless stack), so the list
  badge could show an outcome the detail section hid. The grid now renders
  whenever any label exists.

### Clean axes

- **Modularity** — routers/schemas/queries/worker split respected;
  `derive_state` and `LABEL_FIELDS` single-homed; FE types mirror schemas in
  one file; badges shared across every list surface.
- **Future-proofing** — no new knobs (ratified); compose null-value
  pass-through correctly avoids empty-string key poisoning.
- **Security & auth** — select-only RLS mirroring traces, service-role
  writes, no span bodies or prompts logged. Note, no action: `failed_reason`
  is the raw exception string and `error_context` carries a traceback tail —
  the stage-1 ingestion pattern, and the verbatim reason is spec-mandated.

## Accepted / recorded, no change

- **Stale-analysis race** — an in-flight analyze run that read old content
  can finish after a re-ingest's fresh run and overwrite it with analysis of
  the pre-rewrite content. Tight window; recoverable by `requeue trace`;
  serializing analysis against ingest isn't worth the machinery at this
  stage. Known caveat.
- **Test-coverage drift** — the plan promised middleware unit tests
  "mirroring the existing retry_dlq unit coverage", but no middleware unit
  tests exist (stage 1's coverage is integration, `test_reliability.py`).
  The behavior is covered — the integration suite exercises transient retry,
  the permanent fast-path, dead-letter shape, and requeue for the trace
  scope — so the gap is the claim, not the coverage. Recorded here.

## Re-verification

- Backend: ruff check + format clean; unit 193 passed; integration 56
  passed (54 prior + the two new regressions) against the rebuilt compose
  stack (api/worker/scheduler).
- Frontend: `tsc --noEmit`, eslint, `next build` clean.
