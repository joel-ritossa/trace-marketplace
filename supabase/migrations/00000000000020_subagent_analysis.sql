-- Subagent verdicts (9_session-analysis.md "Subagent verdicts"): a linked
-- subagent is judged on its own, against its brief, before its turn. One
-- row per judged spawn span; rewritten with the turn rows.
create table public.subagent_analysis (
  trace_id uuid not null references public.traces (id) on delete cascade,
  -- source_span_id of the spawn span.
  span_id text not null,
  turn_index integer not null,
  -- The turn recipe over the spawn span and its descendants; a change
  -- means re-judge.
  fingerprint text not null,
  outcome text not null check (outcome in ('success', 'partial', 'failure', 'indeterminate')),
  summary text not null,
  -- [{value, span_ids, reason}]; never part of the turn or session labels.
  failure_modes jsonb not null default '[]',
  model text,
  usage jsonb,
  analyzed_at timestamptz not null default now(),
  primary key (trace_id, span_id)
);

-- Mirrors turn_analysis: rows readable by the owner, or anyone
-- authenticated when the trace is listed; read-only for clients, and only
-- the public verdict columns (model / usage / fingerprint are internal).
alter table public.subagent_analysis enable row level security;

create policy "subagent_analysis_select_visible" on public.subagent_analysis
  for select to authenticated
  using (
    exists (
      select 1 from public.traces t
      where t.id = trace_id
        and (t.owner_id = (select auth.uid()) or t.visibility = 'listed')
    )
  );

revoke select on public.subagent_analysis from anon, authenticated;
grant select (trace_id, span_id, turn_index, outcome, summary, failure_modes, analyzed_at)
  on public.subagent_analysis to authenticated;
