-- Stage 2 A2: analysis plumbing. Per docs/spec/stage-2/2_data-model.md
-- (analyzer_results, trace_analysis, stage-1 deltas) and the A2 buildlog
-- decisions (stable trace identity, analysis retry budget on traces).

-- Stable trace identity (A2 decision 1): re-ingest upserts on this key, so
-- traces.id — and everything cascade-hung off it — survives a rewrite.
alter table public.traces
  add constraint traces_upload_source_trace_key unique (upload_id, source_trace_id);

alter table public.traces
  -- Ingestion-derived sum of span tokens; null when no span carries tokens.
  add column total_tokens integer,
  -- Durable retry budget for analyze_trace, mirroring uploads.attempts;
  -- claim-incremented by the task, reset by re-ingest and operator requeue.
  add column analysis_attempts integer not null default 0,
  add column analysis_attempted_at timestamptz;

-- Analysis tasks are trace-scoped; ingestion rows leave trace_id null
-- (2_data-model.md stage-1 deltas). Analysis rows fill upload_id too —
-- the trace knows its upload, and the linkage is free.
alter table public.dead_letters
  add column trace_id uuid references public.traces (id) on delete cascade;

-- Backs the derived-state probe: failed = a non-requeued analyze dead letter.
create index dead_letters_trace_id_open_idx
  on public.dead_letters (trace_id) where requeued_at is null;

-- One row per analyzer run per trace: the audit + reproducibility layer,
-- never queried by search. Delete-and-rewritten per analyze_trace run.
create table public.analyzer_results (
  id uuid primary key default gen_random_uuid(),
  trace_id uuid not null references public.traces (id) on delete cascade,
  analyzer text not null,
  analyzer_version text not null,
  model_id text,
  output jsonb not null,
  confidence numeric,
  created_at timestamptz not null default now()
);

create index analyzer_results_trace_id_idx on public.analyzer_results (trace_id);

-- The 1:1 side table holding everything filterable. One writer: the
-- analysis job (and, at A3, human resolution). No row = not yet analyzed;
-- null field = the analyzer didn't produce it (null never matches).
create table public.trace_analysis (
  trace_id uuid primary key references public.traces (id) on delete cascade,
  -- Stable ternary set: check-constrained. failure_mode / task_category
  -- taxonomies evolve, so they stay app-validated text (no check).
  outcome text check (outcome in ('success', 'failure', 'indeterminate')),
  outcome_confidence numeric,
  outcome_provenance text
    check (outcome_provenance in ('machine', 'human_confirmed', 'human')),
  failure_mode text,
  failure_mode_confidence numeric,
  failure_mode_provenance text
    check (failure_mode_provenance in ('machine', 'human_confirmed', 'human')),
  task_category text,
  task_category_confidence numeric,
  task_category_provenance text
    check (task_category_provenance in ('machine', 'human_confirmed', 'human')),
  -- Promoted family-1 signals; all nullable (fail open).
  has_retry_loop boolean,
  loop_kind text check (loop_kind in ('exact_repeat', 'cycle', 'stagnation')),
  recovered_from_error boolean,
  truncation_suspected boolean,
  llm_call_count integer,
  tool_call_count integer,
  -- Map metric name -> number (0-1) or boolean flag; reasons stay in
  -- analyzer_results.
  metric_scores jsonb,
  llm_status text not null check (llm_status in ('complete', 'skipped')),
  llm_skip_reason text
    check (llm_skip_reason in ('not_configured', 'owner_opt_out')),
  analyzed_at timestamptz not null default now(),
  -- skip reason exists exactly when skipped.
  check ((llm_status = 'skipped') = (llm_skip_reason is not null))
);

-- No secondary indexes: PK-joined only until query evidence demands them
-- (2_data-model.md "Indexes").

-- The API enforces access with the service role; RLS mirrors the rules for
-- defense in depth. Both tables mirror the referenced trace exactly: owner,
-- or any authenticated user when the trace is listed. Read-only for clients
-- (no insert/update policies) — only the worker and API write here.
alter table public.analyzer_results enable row level security;

create policy "analyzer_results_select_visible" on public.analyzer_results
  for select to authenticated
  using (
    exists (
      select 1 from public.traces t
      where t.id = trace_id
        and (t.owner_id = (select auth.uid()) or t.visibility = 'listed')
    )
  );

alter table public.trace_analysis enable row level security;

create policy "trace_analysis_select_visible" on public.trace_analysis
  for select to authenticated
  using (
    exists (
      select 1 from public.traces t
      where t.id = trace_id
        and (t.owner_id = (select auth.uid()) or t.visibility = 'listed')
    )
  );
