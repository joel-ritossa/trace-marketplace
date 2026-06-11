# Progressive Disclosure

Applies to: trace detail, span detail, filters, review resolve, settings.

```yaml
principle:
  name: Summary First, Raw Data On Demand
  rule: >
    Surfaces layer in three depths: (1) scannable summary (badges, counts,
    names), (2) structured detail (span timings, status, model/tool), (3)
    raw payloads (full attributes JSON, events). Each layer is one
    interaction away from the previous. Nothing is hidden — every layer is
    reachable — but raw JSON never renders by default in lists.
  rationale: >
    Spec mandates "no span data is hidden from users with access" while
    traces can exceed 500 spans. Disclosure depth reconciles completeness
    with scannability: hide nothing, default-render little.
  examples:
    positive:
      - "Span row shows name/kind/duration/status; selecting opens the detail panel; attributes tab shows full raw JSON"
      - "Trace card shows counts; detail page shows everything"
    negative:
      - "Attributes truncated with '...' and no way to expand (violates the no-hiding rule)"
      - "All span attributes inlined in the tree (unscannable)"
  validation:
    - every_data_layer_reachable_within_one_interaction_from_previous
    - no_truncation_without_full_view_affordance
  sources:
    - "NN/g: Progressive Disclosure"
    - "Apple HIG: progressive disclosure in inspectors"
```

```yaml
principle:
  name: Collapsed Does Not Mean Buried
  rule: >
    Collapsed sections show a meaningful summary of what's inside (count,
    status rollup), not just a label. A collapsed subtree with errors inside
    must surface the error count on the collapsed node.
  rationale: >
    Collapsing is for managing density, not for hiding signal. If errors
    can hide inside collapsed spans, the "error spans visually flagged"
    spec requirement silently fails.
  examples:
    positive:
      - "Collapsed span node: 'agent.plan (12 spans, 2 errors)' with error tint"
      - "Collapsed advanced filters showing a count badge of active filters within"
    negative:
      - "Collapsed branch that looks healthy while containing the failure"
  validation:
    - collapsed_nodes_roll_up_child_error_status
    - collapsed_filter_groups_show_active_count
  sources:
    - "Material Design: expansion panels communicate hidden content"
    - "NN/g: accordion pitfalls"
```

```yaml
principle:
  name: Advanced Capability Defaults Closed, Discoverably
  rule: >
    Power features (full filter builder, raw payload tab, analyzer version
    info) default collapsed behind a visible, labeled affordance on the same
    screen — never behind navigation or undiscoverable gestures.
  rationale: >
    The audience spans first-time evaluators and trace power users. Closed-
    by-default keeps the first-run simple; same-screen affordances keep the
    ceiling high without a "pro mode".
  examples:
    positive:
      - "Marketplace: search box + 3 common filters visible; 'All filters' expands the rest"
    negative:
      - "Filter builder only reachable from a settings page"
      - "Raw data tab only via keyboard shortcut"
  validation:
    - advanced_features_have_visible_entry_point
    - default_view_usable_without_opening_advanced
  sources:
    - "NN/g: Progressive Disclosure (staged complexity)"
    - "Microsoft Fluent: progressive disclosure in command surfaces"
```
