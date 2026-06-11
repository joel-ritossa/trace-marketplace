# Pages

New routes plus deltas to stage-1 pages. Stage-1 UI law carries over unchanged: real status verbatim, visibility always visible, the UI never enforces access, not-found covers no-access. Interaction law lives in `docs/ux-principles/` (cited, not duplicated). All routes require a session (JWT — API keys never touch pages).

## Route Map (New)

| Route | Purpose |
|---|---|
| `/review` | HIL queue: traces the analyzers were uncertain about. |
| `/review/[itemId]` | Resolve one item: judge a trace (outcome, failure_mode, category). |
| `/notifications` | Notification history; the bell in the shell is a badge + link (no popover). |
| `/subscriptions` | Manage saved queries. |
| `/subscriptions/[id]` | Subscription feed: live matches, backfill, multi-select → bulk acquire. |
| `/settings` | API keys (mint/revoke) + profile display name. |
| `/uploads` | Upload history; the surface for CLI uploads that failed unattended. |

Nav: Review, Subscriptions, Settings join the primary nav; the bell (unread badge, navigates to `/notifications`) joins the shell edge. `/uploads` is secondary — linked from `/upload` and `/traces`, not a nav slot. Opened surfaces are routes, never overlays; transient confirms/dialogs are the only overlay UI (`docs/ux-principles/navigation/routing.md`).

## New Pages

### /review

- Queue rows: trace identity, machine verdict + confidence, **routing reason in plain language** (indeterminate / low confidence with value / signals disagree with judge / uncertain category), item age. Oldest-first.
- Bulk syncs group by upload ("12 from upload X", expandable), mirroring the notification digest.
- Advisory framing throughout — review improves labels, it gates nothing; no alarm styling.
- States: loading, empty (positive), results, grouped-bulk.

### /review/[itemId]

- Split view: trace evidence (same inspection components as `/traces/[id]`) beside the verdict form; the reviewer never leaves the screen.
- Machine verdict, confidence, routing reason shown as context — **never pre-selected** in the form.
- Form mirrors the label model exactly: ternary outcome (indeterminate is a valid answer, not a skip); failure_mode select (10 categories, one-line descriptions) only when failure chosen; task_category independent. No free text, no scales.
- Resolve commits with provenance; post-resolve shows per-field provenance + confidence 1.0. Partial resolution allowed. "Resolve & next" is primary within a batch.
- Owner-initiated relabel from trace detail reuses this view (same route, self-created item).
- States: loading, already-resolved (read-only with who/when), trace-deleted (item void, stated), form-error.

### /notifications + bell

- Bell: unread count badge; clicking navigates to `/notifications`. One notifications surface — linkable, refreshable, back-button-correct.
- Types: `review_request` (digested per upload), `subscription_match` (grouped per subscription), `upload_failed` (CLI only).
- Every notification links to its object: review_request → queue filtered to the upload group; subscription_match → trace or feed; upload_failed → `/uploads` row. No dead ends.
- Mark-all-read; read items remain listed (history, not inbox-zero).
- States: empty (positive), unread mix, all-read.

### /subscriptions

- List: name, **query rendered as the same filter chips as search**, match stats, last-match time; inline rename/edit/delete.
- Creation is not primary here: subscriptions are born on list pages via "Save as subscription" over the live filter state, with a backfill preview before confirming. This page manages.
- Delete confirms by name and states consequences (notifications stop; library unaffected).
- States: loading, empty (points at marketplace search), results.

### /subscriptions/[id]

- Header: name, query as chips (editable — editing visibly re-runs the feed), match count, manage actions.
- Body: stored query executed live (backfill for free), new-since-last-seen divider, marketplace-style cards.
- Multi-select + persistent bulk bar → bulk acquire: confirm states final count; result itemized ("8 acquired · 2 already in library · 2 no longer listed"). **No auto-acquire toggle may exist.**
- States: loading, no-matches-yet (distinct from empty marketplace — the rule is fine, nothing matches *yet*), results, error.

### /settings

- **API keys:** mint (name it) → plaintext shown exactly once — monospace, copy button, "you won't see this again", dismissed only by user action; reveal includes the CLI usage snippet with the key inlined. List: name, `key_display`, created, `last_used_at` ("never used" explicit), scope stated (upload-only); revoke per-row with consequence-stating confirm.
- **Profile:** display name, inline edit (consumer-facing on marketplace cards).
- **Privacy:** "Allow LLM analysis of private traces" toggle (default on), with honest consequence copy both ways: on = private-trace content is sent to the configured LLM provider for labeling; off = private traces get deterministic signals only until listed (listing always analyzes). Plain statement, no alarm styling; takes effect on subsequent analysis runs, and the copy says so.
- States: empty key list (mint as the empty-state action, links CLI setup), list, reveal, post-revoke.

