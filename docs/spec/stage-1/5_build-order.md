# Build Order

Stage 1 is built as four slices. Each slice ends runnable and demoable; later slices never require reworking earlier ones, only extending them. Implementation of a slice should need no decisions beyond this spec.

## Slice 0 — Walking Skeleton

Stack glue with zero product logic.

- Monorepo scaffold per decision 003: `apps/web`, `services/api`, `supabase/`.
- Local Supabase stack running (Postgres, auth, storage); first migration creates `profiles` with RLS.
- Next.js app with Supabase auth: sign up, sign in, sign out, session-gated layout.
- FastAPI app verifying Supabase JWTs; `GET /v1/health`; one authenticated round-trip endpoint the web app calls and renders.
- Redis container; taskiq worker as a separate Compose service running one trivial `ping` task enqueued by an API endpoint, proving API → Redis → worker → Postgres end to end.
- Docker Compose runs web + API + Redis + worker against local Supabase.

**Done when:** a fresh clone can sign up, sign in, and see an authenticated page that round-trips through FastAPI; a test task enqueued by the API is executed by the worker.

## Slice 1 — Raw Upload Loop

The smallest contributor loop. No parsing.

- `uploads` + `dead_letters` tables + `raw-traces` bucket + migration.
- `POST /v1/uploads` with validation (size, JSON parse, duplicate hash); enqueues `ingest_upload`, which for now just marks the upload `complete` after raw preservation — no trace records yet.
- Reliability skeleton per 6_architecture.md, proven on this trivial job: permanent-vs-transient error classification, retries with backoff, dead-letter on exhaustion, stuck-upload sweep, idempotent re-runs.
- Rate-limit middleware (global + per-user token buckets on Redis), tight bucket on uploads.
- `GET /v1/uploads/{id}`, owner-only.
- `/upload` page with real status states; a minimal uploads list; raw download of own uploads.

**Done when:** upload a fixture file, see it stored and listed, download the identical bytes back; duplicates and invalid files are rejected with readable reasons; a fault-injected transient failure retries to success, and an exhausted job lands in `dead_letters` with the upload marked `failed`.

## Slice 2 — Ingestion And Inspection

The data-foundation core. Built against the provided dev dataset.

- `traces` + `spans` tables and migrations.
- OTLP JSON importer per 1_trace-format.md, run inside the `ingest_upload` job; upload status now reflects parsing (`processing`, `parse_warnings`, `failed`). Parse errors are permanent failures (no retry); span inserts are batched.
- `docker compose up --scale worker=2` processes concurrent uploads correctly (idempotency holds under retry).
- `GET /v1/traces` (`scope=mine`, no search yet), `GET /v1/traces/{id}`, `GET /v1/traces/{id}/spans`, `GET /v1/traces/{id}/download`.
- `/traces` library page and the full `/traces/[traceId]` inspection page: complete span tree, span detail panel with raw attributes and events.
- Importer golden tests against fixtures; ingestion integration test (upload → normalized rows).

**Done when:** uploading the dev dataset produces inspectable traces whose span trees, timings, errors, and attributes are fully visible and match the raw payload.

## Slice 3 — Discovery, Listing, And Acquisition

The consumer side.

- `visibility`, `tags`, `description`, `search_tsv` on traces; `acquisitions` table; listed-visibility and acquisition RLS/API rules.
- `PATCH /v1/traces/{id}` with ownership confirmation; `DELETE`; `POST /v1/traces/{id}/acquire`.
- Search and filters on `GET /v1/traces`; `scope=marketplace` and `scope=acquired`; download gated on owner-or-acquired.
- `/marketplace` and `/library` pages; visibility/tag/description controls, acquire and download actions on the detail page; visibility badges everywhere.
- Seed script loading fixtures as a demo contributor; smoke script exercising the full demo script in 0_README.md.

**Done when:** the README demo script passes end to end on a fresh local run: upload → inspect → list → search from another account → inspect → acquire → download from library.

## After Slice 3

Stage 1 is complete. Stage 2 candidates (enrichment/failure-mode analysis, API access, privacy/redaction, more importers) get their own spec before any code.
