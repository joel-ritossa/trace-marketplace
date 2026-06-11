-- Stage 2 A4: subscriptions + the first-match ledger per
-- docs/spec/stage-2/2_data-model.md and the A4 buildlog decisions
-- (digest-upsert index, last_seen_at default).

create table public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  name text not null,
  -- The stored filter map: the GET /v1/traces param vocabulary minus
  -- scope/sort/pagination (3_api.md). Validated at write time against the
  -- same model the API parses, so it can never fail to execute later.
  query jsonb not null,
  created_at timestamptz not null default now(),
  -- Backs the feed's new-since-last-seen marker (A4 decision 10): defaults
  -- to creation so backfill is never "new".
  last_seen_at timestamptz not null default now()
);

create index subscriptions_owner_idx on public.subscriptions (owner_id);

-- First-match records, for notification dedupe only (2_data-model.md): a
-- trace notifies a subscription at most once, ever, regardless of how many
-- trigger events re-match it.
create table public.subscription_matches (
  id uuid primary key default gen_random_uuid(),
  subscription_id uuid not null references public.subscriptions (id) on delete cascade,
  trace_id uuid not null references public.traces (id) on delete cascade,
  matched_at timestamptz not null default now(),
  unique (subscription_id, trace_id)
);

-- The feed's new-since-last-seen probe joins by trace.
create index subscription_matches_trace_idx
  on public.subscription_matches (trace_id);

-- Digest-upsert target (A4 decision 9, mirroring A3's review digest): at
-- most one unread subscription_match digest per (user, subscription); new
-- matches increment its match_count. A read digest leaves the slot free.
create unique index notifications_subscription_digest_key
  on public.notifications (user_id, ((payload ->> 'subscription_id')))
  where type = 'subscription_match' and read_at is null;

-- The API enforces access with the service role; RLS mirrors the rules for
-- defense in depth (stage-1 rule). Read-only for clients — all writes go
-- through the API/worker.
alter table public.subscriptions enable row level security;

create policy "subscriptions_select_own" on public.subscriptions
  for select to authenticated
  using (owner_id = (select auth.uid()));

alter table public.subscription_matches enable row level security;

create policy "subscription_matches_select_own" on public.subscription_matches
  for select to authenticated
  using (
    exists (
      select 1 from public.subscriptions s
      where s.id = subscription_id and s.owner_id = (select auth.uid())
    )
  );
