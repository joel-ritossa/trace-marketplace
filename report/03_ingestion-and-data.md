# Ingestion & Data

Trace data enters through three doors — web upload, sync CLI, desktop tray app — into one pipeline: the raw bytes are preserved verbatim, and everything else (trace/span rows, names, token counts, the scrubbed copy) is derived from them by a worker, deterministically and re-runnably.

## Trace Format

OTLP JSON (the JSON encoding of `ExportTraceServiceRequest`) is the canonical format: OTel GenAI, OpenInference, OpenLLMetry, Langfuse's OTLP path, and Phoenix all emit or pass through this envelope, so one importer accepts the widest set of real agent tooling ([spec](../docs/spec/stage-1/1_trace-format.md)). Each distinct `trace_id` in a file becomes one marketplace trace; spans keep their full raw `attributes` and `events` as JSONB — nothing is dropped.

Raw coding-agent session logs are also accepted directly: Codex, Claude Code, and Cursor JSONL upload as-is, and the server detects the schema and converts each session into per-turn OTLP traces before the one shared normalize path ([spec](../docs/spec/stage-2/8_session-ingestion.md), `services/api/app/importers/sessions/`). One turn — a user message plus all assistant activity until the next — becomes one trace, with a deterministic id (`sha256(source:session_id:turn_index)`), so re-uploading a session that grew produces only the new turns. Conversion preserves what the logs actually contain: grouped multi-record assistant responses, cache-aware token accounting, reasoning text, generically-paired tool calls; the golden corpus in `fixtures/golden/` pins these shapes against real harness logs. Undetectable bytes reject at POST with `422 unsupported_format`.

## Upload Paths

### Web Upload

Drag a file onto `/uploads`. Validation happens at POST (`services/api/app/routers/uploads.py`): 25 MB size limit (env-tunable), format sniff, and per-user sha256 dedupe (`409 duplicate_upload`, linking the existing upload). Accepted uploads return 201 with status `received` and proceed `received → processing → complete | failed`; the `/uploads` page updates live (Supabase Realtime as an invalidation signal — events trigger an API refetch, the socket is never a second data path). Failures show the ingestion error verbatim; partially malformed payloads complete with skipped-span counts in `parse_warnings`.

### Sync CLI

`trace-sync sync <paths>` walks directories and uploads every new `*.json`/`*.jsonl` file; `watch` is the same loop without the exit condition ([spec](../docs/spec/stage-2/5_cli.md), [demo](../docs/demos/cli-sync.md)). Design choices that matter:

- **Stateless.** No local manifest or config; the server's per-user content hash is the source of truth, so re-syncing any directory from any machine is idempotent — duplicates print `already synced`.
- **Upload-only API keys.** Minted in `/settings`, plaintext shown exactly once, sha256-stored, scoped to exactly two endpoints, soft-revoked. `uploads.source = 'cli'` is inferred from the auth type — clients never claim it.
- **Pipelined.** All files POST first, then the CLI polls the in-flight set as server-side ingestion completes — N files cost N quick uploads plus concurrent ingestion, not N sequential waits. Rate-limit `Retry-After` is honored, not treated as an error.
- **Failures stay visible when nobody is watching.** One bad file never stops the run; exit codes distinguish all-clean (0), some-failed (1), couldn't-run (2); failed CLI uploads surface on `/uploads` and emit an `upload_failed` notification (web failures fail in front of the user, so only CLI uploads notify).

### Desktop App

A Tauri tray app wrapping the same loop for people who don't live in a terminal (`apps/desktop/README.md`): on first run it auto-adds whichever harness session dirs exist (`~/.codex/sessions`, `~/.claude/projects`, `~/.cursor/projects`) and watches them with the CLI's stability debounce, defaulting to files modified in the last 24 h so a first watch doesn't bulk-upload months of history. It signs in with the marketplace account (no API key), remembers synced files per server + account, fires native notifications for review requests, and resolves review items in-app with the same semantics as the web's review page. The sync engine is a TS port of the CLI's modules with "keep in sync" headers pointing at the source of truth.

