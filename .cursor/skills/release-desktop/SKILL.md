---
name: release-desktop
description: Cut a production release of the desktop app (apps/desktop) — bump the version, push a desktop-v* tag, monitor the GitHub release workflow, and verify the published bundle. Use when asked to release, publish, ship, or tag a new version of the desktop app.
---

# Release the desktop app

Releases are tag-driven: pushing a `desktop-v*` tag runs
`.github/workflows/release-desktop.yml`, which builds a universal macOS
bundle with production connection defaults baked in (`VITE_*` env vars from
the repo variables `APP_URL`, `NEXT_PUBLIC_SUPABASE_URL`,
`NEXT_PUBLIC_SUPABASE_ANON_KEY` — same ones the web deploy uses) and
attaches the `.dmg` to a GitHub Release. Bundles are unsigned by design
(trial project); the release notes carry the quarantine bypass.

## Steps

1. **Pick the version.** Tags build whatever commit they point to, so make
   sure the desktop changes you want to ship are committed and pushed
   first. Check the current version and last release:

   ```sh
   jq -r .version apps/desktop/src-tauri/tauri.conf.json
   gh release list --limit 5
   ```

2. **Bump the version in all three places** (they must stay in sync;
   the workflow gates on `tauri.conf.json`):

   - `apps/desktop/src-tauri/tauri.conf.json` → `version`
   - `apps/desktop/package.json` → `version`
   - `apps/desktop/src-tauri/Cargo.toml` → `version`

   Then refresh the lockfile so CI builds clean:

   ```sh
   cd apps/desktop/src-tauri && source "$HOME/.cargo/env" && cargo check
   ```

   Commit and push the bump (skip this step entirely if the current
   version has never been released — e.g. the first `desktop-v0.1.0`).

3. **Tag and push the tag** — the tag must exactly match the
   `tauri.conf.json` version or the workflow fails fast:

   ```sh
   version=$(jq -r .version apps/desktop/src-tauri/tauri.conf.json)
   git tag "desktop-v$version" && git push origin "desktop-v$version"
   ```

4. **Monitor the workflow** (~10–15 min cold, faster with a warm Rust
   cache):

   ```sh
   gh run list --workflow=release-desktop.yml --limit 1
   gh run watch <run-id> --exit-status
   ```

5. **Verify the release** has the `.dmg` attached:

   ```sh
   version=$(jq -r .version apps/desktop/src-tauri/tauri.conf.json)
   gh release view "desktop-v$version"
   ```

   Spot-check by downloading the asset, installing, and running
   `xattr -dr com.apple.quarantine "/Applications/Trace Marketplace.app"`
   before first launch — the app should show the production URLs in
   Settings and sign in against trace-mp.com.

## Redoing a failed release

If the workflow failed and you need to re-run the same version after a
fix, delete the tag (and the draft/partial release if one was created),
then re-tag:

```sh
gh release delete "desktop-v$version" --yes   # only if it was created
git tag -d "desktop-v$version" && git push origin ":refs/tags/desktop-v$version"
git tag "desktop-v$version" && git push origin "desktop-v$version"
```

Never re-tag a version that shipped to users — bump instead.
