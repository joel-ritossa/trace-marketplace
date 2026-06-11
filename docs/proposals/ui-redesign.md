# UI Redesign Proposal — Structure & Layout

Status: **proposal, not spec**. Nothing here is normative until it's agreed and folded into `docs/spec/stage-2/4_pages.md` (and `DESIGN.md` where noted). Interaction law in `docs/ux-principles/` and the cross-cutting rules in the page specs stay in force unless explicitly amended below.

## Why

The UI was built slice-by-slice and it shows. The pages are individually fine; the product they add up to is incoherent:

1. **No mental model in the navigation.** Six peer links in a flat header (`Marketplace · Library · My Traces · Upload · Review · Settings`) hide the product's actual shape: one account that wears two hats — *supplying* trace data and *consuming* it. The nav presents publish-side and acquire-side surfaces as interchangeable siblings.
2. **Orphaned pages.** `/uploads` and `/notifications` exist but aren't in the nav — reachable only via a subtitle link, a post-upload link, or the bell. Two of the product's most operationally important surfaces (did my CLI sync fail? what needs my attention?) are hidden.
3. **Three list UIs for one entity.** Traces render as a dense table on `/traces`, cards on `/marketplace`, and cards-without-filters on `/library`. Same entity, three layouts, asymmetric capabilities (Library has no search/filters at all).
4. **The shell fights its own content.** The app shell is `max-w-5xl`, but the two most important surfaces — trace inspection and review resolve — escape it with a `w-screen -translate-x-1/2` hack. The product's core surface is a wide, dense inspector; the shell was designed for a narrow content site.
5. **Duplicated/confusing concepts.** `/upload` (the action) and `/uploads` (the history) are separate pages where the first embeds a truncated copy of the second. "My Traces" vs "Upload" vs "Uploads" is three labels for two concepts.
6. **No home for what's coming.** Subscriptions (slice A4: saved queries, match feeds, bulk acquire) have no place to live in a flat 6-item header. Bulk selection, filter chips, and "save this search" need a coherent discovery surface, not another nav item bolted on.
7. **Navigation dead ends.** Trace detail hardcodes "← Traces" regardless of whether you arrived from the marketplace, library, review, or a notification. The product title isn't a link. New users land on an empty My Traces page.

## The mental model

Everything in the product is one pipeline viewed from two sides:

```
  SUPPLY                                              DEMAND
  capture → ingest → analyze → review → publish  →   discover → subscribe → acquire → download
  (CLI/web)  (uploads)  (labels)  (HIL)   (list)      (marketplace) (saved queries) (library)
```

