# Slice 2 — Ingestion And Inspection

Spec: `docs/spec/stage-1/5_build-order.md` (Slice 2), `1_trace-format.md` (importer
mapping + validation), `2_data-model.md` (traces, spans), `3_api.md` (trace
endpoints), `4_pages.md` (/traces, /traces/[traceId]).

**Done when:** uploading the dev dataset produces inspectable traces whose span
trees, timings, errors, and attributes are fully visible and match the raw
payload.

Decisions settled in discussion before this plan (with the user):

- Hand-rolled OTLP JSON decoder, no protobuf round-trip — `ParseDict` is
  all-or-nothing and OTLP/JSON deviates from proto3 JSON mapping (hex IDs);
  span-level partial success requires our own walk.
- Idempotency via delete-and-reinsert per upload in one transaction, with a
  `TODO` marking the move to stable trace identity before trace analysis lands.
- Large traces: light span-list endpoint + per-span detail fetch + virtualized
  rendering (spec amendment below), demoed in `docs/demos/large-trace-handling.md`.
- Span tree UI: time-boxed AgentPrism spike; hard stop and discuss together if
  it doesn't drop in cleanly.
- Dev dataset: `Exgentic/agent-llm-traces` (HF, CDLA-Permissive-2.0) via a
  local convert-to-OTLP script; converted real data is never committed.

## Plan

### Spec amendment (resolve first)

`3_api.md` currently has `GET /v1/traces/{id}/spans` returning full
`attributes`/`events` for every span. For large traces that is tens of MB per
response. Amend to:

- `GET /v1/traces/{id}/spans` — light rows only (ids, name, kind, timing,
  status, provider/model/tool, token counts), paginated at 500/page. Enough to
  build the tree; excludes `attributes`/`events`.
- `GET /v1/traces/{id}/spans/{span_id}` — one span with full `attributes` and
  `events`, fetched when a span is selected.

`4_pages.md` detail-panel behavior is unchanged (full attributes still shown —
loaded per selection).

### Migration

`00000000000003_traces.sql`:

- `traces` per 2_data-model.md, excluding the Slice 3 columns (`tags`,
  `description`, `visibility`, `listed_at`, `search_tsv` arrive with
  discovery). Indexes: `traces(owner_id)`, `traces(upload_id)`.
- `spans` per 2_data-model.md, cascade delete from traces. Index
  `spans(trace_id)`.
- RLS mirrors (defense in depth, API uses service role): owner can select own
  traces/spans. Listed-visibility policies are Slice 3.

### Backend — importer (`app/importers/otlp/`)

Expand the existing `otlp.py` module into a package:

- `decode.py` — envelope walk (`resourceSpans` → `scopeSpans` → `spans`) and
  an `AnyValue` decoder (stringValue/intValue-as-string/boolValue/doubleValue/
  arrayValue/kvlistValue/bytesValue). IDs accepted as hex (OTLP spec) or
  base64 (protobuf JSON emitters). Nanosecond-string timestamps →
  `datetime`/`duration_ms`. Malformed spans are skipped and counted, never
  fatal; a payload with zero valid spans is a permanent failure.
- `mapping.py` — semconv extraction with the spec'd fallback chains:
  kind from `gen_ai.operation.name` → `openinference.span.kind` →
  `traceloop.span.kind` → `other`; provider/model from `gen_ai.provider.name`/
  `gen_ai.request.model` → OpenInference `llm.provider`/`llm.model_name` →
  legacy aliases; tokens from `gen_ai.usage.*` + legacy aliases; tool name,
  error type per 1_trace-format.md. Attribute-name constants from
  `opentelemetry-semantic-conventions` where they exist.
- `__init__.py` — keeps `matches`/`SOURCE_FORMAT`, adds
  `import_payload(payload) -> ImportResult` (list of normalized traces, each
  with spans, plus `parse_warnings`) and `IMPORTER_VERSION`.
- Grouping: spans grouped by `traceId` across all resource/scope groups — one
  marketplace trace per distinct ID. Trace rollups (name from root span,
  min/max times, status, span/error counts, dominant provider/model,
  tool_names, error_types, service_name) derived per 1_trace-format.md.
- Determinism: same payload → identical normalized output and identical
  `parse_warnings` (stable ordering, counted samples capped).

### Backend — ingest task

