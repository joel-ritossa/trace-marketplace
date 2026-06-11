# Slice 3 Audit

Post-implementation review of discovery, listing, and acquisition, per the
`code-audit` skill. All axes walked (correctness, spec conformance,
modularity, future-proofing, security/auth, reliability invariants,
consistency). Modularity and security/auth were clean. Backend findings were
fixed in this pass; UI findings are recorded but deferred at the user's
direction.

## Bugs (fixed)

1. **Concurrent deletes of an upload's last traces orphaned the upload row**
   (`queries/traces.py`). `delete_owned` deleted the trace and counted
   survivors in the same READ COMMITTED transaction; two simultaneous deletes
   each saw the other's uncommitted delete as a survivor, both skipped the
   upload cleanup, and the result was exactly the half-dead state the spec
   amendment forbids — an uploads row with zero traces whose download still
   served unreferenced bytes. Reproduced live 8/8 against the running stack.
   Same race class the slice-2 audit fixed in ingest; the fix reuses the same
   primitive: `uploads.lock()` (select … for update) before the delete, which
   also keeps a redelivered ingest rewrite from resurrecting a deleted trace.
   Regression test: `test_simultaneous_deletes_still_clean_up_upload`.
   Re-verified live: 0/8 after the fix.
2. **`PATCH` with explicit `null` for `visibility` or `tags` returned a raw
   500** (`routers/traces.py`) — not even the error envelope.
   `model_fields_set` counted the field as provided, so the empty-body guard
   passed, but `update_owned` treats `None` as "not provided" and built
   `update traces set  where …`. Neither field is semantically nullable
   (explicit-null-to-clear is description-only), so provided-but-null now
   returns `422 invalid_request`. Verified live before (500) and after (422).

## Validation / future-proofing (fixed)

- **Tags had no per-item bound** (`schemas/trace.py`). 20 items max, but each
  item was unbounded — a 2 MB tag was accepted live (200), stored, and shipped
  back on every result card, while Postgres silently dropped the >2 KB lexeme
  from `search_tsv` so it didn't even search. Tags are now
  `strip_whitespace, min_length=1, max_length=80`, which also rejects the
  empty/whitespace tags the API previously stored as blank pills.
- **No index on `acquisitions(trace_id)`** — every trace delete cascades
  through acquisitions by trace_id, and the unique `(consumer_id, trace_id)`
  index can't serve a trace-id-first lookup. Index added to the (uncommitted)
  migration and applied to the live DB; the spec's index list updated to
  match reality (including the slice-2 `spans(trace_id, started_at)` swap it
  had drifted from).

## Nits (fixed)

- `POST /v1/traces/{id}/acquire` OpenAPI only documented 200; the
  201-on-create was set imperatively. Now declared via `responses`, per the
  "OpenAPI is the contract" convention.

## Deferred — UI findings (user will address separately)

- `4_pages.md` lists a `tool` filter for the marketplace; the API and types
  support it but `trace-filters.tsx` renders no input for it.
- Cross-cutting badge rule says every trace rendering carries a
  visibility badge; `trace-cards.tsx` renders it only for owner cards.
- Detail-page provenance omits the spec'd upload link.
- Download failures in `trace-cards.tsx`/`trace-inspector.tsx` show a generic
  message instead of the API's reason (violates the no-generic-shrug rule);
  `trace-actions.tsx` does it right.
- List pages double-fetch on mount (`useTraceList` fires immediately, the
  filter bar's debounce fires again at 300 ms with an identical query).
- Clicking "List on marketplace" with unsaved tag/description edits silently
  discards them.

## Observation (no action)

Ingest's delete-and-rewrite mints new trace IDs, which would wipe listings
and cascade acquisitions if a rewrite ever ran post-listing. Unreachable
today (`mark_processing` drops stale deliveries; requeue requires `failed`),
and the existing `TODO(trace-analysis)` in `ingest.py` covers the
stable-identity fix — revisit when Stage 2 attaches derived data to traces.

## Outcome

Verified against the rebuilt Compose stack on 2026-06-11:

- 89 backend tests green (1 new: the concurrent-delete race; extended PATCH
  validation cases for nulls and tag bounds).
- Both live reproductions re-run against the rebuilt stack: PATCH nulls now
  422, delete race 0/8 (was 8/8).
- `ruff check`/`format` clean; `make smoke` passes end to end.
- `acquisitions_trace_id_idx` in place on the live DB.
