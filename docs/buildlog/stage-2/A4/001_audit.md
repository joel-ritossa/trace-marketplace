# A4 Audit — Discovery at Scale

Post-implementation review per `.cursor/skills/code-audit/SKILL.md`. Scope:
everything A4 touched — migration 10, the filter vocabulary + clause
builders, subscriptions (schemas/queries/router/match task/triggers/digest),
bulk endpoints, and the frontend (filter state/bar/chips, bulk UI,
subscription pages, notifications rendering). Audited against the current
tree, which includes the ui-redesign pass that replaced A4's table/cards
split with the unified `trace-list.tsx`.

## Findings

### Bugs

1. **Filter-bar mount emit dropped `?page` from the URL.** The debounce
   effect in `trace-filters.tsx` fires once on mount (the reseed effect
   replaces the `text` state object), and `useTraceList.apply` rebuilds the
   URL from `filtersToParams`, which never carries `page` — so refreshing or
   deep-linking a paginated `/traces`, `/marketplace`, or `/library` URL
   snapped back to page 1, violating the 4_pages URL-view-state law.
2. **`PATCH /v1/subscriptions/{id}` could 500 on a delete race.** The
   post-update re-read (`get_owned`) wasn't None-guarded; a concurrent
   delete between update and re-read crashed instead of 404ing.

### Spec mismatches (doc-side)

3. **2_data-model.md's `subscription_match` payload row predated decision
   9.** It said `subscription_id + trace_id`; the ratified digest payload is
   `subscription_id + name + match_count` with `trace_id` only while the
   count is 1. The decision-9 amendment had only landed in 3_api.md.
4. **3_api.md said zip collisions are "id-suffixed".** The implementation
   suffixes the storage-object hash (drift 8 of the implementation pass
   recorded it, but the spec sentence was never amended).

### Consistency / honesty nits

5. **URL garbage wasn't fully "dropped, never errored"** as
   `filter-state.ts` claimed: an empty-string number param became a `0`
   filter (`Number("") === 0`), and metric bounds / enum values passed
   through unvalidated, turning a hand-mangled URL into a 422 error banner.
6. **Match ledger and digest weren't atomic.** A crash between
   `record_match` and `subscription_match_upsert` would permanently dedupe
   the match without ever notifying (unlike A3's review digest, which
   commits with its item).
7. **A renamed subscription's open digest kept the stale name** — the
   conflict path didn't refresh `payload->>'name'`.
8. **Empty-query subscriptions were creatable via chip removal.** Creation
   guarded the subscribe-to-everything footgun client-side only; removing
   the last chip on the feed header PATCHed `query: {}` successfully.
9. **Library results omitted the excluded-unanalyzed note** above a
   populated list (the other three surfaces show it).
10. **Selects couldn't render a CSV value** (authored by URL or stored
    subscription) — they silently fell back to the placeholder while the
    filter was active; the value sets were also duplicated between
    `filter-state.ts` and `trace-filters.tsx`.
11. **"Download N now" in the acquire-result dialog swallowed errors**
    (no `onError` wired).
12. `filtersToParams`'s comment claimed it "preserves unrelated params";
    it rebuilds from scratch.

### Clean axes

- **Modularity:** one clause builder for all three executors, one row→card
  mapping, `filter-state.ts` as the single URL/chip home — clean.
- **Future-proofing:** the N+1s (live match counts, per-subscription match
  evaluation, unbounded `fetch_all`) are documented demo-scale decisions.
- **Security & auth:** subscriptions/bulk JWT-only; select-only owner RLS on
  both new tables; all SQL parameterized; no payload logging; bulk-download
  access resolved before streaming — clean.
- **Reliability:** `match_trace`'s deliberate no-retry/no-DLQ posture is
  sound (a matching hiccup must not read as a failed analysis); idempotent
  everywhere; finding 6 was the one soft spot.

## Fixes (all approved, this pass)

- `trace-filters.tsx`: the debounce emit now no-ops when the text-derived
  fields equal the live filters, so the mount/reseed pass never reaches the
  URL writer (fixes 1); selects render an unknown active value as an extra
  option (10); value sets import from `filter-state.ts` (10).
- `routers/subscriptions.py`: None-guard on the post-patch re-read → 404 (2).
- `schemas/subscription.py`: `SubscriptionQuery` rejects a query with no
  active predicate (`stored()` empty → 422), enforcing the footgun guard at
  create and patch alike (8).
- `worker/tasks/match.py` + `queries/subscriptions.py`: `record_match` and
  the digest upsert now share one transaction per subscription; a first
  match can no longer be recorded without its notification (6).
- `queries/notifications.py`: the digest conflict path refreshes `name` (7).
- `filter-state.ts`: `paramsToFilters` now mirrors backend validation —
  strict sets for outcome/provenance/loop-kind, slug shape for taxonomies,
  full metric grammar, 0–1 bounds for confidences, integer counts; empty
  strings no longer coerce to 0 (5); comment fixed (12).
- `subscriptions/[id]/page.tsx`: chip removal down to zero predicates is
  blocked client-side with an inline message (8); query-edit errors render
  under the chips instead of replacing the feed.
- `library/page.tsx`: excluded-unanalyzed note above results (9).
- `bulk-actions.tsx`: download errors surface in the acquire-result
  dialog (11).
- Spec amendments: 2_data-model.md `subscription_match` payload row (3);
  3_api.md collision suffix wording → storage-object hash (4).
- Tests: unit `test_empty_query_rejected` (incl. no-op-only maps);
  integration adds `{}` to the rejected-query matrix.

## Verification

- `ruff check` + `ruff format --check` clean; **293 unit tests pass**.
- `tsc`, `eslint --max-warnings=0`, `next build` clean.
- Integration (`test_discovery_scale.py`) against the rebuilt compose
  stack: CRUD/validation, matching/notifications/feed (which exercises the
  new transactional match path and digest upsert), filter extension, and
  bulk tests pass. **Caveat:** the shared local stack currently carries live
  LLM keys for the parallel B-stream work, so the keyless-only assertions
  (`test_listing_reruns_opt_out_analysis` expects the re-run to land on
  `not_configured`; `wait_analysis` timeouts stretch under live-judge
  latency) fail on it by construction, not regression — the re-run hook
  observably fired and completed with the key. Re-run the file on a keyless
  stack for the strict done-when.

## Accepted (not fixed)

- Notifications referencing a since-deleted subscription link to the feed's
  honest "Subscription not found" — history stays, no dead-end loop.
- The demo-scale N+1s stay until query evidence demands batching.
