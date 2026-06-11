# UI Redesign — Pass 002: Filter bar rework

The filter bar had grown into a three-row wall of always-visible controls (search, five text/date inputs, a checkbox, sort, a second row of five analysis selects, a metric builder, a "More filters" row). Every list surface paid that visual cost whether or not the user was filtering.

## Change

`trace-filters.tsx` rewritten around a compact bar + disclosure panel:

- **Bar**: search (debounced), a "Filters" toggle with an active-predicate count badge, sort. Nothing else.
- **Panel**: inline disclosure (not an overlay — routing law keeps dialogs as the only overlay UI) with the full vocabulary in labeled groups: Trace (provider, model, tool, date range), Analysis (outcome, failure mode, category, provenance, confidence ≥), Quality metrics (the observed-keys metric ≥ builder), Signals & counts (has-errors, loop kind, tri-state signals, count thresholds). Controls are labeled fields instead of placeholder-only inputs.
- **Chips** stay always-visible below the bar — the active filter state is never hidden behind the closed panel.
- The previously specced-but-missing **`tool` filter input** (stage-1 audit debt) ships with the panel.
- `has_errors` stays a checkbox (the URL serializer only carries `true`; a tri-state select would lie).

No changes to `filter-state.ts`, chips, URL serialization, or the API — the vocabulary and one-language rule are untouched, so subscriptions and feeds are unaffected.

## Outcome

`pnpm lint` and `pnpm build` clean; web container rebuilt.
