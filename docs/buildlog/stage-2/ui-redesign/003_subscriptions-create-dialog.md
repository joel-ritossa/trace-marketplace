# UI Redesign — Pass 003: New-subscription dialog

User feedback: the "New subscription" button on `/subscriptions` just linked to Browse, which read as a dead end. Subscriptions should be creatable in place.

## Change

- `FilterFields` extracted from the filter bar's disclosure panel (`trace-filters.tsx`), along with `FilterText`/`textFromFilters`/`mergeText` helpers — the bar and the dialog now render the exact same field grid from one source.
- New `NewSubscription` component (`components/traces/new-subscription.tsx`): a dialog with search text + the full filter vocabulary, chips of the effective query, an explicit **Search** button that previews the live marketplace match count (`listTraces("marketplace", …, limit 1)` for the total), a name field, and **Create subscription** → navigates to the new feed. Any filter edit invalidates the previewed count. Creation still requires at least one filter (the API rejects empty queries).
- `/subscriptions` header swaps the Browse link for the dialog. The "Save as subscription" flow on Browse is unchanged — two entry points, one query vocabulary.
- Spec updated: `4_pages.md` `/subscriptions` now names both creation paths.

## Outcome

`pnpm lint` and `pnpm build` clean; web container rebuilt.
