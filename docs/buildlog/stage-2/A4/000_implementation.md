# A4 — Discovery at Scale: Filter Extension, Subscriptions, Bulk Actions

Spec: `docs/spec/stage-2/6_build-order.md` (A4), `3_api.md` (filter-language
extension, subscriptions, bulk operations), `2_data-model.md`
(`subscriptions`, `subscription_matches`, access rules), `4_pages.md`
(`/subscriptions`, `/subscriptions/[id]`, filter controls, bulk UI,
cross-cutting URL law), `1_analysis.md` (Runtime: the listing→re-run rule).

**Done when:** demo-script steps 6–9 (`0_README.md`) pass end to end.

Consumes B3: `metric_scores` keys exist on analyzed traces and the `metric`
filter param reads them. Stage-1 slice 3 (the thick gate) is done. A2's seams
are ready: the `trace_analysis` left join is already in `list_visible`, and
this slice closes A2's known interim state by wiring the `owner_opt_out`
listing→re-run hook. A1's deferred URL-serialization debt (A1 decision 8)
lands here with the filter-language extension. A3's notification machinery
(digest-upsert pattern, bell, realtime on `notifications`) is reused, and
the `subscription_match` type — in the vocabulary since migration 09 —
finally gets an emitter.

Decisions proposed in this plan, to ratify before implementation:

1. **One Pydantic filter model is the entire vocabulary.** A
   `TraceFilterQuery` model (`extra="forbid"`) holds every filter param —
   stage-1's (`q`, `provider`, `model`, `tool`, `has_errors`, `from`, `to`)
   plus the A4 table: equality CSVs (`outcome`, `failure_mode`,
   `task_category`, `loop_kind`, the three `*_provenance`), booleans
   (`has_retry_loop`, `recovered_from_error`, `truncation_suspected`),
   min-bounds (`outcome_confidence_gte`, `task_category_confidence_gte`,
   `duration_ms_gte`, `total_tokens_gte`, `llm_call_count_gte`,
   `tool_call_count_gte`), and repeatable `metric`. The router parses it
   from query params; `POST/PATCH /v1/subscriptions` validates `query`
   against the same model (unknown params → `422`); subscription execution
   re-parses the stored map through it. One parser, three call sites — a
   stored query that validated at write time cannot fail to execute later,
   by construction. The SQL side is one clause builder in
   `queries/traces.py` shared by `list_visible`, the feed, and match
   evaluation.
2. **Value validation splits by stability.** Check-constrained sets
   (`outcome`, provenances, `loop_kind`) and shapes (booleans, 0–1 floats,
   non-negative ints) validate strictly at parse. `failure_mode` /
   `task_category` values and `metric` names are format-checked only
   (slug pattern): taxonomies soft-retire (old values must stay matchable)
   and metric keys are enumerated from observed data, not hardcoded — an
   unknown value simply matches nothing, which "null never matches" already
   makes the honest semantics.
3. **Metric predicates parse to typed jsonb SQL.** `metric=<name>:<min>` →
   `jsonb_typeof(ta.metric_scores->name) = 'number' and
   (ta.metric_scores->>name)::numeric >= min`; `metric=<name>:true` →
   `ta.metric_scores->name = 'true'::jsonb` (boolean-flag metrics).
   Repeats AND together. The typeof guard means a flag metric queried as a
   number (or vice versa) matches nothing instead of erroring — same
   honest-nothing as decision 2.
