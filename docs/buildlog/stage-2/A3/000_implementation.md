# A3 — HIL Loop: Review Items, Notifications, Resolve UI

Spec: `docs/spec/stage-2/6_build-order.md` (A3), `1_analysis.md` (HIL
routing, label model, feedback loop), `2_data-model.md` (`notifications`,
`review_items`, access rules), `3_api.md` (notifications, review items,
result-card fields), `4_pages.md` (`/review`, `/review/[itemId]`,
`/notifications` + bell, realtime cross-cutting).

**Done when:** uncertain fixtures produce digested notifications + queue
items with plain-language reasons; resolving updates labels with human
provenance; unresolved items leave traces machine-labeled and filterable.

Consumes B2: the routing function (`analysis/routing.py`, frozen contract)
already exists and is unit-tested; A3 wires its output into review items +
notifications. A2 left the seams ready: `open_review_item_id` ships null in
the analysis response, list rows hold back `has_open_review_item`, and the
worker persists through one `rewrite` transaction this slice extends.
Subscriptions (`subscription_match` notifications) are A4; the type is in
the schema vocabulary but nothing emits it yet. Stage-1 slice 3 gated only
"marketplace badges", which A2's `OutcomeBadge` already delivered.

Decisions proposed in this plan, to ratify before implementation:

1. **Routing rides the rewrite transaction.** The worker computes
   `route(signals, verdict, confidence_threshold)` only when a verdict
   exists (skipped/keyless runs never route — only the outcome judge
   creates review items), and the resulting item + notification writes
   commit atomically with `analyzer_results`/`trace_analysis` inside the
   existing `rewrite` transaction. No window where labels exist but the
   review item that routed them is lost to a crash; a re-run converges
   everything together.
2. **Supersede is spec-literal: only a re-run that routes again supersedes.**
   Routing reasons non-empty → mark the trace's open item (if any)
   `superseded`, insert a fresh open one (the partial unique index makes
   duplicates impossible). Routing reasons empty → existing open items are
   left untouched, including owner-initiated ones — the machine becoming
   confident doesn't withdraw a human's request. Caveat accepted: an open
   item's `context` can go stale after a no-route re-run; harmless because
   resolve writes against the current `trace_analysis` row, and the resolve
   view labels the context as the verdict *that routed it*.
3. **Human-answered questions are not re-asked.** Before creating an item,
   reasons are filtered by the current field provenance: outcome-targeted
   reasons (`signals_judge_disagreement`, `outcome_indeterminate`,
   `low_outcome_confidence`) drop when `outcome_provenance` is
   human/human_confirmed; `low_task_category_confidence` drops when
   `task_category_provenance` is. All reasons filtered → no item, no
   supersede. (Pure helper over `(reasons, prior provenances)`, unit-tested;
   the frozen `route()` itself is untouched.)
