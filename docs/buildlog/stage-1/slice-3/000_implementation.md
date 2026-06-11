# Slice 3 — Discovery, Listing, And Acquisition

Spec: `docs/spec/stage-1/5_build-order.md` (Slice 3), `2_data-model.md`
(discovery columns, acquisitions, search, access rules), `3_api.md`
(list/patch/delete/acquire/download), `4_pages.md` (/marketplace, /library,
detail-page actions), `0_README.md` (demo script).

**Done when:** the README demo script passes end to end on a fresh local run:
upload → inspect → list → search from another account → inspect → acquire →
download from library.

Decisions settled in discussion before this plan (with the user):

- **Deleting the last trace of an upload deletes the upload row and the
  storage object together.** The spec only said "remove the storage object
  when no other trace references the upload", which would leave a surviving
  upload row whose download endpoint is broken. No half-dead state: every
  surviving uploads row stays downloadable. (Spec amendment below.)
- **Acquisitions cascade-delete with their trace.** The spec said to keep
  orphaned acquisition rows; for $0 acquisitions orphans are dead weight and
  would force dropping the FK. Plain `on delete cascade`; retention gets
  revisited when licensing is real. (Spec amendment below.)

## Plan

### Spec amendments (resolve first)

`2_data-model.md`:

- Delete rule: "Delete trace: owner only; spans cascade. When no other trace
  references the upload, the upload row and storage object are deleted too."
- Acquisitions: FK `on delete cascade`; drop the "rows are kept but the trace
  no longer resolves" sentence.

### Migration

`00000000000004_discovery.sql`:

- `traces` gains `tags text[] not null default '{}'`, `description text`,
  `visibility text not null default 'private' check (visibility in
  ('private','listed'))`, `listed_at timestamptz`, and `search_tsv tsvector
  generated always as (…) stored` — weighted per 2_data-model.md fields:
  name + tags → A, description → B, provider/model/service_name/tool_names/
  error_types → C. Raw span content is never in scope.
- Indexes: partial `traces(visibility) where visibility = 'listed'`, GIN on
  `search_tsv`.
- `acquisitions`: `id uuid PK`, `consumer_id → profiles`, `trace_id → traces
  on delete cascade`, `price_usd numeric not null default 0`, `acquired_at`,
  unique `(consumer_id, trace_id)`, index `acquisitions(consumer_id)`.
- RLS (defense in depth; API uses service role): traces/spans select becomes
  owner-or-listed; acquisitions select/insert own rows only (insert policy
  mirrors the API rules: trace listed, not own).

### Backend — queries

`queries/traces.py`:

- `list_visible(...)` replaces `list_owned`: one parameterized builder for
  scope (`mine` = owner, `marketplace` = listed, `acquired` = join
  acquisitions on caller), `q` via `websearch_to_tsquery('english', $n)`,
  filters (`provider`, `model`, `tool` = any(tool_names), `has_errors`,
  `from`/`to` on `started_at`), existing sort whitelist + pagination. Left
  join acquisitions for the caller's `acquired` flag; select adds
  `visibility`, `tags`, `listed_at`.
- `get_visible(trace_id, caller_id)` replaces `get_owned` on read paths:
  owner or listed, returning `is_owner` and `acquired` alongside the row.
- `update_owned(...)` for PATCH (tags/description/visibility; `listed_at =
  coalesce(listed_at, now())` on first listing); `delete_owned(...)`
  returning the upload id + whether other traces still reference it.

`queries/acquisitions.py` (new): `create(...)` as a single statement —
`insert … select … where visibility = 'listed' on conflict (consumer_id,
trace_id) do nothing` + fetch, so an unlist mid-flight can't race;
`get(consumer_id, trace_id)`.

### Backend — API

`routers/traces.py`, `schemas/trace.py`:

- `GET /v1/traces` — `TraceScope` widens to `mine|marketplace|acquired`;
  `q` + filter params per 3_api.md; result cards gain `visibility`, `tags`,
  `listed_at`, real `acquired`.
- `GET /…/{id}`, `/spans`, `/spans/{id}` — access check becomes
  owner-or-listed (still 404, never 403, for invisible traces); detail
  response computes real `is_owner` / `acquired` / `can_download`
  (owner or acquirer).
- `PATCH /v1/traces/{id}` — owner only; mutable `visibility`/`tags`/
  `description`; `visibility: "listed"` requires `confirm_ownership: true`
  else `422 confirmation_required`.
- `DELETE /v1/traces/{id}` — owner only; spans cascade; when no other trace
  references the upload, delete the upload row and storage object (storage
  delete after commit; an orphaned object is tolerable, a dangling row is
  not).
- `POST /v1/traces/{id}/acquire` — `409 own_trace`, `409 not_listed`,
  `404` invisible; idempotent repeat returns the existing record with `200`.
- `GET /…/{id}/download` — gate becomes owner-or-acquired;
  listed-but-not-acquired → `403 acquisition_required` with a message
  pointing at acquire.

### Web

- `lib/api/traces.ts` — scope/filter params on the list fetcher; patch,
  delete, acquire fetchers; new fields on the types.
