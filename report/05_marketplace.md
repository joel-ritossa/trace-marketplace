# Marketplace

The marketplace is the consumer side of the platform: discover listed traces through one filter language, watch for new matches with saved-query subscriptions, and acquire into a library with labeled bulk downloads. Two rules anchor the design: listing is the consent act (nothing is discoverable until its owner affirmatively lists it), and acquisition is always a human act (no auto-acquire mechanism exists anywhere).

## Listing & Consent

Every trace is private by default — the `visibility` column defaults to `'private'` regardless of upload path (web, CLI, desktop). Listing is the single consent act, and the API enforces it: flipping visibility to `listed` without `confirm_ownership: true` returns a 422 `confirmation_required` (`app/routers/traces.py`), so the affirmative checkbox is a server-side rule, not a UI nicety.

Bulk listing keeps the same shape: `POST /v1/traces/visibility` takes up to 100 trace ids and requires the same confirmation once for the batch — one dialog naming the exact selection, per the spec's batched-consent decision (`docs/spec/stage-2/0_README.md`). Results are itemized per trace; partial success is normal.

Listing consent also covers analysis. A private trace whose owner opted out of LLM analysis gets re-enqueued for analysis when listed (`schedule_listing_hooks` in `app/routers/traces.py`), so subscriptions only ever see fully-analyzed listed traces. The privacy side of this boundary is in [06](06_privacy-and-redaction.md).

## Search & Filters

One filter vocabulary, one parser, one SQL builder. `TraceFilterQuery` (`app/schemas/trace.py`) is parsed from `GET /v1/traces` query params, validated and stored by subscriptions, and re-parsed when stored queries execute; the WHERE clauses come from a single builder (`app/queries/traces.py::filter_clauses`) shared by the list endpoint, subscription match evaluation, and the feed. A filter added once is searchable and subscribable everywhere — and the designed-for bounties extension (`docs/extensions/task-bounties.md`) would reuse the same vocabulary.

The vocabulary:

- **Stage-1 fields** — full-text `q` (a weighted tsvector over name, tags, description, provider, model, service name, tool names, error types), `provider`, `model`, `tool`, `has_errors`, date range.
- **Analysis equality filters** — `outcome`, `failure_mode`, `task_category`, `loop_kind`, per-field provenance; comma-separated values OR within a field.
- **Promoted signal booleans** — `has_retry_loop`, `recovered_from_error`, `truncation_suspected`; `false` is a real filter, absent means no filter.
- **Min-bounds** — `outcome_confidence_gte`, `duration_ms_gte`, `total_tokens_gte`, call counts; the only range shape in stage 2.
- **Metric predicates** — repeatable `metric=<name>:<min>`; repeats AND.

Matching over derived fields is deterministic: predicates evaluate against stored labels and scores, never against an LLM at query time. A not-yet-analyzed trace never matches an analysis predicate; instead of silently shrinking results, the API returns an `excluded_unanalyzed` count and the UI says "N not-yet-analyzed traces excluded". Search URLs carry every predicate, so a marketplace search is shareable and is the seed for "Save as subscription".

## Subscriptions

A subscription is a stored marketplace query that watches for new matches. The query is validated at write time against the same Pydantic model the API parses, so a stored query can never fail to execute later. The create dialog previews the current match count — backfill is visible before saving.

Matching is event-driven, not polled: `match_trace` (`app/worker/tasks/match.py`) evaluates a trace against every subscription exactly when it becomes listed or when its analysis completes while listed. There is no cron sweep and no missed window between "listed" and "analyzed" — an opt-out trace that gets listed re-enqueues analysis first and matches when its labels land.

Flood control is enforced by Postgres, not remembered by callers: a unique `(subscription_id, trace_id)` pair makes notify-once permanent across re-listing storms, and the unread notification is a partial-unique-index upsert — a second match before the first is read becomes "2 new traces match …" in the same row, never a ping per trace. The match task deliberately has no retry/DLQ: a lost run costs one notification, never correctness, and a matching hiccup must never read as a failed analysis.