4. **Digest mechanics: one unread `review_request` notification per
   (user, upload), upserted.** Partial unique index on
   `(user_id, (payload->>'upload_id')) where type = 'review_request' and
   read_at is null`; item creation does
   `insert … on conflict … do update` incrementing `payload.item_count`
   and re-dating `created_at` (the digest line is "N traces from upload X
   need review" — newest-first ordering should surface it on growth). Once
   read, the next routed item starts a fresh unread digest counting from 1.
   This is the spec's flood control with zero scheduling machinery.
5. **`upload_failed` is emitted at both failure sites, CLI-source only, no
   dedupe.** One query helper (`notifications.upload_failed`) called right
   after `uploads.mark_failed` by its two callers — the permanent-error
   path in `ingest_upload` and the DLQ-exhaustion path in the retry
   middleware. It looks up the upload's `source`/`owner_id` and inserts
   only for `cli` (web failures fail in front of the user, per
   2_data-model.md). A requeue that fails again notifies again — each
   failure event is real.
6. **`human_confirmed` comparator is the field's current machine value.**
   Resolve compares each answered field against the live `trace_analysis`
   value *when its provenance is `machine`*: match → `human_confirmed`,
   else `human`; confidence 1.0 either way. One rule covers routed items
   (where context == current machine value, both being the latest run) and
   owner relabels (empty context). Coherence rule: a human outcome of
   `success`/`indeterminate` nulls a machine-provenance `failure_mode`
   triplet (the judge only diagnoses declared failures; a human-provenance
   failure_mode is the human's business and stays).
7. **Owner relabel requires an existing `trace_analysis` row.**
   `POST /v1/traces/{id}/review-items` returns `409 analysis_pending` when
   the trace has no row yet (state pending/failed): the resolve path writes
   label triplets *into* that row, and a human-only insert would have to
   invent `llm_status`. Relabel of an analyzed-or-skipped trace is always
   fine — `rewrite`'s carryover already protects the result from the next
   machine run.
8. **Review state is owner-only on list rows.** Result cards gain
   `has_open_review_item` (3_api.md) plus `open_review_item_id` — the
   needs-review indicator on `/traces` must link to the item (4_pages.md),
   and a boolean can't. Both are populated only when the caller owns the
   trace; non-owner cards always get `false`/`null` — review items are
   owner-scoped data (2_data-model.md access rules), and a consumer card
   has no business showing the owner's review backlog.
9. **The keyless routing lever is a canned-verdict dev fault.**
   `X-Fault: analyze:verdict:<outcome>:<conf>[:<category>:<conf>]` makes
   `analyze_trace` skip the LLM gate and adopt a fabricated `JudgeVerdict`
   (judge envelope marked `model_id = "fault:canned"`), exercising routing
   → digest → queue → resolve end to end with any reason combination on a
   keyless stack. Same dev-routes-only machinery as the existing faults;
   CI integration tests and the demo both run on it; live-key verification
   stays a manual step like A2's.
10. **The trace evidence pane is extracted, not duplicated.** The
    span-tree + details loading core of `TraceInspector` moves to a shared
    `TraceEvidence` component; `/traces/[traceId]` keeps its header,
    actions, and analysis section around it, and `/review/[itemId]`
    composes the same evidence beside the verdict form — "same inspection
    components" (4_pages.md) by construction, per the repo reuse rule.

Ratified 2026-06-11, all ten as proposed.

## Plan

### Migration (`supabase/migrations/00000000000009_hil.sql`)

- `notifications` per 2_data-model.md: id, `user_id` → profiles, `type`
  (app-validated text), `payload` jsonb, `created_at`, `read_at`.
  Indexes: `(user_id, created_at desc)`, partial on unread, and the
  digest-upsert partial unique index (decision 4). RLS: select for
  recipient (`user_id = auth.uid()`); no client write policies — the
  worker/API (service role) create, the API marks read.
- `review_items` per 2_data-model.md: id, `trace_id` → traces (cascade),
  `question_type` (`verdict`), `context` jsonb, `answer` jsonb nullable,
  `status` check `open | resolved | superseded`, `created_at`,
  `resolved_at`, `resolved_by` → profiles. Partial unique index on
  `(trace_id) where status = 'open'`; partial index on `status = 'open'`.
  RLS: select when the caller owns the referenced trace; no client writes.
- `alter publication supabase_realtime add table public.notifications`
  (mirrors A1's uploads wiring; RLS-checked delivery scopes events to the
  recipient).

### Backend — routing wiring (`worker/tasks/analyze.py`, `queries/analysis.py`, `queries/review_items.py`, `queries/notifications.py`)

- Fault grammar extension (`dev/faults.py`): `analyze:verdict:…` per
  decision 9; `trip_analysis` ignores it; the worker reads it via a new
  `canned_verdict(upload_id)` helper.
- Worker: when a verdict exists, compute `route(...)`, then the
  provenance filter (decision 3) against the prior row — `rewrite`
  already reads it; it now also returns/forwards the prior provenances.
  Pass an optional routing payload (filtered reasons + verdict snapshot +
  owner/upload ids) into `rewrite`.
- `rewrite` extension: inside the existing transaction, when routing
  reasons are non-empty — supersede the open item, insert the fresh one
  (`context = {"verdict": {...values+confidences...}, "reasons":
  [{code, message}, …]}`), and digest-upsert the `review_request`
  notification (decision 4). Item/notification SQL lives in the new
  `queries/review_items.py` / `queries/notifications.py`, called with the
  open connection.
- `upload_failed` (decision 5): `notifications.upload_failed(pool,
  upload_id)` called from `ingest_upload`'s permanent-error path and the
  middleware's upload dead-letter path; payload `{"upload_id": …}`.

### Backend — API (`routers/notifications.py`, `routers/review_items.py`, `schemas/notification.py`, `schemas/review.py`)

- `GET /v1/notifications` — recipient's, newest first, `limit`/`offset`,
  plus `unread_count` and `total`. `POST /v1/notifications/read` — body
  `{"ids": […]}` or `{"all": true}`, idempotent, recipient-scoped.
- `GET /v1/review-items` — caller's items on own traces, oldest first,
  `limit`/`offset`; `status` param (default `open`) to include resolved;
  `upload_id` param (backs the digest link's filtered queue). Each row:
  item fields + trace summary (id, name, status, duration) + the trace's
  `upload_id`, joined in one query.
- `GET /v1/review-items/{id}` — owner of the trace or 404; resolved items
  include `answer`, `resolved_at`, `resolved_by`.
- `POST /v1/review-items/{id}/resolve` — partial answer over
  `outcome | failure_mode | task_category`; values app-validated against
  the analysis-package taxonomies (`Outcome` ternary, `FAILURE_MODES`,
  `TASK_CATEGORIES` — one source of truth, imported). In one transaction
  with the `trace_analysis` row locked (serializes against a concurrent
  machine rewrite): write answered triplets per decision 6, apply the
  failure_mode coherence rule, mark the item resolved (answer, stamps,
  `resolved_by`). `409 already_resolved` on a non-open item.
- `POST /v1/traces/{trace_id}/review-items` (in the review router) —
  owner-initiated relabel: returns the existing open item or creates one
  with empty reasons (`context.reasons = []`, verdict snapshot from the
  current row); `409 analysis_pending` per decision 7; owner-only,
  404-not-403.
- `GET /v1/traces/{id}/analysis`: `open_review_item_id` now populated
  (owner only, decision 8). `TraceListItem` gains `has_open_review_item`
  + `open_review_item_id` via an owner-scoped exists/id subquery.
- All new endpoints are JWT-only by the existing key-scope rule (API keys
  reach exactly the two upload endpoints).

### Frontend

- `lib/api/notifications.ts`, `lib/api/review.ts` — types mirrored from
  the new schemas + fetchers; `lib/api/traces.ts` gains the two new list
  fields and the populated `open_review_item_id`.
- **Bell** (`components/shell/notification-bell.tsx`, in the app layout
  shell edge): unread-count badge from `GET /v1/notifications?limit=1`,
  `useRealtimeRefetch("notifications")` invalidation, navigates to
  `/notifications`. No popover.
- **`/notifications`**: paginated history (Pager), per-type rendering
  with the link law (4_pages.md): `review_request` → "N traces from
  upload X need review" → `/review?upload_id=…`; `upload_failed` →
  filename + `/uploads`; `subscription_match` renders generically until
  A4 emits it. Mark-all-read button; read rows stay listed, visually
  quiet; unread mix / all-read / positive-empty states; realtime
  invalidation.
- **`/review`**: open items oldest first, grouped per upload when a group
  has >1 ("12 from upload X", expandable), honoring `?upload_id=`. Row:
  trace identity, machine verdict + confidence, routing reasons verbatim
  (plain-language messages from the context), item age. Advisory framing,
  no alarm styling; loading / positive-empty / results / grouped states;
  Pager.
- **`/review/[itemId]`**: split view — `TraceEvidence` (decision 10)
  beside the verdict form. Context panel: machine verdict, confidence,
  reasons — never pre-selected. Form mirrors the label model: ternary
  outcome; failure_mode select (10 categories, one-line descriptions)
  only when failure is chosen; task_category independent; partial resolve
  allowed; no free text. "Resolve & next" primary when the queue (under
  the current filter) has more — fetches the next-oldest open item and
  navigates. States: loading, already-resolved (read-only, who/when,
  per-field provenance + 1.0), not-found (covers trace-deleted — the item
  cascades away), form-error.
- **Deltas**: nav gains Review; `/traces` analysis column gains the
  needs-review indicator linking `open_review_item_id`; the Analysis
  section gains the owner relabel entry ("Relabel" → create/return item →
  route to `/review/[itemId]`) and links `open_review_item_id` when an
  item is open.

### Env + docs

No new env vars (`ANALYSIS_CONFIDENCE_THRESHOLD` shipped with B2). Demo:
`docs/demos/hil-loop.md` — fault-driven uncertain verdict on a keyless
stack → digest → queue → resolve, plus the README index line.

### Tests

Integration (`tests/integration/test_hil.py`; keyless CI reaches routing
via the canned-verdict fault, decision 9):

- Uncertain upload (two traces, `analyze:verdict:success:0.4`) → two open
  items with `low_outcome_confidence` plain-language reasons; **one**
  unread `review_request` notification with `item_count = 2`; queue
  endpoint returns both, oldest first, `upload_id` filter works.
- Resolve partial (outcome only, differing value) → `trace_analysis`
  outcome = answer / 1.0 / `human`, machine failure_mode nulled per
  decision 6 when applicable, item `resolved` with answer + stamps;
  matching value → `human_confirmed`; second resolve → `409`.
- Supersede: re-kick analysis with the fault still armed → old item
  `superseded`, exactly one open item, fresh context; resolved-outcome +
  re-route → outcome reasons filtered (no new item when nothing is left,
  decision 3).
- Unresolved items leave traces machine-labeled: list row still carries
  the machine outcome + `has_open_review_item` true,
  `open_review_item_id` set for the owner, null/false for a non-owner on
  a listed trace.
- Owner relabel: create → open item with empty reasons; repeat → same
  item; pending trace → `409 analysis_pending`; non-owner → 404.
- `upload_failed`: CLI-source upload (API-key auth) + permanent ingest
  fault → owner notification; same fault on a web upload → none.
- Notifications API: `unread_count`/`total`, mark-read by ids and `all`,
  idempotent; recipient-only access (other user sees nothing).

Unit:

- The provenance reason-filter (decision 3) over the reason × provenance
  matrix.
- Fault-spec parsing for the `analyze:verdict` grammar (valid/invalid).
- Resolve provenance arithmetic (decision 6) incl. the failure_mode
  coherence rule.

### Verification (done-when walkthrough)

1. Fresh `supabase db reset` + `docker compose up --build` (keyless);
   CLI-sync a directory with the fault-armed uncertain fixture.
2. Bell badge increments live (realtime); `/notifications` shows the
   per-upload digest; its link lands on `/review` filtered to the upload
   group.
3. Open an item: split view, machine verdict shown as context, nothing
   pre-selected; resolve outcome → trace detail + `/traces` row show the
   solid human badge, confidence 1.0; "Resolve & next" walks the batch.
4. Unresolved items: the trace stays machine-labeled and filterable
   (outcome badge outline on lists), needs-review indicator links to the
   item.
5. Relabel from trace detail on an analyzed trace; confirm
   `human_confirmed` when matching the machine value.
6. Re-kick analysis on a trace with an open item → superseded + fresh
   item, never two open.
7. CLI-sync a bad file → `upload_failed` notification → `/uploads` row.
8. Live key (manual, like A2): a genuinely uncertain B2 fixture routes
   with real reasons end to end.
9. Integration + unit suites green; ruff + format clean; `tsc`, eslint,
   `next build` clean.

## Drift

- **Filter placement.** The plan had the worker filter reasons against the
  prior row, with `rewrite` forwarding prior provenances. Implemented
  inside `rewrite` itself instead (`queries/analysis.py:filter_reasons`,
  applied to the post-carryover provenances of the row being written):
  same semantics — carryover swaps human triplets in before the filter
  runs — but one read, no race window, and the filter sits next to the
  carryover it depends on. The worker passes unfiltered reasons in a
  `RoutingContext`. Local imports inside `rewrite` break the queries-module
  cycle (review_items/notifications import analysis for the label
  vocabulary).
- **Payloads gained filenames.** `review_request` and `upload_failed`
  notification payloads carry `filename`, and review-item rows carry
  `upload_filename` (one extra join) — digest copy, queue group headers,
  and the resolve header render without client-side joins. Additive.
- **Resolve response carries the written labels.** `POST …/resolve`
  returns a `labels` map (value, confidence, provenance per answered
  field) alongside the item, so the post-resolve UI shows per-field
  provenance without a second analysis fetch.
- **Superseded items 409 with their own code.** The spec names
  `409 already_resolved` for resolved items and is silent on superseded;
  resolving a superseded item returns `409 item_superseded` rather than
  lying with `already_resolved`.
- **TraceInspector loading split.** Extracting `TraceEvidence`
  (decision 10) moved span loading into the shared component; the trace
  page now shows its header as soon as the trace loads, with the span
  tree loading independently below — a side effect, and a better one.
- `shadcn add select` for the resolve form's two selects (first use of a
  select in the app).

## Outcome

Done-when, verified on the rebuilt compose stack (keyless, migration 9
applied via `supabase migration up`):

- **Uncertain fixtures → digested notifications + queue items with
  plain-language reasons:** `test_routing_creates_items_and_one_digest`
  — two uncertain traces in one upload produce two open items (reason
  messages verbatim from B2's `route()`), exactly one unread
  `review_request` digest with `item_count = 2`, bell count via
  `unread_count`, queue filtered by `upload_id`.
- **Resolving updates labels with human provenance:**
  `test_resolve_writes_provenance` (differ → `human`, 1.0, surfaces on
  analysis + list rows), `test_matching_machine_answer_confirms`
  (`human_confirmed`), `test_non_failure_outcome_nulls_machine_failure_mode`
  (coherence rule), repeats 409, foreign access 404.
- **Unresolved items leave traces machine-labeled and filterable:** the
  routing test lists the trace and checks a second user's marketplace
  card — machine outcome intact, `has_open_review_item` false,
  `open_review_item_id` null for non-owners.
- Supersede + the human filter (`test_reroute_supersedes_then_human_filter
  _stops_routing`), owner relabel incl. `analysis_pending`
  (`test_owner_relabel`), taxonomy validation, `upload_failed` CLI-only
  with idempotent recipient-scoped mark-read.

Suites: backend 309 passed (unit incl. the new filter/grammar/arithmetic
matrices in `tests/unit/test_hil.py`, integration incl.
`tests/integration/test_hil.py`); ruff check + format clean; web `tsc`,
eslint, `next build` clean. Live-key routing on a genuinely uncertain
fixture remains a manual step, as in A2. Click-through (bell realtime,
split view, Resolve & next) left to the operator; the demo script is
`docs/demos/hil-loop.md`.
