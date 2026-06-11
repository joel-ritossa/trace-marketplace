# A1 — Machine Door: API Keys, Sync CLI, /settings, /uploads, Pagination

**Status: done (2026-06-11)** — implemented, done-when verified, closed out.
Audit pass: [`001_audit.md`](001_audit.md) (done 2026-06-11).

Spec: `docs/spec/stage-2/6_build-order.md` (A1), `3_api.md` (dual auth, API-key
+ profile endpoints), `2_data-model.md` (`api_keys`, stage-1 deltas),
`4_pages.md` (`/settings`, `/uploads`, pagination), `5_cli.md` (sync CLI).

**Done when:** fresh compose up → mint key → CLI-sync the dev dataset → watch
picks up a dropped file → re-sync uploads nothing → a bad file shows `failed`
with its reason on `/uploads`; display name and the LLM-analysis toggle persist
through `PATCH /v1/profile`.

Decisions proposed in this plan, to ratify before implementation:

1. **Dual auth keeps one error code.** API-key tokens on JWT-only endpoints
  fail with the existing `unauthorized` 401 (stage-1's single error shape),
   not a new `invalid_token` code — `3_api.md` says "401 invalid_token", read
   here as "401, invalid token" prose rather than a new code. If the literal
   code is wanted, say so and the spec stands as written.
2. **Rate-limit bucket key for key callers.** The middleware needs a cheap
  per-caller key without a DB lookup (same rationale as today's unverified
   JWT sub): bearer tokens starting `tmk_` bucket on the token's sha256. A
   forged key only rate-limits the forger.
3. `**last_used_at` throttled as a constant**, not an env tunable: update
  only when null or older than 60 s, best-effort (an update failure never
   fails auth). It's bookkeeping, not demo-relevant behavior.
4. `**GET/PATCH /v1/profile` replaces `GET /v1/me`.** Same data plus the two
  new fields; nothing in the web app calls `/me` (the `Me` type is dead
   code). One profile concept, one endpoint pair — no alias kept.
5. **Watch mode is a polling loop, no watchdog dependency.** Scan every 2 s;
  a file uploads when its (size, mtime) is stable across two consecutive
   scans ("stopped growing", per spec). In-process seen-set only — the CLI
   stays stateless across runs; server dedupe is the source of truth.
6. **Key material:** 32 chars from `secrets.choice` over `[a-z0-9]`
  (~165 bits) after the `tmk_` prefix; stored as sha256 hex;
   `key_display` = first 6 + `…` + last 4 (`tmk_ab…f3k9`, per the spec
   example).
7. `**/uploads` trace links via an additive list field.** `GET /v1/uploads`
  rows gain `trace_ids` (aggregated in the list query); the page renders
   "N traces" linking to each. Spec says stage 1 "already returns everything
   needed" — true except the list rows lack the detail endpoint's
   `trace_ids`; this is the smallest correction.
8. **Pagination scope:** shared pager (page size 25), `?page=N` serialized to
  the URL on `/traces` and `/uploads`, page resets on filter/sort change.
   Full filter-state URL serialization (the 4_pages cross-cutting law) lands
   with A4's filter-language extension — A1 does not retrofit stage-1 filter
   chips into the URL.
9. **One migration** (`00000000000005_machine_door.sql`): `api_keys` + RLS,
  `uploads.source`, `profiles.allow_private_llm_analysis`. The other stage-1
   deltas (`traces.total_tokens`, `dead_letters.trace_id`) are A2 concerns
   and land with A2's migration.
10. **Supabase Realtime, invalidation-only, plumbed in A1** *(ratified
  2026-06-11, spec amendment in `4_pages.md` Cross-Cutting)*: the web app
    subscribes to `postgres_changes` on its own rows purely as a refetch
    trigger — socket payloads are never consumed as data, the API stays the
    single read path, and every surface stays correct with the socket down.
    A1 ships the shared hook + the first consumer (`/uploads` updating live
    during a CLI sync); A3 reuses it for the bell. Web only — the CLI keeps
    polling per `5_cli.md`.

Ratified 2026-06-11, all nine as proposed (decision 10 was ratified when the
realtime amendment landed). One note on 5: websockets were floated as an
alternative; not applicable — watch observes the local filesystem, so the
poll/stability scan stands.

## Plan

### Migration (`supabase/migrations/00000000000005_machine_door.sql`)

- `api_keys` per `2_data-model.md`: id, owner_id → profiles (cascade), name,
`key_hash` unique, `key_display`, `scope` default `'upload'` (check
constraint deliberately omitted — column exists so scopes stay additive),
created_at, last_used_at, revoked_at. RLS owner-only for select/insert/
update (the API uses the service role; policies mirror, stage-1 rule).
Plaintext is never a column, so "never readable after mint" is structural.
- `alter table uploads add column source text not null default 'web' check (source in ('cli', 'web'))`.
- `alter table profiles add column allow_private_llm_analysis boolean not null default true` (covered by the existing owner-only update policy).
- `alter publication supabase_realtime add table public.uploads` — Realtime
change events for the invalidation hook (decision 10); `postgres_changes`
delivery is RLS-checked against the subscriber, so the existing owner-only
select policy already scopes it.

### Backend — dual auth (`app/auth.py`, the one stage-1 code change)

- `AuthUser` gains `via: Literal["jwt", "api_key"]` (default `"jwt"`).
- New dependency `upload_principal`: bearer starting `tmk_` → sha256 → look
up `api_keys` where `key_hash` matches and `revoked_at is null` →
`AuthUser(id=owner_id, email=None, via="api_key")`, plus the throttled
`last_used_at` touch (decision 3); any other bearer falls through to the
existing JWT path. Miss/revoked → 401 `unauthorized`.
- `current_user` (the existing `CurrentUser`, used by every other route)
short-circuits `tmk_` tokens to 401 before JWT decode — key principals
reach exactly `POST /v1/uploads` and `GET /v1/uploads/{id}`, which switch
to the new `UploadPrincipal` dependency. List + download stay JWT-only.
- `create_upload` passes `source='cli'` when `via == "api_key"`;
`queries.uploads.create` takes the new column. Clients never set it.

### Backend — rate limiting (`app/middleware/rate_limit.py`)

`_subject` returns `key:<sha256-prefix>` for `tmk_` bearers (decision 2);
JWT path unchanged. Key-authed uploads thereby get the same per-user and
tight upload buckets — the CLI's backoff is exercised by the existing limits.

### Backend — API keys (`routers/api_keys.py`, `queries/api_keys.py`, `schemas/api_key.py`)

Per `3_api.md`, JWT-only:

- `POST /v1/api-keys` `{name}` → mint (decision 6), insert hash row, return plaintext once + row fields.60
- `GET /v1/api-keys` → caller's keys (name, key_display, scope, created_at,
last_used_at, revoked_at), newest first.
- `DELETE /v1/api-keys/{id}` → soft revoke, idempotent (sets `revoked_at`
where null; 404 only when the row isn't the caller's).

