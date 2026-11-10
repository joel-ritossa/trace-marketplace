-- Session analysis hardening (9_session-analysis.md): a per-trace run
-- lease, unique turn labels, and owner-only review content on turn rows.

-- Run lease: one analyze_trace run per trace at a time. A run holds it
-- until analysis_lease_until (heartbeat-extended while alive, so a crashed
-- worker frees it within one lease period). A run that finds it held exits
-- and records what it wanted here; the holder re-enqueues that on release.
alter table public.traces
  add column analysis_lease_until timestamptz,
  add column analysis_rerun text check (analysis_rerun in ('incremental', 'finalize'));

-- One row per (turn, field, value): duplicate labels are merged on write.
delete from public.trace_labels l
  using public.trace_labels d
  where l.trace_id = d.trace_id and l.turn_index = d.turn_index
    and l.field = d.field and l.value = d.value and l.id > d.id;
alter table public.trace_labels
  add constraint trace_labels_value_key unique (trace_id, turn_index, field, value);
-- The unique index serves per-turn loads; the plain one is redundant.
drop index public.trace_labels_turn_idx;

-- `uncertain` is review-queue content (owner-only, like review items), and
-- model / usage / fingerprint are internal. RLS is row-level, so direct
-- reads are narrowed by column privileges: clients may select only the
-- public verdict columns, owners included (everything is served in full,
-- owner-scoped, by the API). The primary key stays readable so realtime
-- change events (an invalidation signal only) keep flowing.
revoke select on public.turn_analysis from anon, authenticated;
grant select (trace_id, turn_index, outcome, summary, signals, provenance, analyzed_at)
  on public.turn_analysis to authenticated;
