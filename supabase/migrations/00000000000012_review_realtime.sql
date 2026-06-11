-- Review-queue realtime invalidation (desktop Review tab; same pattern as
-- notifications/uploads). postgres_changes delivery is RLS-checked against
-- the subscriber, so the trace-owner-only select policy already scopes
-- events to the owner.
alter publication supabase_realtime add table public.review_items;
