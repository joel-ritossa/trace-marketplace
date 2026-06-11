-- Deployment guard: only allowlisted emails may sign up. An entry is either a
-- full email ('user@example.com') or a whole domain ('@example.com'). The same
-- table backs the API's per-request check (app/auth.py), which covers sign-in
-- for already-created users. Manage entries with `make allow EMAIL=...`.

create table public.allowed_emails (
  entry text primary key check (entry = lower(entry) and position('@' in entry) > 0),
  created_at timestamptz not null default now()
);

-- Service-role only: RLS enabled with no policies, so anon/authenticated
-- clients can neither read nor probe the allowlist.
alter table public.allowed_emails enable row level security;

create or replace function public.enforce_email_allowlist()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.email is null or not exists (
    select 1 from public.allowed_emails
    where entry = lower(new.email)
       or entry = '@' || split_part(lower(new.email), '@', 2)
  ) then
    -- GoTrue surfaces this as "Database error saving new user"; the web
    -- sign-up form maps that to an allowlist message.
    raise exception 'email_not_allowed';
  end if;
  return new;
end;
$$;

create trigger enforce_email_allowlist
  before insert on auth.users
  for each row execute function public.enforce_email_allowlist();
