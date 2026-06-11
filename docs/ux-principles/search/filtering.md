# Search & Filtering

Applies to: `/traces`, `/marketplace`, `/library`; the same UI seeds stage-2 subscriptions and bounties.

```yaml
principle:
  name: One Filter Language, One Filter UI
  rule: >
    Search box + structured filters (provider, model, tool, has-errors,
    date range; stage 2 adds outcome, failure_mode, task_category,
    confidence/provenance, metric ranges) are one shared component across
    all list pages and the subscription builder. A filter added anywhere
    appears everywhere the field is filterable.
  rationale: >
    Infra spec: subscriptions store "the same filter vocabulary as
    GET /v1/traces"; any filterable field is automatically subscribable.
    Two filter UIs guarantee vocabulary drift and double maintenance.
  examples:
    positive:
      - "'Save as subscription' button on marketplace serializes the exact current filter state"
    negative:
      - "Subscription builder with its own bespoke query form diverging from search"
  validation:
    - single_shared_filter_component
    - subscription_builder_reuses_search_state
  sources:
    - ".archive/stage-2-planning/spec-shaping/infra.md §5"
    - "Nielsen heuristic #4: consistency"
```

```yaml
principle:
  name: Active Filters Are Chips, Always Visible
  rule: >
    Every active filter renders as a labeled, individually removable chip
    between controls and results ("provider: openai ×"), with clear-all when
    2+ are active. Results never silently reflect invisible filters.
  rationale: >
    Filters users can't see are filters users forget — and then mistrust
    the data ("where did my traces go?"). Chips also double as the visual
    spec of what a saved subscription will match.
  examples:
    positive:
      - "Chip row: 'has errors ×' 'model: gpt-4o ×' 'Clear all'"
    negative:
      - "Date filter active but only visible inside a closed dropdown"
  validation:
    - every_active_filter_rendered_as_removable_chip
    - clear_all_present_when_multiple_filters_active
  sources:
    - "NN/g: filter visibility and applied-filter feedback"
    - "Atlassian Design System: filter chips"
```

```yaml
principle:
  name: Filters Apply Fast and Honest
  rule: >
    Single-select filters apply immediately; result count updates with each
    change. Free-text search applies on debounce or Enter. While results
    refresh, the old list dims rather than unmounting (no flash to empty).
    Filter options come from real field values, not hardcoded lists.
  rationale: >
    Immediate application keeps the query-result feedback loop tight —
    that loop is how users learn the corpus. Flashing to empty between
    keystrokes reads as data loss.
  examples:
    positive:
      - "Toggling has-errors updates count '312 -> 41' with dimmed transition"
    negative:
      - "An Apply button gating every facet change"
      - "Provider dropdown listing providers that exist in no trace"
  validation:
    - result_count_updates_with_filter_changes
    - no_empty_flash_during_refetch
    - facet_options_derived_from_data
  sources:
    - "NN/g: interactive filtering response"
    - "Material Design: filter chips apply immediately"
```

```yaml
principle:
  name: Null Never Matches — Say So
  rule: >
    Where stage-2 derived fields are filterable, unanalyzed traces (NULL
    fields) drop out of any predicate on them. The UI states this where it
    bites: filtered counts get a quiet note when analysis-pending traces are
    excluded, and trace detail shows "not yet analyzed" rather than blank
    label slots.
  rationale: >
    "NULL never matches any predicate" is a system rule (judging spec).
    Without surfacing it, a user filtering outcome=failure concludes their
    just-synced traces vanished, when they're merely unanalyzed.
  examples:
    positive:
      - "'41 matches (12 traces not yet analyzed are excluded)'"
      - "Detail page: 'Analysis pending' placeholder in the labels block"
    negative:
      - "Empty label area indistinguishable from 'judged: no labels apply'"
  validation:
    - pending_analysis_visually_distinct_from_no_label
    - filtered_views_disclose_unanalyzed_exclusions
  sources:
    - ".archive/stage-2-planning/spec-shaping/judging/README.md: null semantics"
    - "Nielsen heuristic #1: visibility of system status"
```