4. **Analysis predicates report the excluded-unanalyzed count.** When any
   analysis-backed predicate is active, the list response carries
   `excluded_unanalyzed`: the count of traces matching the *non-analysis*
   filters in scope that have no `trace_analysis` row yet (state
   pending/failed). One extra count query, only on filtered requests; backs
   the 4_pages filter-exclusion note ("N not-yet-analyzed traces
   excluded"). Skipped traces have rows (nulls never match) and are not in
   this count — they were analyzed; the verdict honestly doesn't exist.
5. **Metric keys are enumerated by a tiny endpoint.**
   `GET /v1/traces/metric-keys` (declared before the `/{trace_id}` routes)
   → distinct `jsonb_object_keys(metric_scores)` over rows visible to the
   caller (own + listed), sorted. Feeds the filter UI's metric control per
   the 4_pages "observed data, not hardcoded" rule.
6. **Matching is a dedicated worker task with no retry/DLQ.**
   `match_trace(trace_id)`: load the trace's owner + listed check, loop the
   `subscriptions` table, evaluate each stored query as an
   `exists(<shared clause builder> and t.id = $trace and
   t.visibility = 'listed')`, insert `subscription_matches` on conflict do
   nothing, notify on first insert only. Deliberately *not*
   `retry_dlq="trace"`: trace-scoped dead letters derive the UI's
   `analysis_failed` state, and a matching hiccup must never read as a
   failed analysis. Matching is idempotent (unique pair) and re-fired by
   every trigger event; a lost task costs a notification, not correctness.
   Per-subscription queries at demo scale (one user's subscriptions) need
   no batching.
7. **Trigger wiring, including the opt-out re-run.** Wherever visibility is
   set to `listed` (single `PATCH /v1/traces/{id}` and bulk
   `POST /v1/traces/visibility`): if the trace's `llm_skip_reason` is
   `owner_opt_out`, enqueue `analyze_trace` and *do not* match now — per
   1_analysis.md Runtime, subscriptions only ever see fully-analyzed listed
   traces via trigger (b); otherwise enqueue `match_trace` (trigger a).
   Trigger (b): `analyze_trace` enqueues `match_trace` post-rewrite when
   the trace is listed (best-effort, same pattern as ingest→analyze).
   Re-listing an already-listed trace harmlessly re-fires the idempotent
   match task.
8. **Own traces are not excluded from subscriptions (demo scope).** An
   own-trace exclusion was proposed (subscriptions are a consumer surface;
   a contributor bulk-listing their own sync would self-notify) and
   deliberately not built — at trial scale the extra filter buys nothing.
   Accepted behavior: a subscription can match and notify on the owner's
   own listed traces; the feed shows them like the marketplace does, and a
   bulk acquire over them itemizes `own_trace` honestly. Noted as the
   first sharpening pass if subscriptions outlive the demo.
9. **`subscription_match` is a per-subscription digest** (spec amendment to
   ratify). 3_api.md says "one notification per new match"; 4_pages and the
   flood-control law say grouped/digested per subscription — at sync scale
   (step 8 follows a bulk listing) per-match rows are exactly the flood the
   law exists to stop. Resolution: reuse A3's digest-upsert mechanics — one
   *unread* `subscription_match` notification per subscription, partial
   unique index on `(user_id, (payload->>'subscription_id')) where unread`,
   payload `{subscription_id, match_count, trace_id}` where `trace_id`
   survives only while `match_count = 1` (single match links to the trace,
   digest links to the feed). `subscription_matches` rows stay per-match —
   the dedupe ledger is exact; only the notification digests. On
   ratification, 3_api.md's sentence is amended in the same pass.
10. **New-since-last-seen rides the match ledger.** `last_seen_at` defaults
    to `created_at` at insert. A feed card is `new_since_last_seen` when its
    match row has `matched_at > last_seen_at`; backfill rows (matched no
    event — they predate the subscription) have no match row and are never
    "new". `POST /v1/subscriptions/{id}/seen` stamps now.
11. **Bulk acquire/visibility loop the stage-1 single-trace primitives.**
    ≤100 ids per call (spec constant, like the `limit` cap). Acquire: the
    existing race-safe acquisitions CTE per id, statuses mapped exactly like
    the single router (`acquired | already_acquired | not_listed |
    own_trace | not_found`). Visibility: `update_owned` per id —
    `updated | not_found`, where not-found covers non-owned and absent alike
    (the bulk shape has no 403 slot, consistent with 404-not-403);
    `confirm_ownership` required only when listing, `422
    confirmation_required` otherwise; listing hooks per decision 7 fire per
    updated trace. A loop of ≤100 single statements keeps "per-trace
    semantics identical to stage 1" true by construction; set-based SQL is
    an optimization with no current evidence demanding it.
12. **Bulk download assembles per-upload, streams from a spool.** Every id
    must be owner-or-acquired else `403 acquisition_required` naming the
    offending ids (spec). Payload entries dedupe by upload: traces from one
    upload share one storage object, so the zip gets one payload entry per
    distinct upload in the selection — owner → raw object, acquirer →
    scrubbed artifact (the A5 boundary, same rule as the single download);
    filename collisions across uploads get the upload id suffixed.
    `labels.jsonl` stays one line per *requested trace*: `trace_id`, the
    three label triplets (value/confidence/provenance), `metric_scores`,
    promoted signals, analyzer versions; unanalyzed → nulls. The zip is
    written to a temp spool and streamed (size is capped by upload limit ×
    100, too big to hold in memory); a missing scrubbed artifact fails the
    request before streaming with the single-download's not-found message
    naming the trace.
13. **Filter state serializes into the URL everywhere, via one hook.**
    `useTraceList` grows URL read/write for filters + sort (same
    `useSearchParams` mechanics as `usePageParam`); `/traces`,
    `/marketplace`, and the feed all get it (library has no filter bar —
    its pager is already URL-backed). A shared `FilterChips` component
    renders active predicates verbatim (`faithfulness ≥ 0.8 ×`) with
    per-chip remove; the same chips render subscription queries on
    `/subscriptions` rows and the feed header — one filter language, one
    artifact, per 4_pages.
14. **"Save as subscription" lives on the marketplace; the live total is
    the backfill preview.** The button captures current filter state (minus
    scope/sort/pagination), opens a name dialog showing "N listed traces
    match today" from the already-loaded result total, and POSTs. The feed
    header's query edit reuses the same filter controls and visibly re-runs
    the feed. Empty filter state disables the button (a subscribe-to-
    everything subscription is a footgun with no use).
15. **Keyless test strategy: canned verdicts for labels, seeded scores for
    metrics.** Label/confidence/provenance filter tests ride A3's
    `analyze:verdict` fault (real promotion path, keyless CI). `metric`
    predicate and `metric-keys` tests seed `trace_analysis.metric_scores`
    directly through the test db fixture — the filter layer reads promoted
    columns and doesn't care who wrote them; running real critics in CI
    would need a key. No new fault grammar.

Ratified 2026-06-11: 1–7 and 9–15 as proposed; 8 inverted by user decision —
no own-trace exclusion, behavior accepted and noted above.

## Plan

### Migration (`supabase/migrations/00000000000010_subscriptions.sql`)

- `subscriptions` per 2_data-model.md: id, `owner_id` → profiles, `name`,
  `query` jsonb, `created_at`, `last_seen_at` default `now()` (decision
  10). Index `(owner_id)`.
- `subscription_matches`: id, `subscription_id` → subscriptions (cascade),
  `trace_id` → traces (cascade), `matched_at`. Unique
  `(subscription_id, trace_id)`.
- Notifications digest index (decision 9): partial unique on
  `(user_id, (payload->>'subscription_id')) where type =
  'subscription_match' and read_at is null`.
- RLS: owner-only select on both tables (subscriptions additionally
  insert/update/delete? No — same posture as A3: the API is the writer
  through the service role; client policies are select-only, mirroring the
  access rule for defense in depth).
- No new realtime publication: the bell already rides `notifications`.

### Backend — filter extension

- `schemas/trace.py`: `TraceFilterQuery` (decision 1) — CSV fields parsed
  to lists, strict enums per decision 2, `metric: list[str]` with the
  `<name>:<value>` grammar parsed by a validator; `TraceListResponse`
  gains optional `excluded_unanalyzed` (decision 4).
- `queries/traces.py`: extract the clause-building inside `list_visible`
  into `filter_clauses(filters, param) -> list[str]` covering stage-1 +
  A4 predicates (analysis predicates on `ta.*`, metric SQL per decision 3);
  `list_visible` takes the model instead of loose kwargs; add the
  excluded-unanalyzed count (decision 4) and `metric_keys(pool, caller_id)`
  (decision 5).
- `routers/traces.py`: `list_traces` accepts the model (FastAPI query-model
  dependency keeps OpenAPI exact); `GET /traces/metric-keys` before the
  dynamic routes.

### Backend — subscriptions

- `schemas/subscription.py`: create/patch/list/feed models; `query` typed
  as `TraceFilterQuery` (decision 1).
- `queries/subscriptions.py`: CRUD (owner-scoped), live match count (the
  stored query as a count over listed traces), `last_match_at` from the
  ledger, feed execution (shared clause builder +
  `new_since_last_seen` left join per decision 10, ordered `listed_at`
  desc), match evaluation for one trace (decision 6), `seen`.
- `queries/notifications.py`: `subscription_match_upsert` mirroring A3's
  digest upsert (decision 9).
- `routers/subscriptions.py`: the six endpoints per 3_api.md; JWT-only by
  the existing key-scope rule; `DELETE` hard-deletes (cascade), confirm
  copy lives client-side.
- `worker/tasks/match.py`: `match_trace` (decision 6).
- Triggers (decision 7): `update_trace` enqueues post-update;
  `analyze_trace` enqueues post-rewrite when listed; bulk visibility per
  decision 11.

### Backend — bulk endpoints

- `schemas/trace.py`: bulk request/response models (itemized rows).
- `routers/traces.py` (or a `bulk.py` router if it crowds): `POST
  /v1/traces/acquire`, `/visibility`, `/download` per decisions 11–12.
  Download builds `labels.jsonl` from `trace_analysis` + `analyzer_results`
  versions in one query pass, fetches each distinct upload's payload per
  the A5 boundary, zips into a `SpooledTemporaryFile`, streams with
  `Content-Disposition: traces-<n>.zip`.
- Rate limiting: the standard per-user bucket already covers new routes.

### Frontend

- `lib/api/traces.ts`: `TraceFilters` grows the full vocabulary + `metric`
  list; `listTraces` serializes it; bulk fetchers (`bulkAcquire`,
  `bulkVisibility`, `bulkDownload` via `apiDownload`); `metricKeys()`.
  `lib/api/subscriptions.ts`: types + fetchers for the six endpoints.
- **Filter controls** (`components/traces/trace-filters.tsx` +
  `filter-chips.tsx`): analysis selects (outcome, provenance,
  failure_mode, task_category from `components/review/taxonomy.ts`,
  loop_kind), boolean toggles, `≥` threshold inputs for confidence/numeric
  bounds, metric rows (key select from `metricKeys()` + threshold or flag);
  chips render every active predicate verbatim with remove; "N
  not-yet-analyzed traces excluded" note from `excluded_unanalyzed`.
- **URL state** (decision 13): `useTraceList` serializes filters + sort to
  search params; marketplace, `/traces`, feed.
- **Multi-select + bulk bar** (`components/traces/bulk-bar.tsx`): row/card
  checkboxes, persistent bottom bar with count; on `/traces` → "List N" /
  "Unlist N" with the batched-consent dialog (exact count, affirmative
  ownership checkbox once); on the feed → "Acquire N" with itemized result
  copy ("8 acquired · 2 already in library · 2 no longer listed") and the
  "download now" offer; on `/library` → "Download N". Selection caps at
  100 mirroring the API.
- **`/subscriptions`**: list with name, query as chips, match stats,
  last-match time; inline rename, edit (chips + controls), delete with
  name-confirm stating consequences; empty state points at marketplace
  search. **`/subscriptions/[id]`**: header (name, editable chips, match
  count, manage), new-since-last-seen divider, marketplace-style cards,
  multi-select → bulk acquire, `seen` stamped on view; states per 4_pages
  (loading / no-matches-*yet* / results / error). Nav gains Subscriptions.
- **Marketplace**: "Save as subscription" + dialog (decision 14).
- **`/notifications`**: `subscription_match` rendering — digest line ("N
  new matches for <name>"), link to feed (or the trace when
  `match_count = 1`).

### Env + docs

No new env vars: matching is event-driven (no cron), the bulk cap and zip
bound are spec constants. Spec amendment on ratification of decision 9
(3_api.md notification sentence). Demo: `docs/demos/subscriptions.md` —
save a metric-predicate subscription, list a matching trace from the CLI,
watch digest → feed → bulk acquire → labeled download; README index line.

### Tests

Integration (`tests/integration/test_discovery_scale.py`; keyless per
decision 15):

- **Filters:** canned-verdict traces + seeded `metric_scores` →
  `outcome=failure,indeterminate` ORs within the field; provenance filter
  distinguishes resolved vs machine rows; `outcome_confidence_gte`
  boundary; `metric=faithfulness:0.8` includes/excludes, `metric=<flag>:true`
  works, unknown metric name matches nothing; unanalyzed traces never match
  any analysis predicate and `excluded_unanalyzed` counts them; unknown
  param → `422`; `metric-keys` returns seeded keys only for visible traces.
- **Subscriptions:** create validates query (unknown param `422`); listing
  a matching trace → match row + digested notification (two matches → one
  unread digest, `match_count = 2`); re-listing → no duplicate
  notification (unique pair); private trace never matches; own listed
  trace does match (decision 8); feed returns match with `new_since_last_seen`
  true, false after `seen`; opt-out-skipped trace listed → re-analyzed →
  matched via trigger (b) with no premature trigger-(a) match; delete
  cascades matches.
- **Bulk:** acquire mixed batch → exact itemized statuses; visibility
  without `confirm_ownership` → `422`, mixed owned/absent → itemized,
  newly-listed opt-out trace re-enqueued; download of own + acquired →
  zip with one payload per upload + `labels.jsonl` line per trace
  (unanalyzed line has nulls), unacquired id → `403` naming it; >100 ids
  → `422`.

Unit: filter-model parsing (CSV split, metric grammar valid/invalid,
strict-vs-format value validation matrix); metric clause SQL fragments;
`labels.jsonl` line assembly from a row.

### Verification (done-when walkthrough)

1. Fresh `supabase db reset` + `docker compose up --build` with an LLM key;
   CLI-sync the dev dataset as the contributor.
2. **Step 6:** My Traces → multi-select synced traces → "List N" → one
   batched-consent dialog → all listed.
3. **Step 7:** as the consumer, filter the marketplace on
   `outcome=failure` + `confidence ≥ 0.8` + `faithfulness ≥ 0.8` (URL
   carries the state; chips verbatim) → "Save as subscription" with the
   backfill-preview count.
4. **Step 8:** contributor syncs + lists a new matching trace → consumer's
   bell increments → digest links to the feed → new-since-last-seen
   divider → multi-select → bulk acquire → itemized result.
5. **Step 9:** `/library` → select acquired traces → "Download N" → zip
   has scrubbed payloads + `labels.jsonl`; the contributor downloading own
   traces gets raw.
6. Opt-out hook: opted-out contributor's private trace shows `skipped
   (owner_opt_out)` → listing it → analysis re-runs → labels appear →
   subscription matches.
7. Integration + unit suites green on the keyless stack; ruff + format
   clean; `tsc`, eslint, `next build` clean.

## Drift

1. **FastAPI query models don't mix with loose query params** (the model
   silently becomes a required `filters` param). `TraceListParams`
   subclasses `TraceFilterQuery` with scope/sort/limit/offset for the GET
   endpoint only; the subscribable vocabulary stays exactly the base model.
   Relatedly, `extra="forbid"` moved off the base model onto
   `SubscriptionQuery` — strict at subscription write time (unknown params
   422 per 3_api.md), while `GET /v1/traces` keeps stage-1's
   ignore-unknown-params behavior instead of breaking existing callers.
2. **Feed ordering** follows the shared list default (`created_at` desc)
   rather than the planned `listed_at` desc: the feed reuses `list_visible`
   wholesale (scope=marketplace + stored filters), and consistency across
   list surfaces beat a bespoke sort. `new_since_last_seen` is annotated
   from the match ledger in a second query, not a join, keeping
   `list_visible` single-purpose.
3. **No `GET /v1/subscriptions/{id}`** was added (the spec defines none);
   the feed page resolves its subscription from the list response. Demo
   scale makes this free; a single-get is the obvious extension if
   subscription lists ever grow.
4. **Filter UI shape:** the long-tail vocabulary (loop kind, signal
   booleans, category confidence, count/duration/token bounds) sits behind
   a "More filters" disclosure; the primary row carries outcome / failure
   mode / category / provenance / confidence / metric. Chips render every
   active predicate regardless of which row owns the control. Subscription
   query editing is chip-removal (PATCH per removal, feed re-runs);
   predicate *addition* happens on the marketplace and re-saves.
5. **Feed `seen` stamping:** the page stamps `last_seen_at` after the first
   successful load — the current view keeps its new-markers, the next
   visit starts fresh. (Pagination within one visit recomputes against the
   new stamp; accepted.)
6. **Migration 11 (`owner_trace_identity`, A6 stream) landed
   mid-implementation**, moving trace identity to
   `(owner_id, source_trace_id)`. A4 code needed no change; the new
   integration tests did — fixture payloads now mint unique source trace
   ids (`unique_payload()`), since reusing the shared fixture's hardcoded
   id adopts-and-rewrites one trace instead of creating many.
7. **One out-of-scope fix:** `top-bar.tsx` (A3-stream file) had a
   `"" | {…}` type error that broke `next build`; one-line fix
   (`from ? FROM_CRUMBS[from] : undefined`) to keep the build green.
8. The bulk download's per-batch dedupe key is
   `(storage object, redaction variant)` and entry-name collisions get the
   storage hash suffixed — plan said "id-suffixed"; the hash is what's at
   hand on the storage path and equally unique.

## Outcome

Verified 2026-06-11 against the running stack (`supabase` migrations 1–11
applied, `docker compose up --build`):

- **Migration 10** applied: `subscriptions`, `subscription_matches`
  (unique pair), the `subscription_match` digest partial-unique index,
  select-only RLS on both tables.
- **Filter extension:** all 24 vocabulary params live on `GET /v1/traces`
  (OpenAPI flattens them); CSV ORs, provenance/loop-kind enums, signal
  booleans (false is a filter), `_gte` bounds, repeatable `metric` with
  number/flag grammar and the jsonb_typeof guard; `excluded_unanalyzed`
  populated only under analysis predicates; `GET /v1/traces/metric-keys`
  enumerates observed keys. Malformed values 422.
- **Subscriptions:** six endpoints; write-time query validation (unknown
  params, request-shape params, bad metric grammar → 422); owner-scoped
  404s; live match counts; `match_trace` worker task (no retry/DLQ) fired
  from both triggers — listing (single + bulk PATH) and post-rewrite
  analyze on a listed trace; the `owner_opt_out` listing re-run hook routes
  to `analyze_trace` first and matches on completion (trigger b, proven
  keyless via the skip-reason transition + a signal-only subscription).
  Digest mechanics: first match deep-links the trace, the second folds into
  the same unread row (`match_count` 2, trace link dropped), reading frees
  the slot, the ledger stays exact, re-listing never re-notifies.
- **Bulk:** `/acquire`, `/visibility` (batched consent 422 without
  confirmation), `/download` (zip: payloads deduped per upload, raw for
  owners / scrubbed for acquirers, `labels.jsonl` with triplets + metrics +
  signals + analyzer versions, honest nulls for unanalyzed; 403 names
  unacquired ids; ≤100 ids enforced) — all itemized, partial success
  normal.
- **Frontend:** URL-serialized filters + sort on /traces and /marketplace
  (A1's deferred law paid); extended filter bar + chips + excluded note;
  bulk bars (List/Unlist N with one consent dialog, Acquire N with
  itemized result + download offer, Download N); `/subscriptions` +
  `/subscriptions/[id]` (chips, live counts, new-since divider, seen
  stamping); marketplace Save-as-subscription with backfill preview; nav
  + notification rendering (digest vs deep link). `tsc`, eslint
  (`--max-warnings=0`), `next build` clean.
- **Tests:** 292 unit (incl. new `test_filter_query.py`: parsing matrix,
  metric grammar, clause SQL, `labels.jsonl` assembly) and 81 integration
  (incl. new `test_discovery_scale.py`: 6 tests covering the plan's
  filter/subscription/bulk/hook list) — all green on the keyless stack;
  ruff check + format clean.
- Spec amendment for decision 9 applied to `3_api.md`; demo added at
  `docs/demos/subscriptions.md` and indexed.

Demo-script steps 6–9 are exercised end to end by
`test_discovery_scale.py` (keyless); the live-key walkthrough remains for
the stage-close demo pass.
