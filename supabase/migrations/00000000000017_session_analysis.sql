-- Session analysis (docs/spec/stage-2/9_session-analysis.md): the turn is
-- the unit of judgment. Per-turn verdicts live in turn_analysis, their
-- multi-valued labels in trace_labels; trace_analysis becomes the session
-- roll-up. Votes, confidence, provenance triplets and metric scores go.

-- Existing analysis is disposable and its shapes do not carry over: clear
-- it so the reshape applies on a populated database, and give every trace a
-- fresh analysis budget (the sweep re-analyzes them).
truncate public.analyzer_results, public.trace_analysis, public.trace_embeddings;
delete from public.review_items;
update public.dead_letters set requeued_at = now()
  where trace_id is not null and requeued_at is null;
update public.traces set analysis_attempts = 0, analysis_attempted_at = null;

alter table public.trace_analysis
  drop column outcome_confidence,
  drop column outcome_provenance,
  drop column failure_mode,
  drop column failure_mode_confidence,
  drop column failure_mode_provenance,
  drop column task_category,
  drop column task_category_confidence,
  drop column task_category_provenance,
  drop column metric_scores,
  drop constraint trace_analysis_outcome_check,
  add constraint trace_analysis_outcome_check
    check (outcome in ('success', 'partial', 'failure', 'indeterminate')),
  add column goal text,
  add column summary text,
  -- Union over the trace's turn labels; recomputed on every write.
  add column task_categories text[] not null default '{}',
  add column failure_modes text[] not null default '{}',
  -- Roll-up time; null until the session is finalized, and reset whenever
  -- a turn is rewritten after it (the roll-up is then stale).
  alter column analyzed_at drop not null,
  alter column analyzed_at drop default;

-- task_category / failure_mode filters are array overlap (&&).
create index trace_analysis_task_categories_idx
  on public.trace_analysis using gin (task_categories);
create index trace_analysis_failure_modes_idx
  on public.trace_analysis using gin (failure_modes);

-- Audit rows carry model/usage only; there is no confidence any more.
alter table public.analyzer_results drop column confidence;

-- The embedding input is now the roll-up text, not a rendering.
alter table public.trace_embeddings rename column renderer_version to input_version;

create table public.turn_analysis (
  trace_id uuid not null references public.traces (id) on delete cascade,
  turn_index integer not null,
  -- Hash of the turn's span ids and end time; a change means re-judge.
  fingerprint text not null,
  -- Null = not judged (LLM analysis skipped); signals are always computed.
  outcome text check (outcome in ('success', 'partial', 'failure', 'indeterminate')),
  summary text,
  uncertain text,
  signals jsonb not null,
  -- human turns are never re-judged or overwritten by the machine.
  provenance text not null default 'machine' check (provenance in ('machine', 'human')),
  model text,
  usage jsonb,
  analyzed_at timestamptz not null default now(),
  primary key (trace_id, turn_index)
);

create table public.trace_labels (
  id bigint generated always as identity primary key,
  trace_id uuid not null,
  turn_index integer not null,
  field text not null check (field in ('task_category', 'failure_mode')),
  value text not null,
  span_ids text[] not null default '{}',
  reason text,
  foreign key (trace_id, turn_index)
    references public.turn_analysis (trace_id, turn_index) on delete cascade
);

create index trace_labels_turn_idx on public.trace_labels (trace_id, turn_index);

-- Mirrors trace_analysis: readable by the owner, or anyone authenticated
-- when the trace is listed. Read-only for clients.
alter table public.turn_analysis enable row level security;

create policy "turn_analysis_select_visible" on public.turn_analysis
  for select to authenticated
  using (
    exists (
      select 1 from public.traces t
      where t.id = trace_id
        and (t.owner_id = (select auth.uid()) or t.visibility = 'listed')
    )
  );

alter table public.trace_labels enable row level security;

create policy "trace_labels_select_visible" on public.trace_labels
  for select to authenticated
  using (
    exists (
      select 1 from public.traces t
      where t.id = trace_id
        and (t.owner_id = (select auth.uid()) or t.visibility = 'listed')
    )
  );

-- Turn rows change on incremental runs and relabels; the trace page
-- invalidates on them like on trace_analysis.
alter publication supabase_realtime add table public.turn_analysis;

-- Stored subscription queries: drop the removed filter keys, and the
-- subscriptions that leaves with no predicate at all (they would match
-- every listed trace).
update public.subscriptions
  set query = query - array[
    'outcome_provenance', 'failure_mode_provenance', 'task_category_provenance',
    'outcome_confidence_gte', 'task_category_confidence_gte', 'metric'
  ];
delete from public.subscriptions
  where query = '{}'::jsonb and similar_to_trace_id is null;
