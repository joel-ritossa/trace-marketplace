# Slice 1 — Modularity Restructure

Follow-up to the [audit](001_audit.md): a dedicated modularity pass before
Slice 2. Convention: dedicated files within domain dirs instead of growing
bucket modules. No behavior changes; all moves verified by the full
integration suite.

## Backend

- `app/worker/tasks.py` → `app/worker/tasks/` package: `ping.py`, `ingest.py`,
  `sweep.py`. The package `__init__.py` imports each module (registers tasks on
  the broker for the `taskiq worker app.worker:broker` entrypoint) and
  re-exports them, so call sites keep importing from `app.worker.tasks`.
  - Note: taskiq canonical task names changed
    (`app.worker.tasks:ingest_upload` → `app.worker.tasks.ingest:ingest_upload`).
    Only affects in-flight Redis messages at deploy time; irrelevant locally.
- `app/worker/middleware.py` → `app/worker/retry_dlq.py`: bucket name held one
  thing; now matches the HTTP side's `middleware/rate_limit.py` naming.
- `app/clients/` groups the process-lifetime external clients: `db.py`,
  `redis.py`, `storage.py` (identical open/close/accessor lifecycle pattern).
- `app/dev/` groups dev-only tooling, starting with `faults.py` (fault
  injection); future demo/debug helpers land here.
- `app/importers/` created with `otlp.py`. **Decision: each Slice 2+ importer
  is a dedicated module here, pure (bytes/JSON in, rows out), owning all
  format-specific knowledge.** The upload router's format sniff and the
  `otlp_json` source-format constant moved in now; `ingest_upload` stays a
  thin orchestrator.

## Frontend

- `lib/api/types.ts` (single type bucket) dissolved into per-domain modules
  that mirror the backend's `schemas/` one-file-per-domain layout:
  - upload types → `lib/api/uploads.ts` (with the upload functions)
  - `Me` → `lib/api/me.ts`
  - `ApiErrorBody` → `lib/api/client.ts` (next to `ApiError`)
- `components/auth/` (`auth-form`, `sign-out-button`) and `components/shell/`
  (`nav-links`) follow the dir-per-domain convention `components/uploads/` set.
  Slices 2–3 add `traces/` and `marketplace/` the same way.
- `FlowStatus` extracted from `upload-flow.tsx` into
  `components/uploads/flow-status.tsx` (type-only import of `Flow` back from
  the orchestrator, no runtime cycle).

## Considered and rejected

- Service layer between routers and queries — over-engineering at this scale;
  routers stay thin and call queries directly. Revisit if a router's
  validation half keeps growing in Slice 2.
- Splitting upload validation out of `routers/uploads.py` — at the threshold,
  not over it; the format sniff (the part with a real home) moved to
  `importers/`.

## Verification

- `ruff check` + `ruff format` clean; `tsc --noEmit` + `eslint` clean.
- Worker and scheduler boot with the new task names; sweep fires.
- Full integration suite (14 tests) green against rebuilt containers,
  including the dead-letter test updated for the new canonical task name.
