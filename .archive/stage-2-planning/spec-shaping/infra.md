# Stage 2 Infra

The infrastructure components of stage 2, discussed and settled at spec-shaping level. None of this depends on the judging/analysis discussion; where a component touches analysis, only the *plumbing* is defined here and the content is a placeholder. Promote into `spec/stage-2/` once judging is settled.

## 1. Sync CLI

Lives in `apps/cli`, Python + uv (same toolchain as `services/api`).

- **Commands:** `sync <paths...>` — walk paths, upload new trace files, exit. `watch <paths...>` — same loop, stays alive on filesystem changes. Watch is base scope, not an extension. One code path; watch just changes the exit condition.
- **Stateless.** No local manifest. Stage-1 per-user sha256 dedupe makes re-sync idempotent: `409 duplicate_upload` → skip, print "already synced". Server is the source of truth.
- **Status feedback.** After each upload, poll `GET /v1/uploads/{id}` briefly and print the terminal result (`complete, 3 traces` / `failed: <reason>`).
- **Rate-limit aware.** First sync of a big directory will hit the tight upload bucket; the CLI respects `Retry-After` and backs off rather than erroring.
- **Config:** API URL + API key via env vars/flags. No config file in base.
- **File detection:** `*.json` files under the given paths.
- The CLI sends raw bytes and nothing else — no tags, no metadata, no analysis. Everything derived happens server-side.

## 2. API keys

The CLI cannot do browser auth, so the platform gains API keys.

- Table: `api_keys` — `id`, `owner_id`, `name`, `key_hash` (plaintext shown once at mint), `created_at`, `last_used_at`, `revoked_at`. A scope column is reserved for later; stage 2 ships one scope.
- **Upload-only scope:** `POST /v1/uploads` + `GET /v1/uploads/{id}`. Least privilege; everything else stays JWT-only.
- Webapp: settings page to mint/revoke keys.
- API middleware accepts a Supabase JWT or an API key on the same `Authorization` header. This is the only modification to existing stage-1 code; everything else in stage 2 is additive.

## 3. Notifications

In-app only in base (desktop notifications are an extension).

- Table: `notifications` — `id`, `user_id`, `type`, `payload` jsonb, `created_at`, `read_at`.
- Types in base: `review_request`, `subscription_match`. Bounties later add `bounty_match` with no schema change.
- Endpoints: list, mark-read. Web: bell + notifications list.
- Generated server-side (worker jobs / API), never by clients.

## 4. Review-queue plumbing

Content is a judging-discussion placeholder; plumbing is fixed:

- Generic review item: trace ref, question type, context payload, **answer payload as jsonb**, status, resolved timestamps — the label model can change without migration churn.
- Uncertain analysis outcomes create a review item + a `review_request` notification.
- Web: queue page + per-item resolve view; resolve endpoint stores the answer with provenance.

## 5. Subscriptions + bulk acquire

- Subscription = stored query: `id`, `owner_id`, `name`, query params jsonb — **the same filter vocabulary as `GET /v1/traces`**. One filter language everywhere (search UI, subscriptions, later bounties); any field that becomes filterable automatically becomes subscribable.
- **Event-driven matching, two triggers:** (a) a trace is listed; (b) analysis completes/updates derived fields on a listed trace (a trace may only start matching once the field a rule uses is filled in). No cron sweep.
- Matches generate **per-match** `subscription_match` notifications (batching/digest is a future knob).
- Feed: subscription detail page executes the stored query live (backfill for free) with a new-since-last-seen marker.
- **Bulk acquire:** one endpoint taking `trace_ids[]`; per-trace semantics identical to the existing acquire (idempotent, $0, listed-only, non-owner). Multi-select in results/feed UI. No auto-acquire anywhere.

## 6. Analysis / derived-field plumbing

Analyzers are placeholders; their infrastructure is not:

- Post-ingestion worker job(s) (same taskiq/retry/DLQ machinery as ingestion).
- Results table: trace ref, analyzer name, analyzer version, output jsonb, confidence — provenance and re-runnability, mirroring the ingestion invariant (re-running an analyzer reproduces its rows).
- Fields used for *matching* get promoted onto `traces` as real columns/arrays (like `tool_names` today) so rule-based filtering stays plain SQL. Which fields exist is the judging discussion's output; the promotion mechanism is infra.
- Uncertainty routing: analyzer output below a confidence threshold → review item + notification (see §4).

## 7. Upload source provenance

`uploads.source: cli | web`, inferred by the API from the auth type (API key → `cli`, JWT → `web`). The CLI does not set it. Debugging/analytics only.

## Cross-cutting

- **Privacy unchanged from stage 1:** CLI uploads are private by default; listing remains the explicit consent act in the webapp. Subscriptions match listed traces only.
- **Stage-1 contact surface is minimal:** auth middleware (API keys) and the `uploads.source` column. Everything else is new tables, new endpoints, new worker jobs, new pages.
