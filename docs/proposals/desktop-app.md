# Desktop Tray App — Sync + Notifications + Review

Status: **proposal, not spec**. The web app and CLI specs (`docs/spec/`) stay normative; this describes a new, additive surface (`apps/desktop`) that consumes the existing API unchanged.

## Why

The supply-side loop today spans two tools: the `trace-sync` CLI watches folders and uploads, while review requests and notifications live in the web app. A contributor running the loop locally has to keep a terminal open *and* watch the bell in a browser tab. A lightweight tray app collapses that into one always-on surface: pick folders to watch, get native notifications when analysis wants a human, resolve review items in two clicks.

## Scope

One Tauri v2 menubar/tray app at `apps/desktop` (joins the existing pnpm workspace):

1. **Watch & sync** — a TS port of the `trace_sync` engine (`apps/cli/src/trace_sync/`): recursive `*.json`/`*.jsonl` discovery, the (size, mtime) stability debounce, pipelined upload + status polling, `Retry-After` honoring, retryable-vs-permanent outcome split. Folders are picked in-app (native dialog) and persisted. On first run the app auto-adds the harness session dirs that exist (`~/.codex/sessions`, `~/.claude/projects`, `~/.cursor/projects` — the same set as `tools/link_sessions.sh`), with a re-detect button for later; the modified-since filter defaults to 24 h so a first watch doesn't bulk-upload months of session history. Same invariants as the CLI: stateless, server-side content-hash dedup is the source of truth, one bad file never stops the run.
2. **Notifications** — Supabase realtime invalidation on `notifications` (same pattern as the web's `useRealtimeRefetch`) plus a fallback poll; new unread items fire native OS notifications; the tray title shows the unread count. In-app list with mark-read.
3. **Review queue** — open items from `GET /v1/review-items`, with the resolve form (outcome / failure mode / task category, closed vocabularies mirrored from the web's `taxonomy.ts`) posting to `/v1/review-items/{id}/resolve`. Full trace inspection deep-links to the web app.

## Auth decision

**In-app email/password login via supabase-js. No API keys, no backend changes.**

- The product's auth is email+password (no OAuth provider), so a browser-handoff flow has no IdP redirect to delegate to — it would require a bespoke token-handoff page and risk refresh-token rotation conflicts between the browser and app sessions.
- Login is one-time: the session persists through a supabase-js storage adapter backed by the app's local store, and supabase-js auto-refreshes. The allowlist guard still applies per-request server-side.
- The JWT reaches every endpoint the app needs: review/notifications require a JWT (`current_user`), and the upload pair accepts JWTs via `upload_principal`. The `tmk_` API-key surface stays exactly the upload pair — no scope changes.

## Deliberately out of scope

- Browser-handoff auth, OAuth, API-key scope changes.
- A full in-app trace inspector (deep-link to the web app instead).
- Auto-update, code signing/notarization, store distribution — local `pnpm tauri build` only for the trial.

## Done when

From a fresh `docker compose up` plus `pnpm tauri dev`:

1. Sign in once with an allowlisted email/password; restart the app — still signed in.
2. Existing harness session folders are pre-listed on first run. Add a folder, drop a fixture trace file into it — the app uploads it, shows the per-file outcome, and re-dropping the same file shows `already synced`.
3. A review request routed by analysis raises a native notification and the tray badge; the item appears in the Review tab; resolving it writes human-provenance labels (verifiable on the web trace page) and clears it from the queue.
4. Mark-read clears the badge.
