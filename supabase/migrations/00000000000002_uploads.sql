create table public.uploads (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  filename text not null,
  size_bytes bigint not null,
  sha256 text not null,
  storage_path text not null,
  source_format text not null,
  status text not null default 'received'
    check (status in ('received', 'processing', 'complete', 'failed')),
  error_message text,
  attempts integer not null default 0,
  parse_warnings jsonb,
  created_at timestamptz not null default now(),
  -- Set each time a worker claims the job; the stuck-upload sweep keys off
  -- this so a long-running attempt isn't re-enqueued every sweep tick.
  last_attempt_at timestamptz,
  processed_at timestamptz,
  unique (owner_id, sha256)
);

create index uploads_owner_id_idx on public.uploads (owner_id);

-- The API enforces access with the service role; RLS mirrors the rules for
-- defense in depth (2_data-model.md "Access Rules").
alter table public.uploads enable row level security;

create policy "uploads_select_own" on public.uploads
  for select using ((select auth.uid()) = owner_id);

-- Ingestion DLQ. Operator-only surface: RLS enabled with no policies, so only
-- the service role (API/worker) and SQL access can touch it.
create table public.dead_letters (
  id uuid primary key default gen_random_uuid(),
  upload_id uuid not null references public.uploads (id) on delete cascade,
  task_name text not null,
  attempts integer not null,
  last_error text not null,
  error_context jsonb,
  failed_at timestamptz not null default now(),
  requeued_at timestamptz
);

create index dead_letters_upload_id_idx on public.dead_letters (upload_id);

alter table public.dead_letters enable row level security;

-- Private bucket for raw payloads; objects served only through the API.
insert into storage.buckets (id, name, public)
values ('raw-traces', 'raw-traces', false)
on conflict (id) do nothing;
