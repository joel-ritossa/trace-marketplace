# Trace Lists (Tables & Result Cards)

Applies to: `/traces` (table), `/marketplace` and `/library` (result cards), stage-2 subscription feeds.

```yaml
principle:
  name: Columns Answer the Section's Question
  rule: >
    Each list shows the fields that serve its intent, in scan order.
    My Traces (manage): name, created, span count, errors, duration, model,
    visibility badge. Marketplace (evaluate): adds contributor, listed date,
    in-your-library badge; drops visibility (everything is listed).
    Library (retrieve): adds acquired date and a direct download. Don't
    unify into one column set.
  rationale: >
    The three lists share a data shape but not a user question. "Is this
    worth acquiring" needs provenance and freshness; "what did I upload"
    needs status and visibility. Generic columns serve neither.
  examples:
    positive:
      - "Library card with acquired date + download icon-button per card"
    negative:
      - "Visibility badge column on /marketplace where every row says 'listed'"
  validation:
    - column_set_matches_section_intent
    - at_most_7_columns_per_table
  sources:
    - "NN/g: data tables — show what the task needs, not what the schema has"
    - "docs/spec/stage-1/4_pages.md: per-page field lists"
```

```yaml
principle:
  name: The Whole Row Is the Link
  rule: >
    The entire row/card is a click target navigating to /traces/[id], with
    the name styled as the visible link affordance. Inline actions (download
    in library) are separate, clearly bounded targets that stop propagation.
    Hover state on the row signals clickability.
  rationale: >
    Fitts's law: a 24px name link in a 1000px row wastes the click target.
    But overlapping targets (whole-row link + inline button) misfire without
    clear bounds — bound the inline action visually and behaviorally.
  examples:
    positive:
      - "Linear issue rows: full-row click, discrete action buttons"
    negative:
      - "Only the trace name clickable; clicking the row does nothing"
      - "Row click and download button overlapping so downloads navigate"
  validation:
    - full_row_navigates_to_detail
    - inline_actions_do_not_trigger_row_navigation
  sources:
    - "Fitts's law; NN/g: clickable areas should match perceived areas"
    - "GitHub Primer: list item interaction patterns"
```

```yaml
principle:
  name: Badges Encode State, Not Decoration
  rule: >
    Badges in lists carry system state with one consistent design per state
    family: visibility (private/listed) on every trace rendering, error
    presence, in-your-library, and stage-2 outcome + provenance. Same badge,
    same meaning, every surface — list, card, detail header, notification.
  rationale: >
    "Visibility is always visible" is a spec rule rooted in consent: a user
    must never be surprised that a trace is listed. Badge consistency is
    what lets the eye verify state across 50 rows in one pass.
  examples:
    positive:
      - "private = neutral badge, listed = accented badge, identical on table row and detail header"
    negative:
      - "Visibility as a tooltip on an icon in lists but a labeled badge on detail"
  validation:
    - visibility_badge_on_every_trace_rendering
    - badge_styles_consistent_across_surfaces
  sources:
    - "Nielsen heuristic #4: consistency"
    - "Shopify Polaris: badge semantics (status, not decoration)"
```

```yaml
principle:
  name: Lists Stay Fast Past 1k Rows
  rule: >
    Server-side pagination/infinite-load with a stable sort (created desc
    default), sort indicators where sortable, and result counts visible.
    Never fetch-all-and-filter client-side; never reflow already-rendered
    rows when a page appends.
  rationale: >
    The stage-2 sync CLI will pour hundreds of traces in per user. Lists
    designed for 10 fixtures fall over exactly when the product starts
    succeeding.
  examples:
    positive:
      - "'312 traces' count near the search box; pages append below"
    negative:
      - "Loading all traces to filter in JS; sort order shifting between pages"
  validation:
    - pagination_server_side
    - total_count_visible_with_results
    - stable_default_sort_documented
  sources:
    - "IBM Carbon: data table pagination guidance"
    - "Material Design: list performance with large collections"
```
