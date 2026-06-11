# Bulk Selection & Bulk Acquire (Stage 2)

Applies to: marketplace results, subscription feeds — anywhere multi-select + bulk acquire ships.

```yaml
principle:
  name: Selection Mode Is Explicit and Summarized
  rule: >
    Rows get checkboxes; selecting any row raises a persistent action bar
    showing the count ("12 selected"), the bulk action (Acquire), select-all
    -matching and clear-selection controls. The bar stays visible while
    scrolling. Zero selection = no bar.
  rationale: >
    Bulk actions detached from a visible selection summary cause
    wrong-scope catastrophes ("I thought I had 3 selected, it acquired 300").
    The count is the user's verification step.
  examples:
    positive:
      - "Polaris ResourceList / Gmail: persistent bulk bar with live count"
    negative:
      - "Acquire-all button in the page header acting on an invisible selection"
  validation:
    - bulk_bar_shows_live_selection_count
    - bulk_bar_persistent_during_scroll
    - clear_selection_always_available
  sources:
    - "Shopify Polaris: bulk actions on resource lists"
    - "IBM Carbon: data table batch actions"
```

```yaml
principle:
  name: Select-All Is Scope-Honest
  rule: >
    "Select all" selects visible rows; extending to all query matches is a
    separate, explicit step that states the real number ("Select all 240
    matching traces"). The bulk confirmation restates final count before
    executing. No auto-acquire anywhere — selection is always a human act.
  rationale: >
    The requirements lock "no auto-acquire": the consumer multi-selects
    deliberately. Gmail's two-step select-all is the proven pattern for
    page-vs-query scope honesty; silent query-wide selection is the
    classic bulk-action disaster.
  examples:
    positive:
      - "Header checkbox -> 'All 50 on this page selected. Select all 240 matching?'"
    negative:
      - "Subscription with an 'auto-acquire new matches' toggle"
  validation:
    - select_all_distinguishes_page_from_query_scope
    - bulk_action_confirms_final_count
    - no_auto_acquire_mechanism_exists
  sources:
    - ".archive/stage-2-planning/spec-shaping/requirements.md: no auto-acquire"
    - "NN/g: preventing wrong-scope bulk operations"
```

```yaml
principle:
  name: Bulk Results Itemize
  rule: >
    Bulk acquire reports per-item outcomes: n acquired, m skipped/failed
    with per-trace reasons (already owned, no longer listed). Succeeded rows
    flip to in-your-library in place. Re-running is safe and says so
    (acquire is idempotent).
  rationale: >
    All-or-nothing reporting on a partial batch either hides failures or
    discards successes. Idempotency is an API guarantee the UI should
    surface as calm copy, not hide behind scary warnings.
  examples:
    positive:
      - "'8 acquired - 2 already in your library' with rows updated in place"
    negative:
      - "'Bulk acquire failed' because 1 of 10 traces was delisted"
  validation:
    - bulk_outcome_itemizes_failures_with_reasons
    - succeeded_rows_update_in_place
  sources:
    - "global/feedback.md: Partial Success Is a First-Class State"
    - "Microsoft Fluent: batch operation feedback"
```
