-- Traces and spans per 2_data-model.md. Slice 3 columns (tags, description,
-- visibility, listed_at, search_tsv) arrive with discovery in their own
-- migration.

create table public.traces (
  id uuid primary key default gen_random_uuid(),
  upload_id uuid not null references public.uploads (id) on delete cascade,
  -- Denormalized from the upload for access checks without a join.
  owner_id uuid not null references public.profiles (id) on delete cascade,
  source_trace_id text not null,
  name text not null,
  status text not null check (status in ('ok', 'error')),
  started_at timestamptz not null,
  ended_at timestamptz not null,
  duration_ms integer not null,
  span_count integer not null,
  error_count integer not null,
  provider text,
  model text,
  service_name text,
  tool_names text[] not null default '{}',
  error_types text[] not null default '{}',
  source_format text not null,
  importer_version text not null,
  created_at timestamptz not null default now()
);

create index traces_owner_id_idx on public.traces (owner_id);
create index traces_upload_id_idx on public.traces (upload_id);

create table public.spans (
  id uuid primary key default gen_random_uuid(),
  trace_id uuid not null references public.traces (id) on delete cascade,
  source_span_id text not null,
  source_parent_span_id text,
  name text not null,
  kind text not null check (
    kind in ('llm', 'agent', 'tool', 'chain', 'retriever', 'embedding', 'other')
  ),
  started_at timestamptz not null,
  ended_at timestamptz not null,
  duration_ms integer not null,
  status text not null check (status in ('ok', 'error', 'unset')),
  status_message text,
  error_type text,
  provider text,
  model text,
  tool_name text,
  input_tokens integer,
  output_tokens integer,
  total_tokens integer,
  attributes jsonb not null default '{}',
  events jsonb not null default '[]'
);

-- Composite: the span-list query filters on trace_id and orders by
-- started_at, so pages come straight off the index even at 50k spans.
create index spans_trace_id_started_at_idx on public.spans (trace_id, started_at);

-- The API enforces access with the service role; RLS mirrors the rules for
-- defense in depth (2_data-model.md "Access Rules"). Listed-visibility
-- policies land in Slice 3 with the visibility column.
alter table public.traces enable row level security;

create policy "traces_select_own" on public.traces
  for select using ((select auth.uid()) = owner_id);

alter table public.spans enable row level security;

create policy "spans_select_own" on public.spans
  for select using (
    exists (
      select 1 from public.traces t
      where t.id = trace_id and t.owner_id = (select auth.uid())
    )
  );
