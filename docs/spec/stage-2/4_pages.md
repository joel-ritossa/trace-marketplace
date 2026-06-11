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

Nav (per the approved `docs/proposals/ui-redesign.md`): a fixed left sidebar with two labeled groups carrying the supply/demand mental model — **Workspace**: Traces (`/traces`, with an Uploads tab at `/uploads` — one nav item, two link-tabs, so users navigate "my data" without first learning the ingest pipeline), Review (`/review`, open-count badge) — **Marketplace**: Browse (`/marketplace`), Subscriptions (`/subscriptions`), Library (`/library`) — plus a Settings footer item. The sidebar collapses to an icon rail on narrow viewports. A slim top bar carries a contextual breadcrumb on the left and the bell (unread badge, navigates to `/notifications`) plus account menu on the right; the brand mark links to `/`. `/upload` no longer exists as a page — it redirects to `/uploads`, which is now the single ingest surface (dropzone + history, below). Opened surfaces are routes, never overlays; transient confirms/dialogs are the only overlay UI (`docs/ux-principles/navigation/routing.md`).

Content measures, set per page — no page escapes its container: full width (trace detail, review resolve), wide `max-w-6xl` (all list surfaces), narrow `max-w-2xl` (settings).

## New Pages

### /review

- Queue rows: trace identity, machine verdict + confidence, **routing reason in plain language** (indeterminate / low confidence with value / signals disagree with judge / uncertain category), item age. Newest-first.
- Bulk syncs group by upload ("12 from upload X", expandable), mirroring the notification digest.
- Advisory framing throughout — review improves labels, it gates nothing; no alarm styling.
- States: loading, empty (positive), results, grouped-bulk.

### /review/[itemId]

- Split view: trace evidence (same inspection components as `/traces/[id]`) beside the verdict form; the reviewer never leaves the screen.
- Evidence defaults to the conversation view (a chat-style reconstruction of LLM messages and tool calls, deduped across replayed history) so a reviewer can read and score without span literacy; the span tree + details panel sits behind a Conversation/Spans toggle.
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
- Two creation paths, one vocabulary: "Save as subscription" over the live filter state on Browse, and a "New subscription" dialog here (the same filter fields, an explicit search-to-preview of the live match count, then save). Both preview the backfill before confirming.
- Delete confirms by name and states consequences (notifications stop; library unaffected).
- States: loading, empty (points at marketplace search), results.

### /subscriptions/[id]

- Header: name, query as chips (editable — editing visibly re-runs the feed), match count, manage actions.
- Body: stored query executed live (backfill for free), new-since-last-seen marker, rendered with the unified trace list (below).
- Multi-select + persistent bulk bar → bulk acquire: confirm states final count; result itemized ("8 acquired · 2 already in library · 2 no longer listed"). **No auto-acquire toggle may exist.**
- States: loading, no-matches-yet (distinct from empty marketplace — the rule is fine, nothing matches *yet*), results, error.

### /settings

- **API keys:** mint (name it) → plaintext shown exactly once — monospace, copy button, "you won't see this again", dismissed only by user action; reveal includes the CLI usage snippet with the key inlined. List: name, `key_display`, created, `last_used_at` ("never used" explicit), scope stated (upload-only); revoke per-row with consequence-stating confirm.
- **Profile:** display name, inline edit (consumer-facing on marketplace cards).
- **Privacy:** "Allow LLM analysis of private traces" toggle (default on), with honest consequence copy both ways: on = private-trace content is sent to the configured LLM provider for labeling; off = private traces get deterministic signals only until listed (listing always analyzes). Plain statement, no alarm styling; takes effect on subsequent analysis runs, and the copy says so.
- States: empty key list (mint as the empty-state action, links CLI setup), list, reveal, post-revoke.

### /uploads

