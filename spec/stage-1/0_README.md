# Stage 1 Spec

This directory is the normative spec for Stage 1: the foundational platform. Every statement here is "the system does X." Background and rationale live in `.archive/planning_docs/` (historical, non-normative); if this spec and a planning doc disagree, this spec wins.

Stage 1 is complete when one person, running the app locally, can exercise the full demo script below with no operator help. Stage 2 (drilling into one interesting aspect, e.g. failure-mode analysis, enrichment, or API access) is intentionally undefined until Stage 1 ships.

## Stage 1 In One Sentence

Contributors upload agent traces that are validated, preserved raw, and normalized; consumers discover listed traces by search, inspect them, acquire them into their library at no cost, and download them through the web app.

## Demo Script

This is the literal click-through that defines done:

1. Sign up / sign in (Supabase auth, email-based; one account type — every user can both contribute and consume).
2. Open **Upload**, submit an OTLP JSON trace file (or a provided fixture).
3. See validation result and ingestion status: `received → processing → complete` (or `failed` with a readable reason).
4. Open the trace from **My Traces**: see metadata (model, provider, tools, span count, errors, duration) and the full span tree — every span expandable to its timings, status, attributes, and events.
5. Flip the trace from `private` to `listed`, confirming the "this data is yours to share" checkbox.
6. (As a consumer — same or different account) open **Marketplace**, search by keyword, filter by source format / has-errors / date.
7. Open a listed trace's detail page, inspect its metadata and span tree.
8. Click **Acquire** — the trace is added to **My Library** (a $0 acquisition; no payment flow).
9. From the trace page or My Library, click **Download** and receive the original raw uploaded payload.

## Scope: In

- Supabase auth, single user type, lightweight profile.
- File upload (single JSON file per upload) with validation: size limit, JSON parse, format detection, duplicate hash check.
- Raw payload preserved verbatim in Supabase Storage, keyed by content hash.
- One importer: OTLP JSON (which transparently covers OTel GenAI, OpenInference, OpenLLMetry, Langfuse-OTLP, Phoenix payloads). One synthetic fixture format ships in `fixtures/`.
- Normalization into a canonical trace + spans shape (see [1_trace-format.md](1_trace-format.md)).
- Ingestion runs async: the API enqueues a job on Redis (taskiq); a separate worker process consumes it. Retries with backoff for transient failures, a dead-letter table for exhausted ones, horizontal worker scaling via Compose. See [6_architecture.md](6_architecture.md).
- Global + per-user rate limiting on the API (Redis token bucket), tighter on uploads.
- Two visibility states: `private` (default) and `listed`.
- Search: Postgres full-text over safe metadata (trace name, model, provider, tool names, error types, tags) plus structured filters. Raw prompt/output text is never indexed.
- Trace detail page with full span inspection: complete span tree with per-span detail (timings, status, kind, model/tool info, raw attributes, events). This is a first-class Stage 1 surface, not a thin preview.
- Acquisitions (entitlements): a consumer acquires a listed trace at $0, adding it to their library. Acquisition is its own object — no pricing, payment, or exchange logic.
- Download of the original raw payload for traces the user owns or has acquired.
- Docker Compose local run, seed fixtures, smoke script.

## Scope: Deferred to Stage 2+

Explicitly out, even if planning docs discuss them:

- **Payments and pricing on acquisitions.** Acquisitions exist but are always $0; checkout, pricing, and licensing come later.
- **Trace sets / bundles as marketplace objects.** Listing and acquisition are per-trace in Stage 1. Traces uploaded together already share an `upload_id`, so arrival grouping is preserved; named, priced, or generated sets (including curated/derived bundles that cut across uploads) are a Stage 2 candidate.
- **API-key / programmatic download.** Web app only.
- **Privacy subsystem.** No secret detection, redaction pipeline, or safe-preview generation. Listing requires an explicit contributor confirmation instead.
- **`shared` visibility state.** Only `private` and `listed`.
- **Enrichment.** No summaries, failure-mode labels, quality/value signals, eval scores, or annotations.
- **Additional importers.** No OpenInference-native, Langfuse-export, or generic-JSON adapters. The importer interface leaves room for them.
- **Per-trace job fan-out, autoscaling, circuit breakers.** One job per upload; the queue exists, but advanced parallelism waits for evidence it's needed.
- **Artifacts, annotations, audit_events, search_documents tables.** Span payloads stay inline; search is a `tsvector` column.
- **Payments, licensing, orgs, moderation, admin roles.**
- **Generated OpenAPI TS client CI checks and Playwright e2e.** A shell smoke script covers the demo path.

## Spec Documents

| Doc | Defines |
|---|---|
| [1_trace-format.md](1_trace-format.md) | Accepted input format, canonical normalized shape, fixture format. |
| [2_data-model.md](2_data-model.md) | Tables, columns, storage layout, access rules. |
| [3_api.md](3_api.md) | Endpoints and request/response shapes. |
| [4_pages.md](4_pages.md) | Routes, page responsibilities, required UI states. |
| [5_build-order.md](5_build-order.md) | Implementation slices 0–3 with done criteria. |
| [6_architecture.md](6_architecture.md) | Runtime topology, job lifecycle, retry/DLQ rules, rate limiting, scaling knobs. |

## Decisions Embedded In This Spec

These were open questions during planning (now archived in `.archive/planning_docs/`); this spec resolves them for Stage 1:

| Question | Resolution |
|---|---|
| First trace format | OTLP JSON (`ExportTraceServiceRequest` shape) with GenAI/OpenInference attribute mapping. |
| Raw storage | Supabase Storage bucket, path keyed by SHA-256. |
| Worker vs inline | Queue + dedicated worker from the start: Redis broker (taskiq), retries with backoff, dead-letter table, `--scale worker=N`. |
| Broker | Redis over RabbitMQ/Postgres-queue: one container that also backs rate limiting; job state of record stays in Postgres (`uploads.status`). |
| Identity | Supabase auth, one user type. |
| Raw text in search | Excluded. Metadata only. |
| Private by default | Yes; explicit opt-in to `listed`. |
| Consumer access model | Listed traces are fully inspectable by any signed-in user; download requires owning or acquiring the trace. |
| Trace sets | Deferred to Stage 2; `upload_id` preserves arrival grouping in the meantime. |
| Infra dependencies | Supabase (Postgres + auth + storage) via local Supabase stack, plus Redis (queue broker + rate limiting). |
