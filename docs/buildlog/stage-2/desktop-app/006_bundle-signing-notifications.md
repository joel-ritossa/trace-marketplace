# Desktop Tray App — Native Popups Silently Dead: Bundle Signing

User report: no OS popup from the debug bundle despite a healthy pipeline
(realtime delivering, unread increasing, plugin registered, `.app` bundle).
Diagnosed from the outside in: macOS had **no notification-center
registration at all** for the app (`~/Library/Preferences/com.apple.ncprefs.plist`
had no entry under any identifier), meaning the app never even reached the
permission prompt.

## Root cause

Tauri debug bundles were only **linker-signed**: `codesign -dv` showed
`flags=(adhoc,linker-signed)`, a random `Identifier=desktop-3071634ed4e8b4e8`,
and `Info.plist=not bound`. UNUserNotificationCenter silently refuses to
register an app whose signature doesn't bind the bundle and its identifier —
no prompt, no error. The frontend's best-effort `catch` in `notify.ts`
(there so dev mode degrades quietly) swallowed whatever surfaced, making the
failure invisible. The random linker identifier also changes per rebuild, so
even a one-off success would not survive the next build.

## Fix

- `tauri.conf.json`: `bundle.macOS.signingIdentity: "-"` — every build now
  gets a real ad-hoc *bundle* signature (`Identifier=com.trace-marketplace.desktop`,
  Info.plist bound, sealed resources). Applies to CI release builds too.
- `run-desktop-app` skill: new troubleshooting entry (symptom, codesign
  check, fix); build-section wording updated (ad-hoc signed, not notarized).
- `release-desktop.yml`: header comment updated to match.

## Outcome

- Rebuilt debug bundle verifies (`codesign -dv` shows the real identifier,
  `Info.plist entries=14`), and on the next seeded `review_request`
  notification the permission prompt appeared and the popup fired —
  confirmed interactively by the user.
