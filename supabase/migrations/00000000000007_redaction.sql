-- Stage 2 A5: redaction at ingestion. Per docs/spec/stage-2/7_redaction.md
-- and 2_data-model.md (span_raw, uploads deltas).

-- Owner-only raw copies of the scrubbed span content fields. `spans` itself
-- is scrubbed-by-default; this table is the only place original values exist
-- in Postgres. Written in the same ingestion transaction as `spans`.
create table public.span_raw (
  span_id uuid primary key references public.spans (id) on delete cascade,
  attributes jsonb not null default '{}',
  events jsonb not null default '[]',
  status_message text
);

-- Owner of the referenced trace only — deliberately no listed-visibility
-- policy, ever (2_data-model.md "Access Rules").
alter table public.span_raw enable row level security;

create policy "span_raw_select_own" on public.span_raw
  for select to authenticated
  using (
    exists (
      select 1
      from public.spans s
      join public.traces t on t.id = s.trace_id
      where s.id = span_id and t.owner_id = (select auth.uid())
    )
  );

-- Keys the deterministic placeholder HMAC; minted in Python at upload
-- creation. The default here backfills pre-A5 rows (their salt first applies
-- on re-ingest) and is dropped so application code stays the one mint path.
alter table public.uploads
  add column redaction_salt text not null
    default encode(sha256(uuid_send(gen_random_uuid())), 'hex'),
  add column redaction_version text,
  add column redaction_counts jsonb;

alter table public.uploads alter column redaction_salt drop default;
