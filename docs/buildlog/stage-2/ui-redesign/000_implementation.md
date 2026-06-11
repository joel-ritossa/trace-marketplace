# UI Redesign — Implementation

Implements the approved `docs/proposals/ui-redesign.md` (phases 1–4 + multi-file upload). Phase 5 (subscriptions pages, bulk surfaces) is A4's scope and lands separately; this pass wires A4's already-built components (selection, bulk bar, bulk actions, save-subscription) into the new unified list so A4 lands on the new foundation.

## Plan

1. **Spec amendments first** (spec stays normative): `docs/spec/stage-2/4_pages.md` — sidebar shell + groups, `/uploads` merge with multi-file dropzone, `/upload` redirect, unified list rows replacing marketplace/library cards (incl. the subscription feed), trace-detail regions. `DESIGN.md` adaptation — sidebar nav chrome, amend the `card-marketing` result-card density rule to the unified row spec. `.env.example` — `NEXT_PUBLIC_UPLOAD_MAX_FILES`.
2. **Shell**: left sidebar (Workspace: Traces, Uploads, Review+open-count badge; Marketplace: Browse, Library; footer: Settings) + top bar (breadcrumb honoring `?from=`, bell, account menu). Brand mark component + `app/icon.svg` favicon. Content measures: full (detail/resolve), `max-w-6xl` (lists), `max-w-2xl` (settings). Width-escape hacks removed.
3. **Unified trace list**: one `TraceList` row table for `mine` / `marketplace` / `acquired` scopes (+ `newIds` support for the A4 feed). Filter bar on all three list pages (Library gains it). Wire selection + bulk: list/unlist on Traces, acquire + SaveSubscription on Browse, download on Library. `trace-cards.tsx` deleted.
4. **Uploads merge**: dropzone band (multiple files, up to `NEXT_PUBLIC_UPLOAD_MAX_FILES`, sequential upload, per-file status, shared poll) + full history table on `/uploads`; `/upload` redirects.
5. **Trace detail relayout**: header strip (identity badges + actions cluster: download, acquire, owner dropdown for list/unlist/delete), collapsible overview (metadata grid + owner tags/description + analysis), full-width evidence, contextual back via `?from=`.
6. Verify: `pnpm lint`, `pnpm build`; record outcome.

## Coordination with A4 (in flight)

A4 landed concurrently during this pass — its bulk wiring, `ExcludedNote`, `SaveSubscription`, and the `/subscriptions` pages appeared in the working tree mid-implementation. The redesign absorbed them rather than racing them: the subscriptions pages got their sidebar slot, the feed page migrated to the unified list, and the A4 bulk components are wired into the unified list pages.

## Drift

- Multi-file upload cap raised from the planned 10 to **50** at user request; recorded in `.env.example` with the rate-limit rationale (50 sequential < 60/min per-user upload limit).
- Plan said "Sidebar omits Subscriptions until A4 lands" — A4's pages landed mid-pass, so the item shipped here instead.
- `BulkAcquireAction` was wired on Browse (proposal scope) in addition to A4's feed wiring; both reuse the same component.
- Subscription feed's local "← Subscriptions" back link removed — the top-bar breadcrumb (with `?from=` support and a "Feed" leaf) covers it.
- `Selection` type moved from the deleted `traces-table.tsx` into `trace-list.tsx`.
- Notifications `subscription_match` deep link now carries `?from=notifications` for the contextual breadcrumb.
- Docs touched beyond plan: `README.md` quickstart and two demo files referenced the old Upload page / "My Traces" naming.

## Outcome

- `pnpm lint` clean; `pnpm build` (Next 16 + TypeScript) clean; route table confirms `/upload` survives only as a redirect and all pages render under the new shell.
- Shipped: sidebar shell (Workspace / Marketplace groups, review open-count badge, brand mark + SVG favicon), top bar with contextual breadcrumb, three content measures (width-escape hacks deleted), unified `TraceList` across Traces / Browse / Library / feed (cards and old table deleted), filter bar on Library, merged `/uploads` with a multi-file dropzone (sequential per-file uploads, shared poll loop, cap notice), trace-detail header strip + collapsible overview + full-width evidence, `?from=` contextual back links from Browse / Library / feed / notifications.
- Click-through verification left to the user per testing rules (no browser automation).
