-- Slice 3: discovery columns on traces, full-text search, acquisitions.
-- Per 2_data-model.md (discovery columns, Search, acquisitions, Access Rules).

alter table public.traces
  add column tags text[] not null default '{}',
  add column description text,
  add column visibility text not null default 'private'
    check (visibility in ('private', 'listed')),
  add column listed_at timestamptz;

-- array_to_string is only stable (anyarray overload); this text[]-only
-- wrapper is genuinely immutable so the generated column can use it.
create function public.immutable_array_to_string(text[], text)
returns text
language sql immutable parallel safe
return array_to_string($1, $2);

-- Searchable metadata only (2_data-model.md "Search"): never span
-- attributes/events. Weights: name/tags A, description B, the rest C.
alter table public.traces
  add column search_tsv tsvector generated always as (
    setweight(to_tsvector('english', name), 'A')
    || setweight(to_tsvector('english', public.immutable_array_to_string(tags, ' ')), 'A')
    || setweight(to_tsvector('english', coalesce(description, '')), 'B')
    || setweight(
         to_tsvector(
           'english',
           coalesce(provider, '') || ' ' || coalesce(model, '') || ' '
             || coalesce(service_name, '') || ' '
             || public.immutable_array_to_string(tool_names, ' ') || ' '
             || public.immutable_array_to_string(error_types, ' ')
         ),
         'C'
       )
  ) stored;

create index traces_listed_idx on public.traces (visibility)
  where visibility = 'listed';
create index traces_search_tsv_idx on public.traces using gin (search_tsv);

-- One row per consumer-trace entitlement; the $0 "purchase" object that
-- grants download access and populates the library (2_data-model.md).
create table public.acquisitions (
  id uuid primary key default gen_random_uuid(),
  consumer_id uuid not null references public.profiles (id) on delete cascade,
  trace_id uuid not null references public.traces (id) on delete cascade,
  price_usd numeric not null default 0,
  acquired_at timestamptz not null default now(),
  -- Acquiring is idempotent.
  unique (consumer_id, trace_id)
);

create index acquisitions_consumer_id_idx on public.acquisitions (consumer_id);
-- Trace deletes cascade through acquisitions by trace_id; the unique
-- (consumer_id, trace_id) index can't serve a trace-id-first lookup.
create index acquisitions_trace_id_idx on public.acquisitions (trace_id);

-- The API enforces access with the service role; RLS mirrors the rules for
-- defense in depth (2_data-model.md "Access Rules").

-- Trace/span reads widen from owner-only to owner-or-listed: inspection is
-- deliberately open for listed traces so consumers evaluate before acquiring.
drop policy "traces_select_own" on public.traces;
create policy "traces_select_visible" on public.traces
  for select to authenticated
  using ((select auth.uid()) = owner_id or visibility = 'listed');

drop policy "spans_select_own" on public.spans;
create policy "spans_select_visible" on public.spans
  for select to authenticated
  using (
    exists (
      select 1 from public.traces t
      where t.id = trace_id
        and (t.owner_id = (select auth.uid()) or t.visibility = 'listed')
    )
  );

alter table public.acquisitions enable row level security;

create policy "acquisitions_select_own" on public.acquisitions
  for select to authenticated
  using ((select auth.uid()) = consumer_id);

create policy "acquisitions_insert_own" on public.acquisitions
  for insert to authenticated
  with check (
    (select auth.uid()) = consumer_id
    and exists (
      select 1 from public.traces t
      where t.id = trace_id
        and t.visibility = 'listed'
        and t.owner_id <> (select auth.uid())
    )
  );
