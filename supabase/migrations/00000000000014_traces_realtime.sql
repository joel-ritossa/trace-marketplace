-- Traces realtime invalidation (web traces list + trace detail; same pattern
-- as uploads/notifications/review_items). postgres_changes delivery is
-- RLS-checked against the subscriber: owners get events for their own rows,
-- and anyone authenticated gets events for listed traces — which is exactly
-- the read rule the surfaces already follow. trace_analysis joins into both
-- the list (outcome badge) and the detail Analysis section, so it signals too.
alter publication supabase_realtime add table public.traces;
alter publication supabase_realtime add table public.trace_analysis;
