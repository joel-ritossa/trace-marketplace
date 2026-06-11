# Stage 2 UI — New Surfaces

The pages stage 2 adds, at spec-shaping level — the companion to [ui-deltas.md](ui-deltas.md) (which covers mutations to existing stage-1 pages). Mirrors the shape of `spec/stage-1/4_pages.md`; interaction law for each surface lives in `ux-principles/` (cited per page, not duplicated). Promote with `infra.md` + `judging/`.

All routes require a session (JWT — API keys are upload-only and never touch these pages).

## Route map

| Route | Purpose |
|---|---|
| `/review` | HIL queue: traces the analyzers were uncertain about. |
| `/review/[itemId]` | Resolve one item: judge a trace (outcome, failure_mode, category). |
| `/notifications` | Notification history; the bell in the shell is a badge + link to it (no popover). |
| `/subscriptions` | Manage saved queries. |
| `/subscriptions/[id]` | Subscription feed: live matches, backfill, multi-select → bulk acquire. |
| `/settings` | API keys (mint/revoke) + profile display name. |
| `/uploads` | Upload history; the surface for CLI uploads that failed unattended (ui-deltas §4). |

Nav: Review, Subscriptions, Settings join the primary nav; the bell joins the shell edge (`ux-principles/navigation/app_shell.md`). `/uploads` is secondary — linked from `/upload` and `/traces`, not a nav slot.

## Page specs

### /review

- Queue rows: trace identity, machine verdict + confidence, **routing reason in plain language** (indeterminate / low confidence with value / signals disagree with judge / uncertain category), item age. Oldest-first.
- Bulk syncs group by upload ("12 from upload X", expandable), mirroring the notification digest.
- Advisory framing throughout — review improves labels, it gates nothing; no alarm styling (`ux-principles/review-queue/queue.md`).
- States: loading, empty (positive — "nothing needs review"), results, grouped-bulk.

### /review/[itemId]

- Split view: trace evidence (same inspection components as `/traces/[id]` — metadata header + span tree) beside the verdict form. The reviewer never leaves the screen.
- Machine verdict, confidence, and routing reason shown as context — framed as "the machine's take", **never pre-selected** in the form.
- Form mirrors the label model exactly: ternary outcome (indeterminate is a valid answer, not a skip); failure_mode select (10-category, one-line descriptions) only when failure chosen; task_category independent. No free text, no scales (`ux-principles/review-queue/labeling.md`).
- Resolve commits with provenance; post-resolve shows per-field provenance + confidence 1.0. Partial resolution allowed. "Resolve & next" is primary within a batch.
- Owner-initiated relabel from trace detail reuses this view (same route, self-created item).
- States: loading, already-resolved (read-only with resolution + who/when), trace-deleted (item void, stated), form-error.

### /notifications + bell

- Bell: unread count badge in the shell edge; clicking **navigates to `/notifications`** — no popover panel. Routed page over ephemeral overlay (URL-carries-state rule in `ux-principles/navigation/routing.md`): one notifications surface, linkable, refreshable, back-button-correct.
- Types in base: `review_request` (digested per upload), `subscription_match` (grouped per subscription), `upload_failed` (CLI uploads only — ui-deltas §4).
- Every notification links to its object: review_request → queue (filtered to the upload group); subscription_match → trace or feed; upload_failed → `/uploads` row. No dead ends (`ux-principles/notifications/notifications.md`).
- Mark-all-read; read items remain listed (history, not inbox-zero).
- States: empty (positive), unread mix, all-read.

### /subscriptions

- List of saved queries: name, **query rendered as the same filter chips as search**, match stats, last-match time; inline rename/edit/delete.
- Creation is not primary here: subscriptions are born on `/traces`-style list pages via "Save as subscription" over the live filter state, with a backfill preview before confirming (`ux-principles/search/saved_queries.md`). This page manages, it doesn't author from blank.
- Delete confirms by name and states consequences (notifications stop; library unaffected).
- States: loading, empty (points at marketplace search + "Save as subscription"), results.

### /subscriptions/[id]

- Header: name, query as chips (editable — editing visibly re-runs the feed), match count, manage actions.
- Body: stored query executed live (backfill for free), new-since-last-seen divider, marketplace-style result cards.
- Multi-select + persistent bulk bar → bulk acquire: confirm states final count; result is itemized ("8 acquired · 2 already in library · 2 no longer listed"). **No auto-acquire** (locked decision; no such toggle may exist).
- A trace may start matching only after analysis fills the field its rule uses — the visible chips are what keep that self-explaining.
- States: loading, no-matches-yet (distinct from empty marketplace: the rule is fine, nothing matches *yet*), results, error.

### /settings

- **API keys:** mint (name it) → plaintext shown exactly once — monospace, copy button, "you won't see this again", dismissed only by user action; reveal includes the CLI usage snippet with the key inlined (the key is mid-task; the goal is a working sync). List shows name, prefix/last-4, created, `last_used_at` ("never used" explicit), scope stated (upload-only); revoke per-row with consequence-stating confirm (`ux-principles/settings/api_keys.md`).
- **Profile:** display name, inline edit (consumer-facing on marketplace cards — ui-deltas §9).
- States: empty key list (mint as the empty-state action, links CLI setup docs), list, reveal, post-revoke.

### /uploads

- Table: filename, source (`cli`/`web`), status, `error_message` verbatim, created/processed, link to created traces (complete) — backed by the existing `GET /v1/uploads` (status + error fields already in stage 1; only the page is new).
- The honest surface for watch-mode failures: a failed CLI upload never becomes a trace and is invisible everywhere else.
- States: loading, empty, results, with failed rows visually flagged.

## Cross-cutting

- Stage-1 UI law carries over unchanged: real status verbatim, visibility always visible, UI never enforces access, not-found covers no-access.
- One filter language: chips and the filter component are the same artifacts on search pages, subscription rows, and feed headers — a filter added anywhere appears everywhere (`ux-principles/search/filtering.md`).
- All new list surfaces paginate from day one (ui-deltas §6).
- Flood control is a system property, not per-page: digests at the source (per upload, per subscription), grouping in the queue and panel — the first big CLI sync is the stress test everywhere.

## Open questions

None. (Settled: opened surfaces are routes, not overlays — the bell links to `/notifications` rather than opening a popover, and `/review/[itemId]` is a real route. Anything that opens a distinct view gets a URL; transient confirms/dialogs are the only overlay UI.)
