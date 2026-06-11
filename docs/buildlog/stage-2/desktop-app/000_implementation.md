# Desktop Tray App — Implementation

Implements the approved `docs/proposals/desktop-app.md`: a Tauri v2 tray app at `apps/desktop` combining folder watch/sync (TS port of `trace_sync`), native notifications, and the review resolve loop. No backend changes — JWT auth covers every endpoint the app touches.

## Plan

1. **Proposal first** (this slice is additive; `docs/spec/` untouched): `docs/proposals/desktop-app.md` records scope, the auth decision (in-app supabase-js email/password, persisted session, no API keys), and the done-when.
2. **Scaffold**: `apps/desktop` joins the pnpm workspace (`apps/*` already covered). Tauri v2 + React + TS (Vite), strict tsconfig mirroring `apps/web`. Plugins: `store` (session + settings), `fs` (folder scan/read), `dialog` (folder picker), `notification`, tray via core `tray-icon` feature. No custom Rust beyond the template + tray setup.
3. **Auth**: login screen → `supabase.auth.signInWithPassword`; session persisted via a storage adapter over plugin-store; `apiFetch` adapted from `apps/web/src/lib/api/client.ts` (same error envelope, bearer from the session).
4. **Watch engine**: TS port of `discover` / `StabilityScanner` / `SyncClient` semantics from `apps/cli/src/trace_sync/` (2s tick, stability debounce, enqueue-then-drain, 429 Retry-After, retryable-vs-permanent). Watch tab: folder list (native picker), start/stop, live outcome log + counts.
5. **Notifications**: realtime invalidation on `notifications` + fallback poll; native notification on unread increase; tray title badge; list + mark-read tab. Types mirrored from `apps/web/src/lib/api/notifications.ts`.
6. **Review**: open-queue tab, resolve form with the closed vocabularies (mirrored `taxonomy.ts`), 409 conflict handling (already_resolved / superseded / analysis_pending), deep-link to the web trace page. Types mirrored from `apps/web/src/lib/api/review.ts`.
7. **Docs**: `apps/desktop/README.md`, root README pointer.
8. Verify the proposal's done-when against the local stack; record outcome.

## Drift

- **Harness auto-listen added mid-slice** (user request): first run seeds the watched folders with whichever harness session dirs exist (`~/.codex/sessions`, `~/.claude/projects`, `~/.cursor/projects` — the same set as `tools/link_sessions.sh`, mirrored in `src/lib/harnesses.ts`), plus a "Detect agent sessions" button for later. `sinceHours` defaults to 24 (CLI demo guidance) so a first watch doesn't bulk-upload months of history; clearable in the UI. Proposal updated in the same pass.
- **`plugin-http` added** beyond the planned plugin list: the API's CORS allowlist covers only the web origin (`settings.web_origins`), so webview `fetch` would be blocked. All API and Supabase HTTP goes through the Tauri-side fetch (no CORS); realtime stays on the webview WebSocket (not CORS-gated).
- **fs scope is read-only but path-broad** (`**`, `requireLiteralLeadingDot: false` for the hidden harness dirs): watched folders are arbitrary user picks, and only `read-dir`/`read-file`/`stat`/`exists` are granted — the app can never write or delete through the fs plugin.
- **No tailwind/shadcn in the desktop shell**: the UI is a small hand-rolled stylesheet whose values mirror the DESIGN.md token ladders (light + dark via `prefers-color-scheme`). Pulling the web's Tailwind v4 + shadcn stack into a four-tab tray app would be more machinery than UI; DESIGN.md governs the look, not the toolchain.
- **Rust toolchain is a new prerequisite** for this app only (documented in `apps/desktop/README.md`); the rest of the repo is unaffected.
- **Post-launch fixes from live testing**: (1) the `http:default` URL scope needs explicit host+port wildcards (`http://*:*`) — `http://**` doesn't match URLs with explicit ports; (2) realtime channels get a unique topic per subscriber — the desktop's single long-lived supabase client reuses channels by topic, and a second `.on()` after `subscribe()` throws and unmounted the whole tree (the web app dodges this with per-call browser clients); realtime setup is also try/caught so it can only degrade to the fallback polls; (3) harness watch roots restrict discovery to `.jsonl` (one deliberate extension over the CLI port: session transcripts are always JSONL, and the `.json` junk beside them — Cursor MCP descriptors, Claude project metadata — was being uploaded and rejected file by file); (4) the watcher checks `stopped` inside the enqueue/drain loops so Stop is responsive mid-batch, not just between ticks.

## Outcome

- `pnpm exec tsc --noEmit`, `pnpm build` (Vite), `cargo check`, and `pnpm tauri build --debug --no-bundle` all pass; `pnpm tauri dev` launches against the running Compose stack (API health 200).
- Sync engine, API modules, taxonomy, and realtime hook are line-for-line ports/mirrors with "keep in sync" headers; no backend or web-app changes anywhere in the slice.
- The proposal's done-when (one-time login persisting across restarts, harness folders pre-listed, upload → `already synced` dedupe, native notification + tray badge → in-app resolve with human provenance, mark-read clearing the badge) needs interactive click-through, which per the testing rules is left to the user; the API contracts it exercises are already covered by `tests/integration/test_hil.py` and the upload suite.
