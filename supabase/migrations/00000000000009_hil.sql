-- Stage 2 A3: the HIL loop. notifications + review_items per
-- docs/spec/stage-2/2_data-model.md and the A3 buildlog decisions
-- (digest-upsert index, realtime invalidation).

create table public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  -- review_request | subscription_match | upload_failed; app-validated text
  -- (new types are additive, no check constraint).
  type text not null,
  -- Type-specific, always enough to build the link target (2_data-model.md).
  payload jsonb not null,
  created_at timestamptz not null default now(),
  read_at timestamptz
);

create index notifications_user_created_idx
  on public.notifications (user_id, created_at desc);

create index notifications_user_unread_idx
  on public.notifications (user_id) where read_at is null;

-- Digest-upsert target (A3 decision 4): at most one unread review_request
-- digest per (user, upload); routed items increment its item_count. A read
-- digest leaves the slot free, so the next item starts a fresh unread one.
create unique index notifications_review_digest_key
  on public.notifications (user_id, ((payload ->> 'upload_id')))
  where type = 'review_request' and read_at is null;

create table public.review_items (
  id uuid primary key default gen_random_uuid(),
  trace_id uuid not null references public.traces (id) on delete cascade,
  -- 'verdict' in stage 2; the label model lives in the jsonb payloads so it
  -- can change without migration churn (2_data-model.md).
  question_type text not null default 'verdict',
  -- Machine verdict + per-field confidence + routing reasons in plain
  -- language. Empty reasons = owner-initiated relabel.
  context jsonb not null,
  -- Null until resolved; partial answers allowed.
  answer jsonb,
  status text not null default 'open'
    check (status in ('open', 'resolved', 'superseded')),
  created_at timestamptz not null default now(),
  resolved_at timestamptz,
  resolved_by uuid references public.profiles (id)
);

-- Supersede, never duplicate: at most one open item per trace.
create unique index review_items_one_open_key
  on public.review_items (trace_id) where status = 'open';

create index review_items_trace_id_idx on public.review_items (trace_id);

-- The queue lists open items oldest-first.
create index review_items_open_created_idx
  on public.review_items (created_at) where status = 'open';

-- The API enforces access with the service role; RLS mirrors the rules for
-- defense in depth (stage-1 rule). Read-only for clients — notifications and
-- review items are generated server-side only; mark-read and resolve go
-- through the API.
alter table public.notifications enable row level security;

create policy "notifications_select_own" on public.notifications
  for select to authenticated
  using (user_id = (select auth.uid()));

alter table public.review_items enable row level security;

create policy "review_items_select_trace_owner" on public.review_items
  for select to authenticated
  using (
    exists (
      select 1 from public.traces t
      where t.id = trace_id and t.owner_id = (select auth.uid())
    )
  );

-- Bell + /notifications realtime invalidation (4_pages.md Cross-Cutting).
-- postgres_changes delivery is RLS-checked against the subscriber, so the
-- recipient-only select policy already scopes events.
alter publication supabase_realtime add table public.notifications;
