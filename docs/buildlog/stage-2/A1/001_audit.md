# A1 — Audit Pass

**Status: done (2026-06-11)** — findings reported, fixes approved ("fix
everything; SE1 accepted; C3 handled properly"), implemented, re-verified.

Scope read in full: migration 5, `auth.py` + rate-limit middleware, api-keys/
profile/uploads routers + queries + schemas, the entire CLI (`apps/cli` src +
tests), frontend (settings sections, `/uploads`, pager, realtime hook, api
libs, list pages), both A1 integration suites, the session converter + demo
doc, env/Makefile, and the governing specs (2/3/4/5) plus the A1 plan.

## Findings → resolutions

### Correctness

- **C1 (bug, fixed)** — Enter in the mint dialog wasn't guarded against an
  in-flight request: double-Enter minted two keys. `!minting` added to the
  key handler (`api-keys-section.tsx`); same guard on the profile save.
- **C2 (bug, fixed)** — `count(*) over ()` loses the total when the offset is
  past the end, so an out-of-range `?page=N` rendered a false "No uploads
  yet" empty state with no pager to escape. Fixed both ends: the list queries
  (`queries/uploads.py list_owned`, `queries/traces.py list_visible`) fall
  back to a real count when zero rows return with an offset, and the clients
  (`/uploads` page, `use-trace-list.ts`) snap to the last page when a
  non-empty list returns an empty page.
- **C3 (reliability, fixed per discussion)** — watch mode marked *every*
  attempted file as synced, so a transient network failure silently dropped a
  file until its bytes changed. `FileOutcome` gained `retryable` (true for
  transport errors — file read failure, upload POST network error, status-poll
  network error; false for every server rejection and ingestion failure);
  `run_watch` skips `mark_synced` on retryable outcomes so the scanner
  re-offers the file, while permanently bad files still never loop. Covered by
  two new unit tests (retry on transport failure, no retry on rejection).

### Spec conformance

- **S1 (violation, fixed)** — `4_pages.md` requires created/processed on the
  `/uploads` table; the processed column was missing. Added.
- **S2 (spec text, amended)** — `3_api.md` said keys get `401 invalid_token`;
  ratified decision 1 (A1 plan) chose the stage-1 `unauthorized` code. The
  spec now says `401 unauthorized` — code and spec agree.
- **S3 (nit, fixed)** — the empty key list now points at the CLI setup
  walkthrough (`docs/demos/cli-sync.md`).

### Security & auth

- **SE1 (accepted, documented)** — API keys do not re-check the email
  allowlist: removing an email kills JWT sessions but not previously minted
  keys. Accepted by the user; offboarding = remove from allowlist **and**
  revoke keys. Recorded as a comment in `auth.py _api_key_user`.
- **SE2 (accepted)** — `api_keys` RLS mirrors select/insert/update but not
  delete. Hard delete is not an API operation (revoke is soft, history is the
  point); the omission fails safer than the literal "all operations" mirror.
  No change.
- Clean otherwise: plaintext-once (test-pinned), keys sha256-stored and never
  logged, 404-not-403, realtime delivery RLS-scoped.

### Future-proofing

- **F1 (fixed)** — key auth now requires `scope = 'upload'` in
  `find_active_by_hash`: today a no-op (only scope), but a wider scope landing
  later fails closed instead of silently inheriting the upload pair.
- **F2 (accepted)** — no cap on keys per user; rate limiting bounds the abuse
  rate and the trial scale doesn't justify a quota.
- **F3 (accepted, ratified decision 2)** — per-key rate buckets mean N keys =
  N× one user's upload throughput; the no-DB-lookup middleware design wins.

### Modularity / reliability / consistency

Modularity and reliability axes were clean (layouts held; ingestion
invariants untouched; `touch_last_used` best-effort). Consistency nits, all
fixed:

- **N1** — `lib/api/uploads.ts` type mirror missing `redaction_counts`
  (resolved by the in-flight A5 work before this pass landed).
- **N2** — CLI fatal errors (`no API key`, missing path, preflight failures,
  no files found) now print to stderr; the e2e test asserts it.
- **N3** — `usePageParam` truncates to an integer (`?page=1.5` can no longer
  become a fractional offset → 422).
- **N4** — `profile.py _response` annotates `AuthUser`, not the `Annotated`
  dependency alias.
- **N5** — `StabilityScanner` prunes state for deleted files each scan.
- **N6** — the realtime hook coalesces bursts with a non-resetting timer
  (first event always fires within 500 ms; a continuous stream can no longer
  starve the refetch).
- **N7** — CLI discovery matches `.json` case-insensitively.

## Re-verification

- CLI: ruff + format clean; 20 unit tests green (+3 new: retry semantics ×2,
  non-retryable ingestion failure).
- API: ruff + format clean; unit suite green except 6 `test_importer_golden`
  failures owned by the in-flight A2/A5 working-tree changes (stash-verified:
  they pass with the tree stashed — not from this pass).
- Web: eslint, `tsc --noEmit`, `next build` all clean.
- Integration: api/worker images rebuilt, pending `00000000000008_analysis.sql`
  applied (the parallel A2 work had landed an importer change ahead of its
  migration, breaking ingestion stack-wide); then `test_machine_door.py` +
  `test_cli_sync.py` 10/10 green, full integration suite 46/47 — the one
  failure (`test_redaction.py::test_reingest_is_byte_identical`) belongs to
  the in-flight A5 slice, untouched by this pass.