### Backend — profile (`routers/me.py` → `routers/profile.py`, schema + query updates)

- `GET /v1/profile` — id, email, display_name, allow_private_llm_analysis,
created_at. `PATCH /v1/profile` — partial body, `display_name` (trimmed,
non-empty, length-capped) and/or `allow_private_llm_analysis`; returns the
updated profile. `/v1/me` is removed (decision 4); web `me.ts` →
`profile.ts`.

### Backend — uploads list (`schemas/upload.py`, `queries/uploads.py`)

`UploadListItem` + `UploadStatusResponse` gain `source`; list rows gain
`trace_ids` via a lateral/array_agg join (decision 7).

### Sync CLI (`apps/cli`)

Own uv project (`trace-sync` console script), httpx + stdlib argparse only —
mirrors the no-CLI-framework pattern of `app/cli/`*. Layout:

```
apps/cli/
  pyproject.toml          # name: trace-sync; deps: httpx
  src/trace_sync/
    __init__.py
    main.py               # argparse: sync | watch; flags --api-url --api-key
    files.py              # recursive *.json discovery; watch stability scan
    client.py             # upload + status-poll over httpx; Retry-After backoff
    run.py                # the one sync loop (watch = same loop, no exit)
  tests/                  # unit tests, httpx.MockTransport
```

Behavior, mapping `5_cli.md` rules to mechanics:

- **Per file:** `POST /v1/uploads` (multipart, raw bytes verbatim) → on 201
poll `GET /v1/uploads/{id}` (1 s interval, 120 s bound) until terminal →
print `path → uploaded (complete, N traces)` / `failed: <error_message verbatim>`. 409 `duplicate_upload` → `already synced`, no poll. 4xx
(too large, invalid json…) → `failed: <message>`, run continues.
- **429:** sleep `Retry-After` (cap 60 s) and retry the same request,
indefinitely — provider backpressure is normal operation. Applies to both
upload and poll calls.
- **Startup preflight:** unreachable API or 401 on the first request → one
readable line, exit 2. No files found → exit 2.
- **Exit codes:** 0 all uploaded/skipped, 1 any failed, 2 couldn't run.
Summary line `synced 12 · skipped 40 · failed 1` on exit (and on watch
interrupt, whose code reflects failures seen).
- **Watch:** initial sync pass, then the polling stability scan (decision 5);
changed files (new size/mtime → new sha) re-upload; server dedupe makes
redundant uploads harmless.
- **Config:** `TRACE_API_URL` (default `http://localhost:8000`) /
`TRACE_API_KEY`, overridden by `--api-url` / `--api-key`. Documented in
`.env.example`; README gets a CLI quickstart (uv run from `apps/cli`).

