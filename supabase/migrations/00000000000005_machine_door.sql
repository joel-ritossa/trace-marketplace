-- Stage 2 A1: API keys, upload source, private-trace LLM-analysis opt-out,
-- realtime invalidation. Per docs/spec/stage-2/2_data-model.md (api_keys,
-- Stage-1 Deltas) and 4_pages.md Cross-Cutting (realtime).

create table public.api_keys (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  name text not null,
  -- SHA-256 hex of the full key; plaintext is shown once at mint and never
  -- stored, so "never readable after mint" is structural.
  key_hash text not null,
  -- Prefix + last 4 (e.g. tmk_ab…f3k9) for list rendering.
  key_display text not null,
  -- 'upload' is the only stage-2 scope; no check constraint so new scopes
  -- stay additive (app-validated, like taxonomy fields).
  scope text not null default 'upload',
  created_at timestamptz not null default now(),
  last_used_at timestamptz,
  -- Soft revoke: revoked keys fail auth but the row remains for history.
  revoked_at timestamptz
);

create unique index api_keys_key_hash_idx on public.api_keys (key_hash);
create index api_keys_owner_id_idx on public.api_keys (owner_id);

-- The API enforces access with the service role; RLS mirrors the rules for
-- defense in depth (2_data-model.md "Access Rules": owner only, all ops).
alter table public.api_keys enable row level security;

create policy "api_keys_select_own" on public.api_keys
  for select to authenticated
  using ((select auth.uid()) = owner_id);

create policy "api_keys_insert_own" on public.api_keys
  for insert to authenticated
  with check ((select auth.uid()) = owner_id);

create policy "api_keys_update_own" on public.api_keys
  for update to authenticated
  using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id);

-- Set by the API from auth type (API key -> 'cli'); clients never set it.
alter table public.uploads
  add column source text not null default 'web'
    check (source in ('cli', 'web'));

-- Per-account opt-out of LLM analysis for private traces (default on).
-- Covered by the existing owner-only profiles update policy.
alter table public.profiles
  add column allow_private_llm_analysis boolean not null default true;

-- Realtime invalidation signal for /uploads (4_pages.md Cross-Cutting).
-- postgres_changes delivery is RLS-checked against the subscriber, so the
-- owner-only select policy already scopes events to the row owner.
alter publication supabase_realtime add table public.uploads;
