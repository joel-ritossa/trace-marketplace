# Desktop Tray App — Drop the Notifications Tab

User feedback pass, following 004: in a tray companion app the Notifications
tab was a redundant list — review requests dominate the feed and belong in
the Review queue (the desktop's only actionable surface); the other two
event types (subscription match, upload failed) just deep-link to the web.
Confirmed direction with the user: remove the tab, point the tray count at
open review items, keep native popups for review requests.

## Changes

- **Tab removed** (`NotificationsTab.tsx` deleted, `App.tsx`): the desktop
  has no in-app notification feed; the web's `/notifications` page owns that
  surface. Tabs are now Watch / Review / Settings.
- **Tray count = open review items** (`App.tsx`, `tray.ts`): the tray title
  mirrors the Review tab badge (work outstanding), not unread announcements.
  The count comes from the Review tab's existing 60s poll + realtime reload.
- **Native popups stay** (`App.tsx` `useNotificationPopups`, `notify.ts`):
  same trigger as before (one popup per unread increase, worded like the
  newest unread item). Click routing reworked: review requests surface the
  window on the Review tab; everything else opens the web app at the
  notification's target page (`extra` now carries `{target:"web", path}`
  instead of a tab name).
- **Pruned** (`lib/notifications.ts`): `markNotificationsRead` removed —
  the desktop only reads notifications to drive popups; read-state is
  managed on the web.
- README feature list updated for this pass and 004 (resolve page).

## Outcome

- `pnpm exec tsc --noEmit` passes; no linter errors.
- Native-popup click routing needs the bundled app (dev-mode constraint,
  see 002); left to interactive verification per the testing rules.
