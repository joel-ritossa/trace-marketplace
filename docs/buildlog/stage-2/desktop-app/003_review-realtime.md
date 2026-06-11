# Desktop Tray App — Review Tab Not Updating

User report: the Notifications tab updates live but the Review tab goes
stale. Two compounding causes:

1. `review_items` was never added to the `supabase_realtime` publication
   (only `notifications` and `uploads` were, from A3/machine-door), so the
   Review tab's `useRealtimeRefetch("review_items", …)` subscription never
   received an event.
2. `ReviewTab` had no fallback poll — it loaded once on mount and then relied
   entirely on the dead realtime channel, violating the realtime hook's own
   contract ("a dead socket degrades silently to the fallback poll the
   callers keep running").

## Changes

- `supabase/migrations/00000000000012_review_realtime.sql`: adds
  `public.review_items` to the publication. Delivery is RLS-checked, so the
  trace-owner-only select policy scopes events — same pattern as the
  notifications and uploads tables.
- `ReviewTab.tsx`: 60s fallback poll alongside the realtime invalidation,
  mirroring the notification center.

## Outcome

- Migration applied to the local stack (`supabase migration up`);
  `pg_publication_tables` shows uploads, notifications, review_items.
- `pnpm exec tsc --noEmit` passes.
- Production needs the same migration applied on the next deploy.
