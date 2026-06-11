-- Owner-scoped trace identity (A6 amendment, 8_session-ingestion.md).
--
-- Session logs grow: re-syncing one produces a new upload whose turns are
-- the same logical traces (deterministic per-turn ids). Identity therefore
-- moves from (upload_id, source_trace_id) to (owner_id, source_trace_id):
-- the ingest upsert adopts the row into the newest upload, so a re-sync
-- updates existing turns in place and appends new ones — never duplicates.
-- One rule for every format: an OTLP re-upload carrying the same trace id
-- updates that trace too.

-- Existing duplicates keep the newest row (latest content wins); spans and
-- derived rows cascade with the losers.
delete from public.traces t
using public.traces newer
where newer.owner_id = t.owner_id
  and newer.source_trace_id = t.source_trace_id
  and (newer.created_at, newer.id) > (t.created_at, t.id);

alter table public.traces
  drop constraint traces_upload_source_trace_key,
  add constraint traces_owner_source_trace_key unique (owner_id, source_trace_id);