`worker/tasks/ingest.py` grows the real pipeline: fetch raw → verify sha →
decode/import → in one transaction: delete existing traces for the upload_id
(cascades to spans), insert traces, batch-insert spans (`executemany`,
chunked) → set `complete` + `parse_warnings` + `processed_at`.

- Decode/import failure raises `PermanentIngestError` (readable message, no
  retry — existing classification handles the rest). DB/storage errors stay
  transient.
- `TODO` at the delete-and-reinsert site: switch to stable trace identity
  (upsert on `(upload_id, source_trace_id)`) before derived analysis attaches
  to `traces.id`.
- Concurrency: correctness under `--scale worker=2` comes from the
  single-transaction rewrite + status writes being absolute; verified in
  tests.

### Backend — API

`routers/traces.py`, `schemas/trace.py` + `schemas/span.py`,
`queries/traces.py` + `queries/spans.py`:

- `GET /v1/traces` — `scope=mine` only this slice (no `q`/filters; Slice 3),
  result-card fields + `total`, `sort` + pagination per 3_api.md.
- `GET /v1/traces/{id}` — full metadata + `is_owner`/`acquired`/`can_download`
  (`acquired` always false until Slice 3, `can_download` = `is_owner`).
- `GET /v1/traces/{id}/spans` and `/spans/{span_id}` per the amendment.
- `GET /v1/traces/{id}/download` — raw payload of the owning upload, owner
  only this slice.
- Invisible traces are `404`, never `403`, per 3_api.md.
- `GET /v1/uploads/{id}` now populates `trace_ids` (query by `upload_id`).

### Web

- `lib/api/traces.ts` — types mirroring the trace/span schemas + fetchers
  (list, detail, spans pager that drains pages, span detail).
- `/traces` — table per 4_pages.md (name, created, spans, errors, duration,
  model; visibility badge is Slice 3), loading/empty/results states. Nav link.
- `/traces/[traceId]` — header/metadata section, span tree, span detail panel,
  owner download action. States: loading, not-found, error-flagged spans.
- **AgentPrism spike runs immediately after the migration** — before backend
  work, so a failed spike surfaces the fallback decision (made together) while
  there's still room to absorb it. Time-boxed ~half a day; pass criteria — works
  under React 19/Next 16, themable to DESIGN.md tokens, handles a
  multi-thousand-span trace without jank (virtualizes or tolerates it),
  detail panel can render full raw attributes. **If it fails any of these:
  stop, discuss together before building anything else.** Fallback candidates
  already identified: `@assistant-ui/react-o11y` headless primitives or a
  hand-rolled tree (~200–300 lines).
- Tree built client-side from `source_parent_span_id`; orphaned parents render
  at root level rather than disappearing.
- Upload flow: `complete` state links to created traces via `trace_ids`.

### Dev dataset + fixtures

- `tools/exgentic_to_otlp.py` — self-contained uv script (PEP 723 inline
  deps): pulls N sessions from `Exgentic/agent-llm-traces`, regroups flattened
  spans, emits proper OTLP JSON files (hex IDs, nano timestamps, AnyValue
  attribute lists) into a git-ignored `devdata/` dir. Selection includes
  small, medium, multi-thousand-span, and one over-25MB (cap-rejection) file.
  Makefile target `make dev-dataset`.
- `fixtures/` — the three committed synthetic files per 1_trace-format.md
  (multi-span agent session, failure trace with exception event, minimal
  single-span), OTel GenAI attribute names, no real data. Plus malformed-span
  variants used by golden tests.

### Tests

- Importer golden tests (unit): fixture in → expected normalized JSON out;
  edge cases — AnyValue variants, base64 IDs, missing parent IDs, malformed
  spans counted in `parse_warnings`, zero-valid-spans permanent failure,
  multi-trace files, fallback-chain precedence.
- Ingestion integration: upload fixture → poll complete → assert traces/spans
  rows match golden expectations; `trace_ids` populated; partial-success
  upload surfaces `parse_warnings`.
- Idempotency integration: fault-injected transient mid-ingest → retry →
  exactly one set of traces/spans (no duplicates).
- API integration: list/detail/spans/span-detail/download with ownership
  checks (foreign trace → 404), span pagination boundaries.

### Demo