### /uploads

- Table: filename, source (`cli`/`web`), status, `error_message` verbatim, created/processed, link to created traces. Backed by `GET /v1/uploads` (stage 1 already returns everything needed).
- Once A5 lands: redaction counts per upload (e.g. "4 emails, 1 API key masked"), from `uploads.redaction_counts` ([7_redaction.md](7_redaction.md)). Zero replacements shows nothing.
- The honest surface for watch-mode failures: a failed CLI upload never becomes a trace and is invisible everywhere else.
- States: loading, empty, results, failed rows visually flagged.

## Deltas To Stage-1 Pages

### /traces/[traceId] — Analysis section

- A third section between the metadata header and the span tree. Header keeps a compact label strip (outcome / failure_mode / task_category badges with provenance + confidence) for triage; the section is the full view.
- Contents in disclosure order: labels with per-field provenance + confidence → judge reasoning → deterministic signals → metric scores (flag/score + reason each). Audit details (analyzer versions, model id, stored votes) behind a collapsed disclosure.
- Owner-initiated relabel entry point lives here (routes to the resolve view).
- The section always renders, with explicit non-result states (below).

### Analysis states — never a lie

| State | Rendering |
|---|---|
| `pending` | "Analysis pending" (queued/running — it will arrive). |
| `complete` | Results render. |
| `skipped` | Reason-specific, never generic: `not_configured` → "Judge not configured"; `owner_opt_out` → "LLM analysis is off for your private traces" (links to `/settings` for the owner). Deterministic signals still shown. Never a false "pending". |
| `failed` | Real reason, verbatim. |

Filter-exclusion notes ("N not-yet-analyzed traces excluded") use the same state.

### Labels at list level (marketplace cards, /traces rows, feed cards)

- **Outcome + provenance only:** one outcome badge whose variant encodes provenance (solid = human/human_confirmed, outline = machine), confidence as secondary text on the badge — rendered as the raw number (`0.84`), not bucketed.
- `failure_mode`, `task_category`, metric scores: filterable but not rendered at list level.
- Unanalyzed traces show a quiet "not analyzed" placeholder, visually distinct from a verdict.

### Filter controls

- Numeric predicates get a **threshold control, min-bound only** (number input with a `≥` affordance) — no dual-handle sliders. Chips render the predicate verbatim: `faithfulness ≥ 0.8 ×`.
- `metric_scores` keys are enumerated from observed data, not hardcoded.
- One filter language: chips and the filter component are the same artifacts on search pages, subscription rows, and feed headers.

### /traces (My Traces) at sync scale

- **Pagination UI** on every list surface (standard pager, no infinite scroll; API already paginates).
- New **analysis column**: outcome badge or pending/skipped state, plus a needs-review indicator linking to the review item.
- **Bulk listing (batched consent):** multi-select → "List N traces" → one confirmation dialog with the same ownership-consent copy, naming the exact count, requiring the affirmative checkbox once for the batch. Operates only on an explicit selection — no "list all" shortcut. Per-trace listing on the detail page unchanged. Bulk-unlist included for symmetry.

### /library

- Bulk-selection → "Download N": zip of payloads (scrubbed for acquired traces, raw for own — [7_redaction.md](7_redaction.md)) + `labels.jsonl` covering the selection. Same artifact offered at the bulk-acquire confirmation moment ("Acquired 50 — download now").
- Single-trace download unchanged in UI; serves per the same redaction boundary.

### /upload

- Links to `/uploads` ("history"). Poll loop unchanged.

## Cross-Cutting

- All new list surfaces paginate from day one.
- Flood control is a system property: digests at the source (per upload, per subscription), grouping in queue and notifications list — the first big CLI sync is the stress test everywhere.
- URL carries view state: filters, search, pagination serialize into the URL on every list surface, including feeds.
- **Live surfaces use Supabase Realtime as an invalidation signal only.** The web app subscribes to `postgres_changes` on its own rows (RLS-enforced) and refetches through the API on change — row payloads from the socket are never consumed as data; the API stays the single read path. Web only (the CLI keeps polling per [5_cli.md](5_cli.md)). Wired surfaces: `/uploads` status flips (A1), the notification bell + `/notifications` (A3); later surfaces opt in with the same hook. Realtime is an enhancement layer — every surface must remain correct with the socket disconnected (load/refetch paths unchanged).
