# Trace Marketplace Desktop

A lightweight Tauri tray app that runs the contributor loop without a terminal or browser tab: watch local folders for trace/session files and upload them, get native notifications when analysis wants a human, and resolve review items in two clicks. See `docs/proposals/desktop-app.md` for scope and decisions.

## For users — install

No local stack needed: release builds are pointed at production (trace-mp.com) out of the box.

1. **Get access** (once, ask an operator): your email must be on the marketplace allowlist, and you need an account — sign up at [trace-mp.com](https://trace-mp.com) first if you don't have one. The desktop app uses the same email/password.
2. **Download** the `.dmg` from the latest `desktop-v*` [GitHub Release](../../../../releases), open it, and drag the app to Applications.
3. **Clear the quarantine flag** once — the build is ad-hoc signed but not notarized (deliberate for the trial), so macOS blocks it until you run:

   ```sh
   xattr -dr com.apple.quarantine "/Applications/Trace Marketplace.app"
   ```

4. **Launch and sign in** with your marketplace email/password. The session persists across restarts and auto-refreshes; no API key needed.

On first run the app auto-adds whichever harness session dirs exist (`~/.codex/sessions`, `~/.claude/projects`, `~/.cursor/projects`) and starts watching. Closing the window hides to the tray; click the tray icon to bring it back. Allow notifications when macOS asks so review requests can pop up.

## For users — what it does

- **Watch** — recursive `*.json`/`*.jsonl` discovery with the CLI's stability debounce, pipelined upload + ingestion status polling, `Retry-After` honoring. Synced files are remembered across restarts (per server + account, cleared on sign-out), so a relaunch only uploads what's new or changed; the server's content hash still dedupes everything else, so re-syncing is always safe. The modified-since filter defaults to 24 h so a first watch doesn't bulk-upload months of history.
- **Review** — the open queue, with a full resolve page per item mirroring the web's `/review/[itemId]`: reconstructed conversation evidence beside the machine context and verdict form, same resolve semantics (partial answers fine, nothing pre-selected, failure mode only with a failure verdict), and "Resolve & next" to walk the queue. Raw span inspection deep-links to the web trace page. The tray badge and tab count show open items.
- **Notifications** — native popups only; there is no in-app feed (the web's `/notifications` page owns that surface). Supabase realtime invalidation plus a fallback poll detect new unread items; clicking a popup opens the Review tab for review requests and the web app for everything else.

## For developers — run from source

Prereqs: the local stack (`supabase start` + `docker compose up`), Node 22+/pnpm, and a [Rust toolchain](https://rustup.rs) (Tauri compiles a native shell).

```sh
pnpm install            # repo root — the app is part of the workspace
cd apps/desktop
pnpm tauri dev          # dev app (first compile takes a few minutes)
pnpm tauri build        # local bundle under src-tauri/target/release/bundle/
```

Dev builds fall back to the local stack connection defaults (`.env.example`); the Settings tab can override API URL, Supabase URL + anon key (public), and the web URL used for deep links (stored via the Tauri store plugin in the app's data dir, alongside the auth session). Native notifications are a no-op under `tauri dev` — macOS only registers notifications for a signed `.app` bundle, so test them with `pnpm tauri build --debug --bundles app`. More setup detail and troubleshooting in `.cursor/skills/run-desktop-app/SKILL.md`.

## For developers — cut a release

Releases are tag-driven. Make sure the desktop changes you want to ship are committed and pushed to main, then:

1. Bump `version` in `src-tauri/tauri.conf.json`, `package.json`, and `src-tauri/Cargo.toml` (skip if the current version has never been released), run `cargo check` in `src-tauri/` to refresh the lockfile, and push the bump.
2. Push the matching tag:

   ```sh
   version=$(jq -r .version apps/desktop/src-tauri/tauri.conf.json)
   git tag "desktop-v$version" && git push origin "desktop-v$version"
   ```

3. `.github/workflows/release-desktop.yml` builds a universal macOS bundle (~10–15 min) with production connection defaults baked in (`VITE_*` from the same repo variables the web deploy uses) and attaches the `.dmg` to a GitHub Release.

The step-by-step process — version checks, monitoring the run, verifying the asset, redoing a failed release — lives in `.cursor/skills/release-desktop/SKILL.md`.

## Code layout

`src/lib/sync/` is a TS port of `apps/cli/src/trace_sync/` (files/client/run); `src/lib/{notifications,review,taxonomy}.ts` mirror the web's API modules; `src/lib/realtime.ts` mirrors the web's invalidation-only realtime hook. All carry "keep in sync" headers pointing at their source of truth. The Rust side is the stock Tauri template plus plugin registrations — no custom commands. Notifications use the community `tauri-plugin-notifications` fork (notify-rust disabled) because the official plugin has no desktop click callbacks; it drives macOS's notification center directly, so it's only registered when running from a bundle (`src-tauri/src/lib.rs`).