- The single ingest surface: a dropzone band on top, the full paginated history below. The stage-1 `/upload` page is merged in; `/upload` redirects here. Rendered as the second tab of the Traces workspace surface (own URL, shared header), not a separate nav item.
- Dropzone accepts **multiple files** (up to `NEXT_PUBLIC_UPLOAD_MAX_FILES`, local-demo default 50 — under the per-user upload rate limit). Each file is its own `POST /v1/uploads` — the single-file API contract is unchanged — uploaded sequentially with per-file status (uploading / processing / complete / failed / rejected, real reasons verbatim, duplicates included). Extra files beyond the cap are rejected client-side with the cap stated.
- Table: filename, source (`cli`/`web`), status, `error_message` verbatim, created/processed, link to created traces. Backed by `GET /v1/uploads` (stage 1 already returns everything needed).
- Once A5 lands: redaction counts per upload (e.g. "4 emails, 1 API key masked"), from `uploads.redaction_counts` ([7_redaction.md](7_redaction.md)). Zero replacements shows nothing.
- The honest surface for watch-mode failures: a failed CLI upload never becomes a trace and is invisible everywhere else.
- States: loading, empty, results, failed rows visually flagged.

## Deltas To Stage-1 Pages

### Unified trace list (all list surfaces)

One trace-list component renders every trace list — `/traces`, `/marketplace`, `/library`, subscription feeds — as dense rows (per DESIGN.md density rules), replacing the stage-1 table/cards split. Scope drives the deltas:

- *Traces (mine)*: visibility badge, analysis column + needs-review link; bulk select → batched-consent list/unlist.
- *Browse (marketplace)*: contributor display name, in-library badge; bulk select → bulk acquire; populated filter bar grows "Save as subscription".
- *Library*: acquired date, per-row download; bulk select → bulk download.
- *Subscription feed*: Browse columns + the new-since-last-seen marker.

The same search/filter/sort bar (full analysis vocabulary, verbatim chips, URL-serialized) appears on all of them — Library included.

### /traces/[traceId] — layout

Three regions, full content width: a header strip (status, name, visibility + outcome badges, and one actions cluster — download, acquire, owner manage actions), a collapsible overview region (metadata grid, owner tags/description editing, the Analysis section), and the evidence region taking the remaining width — a Conversation/Spans toggle, conversation (chat-style reconstruction) by default, span tree + detail panel behind it. Back navigation is contextual: list surfaces pass their origin (`?from=`), and the breadcrumb/back link honors it, falling back by ownership.

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

### Labels at list level (all unified-list rows)

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
- **Bulk listing (batched consent):** multi-select → "List N traces" → one confirmation dialog with the same ownership-consent copy, naming the exact count, requiring the affirmative checkbox once for the batch. Operates only on an explicit selection of visible rows — a header checkbox may select all rows *on the current page*, but no "all matching" shortcut over unseen rows exists. Per-trace listing on the detail page unchanged. Bulk-unlist included for symmetry.

### /library

- Bulk-selection → "Download N": zip of payloads (scrubbed for acquired traces, raw for own — [7_redaction.md](7_redaction.md)) + `labels.jsonl` covering the selection. Same artifact offered at the bulk-acquire confirmation moment ("Acquired 50 — download now").
- Single-trace download unchanged in UI; serves per the same redaction boundary.

### /upload

- Merged into `/uploads` (above); the route remains only as a redirect.

## Cross-Cutting

- All new list surfaces paginate from day one.
- Flood control is a system property: digests at the source (per upload, per subscription), grouping in queue and notifications list — the first big CLI sync is the stress test everywhere.
- URL carries view state: filters, search, pagination serialize into the URL on every list surface, including feeds.
- **Live surfaces use Supabase Realtime as an invalidation signal only.** The web app subscribes to `postgres_changes` on its own rows (RLS-enforced) and refetches through the API on change — row payloads from the socket are never consumed as data; the API stays the single read path. Web only (the CLI keeps polling per [5_cli.md](5_cli.md)). Wired surfaces: `/uploads` status flips (A1), the notification bell + `/notifications` (A3), the trace list surfaces + trace detail including the Analysis section (`traces` + `trace_analysis` tables — new traces landing and verdicts appearing live); later surfaces opt in with the same hook. Realtime is an enhancement layer — every surface must remain correct with the socket disconnected (load/refetch paths unchanged).
