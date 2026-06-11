---
name: run-desktop-app
description: Run the Trace Marketplace desktop tray app (apps/desktop, Tauri) locally in dev mode or as a built bundle, including prerequisites, stack dependencies, and troubleshooting. Use when asked to run, launch, start, build, or debug the desktop app or tray app.
---

# Run the desktop app locally

`apps/desktop` is a Tauri v2 tray app (folder watch/sync + notifications +
review). It talks to the local stack, so the stack must be up first.

## Prerequisites (check before launching)

1. **Rust toolchain**: `source "$HOME/.cargo/env" && cargo --version`.
   If missing: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal`.
2. **JS deps**: `pnpm install` at the repo root (the app is a workspace member).
3. **Local stack**: `supabase start` + `docker compose up` — verify with
   `curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/v1/health`
   (expect `200`). The app signs in with a real account: the email must be
   allowlisted (see the `allow-email` skill) and registered via the web app.

## Dev mode

Run in a background terminal — it blocks for the app's lifetime and the first
compile takes several minutes (subsequent ones seconds):

```sh
cd apps/desktop && source "$HOME/.cargo/env" && pnpm tauri dev
```

(`pnpm dev:desktop` from the repo root is equivalent.) Ready when the output
shows ``Finished `dev` profile`` then ``Running `target/debug/desktop` `` — a
window opens and a tray icon appears. Vite hot-reloads `src/`; edits under
`src-tauri/` (including `capabilities/default.json` and `tauri.conf.json`)
trigger an automatic Rust rebuild and app relaunch — wait for the second
`Running` line, don't restart manually.

Only one instance can run: port 1420 is fixed (`strictPort`), so kill any
existing dev process before starting another.

## Build a binary / bundle

```sh
cd apps/desktop && source "$HOME/.cargo/env"
pnpm tauri build --debug --no-bundle   # fast compile check, binary only
pnpm tauri build                       # release .app/.dmg under src-tauri/target/release/bundle/
```

Bundles are ad-hoc signed (`bundle.macOS.signingIdentity: "-"`, required for
native notifications — see Troubleshooting) but not notarized, so macOS
Gatekeeper warnings are expected; real signing/notarization is deliberately
out of scope (trial project). Clear
the quarantine flag on a downloaded bundle with
`xattr -dr com.apple.quarantine "/Applications/Trace Marketplace.app"`.

Production builds ship via a `desktop-v*` tag and
`.github/workflows/release-desktop.yml` — full process in the
`release-desktop` skill. Local dev builds keep the local-stack defaults;
release builds bake production URLs via `VITE_*` env vars (see
`src/lib/settings.ts`).

## Troubleshooting

- **No native notifications in dev mode**: expected. The notifications
  plugin (community fork, notify-rust disabled) needs macOS's
  UNUserNotificationCenter, which only works from a `.app` bundle, so
  `src-tauri/src/lib.rs` skips registering it under `tauri dev` and the
  frontend no-ops every call. Test notifications (and click-to-open) with a
  bundle: `pnpm tauri build --debug --bundles app`, then run the app from
  `src-tauri/target/debug/bundle/macos/`.

- **No native notifications from a bundle either (no permission prompt, no
  entry in System Settings → Notifications)**: the bundle must carry a real
  (at least ad-hoc) *bundle* signature. UNUserNotificationCenter silently
  rejects apps with only the linker's ad-hoc Mach-O signature (codesign
  shows `linker-signed`, a random `desktop-…` identifier, and
  `Info.plist=not bound`) — no prompt, no error, the frontend's best-effort
  catch swallows it. `tauri.conf.json` sets
  `bundle.macOS.signingIdentity: "-"` so every build is ad-hoc signed as a
  bundle; verify with `codesign -dv` (expect
  `Identifier=com.trace-marketplace.desktop` and `Info.plist entries=…`).
  The first properly signed launch shows the permission prompt — Allow it.

- **Black/blank window**: the boot sequence failed before React rendered
  (in dark mode the empty shell is pure black). Check the dev terminal for
  panics, then the webview console (right-click → Inspect Element in dev
  builds). Usual causes: a Tauri permission missing from
  `src-tauri/capabilities/default.json`, or the store/tray init throwing.
- **"url not allowed on the configured scope"**: the `http:default`
  permission's URL patterns must wildcard host *and* port explicitly
  (`http://*:*`) — `http://**` alone does not match URLs with an explicit
  port like `127.0.0.1:55321`.
- **CORS-looking failures**: API/Supabase HTTP must go through
  `@tauri-apps/plugin-http`'s fetch, never the webview's global `fetch` —
  the API's CORS allowlist only covers the web origin.
- **Login rejected**: confirm the account exists in the web app, the email
  is allowlisted, and Settings → Connection points at the right
  API/Supabase URLs (defaults match `.env.example`).
- **App state reset**: settings and the auth session live in the Tauri
  store under the app data dir (`~/Library/Application Support/com.trace-marketplace.desktop/`
  on macOS); delete `settings.json` / `auth.json` there to reset.