## Ingestion Pipeline

The order of operations is the guarantee. At POST, the raw object is written to storage (content-hash keyed, never mutated), the `uploads` row commits, and only then is `ingest_upload` enqueued — once a client has a 201, the upload is durable ([explainer](../docs/explainers/trace-upload-delivery-guarantee.md)).

The worker (`services/api/app/worker/tasks/ingest.py`) then treats ingestion as a pure function of the stored payload:

- It re-fetches the raw bytes, verifies the recorded checksum, and re-detects the format from the bytes (not the row) — so the result depends on nothing but the payload.
- Session JSONL converts to per-turn OTLP first; both formats share one normalize path (`app/importers/otlp/`).
- Trace rows are upserted keyed on `(owner_id, source_trace_id)`, spans deleted and re-inserted per trace, traces absent from the payload dropped — all in one transaction with the status flip. Re-running any state converges to identical rows, and `traces.id` survives both re-ingest and re-upload of the same logical trace, so acquisitions, labels, and review items never cascade away.
- Derivations ride along: trace names come from the root span (falling back to the source filename when the derived name is empty or a bare id — names must stay scannable at list volume), and `total_tokens` sums span-level usage.
- Redaction happens inside this same pass — span content is scrubbed before it lands in `spans`, originals go to the owner-only `span_raw` table, and a scrubbed payload artifact is written for non-owner downloads (details in [06](06_privacy-and-redaction.md)).
- Analysis is kicked per trace after commit, so every (re)ingest gets labels consistent with the rewritten content (see [04](04_analysis-pipeline.md)).

## Reliability

Delivery is at-least-once with an idempotent consumer; Postgres, not Redis, is the source of truth. The full mechanism is in the [delivery-guarantee explainer](../docs/explainers/trace-upload-delivery-guarantee.md); the shape:

- **Typed error classification.** `PermanentIngestError` (checksum mismatch, unsupported schema, zero-turn session) fails immediately with a readable reason — no retries. Everything else is transient and retries up to `INGEST_MAX_ATTEMPTS` (default 5) with exponential backoff + jitter.
- **Dead letters in Postgres.** Exhausted retries write a `dead_letters` row (final error, per-attempt timing, no payload content) and mark the upload `failed` — durable and inspectable with SQL, never limbo. Recovery is one command: `make requeue UPLOAD=<id>`.
- **The sweep is the guarantee, not the queue.** The Redis broker has no acks; a crash can lose an in-flight message. Every 60 s the scheduler re-enqueues uploads stuck in `received`/`processing` past `SWEEP_STUCK_AFTER_MINUTES` (default 10) — a lost message costs at most ~11 minutes of delay, never the upload. Idempotent ingestion makes the resulting double-deliveries harmless.
- **Demoable on purpose.** With `DEV_ROUTES=true`, an `X-Fault` header on upload (`transient:N`, `exhaust`, `permanent`) trips the retry, dead-letter, and immediate-fail paths on demand (`services/api/app/dev/faults.py`); `tests/integration/test_reliability.py` exercises them against the real stack.

A 5,000-span trace uploads, ingests, and inspects without falling over — payload cost scales with what the user looks at, not trace size ([demo](../docs/demos/large-trace-handling.md), with measured limits).

## Data Model

The ingestion side is four tables: `uploads` (one per submitted file; status is the state of record), `traces` (one per source trace id, many per upload), `spans` (scrubbed attributes/events as JSONB), and `span_raw` (owner-only originals). `dead_letters` is the audit trail; analysis and marketplace tables hang off `traces` and are covered in [04](04_analysis-pipeline.md) and [05](05_marketplace.md). Every access rule is enforced twice — in the API query and as an RLS policy. Full column-level detail: [stage-1](../docs/spec/stage-1/2_data-model.md) and [stage-2](../docs/spec/stage-2/2_data-model.md) data-model specs.