### Frontend — /settings

`apps/web/src/app/(app)/settings/page.tsx` + `components/settings/`:

- **API keys** (`api-keys-section.tsx`): list (name, key_display monospace,
scope "upload-only", created, last_used "never used" when null); empty
state with mint as the action + CLI setup link; mint dialog (name field) →
reveal state: plaintext monospace + copy button + "you won't see this
again" + CLI snippet with the key inlined (`TRACE_API_KEY=tmk_… trace-sync sync ./traces`), dismissed only by explicit action; revoke per-row with
consequence-stating confirm; revoked rows stay listed, struck.
- **Profile** (`profile-section.tsx`): display name inline edit →
`PATCH /v1/profile`.
- **Privacy**: "Allow LLM analysis of private traces" switch, honest
consequence copy both ways + "takes effect on subsequent analysis runs"
(4_pages wording), no alarm styling.
- `lib/api/api-keys.ts`, `lib/api/profile.ts` (types mirroring the schemas,
existing convention). Nav: `Settings` joins `nav-links.tsx` (Review/
Subscriptions wait for A3/A4).

### Frontend — realtime invalidation (`lib/realtime.ts`)

One shared hook, `useRealtimeRefetch({ table, filter, onChange })`: opens a
Supabase channel on `postgres_changes` for the caller's rows (e.g.
`owner_id=eq.<uid>`), debounces bursts (~500 ms — a big CLI sync flips many
rows fast), and invokes the refetch callback. Event payloads are discarded —
invalidation only (decision 10). Subscribe/teardown follows the component
lifecycle; a failed or absent socket degrades to today's behavior (data still
loads on navigation/refetch). `/uploads` is the only consumer in A1; A3's
bell reuses the hook unchanged.

### Frontend — /uploads + pagination

- `app/(app)/uploads/page.tsx`: extends the existing `UploadsTable` with
source (`cli`/`web` badge), error verbatim (already rendered), processed
time, trace links (decision 7); failed rows flagged. States: loading,
empty, results. Linked from `/upload` ("Upload history") and `/traces`
(subhead link); not a nav slot.
- Shared `components/ui/pagination.tsx`-style pager (shadcn-themed, page
numbers + prev/next, "N–M of T"): wired into `/uploads`, and into
`useTraceList` (gains `page`, passes `limit/offset` through `listTraces`)
for `/traces`. Marketplace/library share `useTraceList`, so they get the
pager too — same component, no per-page styling. `?page=N` in the URL
(decision 8).

### Env + docs

- `.env.example`: CLI section (`TRACE_API_URL`, `TRACE_API_KEY`).
- README: CLI quickstart (mint on `/settings` → `uv run trace-sync sync`),
`/uploads` mention. No compose change — the CLI runs on the host.

### Tests

Integration (`services/api/tests/integration/test_machine_door.py`):