The feed (`/subscriptions/[id]`) runs the stored query live, marks matches new-since-last-seen (cleared on the next visit), and offers bulk acquire. There is no auto-acquire — the spec locks this ("no auto-acquire anywhere", `docs/spec/stage-2/0_README.md`): subscriptions notify, a human multi-selects, and the bulk action confirms the final count. The full loop is runnable: [docs/demos/subscriptions.md](../docs/demos/subscriptions.md), or keylessly via `tests/integration/test_discovery_scale.py`.

## Similar-Behavior Extension

Beyond field filters, a consumer can search by behavior: "find traces that act like this one." Built on a research pass first (`sandbox/behavior-similarity/_FINDINGS.md`): whole-transcript embeddings over the judge's rendering were the best single behavior retriever tested (blind pairwise precision 1.0 in-corpus, 0.6 cross-benchmark vs a 0.13 base rate); structural representations and window matching underperformed and were dropped.

What shipped (design in [docs/proposals/similar-behavior.md](../docs/proposals/similar-behavior.md)):

- **Embedding at analysis.** Each `analyze_trace` run embeds the trace's judge rendering (`text-embedding-3-small`, 1536 dims) into a pgvector table with an HNSW cosine index. The embedding rides the judge's exact gates — skipped without a provider key, skipped for opted-out private traces — and a gated run deletes any existing vector, keeping the table a pure function of payload and gates.
- **Similar-traces lookup.** `GET /v1/traces/{id}/similar` returns cosine nearest neighbors among traces visible to the caller (own + listed), surfaced as a modal on the trace page.
- **Behavior-anchored subscriptions.** A subscription may carry an anchor trace plus a similarity threshold (a 0–1 slider with a live count of currently-matching listed traces as the preview). The anchor ANDs with the stored filter query.

The anchor stays inside the deterministic-matching rule: at match time it is a SQL vector-distance comparison against stored embeddings — no LLM call, same inputs, same answer. Deleting the anchor trace nulls the anchor (`on delete set null`) and the subscription matches nothing until edited.

## Acquisition & Downloads

Acquisition is free and idempotent: the `acquisitions` row carries `price_usd` defaulting to 0 (pricing is future-work narrative, not built), and a unique `(consumer_id, trace_id)` pair makes re-acquiring a no-op. Acquired traces appear in the library (`/library`, the `acquired` scope of the same list endpoint).

Bulk acquire takes up to 100 trace ids and returns an itemized status per trace — `acquired`, `already_acquired`, `own_trace`, `not_listed`, `not_found` — partial success is normal, never all-or-nothing (`app/routers/bulk.py`). Each item loops the single-trace primitive, so per-trace semantics are identical by construction.

Bulk download streams a zip containing:

- **One payload per distinct upload** (traces from one upload share a storage object, so entries dedupe), following the redaction boundary per trace: the owner gets the raw object, everyone else gets the scrubbed artifact ([06](06_privacy-and-redaction.md)).
- **`labels.jsonl`** — one line per trace with the label triplets (value, confidence, provenance for outcome / failure mode / task category), metric scores, promoted signals, and analyzer versions. Unanalyzed traces get honest nulls, never invented labels.

## Notifications

Notifications are in-app only and generated server-side only — rows are inserted by the worker and API (`app/queries/notifications.py`); no client ever creates one. Three types ship:

- **`review_request`** — uncertain analysis verdicts routed to human review, digested per upload: one unread notification per upload that accumulates a count ([04](04_analysis-pipeline.md)).
- **`subscription_match`** — digested per subscription, as above.
- **`upload_failed`** — emitted for CLI-source uploads only, on both failure paths (permanent error and retry exhaustion). Web upload failures fail in front of the user; CLI failures happen while nobody watches, so they get a notification.

There is one notifications surface: a routed `/notifications` page, no popover panel. The shell bell shows an unread badge and links there; Supabase Realtime events on the user's own rows trigger a refetch, so the badge increments — and clears after mark-read — without a refresh. Mark-read is idempotent: already-read, foreign, and malformed ids no-op alike.