`docs/demos/large-trace-handling.md` (first entry in the new `docs/demos/` convention):
steps to convert + upload a multi-thousand-span Exgentic trace and inspect it;
what was solved (unbounded span payloads); why it's interesting (light-list +
per-span detail + virtualization, costs stay flat with span count).

### Verification (done-when walkthrough)

1. `make dev-dataset` → upload converted Exgentic files via `/upload` →
   uploads reach `complete`, links lead to created traces.
2. `/traces` lists them with correct counts/durations/models; `/traces/[id]`
   shows the full span tree; spot-check spans against the raw JSON (timings,
   status, attributes byte-for-byte in the detail panel).
3. A failure-trace fixture shows error-flagged spans in the tree.
4. The multi-thousand-span trace inspects smoothly; the over-cap file is
   rejected with the readable 413.
5. `docker compose up --scale worker=2`, upload several files concurrently +
   fault-inject a retry → no duplicate or missing rows.
6. Integration + golden suites green; ruff/eslint/`next build` pass.

## Drift

1. **AgentPrism spike: passed with caveats** (user call: adopt, track
   alternatives in `docs/follow-up/trace-viewer-alternatives.md`). Findings:
   components are vendored via degit into `components/agent-prism/` (their
   distribution model), not an npm dep; `react-resizable-panels` pinned to v3
   (vendored code predates v4's renamed exports); their Tailwind 3 theme
   needed a generated Tailwind 4 `@theme` bridge
   (`theme/tailwind-bridge.css`); upstream `theme.css` keys off OS
   `prefers-color-scheme`, rewritten to light-only values per DESIGN.md.
   Perf: no virtualization — 3000 spans fully expanded renders (~147k DOM
   nodes) but span-selection re-render is ~1.2s in dev; ~560 visible spans
   ≈ 0.5s. Mitigation: shallow default expansion + paginated spans API;
   acceptable for the slice.
2. **"Virtualized rendering" → capped default expansion.** The plan assumed
   the tree would virtualize; AgentPrism doesn't. Shipped a breadth-first
   default-expansion cap (~300 visible spans, `span-tree.ts`) instead —
   every span stays reachable, the initial DOM stays small. Measured on a
   5,000-span trace (prod build): tree renders immediately, span-selection
   re-render ~1s. Virtualization is the noted fix in
   `docs/follow-up/trace-viewer-alternatives.md`.
3. **`PermanentIngestError` moved to `app/importers/errors.py`** (from
   `app/worker/errors.py`). The importer raising it pulled in the worker
   package, whose `__init__` imports tasks → queries → importers: a circular
   import. Importers stay worker-free; the worker imports the error from
   the importers package (dependency now points the right way).
4. **Semconv constants pinned in `mapping.py`**, not imported from
   `opentelemetry-semantic-conventions`: the gen_ai names live in that
   package's private `_incubating` module with an unstable import path.
5. **Converter is stdlib-only python3, not a PEP 723 uv script** — it only
   needs urllib + json, so the inline-deps machinery would be ceremony. It
   pulls via the HF datasets-server REST API (no parquet deps). The
   over-25MB cap-rejection file comes from `tools/make_large_trace.py`
   (which also powers the large-trace demo) rather than hunting for an
   oversized real session.
6. **Vendored `agent-prism/**` excluded from eslint** — upstream code
   trips this repo's react-hooks rules; we keep it close to upstream
   instead of patching it to satisfy our lint.

## Outcome

Done-when met: uploaded dev-dataset sessions (Exgentic via `make
dev-dataset`) and fixtures produce inspectable traces; span trees, timings,
errors, and attributes render fully and match the raw payload (browser
walkthrough on the seeded demo user, including the Attributes/RAW tabs).

Verification walkthrough results:

1. Dev dataset converts, uploads, completes; upload success links to traces. ✓
2. `/traces` lists with correct counts/durations/models; detail page renders
   tree + per-span attributes. ✓
3. `failure-trace` fixture: trace flagged error, "Error types: TimeoutError"
   in header, error dots on tree spans. ✓
4. 5,000-span trace inspects smoothly (capped expansion); 26.6MB file
   rejected with readable 413. ✓
5. `--scale worker=2` + 7 concurrent uploads incl. a `transient:2` fault:
   all complete, exactly one trace per upload, no duplicates. ✓
6. 43 backend tests green (21 importer unit + golden, 22 integration);
   ruff, eslint, tsc, and `next build` clean. ✓
