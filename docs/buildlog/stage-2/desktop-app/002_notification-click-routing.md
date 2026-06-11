# Desktop Tray App — Notification Click Routing + Watch Log Polish

User feedback pass: (1) clicking a native notification should land in the
right place in the app; (2) clicking a review-request row in the
Notifications tab should open the desktop Review tab, not the web app;
(3) the Watch tab's activity list grew past the window and had no
timestamps.

## Changes

- **Plugin swap** (`Cargo.toml`, `package.json`, `capabilities/default.json`,
  `src-tauri/src/lib.rs`): the official `tauri-plugin-notification` has no
  desktop click callbacks (actions/click events are mobile-only; its
  notify-rust backend can't deliver them on macOS). Replaced with the
  community fork `tauri-plugin-notifications` (Choochmeque, 0.4.x) with
  `default-features = false`, which drives UNUserNotificationCenter directly
  and emits a `notificationClicked` event carrying the notification's
  `extra` payload.
  - The plugin links Swift via swift-bridge, so `build.rs` adds an rpath to
    the system Swift runtime (`/usr/lib/swift`) on macOS — without it the
    binary aborts at launch with "Library not loaded:
    @rpath/libswift_Concurrency.dylib".
  - Constraint: UNUserNotificationCenter requires a real `.app` bundle; the
    plugin's setup fails fatally under `tauri dev`. `lib.rs` registers the
    plugin only when the executable lives inside a bundle; `notify.ts`
    try/catches every call, so dev mode degrades to no native notifications
    (badge, tray count, and tabs unaffected). Documented in the app README
    and the `run-desktop-app` skill.
- **Click routing** (`notify.ts`, `App.tsx`): `nativeNotify` now attaches
  `extra.target` ("review" when the newest unread is a review request,
  "notifications" otherwise); a Shell-level `onNotificationClicked` listener
  shows/focuses the window and switches to that tab.
- **In-app notification rows** (`NotificationsTab.tsx`, `App.tsx`): review
  requests now switch to the desktop Review tab (still mark-read first);
  subscription matches and upload failures keep deep-linking to the web app,
  which owns those surfaces.
- **Watch activity log** (`WatchTab.tsx`, `styles.css`): each line gets an
  `HH:MM:SS` timestamp recorded at append time; the Watch page now fills the
  window (`.page.fill`/`.card.fill`/`.log.fill`) so the log flexes to the
  remaining height and scrolls internally instead of growing the page.

## Outcome

- `pnpm exec tsc --noEmit` and `cargo check` pass; `pnpm tauri build --debug
  --bundles app` produces the bundle the click path runs in.
- Click-through of the native-notification → tab flow needs the bundled app
  and a real notification (seed-demo or an upload-triggered review request);
  left to interactive verification per the testing rules.