- Mint → returned plaintext authenticates `POST /v1/uploads`; the created
upload has `source='cli'`; `GET /v1/uploads/{id}` works with the key.
- Key on a JWT-only endpoint (`GET /v1/traces`, `GET /v1/uploads`) → 401;
garbage `tmk`_ token → 401; revoked key → 401 on uploads.
- `GET /v1/api-keys` never contains plaintext; `last_used_at` set after use;
revoke is idempotent.
- Duplicate upload via key → 409 with existing id (the CLI's skip signal).
- Profile: `PATCH` display_name + toggle → `GET` reflects both; invalid
body → 422.

CLI unit (`apps/cli/tests`, `httpx.MockTransport` — no live stack):

- Discovery: recursive `*.json`, non-json ignored, missing path → exit 2.
- Result lines + exit codes for 201→complete, 201→failed, 409, 413/422.
- 429 honors Retry-After then succeeds.
- Watch stability: growing file not uploaded until size/mtime stable across
scans (loop factored to be drivable in-test).

Frontend: type mirrors kept in sync per file-header convention (no new test
infra; UI verified by the walkthrough, per repo rule against browser
automation).

### Verification (done-when walkthrough)

1. Fresh `supabase db reset` + `docker compose up --build`; sign in.
2. `/settings`: mint a key — plaintext shown once with CLI snippet; key
  listed with display form after dismissal.
3. `uv run trace-sync sync ../../devdata` (key in env) → per-file lines,
  summary, exit 0; traces visible on `/traces` with the pager.
4. Re-run the same sync → every line `already synced`, exit 0, no new
  uploads.
5. `trace-sync watch` on a temp dir; drop a fixture in → uploads within a
  few seconds; drop a malformed `.json` → `failed: <reason>` line, watch
   stays alive; Ctrl-C → summary, exit 1.
6. `/uploads`: the bad file's row shows `failed` + reason verbatim +
  `cli` source; pager works. With `/uploads` open while a sync runs, rows
   appear and flip `processing → complete/failed` without a manual refresh
   (realtime invalidation).
7. `PATCH /v1/profile` via the `/settings` UI (rename + toggle off) →
  reload → both persist; verify with `GET /v1/profile` via curl.
8. Integration + CLI suites green; ruff + format clean; key-authed request
  to `GET /v1/traces` 401s (scope check).

## Drift

1. **CLI stdout is forced line-buffered** (`sys.stdout.reconfigure` in
   `main`). The first watch-mode walkthrough lost its output: Python
   block-buffers stdout when redirected, so per-file lines only landed at
   exit. Watch is exactly the mode whose output gets piped to logs.
2. **`last_used_at` throttle lives in the SQL guard**
   (`touch_last_used`: update only when null or older than 60 s), not in
   auth-layer logic — one fewer clock in app code; the write stays
   best-effort (failure logged, auth unaffected).
3. **Watch-interrupt verification moved to a unit test.** Processes
   backgrounded from a non-interactive shell inherit `SIGINT = SIG_IGN`, so
   the walkthrough can't exercise Ctrl-C; `test_watch_interrupt_prints_summary`
   drives `KeyboardInterrupt` through the scan sleep instead (summary line +
   failure-reflecting exit code).

Not drift, but noted: the pager landed on `/marketplace` and `/library` too —
the plan called this out (they share `useTraceList`); `/uploads`' realtime
invalidation verified at the data layer (publication row present, events
RLS-scoped) with the visual check left to the user per the no-browser rule.

## Outcome

Done-when met (2026-06-11), on a fresh `supabase db reset` +
`docker compose up --build`:

1. **Mint → CLI-sync → watch → re-sync → bad file**, end to end with a real
   minted key (`tmk_ga…dr9l`):
   - `trace-sync sync devdata/` → 4 × `uploaded (complete, 1 trace)`,
     `over-cap.json → failed: File exceeds the 25 MB limit.` (verbatim),
     summary `synced 4 · skipped 0 · failed 1`, exit 1.
   - Re-sync → every file `already synced`, exit 0, no new uploads.
   - `watch` on a temp dir picked up a dropped fixture within the 2 s scan
     (`uploaded (complete, 1 trace)`), a dropped empty-spans file printed
     `failed: Payload contains no valid spans (no spans found).` and the
     watcher stayed alive.
   - DB confirms every CLI upload row has `source = 'cli'`, web rows `'web'`;
     the failed row carries its reason for `/uploads` to render.
2. **Profile persistence:** `PATCH /v1/profile` round-trips display name +
   `allow_private_llm_analysis` (default true), partial updates leave the
   other field untouched, whitespace name 422s — `test_profile_roundtrip`.
3. **Scope + revocation:** key principals reach exactly the upload pair
   (list/traces/profile/api-keys all 401 `unauthorized`); revoked and
   garbage keys fail auth; revoke is idempotent and 404s on foreign keys;
   plaintext appears in exactly one response, ever.
4. **Realtime:** `uploads` confirmed in the `supabase_realtime` publication;
   `/uploads` subscribes via the invalidation-only hook.

Suites: 40 integration (7 new machine-door), 96 API unit, 17 CLI unit — all
green; ruff + format clean on both Python projects; `next build` + eslint
clean; `/settings`, `/uploads` routes live and session-gated. UI click-through
(reveal-once dialog, pager, live row flips) left to the user per the
no-browser-automation rule.

**Addendum (2026-06-11):** added `tests/integration/test_cli_sync.py` — the
real `trace-sync` binary run as a subprocess against the live stack with a
freshly minted key (sync → complete with `source='cli'`, re-sync → dedupe
skip, ingestion failure surfaced verbatim with exit 1, bad key → exit 2).
Closes the contract-drift gap the mock-transport CLI unit tests can't see;
the manual walkthrough is no longer the only end-to-end CLI coverage.
Integration suite is now 43 tests.

**Addendum (2026-06-11), demo assets:** `docs/demos/cli-sync.md` (the
machine-door walkthrough, indexed) plus `tools/agent_sessions_to_otlp.py`
(`make my-sessions`) — converts local Codex / Claude Code / Cursor session
logs into GenAI-semconv OTLP under git-ignored `devdata/agent-sessions/`,
so the demo runs on the evaluator's own real sessions. Verified: 10 real
sessions across all three sources converted, synced via the CLI, ingested
complete with scannable names, models, token counts, and error statuses.
Shared OTLP builders extracted to `tools/_otlp.py` (second consumer rule);
`tools/seed_dev.py` already covered listed-benchmark seeding and stands.