- `/traces` — search box + filters (provider, model, has-errors, date range)
  driving `scope=mine`; visibility badge column; no-results-for-query state.
- `/traces/[traceId]` — actions section per 4_pages.md, driven by
  `is_owner`/`acquired`/`can_download`: owner edit panel (tags, description,
  private↔listed toggle with the ownership-confirmation checkbox, delete
  with confirm, download); non-owner Acquire (labeled free) or Download +
  "in your library" badge; disabled download with "acquire to download"
  when listed-not-acquired.
- `/marketplace` — `scope=marketplace` cards with contributor display name,
  listed date, acquired badge; same search + filters; empty-marketplace and
  no-results states. Cards link to the detail page.
- `/library` — `scope=acquired` cards with acquired date and direct
  download; empty state pointing at `/marketplace`.
- Nav gains Marketplace and Library links; visibility badges on every trace
  rendering (cross-cutting rule in 4_pages.md).

### Seed + smoke

- `make seed` — script creates a demo contributor (Supabase admin API),
  uploads the `fixtures/` files through the real HTTP API, waits for
  ingestion, then lists them with tags/descriptions. Fresh clones get a
  populated marketplace. Idempotent re-runs.
- `make smoke` — shell script running the literal README demo script with
  two throwaway accounts: upload → poll to complete → inspect (traces +
  spans) → list with confirmation → search from the consumer account →
  inspect → acquire → download → byte-diff against the uploaded fixture.
  Fails loudly on any step.

### Tests

- Integration — visibility matrix: private invisible to non-owner (404 on
  detail/spans/download), listed inspectable by any auth user; search (`q`)
  and each filter + scope combination; PATCH confirmation flow
  (`confirmation_required`, `listed_at` set once); acquire (idempotent 200,
  `own_trace`, `not_listed`, unlist-then-acquire race); download gating
  (owner, acquirer, listed-not-acquired 403, private non-owner 404); delete
  (spans cascade, acquisitions cascade, last-trace deletes upload row +
  storage object, shared-upload trace keeps both).
- RLS check: anon-key client reads a listed trace, cannot read a private
  one.

### Verification (done-when walkthrough)

1. Fresh `docker compose up` + migrations + `make seed` → marketplace shows
   seeded listed traces.
2. Demo script by hand in the browser: upload fixture → status to complete
   → My Traces → inspect → list with checkbox → second account →
   marketplace search + filters → inspect → acquire → library → download →
   bytes identical.
3. `make smoke` green on the same fresh stack.
4. Full backend suite + ruff + eslint + tsc + `next build` clean.

## Drift

1. **Unlist semantics pinned down in the spec amendment.** The original spec
   already implied unlist revokes non-owner access ("the trace no longer
   resolves"); the amendment now states it explicitly: acquisition rows
   survive, the trace 404s for non-owners (downloads included), relisting
   restores access. Consequence: `scope=acquired` shows currently-listed
   acquisitions only, so the library never renders cards that 404 on click.
2. **403 vs 404 refinement.** PATCH/DELETE by a non-owner on a *listed* trace
   returns `403 forbidden`, not 404 — a listed trace's existence isn't
   secret, so the honest status wins. Invisible traces still 404 everywhere.
3. **Acquire returns 201 on create, 200 on idempotent repeat** (the spec only
   pinned the 200-on-repeat half).
4. **Seed/smoke are stdlib python3, not shell** (`tools/seed.py`,
   `tools/smoke.py`, shared `tools/_stack.py`): JSON-heavy steps in bash
   would mean a jq dependency; same precedent as the converter tool. Both
   read the repo `.env` for Supabase coordinates; seed is idempotent
   (reuses the duplicate-upload 409).
5. **RLS test simulates PostgREST in SQL** (`set local role authenticated` +
   `request.jwt.claims` GUC in a rolled-back transaction) instead of an
   anon-key client — the API config deliberately has no anon key.
6. **`immutable_array_to_string` helper function** in the migration:
   `array_to_string` is only `stable` in Postgres, so the generated
   `search_tsv` column needs a text[]-only `immutable` wrapper.

## Outcome

Done-when met: `make smoke` runs the literal README demo script end to end
against a fresh stack — upload → ingest → inspect → confirmation-gated
listing → marketplace search + filters from a second account → inspect →
gated download (403) → acquire ($0, idempotent) → library → byte-identical
download. ✓

Verification:

1. Backend suite green: 56 tests (24 unit, 32 integration) including 7 new
   discovery tests — visibility matrix, search/filters, patch confirmation,
   acquire edge cases, unlist revocation, delete cascades + upload/object
   cleanup, RLS policy check. ✓
2. `make seed` populates the marketplace from fixtures and re-runs
   idempotently. ✓
3. ruff, eslint, tsc, `next build` all clean. ✓
4. Browser spot-check on the rebuilt stack: My Traces (badges, live search),
   owner detail panel (tags/description editor, unlist, delete, download),
   marketplace cards (contributor, listed date, tags, descriptions),
   consumer detail (disabled download → acquire → "in your library" badge +
   enabled download). ✓