The redesign makes this the literal structure of the UI: a **Workspace** group (your data moving through the supply pipeline) and a **Marketplace** group (everyone's listed data moving toward your library), plus cross-cutting chrome (notifications, settings, account).

## Proposed structure

### App shell: sidebar, not header

Replace the flat header nav with a **fixed left sidebar** and a slim top bar. This is the standard shape for data-dense workspace products, and it directly fixes problems 1, 2, 4, and 6:

```
┌────────────┬──────────────────────────────────────────────┐
│ ⬡ Trace    │  top bar: page title / breadcrumb   🔔  👤  │
│ Marketplace├──────────────────────────────────────────────┤
│            │                                              │
│ WORKSPACE  │                                              │
│  Traces    │   content area — full width,                 │
│  Uploads   │   per-page max-width (see Layout)            │
│  Review  ③ │                                              │
│            │                                              │
│ MARKETPLACE│                                              │
│  Browse    │                                              │
│  Subscript.│                                              │
│  Library   │                                              │
│            │                                              │
│ ──────────│                                              │
│  Settings  │                                              │
└────────────┴──────────────────────────────────────────────┘
```

- **Sidebar** (~220 px, collapsible to icon rail on narrow viewports): two labeled groups + footer. Groups carry the supply/demand mental model; labels are flat nouns. The Review item shows a count badge for open items (same data the queue already loads).
- **Top bar**: breadcrumb/page title on the left (giving detail pages contextual "back"), notification bell and account menu on the right. The bell keeps its badge and links to `/notifications` — no popover, per the stage-2 cross-cutting rule.
- **Logo/wordmark** links to `/`.
- **New product icon**: the product currently has no mark — the header is plain text and the favicon is the Next.js default. The sidebar header, favicon, and auth pages need a proper icon: a simple geometric mark (e.g. a span-tree / trace motif) drawn in `DESIGN.md` tokens, monochrome ink so it survives both schemes, with light/dark favicon variants. No ad hoc styling — it becomes the one sanctioned brand asset.
- shadcn `sidebar` component, themed per `DESIGN.md` tokens. `DESIGN.md` §Navigation needs a small amendment for in-app sidebar chrome (active state = `canvas-soft-2` fill + `primary` left-edge indicator, matching the existing `ex-app-shell-row` pattern).

### Route map

| Route | Nav | Change from today |
|---|---|---|
| `/` | — | Redirects to `/traces` (unchanged; see Open Questions) |
| `/traces` | Workspace → **Traces** | Stays the default landing; same table, now sharing the unified list pattern |
| `/traces/[traceId]` | — | Full-width inspector by design; contextual back via breadcrumb |
| `/uploads` | Workspace → **Uploads** | **Merges `/upload` + `/uploads`**: dropzone band on top, full paginated history below, realtime refresh. `/upload` becomes a redirect. Dropzone accepts **multiple files (up to N, env-tunable)** — each file becomes its own upload record with per-file status; the single-file API contract is unchanged. CLI-sync callout links to Settings → API keys |
| `/review` | Workspace → **Review** | Unchanged scope; row chrome aligned with the unified list pattern (no native `<details>`) |
| `/review/[itemId]` | — | Unchanged scope; full-width split view by design |
| `/marketplace` | Marketplace → **Browse** | Unified list pattern with full filter bar + chips; **"Save as subscription"** action on the filter bar (A4); acquire action available from the row |
| `/subscriptions` | Marketplace → **Subscriptions** | **New (A4)**: saved queries with their predicate chips, match counts, pause/delete |
| `/subscriptions/[id]` | — | **New (A4)**: match feed using the unified list pattern; bulk select → bulk acquire |
| `/library` | Marketplace → **Library** | Gains the same search/filter bar as Browse; bulk select → bulk download (zip + `labels.jsonl`, A4) |
| `/notifications` | — (bell) | Unchanged scope; rows mark read on click |
| `/settings` | footer → **Settings** | Unchanged (API keys, profile, privacy toggle) |
| `/auth/*` | — | Unchanged |

Net: one page merged away (`/upload`), two added (A4 subscriptions — which the spec already requires), zero orphans.

### One trace list pattern

Replace the table/cards split with a single **trace list** component used by Traces, Browse, Library, and subscription feeds. One layout, one source of truth, scope-driven configuration:

- **Shape**: dense rows (the current `/traces` table is the right density per `DESIGN.md` §Density Rules), not marketing cards. Each row: name + mono trace ID, provider/model, span/error counts, duration, age, **outcome badge with provenance variant** (the only list-level label, per the cross-cutting rule), and scope-specific columns/actions.
- **Per-scope deltas**:
  - *Traces (mine)*: + visibility badge, analysis state, needs-review link; row actions list/unlist; bulk select → batched-consent listing.
  - *Browse*: + contributor display name, acquired/in-library badge; row action acquire ($0); bulk select → bulk acquire.
  - *Library*: + acquired date; row action download; bulk select → bulk download.
  - *Subscription feed*: Browse columns + matched-at.
- **Filter bar everywhere**: the same search + filter + sort bar (today only on `/traces` and `/marketplace`) appears on all four surfaces, including the stage-2 analysis predicates (`outcome=`, `failure_mode=`, `metric=faithfulness>=0.8`, …). Active predicates render as **chips, verbatim**, URL-serialized — one vocabulary across search and subscriptions, exactly as `3_api.md` defines it. On Browse, the populated filter bar grows the "Save as subscription" button.
- **Bulk selection** is built into the pattern once (checkbox column appears when the scope has a bulk action), instead of being retrofitted three times for A4.

This supersedes `DESIGN.md`'s "marketplace/library result cards: `card-marketing` chrome" density rule — that line gets amended to the row spec above.

### Trace detail: designed wide, not hacked wide

`/traces/[traceId]` becomes the product's flagship surface, laid out for its actual content:

```
┌──────────────────────────────────────────────────────────────┐
│ breadcrumb: Browse / trace-name        [badges] [actions ▾]  │  header strip
├──────────────────────────────────────────────────────────────┤
│ metadata grid (provider · model · tools · counts · duration) │  collapsible
│ analysis: labels + provenance · reasoning · signals · metrics│  region
├───────────────────────────┬──────────────────────────────────┤
│ span tree                 │ span detail panel                │  evidence
│ (tree + duration bars)    │ (attributes, events, raw JSON)   │  region
└───────────────────────────┴──────────────────────────────────┘
```

- **Header strip** (sticky): name, visibility badge, outcome badge, and a single actions cluster (owner: tags/description, list/unlist, relabel, delete; consumer: acquire/download). Today these are scattered across the page.
- **Overview region**: metadata grid and the analysis section side by side on wide viewports, stacked on narrow. Analysis keeps its honest four-state rendering and audit disclosure. Collapsible so power users can maximize the evidence region.
- **Evidence region**: the existing `TraceEvidence` split (tree + detail) gets the full remaining height. No width hack — the shell's content area is full-width by default and pages opt *into* narrower measures, not out of them.
- **Contextual back**: breadcrumb reflects the arriving surface (`?from=marketplace|library|review|subscription`), falling back to Traces/Browse by ownership.
- Review resolve (`/review/[itemId]`) reuses the same evidence region beside the verdict form — its layout is already right; it just stops being the exception.

### Layout system

Three content measures, set by the shell per page — no page ever escapes its container:

| Measure | Used by |
|---|---|
| **Full width** (gutters only) | Trace detail, review resolve |
| **Wide** (`max-w-6xl`) | All list surfaces (Traces, Uploads, Review, Browse, Subscriptions, Library, Notifications) |
| **Narrow** (`max-w-2xl`) | Settings, auth |

Spacing between page regions stays `{spacing.lg}`–`{spacing.xl}` per the `DESIGN.md` adaptation; surface ladder (`canvas-soft` page / `canvas` cards / `canvas-soft-2` insets) unchanged.

### Naming

| Today | Proposed | Why |
|---|---|---|
| My Traces | **Traces** | The Workspace group already says "mine"; shorter |
| Upload + Uploads | **Uploads** | One noun for the ingest surface; the dropzone is the page's primary action, not a separate page |
| Marketplace (nav item) | **Browse** | "Marketplace" is the group/product name; the page is the browsing action |
| Review | Review | unchanged |
| Library | Library | unchanged |

## What deliberately does not change

- **Auth flow**, Supabase session handling, and the `(app)` layout gate.
- **Cross-cutting law** from the page specs: real status verbatim, visibility always visible, UI never enforces access, analysis honesty, pagination (no infinite scroll), notifications as bell + page (no popover), realtime as invalidation-only.
- **Review resolve interior**: machine verdict as context (never pre-selected), closed enums, resolve-and-next, advisory tone.
- **AgentPrism** as the span-tree renderer (alternatives tracked in `docs/follow-up/trace-viewer-alternatives.md`); it gets retokenized chrome, not replaced.
- **No dashboard/admin surfaces** — out of scope per stage specs.

## Migration plan

Ordered so each phase ships coherently and A4 lands on the new foundation rather than the old one:

1. **Shell** — sidebar + top bar + breadcrumb, three-measure layout system, remove the width hack, link the wordmark, ship the new product icon (sidebar mark + favicon), put Uploads/Notifications in the IA. Pure chrome; no page logic changes.
2. **Unified trace list** — one list component with scope config + shared filter bar; migrate Traces, Browse, Library. Deletes `trace-cards.tsx`.
3. **Uploads merge** — fold `/upload` into `/uploads`, redirect the old route.
4. **Trace detail relayout** — header strip, overview region, full-height evidence, contextual back.
5. **A4 on the new foundation** — Subscriptions pages, save-from-filter-bar, bulk select/acquire/list/download as list-pattern features.

Phases 1–2 are the bulk of the value; 3–4 are small; 5 is already-specced work landing in its natural home.

## Spec & design-system amendments required

- `docs/spec/stage-2/4_pages.md`: route table (drop `/upload`, add the merged `/uploads` shape), shell description, trace-detail layout, list-pattern description.
- `DESIGN.md` adaptation: in-app sidebar nav chrome; amend the marketplace/library "card-marketing" density rule to the unified row spec.
- `docs/ux-principles/`: shell/nav archetype update; `feed.yaml` and `bulk_selection` already anticipate the A4 surfaces.

## Open questions

1. **Default landing**: keep `/` → `/traces` (contributor-first, matches the trial's data-foundation emphasis), or land on Browse to lead with the marketplace? Proposal assumes Traces.
2. **Cards vs rows for Browse**: this proposal unifies on dense rows for consistency and bulk-selection ergonomics, overriding the current `DESIGN.md` card rule. If marketplace browsing should feel more "storefront", Browse could keep a card *option* — but the default should still be the unified row.
3. **Upload as page-band vs dialog**: proposal puts the dropzone at the top of `/uploads`. A global "Upload" button in the top bar opening a dialog is the alternative; deferred as chrome polish.
4. **Review badge count**: sidebar badge requires a cheap open-count endpoint (or reuse of the existing list call with `limit=1`). Worth it, but confirm before adding API surface.
