# Pages

Next.js app router. All routes except `/` and auth require a session. Seven routes total.

## Route Map

| Route | Purpose |
|---|---|
| `/` | Entry: sign in / sign up, or straight to library when signed in. |
| `/upload` | Contributor upload flow. |
| `/traces` | My Traces: the caller's own uploads (private + listed). |
| `/traces/[traceId]` | Trace detail: metadata, span inspection, visibility controls, acquire, download. |
| `/marketplace` | Consumer discovery over listed traces. |
| `/library` | My Library: traces the caller has acquired. |
| `/auth/*` | Supabase auth pages/callbacks as needed. |

## Page Specs

### /upload

- File picker + drop zone, single JSON file.
- On submit: client-side size check, then `POST /v1/uploads`, then poll `GET /v1/uploads/{id}` until terminal status.
- States to render: idle, uploading, `received`/`processing` (spinner with status text), `complete` (links to created traces), `failed` (the `error_message`, verbatim), duplicate (link to the existing upload), partial success (`parse_warnings` shown next to the success state).

### /traces

- Table of the caller's traces: name, created, span count, errors, duration, model, visibility badge.
- Search box and filters backed by `GET /v1/traces?scope=mine`.
- States: loading, empty ("upload your first trace" pointing at `/upload`), results, no-results-for-query (shows the active query/filters).

### /traces/[traceId]

The core inspection surface. Three sections:

1. **Header / metadata**: name, status, duration, span/error counts, provider, model, service, tools, tags, description, provenance (source format, importer version, upload link), visibility state.
2. **Span tree**: full hierarchy reconstructed from parent IDs, every span shown. Each node: name, kind badge, duration, status. Selecting a span opens a detail panel: timings, status message, error type, model/provider/tool, token counts, full raw `attributes` (pretty-printed JSON), and `events` list. No span data is hidden from users with access.
3. **Actions**, driven by the `is_owner` / `acquired` / `can_download` flags from the API:
   - Owner: edit tags/description; visibility toggle private ↔ listed with the ownership-confirmation checkbox; delete with confirm; download.
   - Listed, not acquired (owner or not): **Acquire** button (labeled as a free acquisition) → `POST /v1/traces/{id}/acquire`; for non-owners the download button shows disabled with "acquire to download".
   - Acquired: **Download** button → `GET /v1/traces/{id}/download`, plus an "saved" badge.

States: loading, not found (covers no-access by design), error-status trace (error spans visually flagged in the tree), large trace (spans paginated/lazy-loaded past 500).

### /marketplace

- Same result-card list as `/traces` but `scope=marketplace`, plus contributor display name, listed date, and an "saved" badge on already-acquired cards.
- Search + filters (provider, model, tool, has-errors, date range).
- Cards link to `/traces/[traceId]`; acquire and download happen there.
- States: loading, empty marketplace, results, no-results-for-query.

### /library

- Result cards for `scope=acquired`: the consumer's acquired catalog, with acquired date and direct download per card.
- States: loading, empty ("browse the marketplace" pointing at `/marketplace`), results.

## Cross-Cutting UI Rules

- Ingestion progress and failures are always shown with their real status and message — no generic "something went wrong" where the API gives a reason.
- Visibility is always visible: every trace rendering carries a `private`/`listed` badge.
- The UI never enforces access itself; it renders what the API returns and explains 4xx reasons.
