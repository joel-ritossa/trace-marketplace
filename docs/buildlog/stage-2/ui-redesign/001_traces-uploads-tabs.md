# UI Redesign — Pass 001: Traces/Uploads as one surface

User feedback after the redesign shipped: two adjacent Workspace nav items ("Traces", "Uploads") both read as "my data" — the parsed-vs-raw distinction forced users to learn the ingest pipeline before navigating.

## Change

- One **Traces** nav item; `/uploads` becomes the surface's second tab via a shared link-tab strip (`workspace-tabs.tsx`). URLs unchanged, so notification deep links (`upload_failed` → `/uploads`) and the `/upload` redirect still hold.
- Sidebar highlights Traces for `/uploads` paths (`alsoMatches`); top-bar breadcrumb renders `/uploads` as `Traces › Uploads`.
- Both tabs share the `Traces` h1; subtitles stay tab-specific. The traces subtitle's inline "your uploads" link is gone — the tab replaces it.
- Spec updated in the same pass (`4_pages.md` nav + `/uploads`).

## Why tabs, not a rename or full merge

Rename keeps two peer items (the confusion); full inline merge would mix file rows into the trace list and muddy the failure surface. Tabs keep the upload/trace entities and the honest failure surface intact while presenting one "my data" destination.

## Outcome

`pnpm lint` and `pnpm build` clean; web container rebuilt.
