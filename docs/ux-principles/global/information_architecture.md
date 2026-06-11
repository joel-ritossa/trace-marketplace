# Information Architecture

Applies to: route map, page grouping, where new features land.

```yaml
principle:
  name: Organize by Possession, Not by Role
  rule: >
    Top-level sections are possession/intent buckets — Upload (give),
    My Traces (mine), Marketplace (everyone's), Library (acquired) — not
    "contributor mode" vs "consumer mode". There is one user type; never
    introduce role-based navigation.
  rationale: >
    The spec defines a single account type that both contributes and
    consumes. Mode switches create orientation loss and duplicate surfaces
    for the same objects. A trace is the same object whether you made it
    or bought it; only the section answers "why am I looking at it".
  examples:
    positive:
      - "The same /traces/[id] detail page serves owner, browser, and acquirer; only the actions differ"
    negative:
      - "Separate /marketplace/traces/[id] and /my/traces/[id] detail pages"
      - "A 'switch to seller view' toggle"
  validation:
    - one_detail_route_per_object_type
    - no_role_or_mode_switcher_in_nav
  sources:
    - "NN/g: IA based on user mental models, not org structure"
    - "Information Architecture (Rosenfeld/Morville): organization by audience is a last resort"
```

```yaml
principle:
  name: One Object, One Canonical Page
  rule: >
    Every domain object (trace, upload, subscription, review item) has
    exactly one canonical URL where it is fully represented. Lists, cards,
    notifications, and feeds are previews that link there; deep actions
    (acquire, download, resolve, visibility) live on the canonical page or
    are shortcuts to its semantics.
  rationale: >
    Spec already encodes this: marketplace cards link to /traces/[id];
    acquire and download happen there. Splitting an object across surfaces
    forks state handling and breaks shareable links.
  examples:
    positive:
      - "subscription_match notification links to the trace detail, not to an inline mini-viewer"
      - "Library card's direct download is a shortcut to the same download semantics as the detail page"
    negative:
      - "A modal trace previewer in the marketplace that re-implements half the detail page"
  validation:
    - every_object_reference_links_to_canonical_route
    - no_duplicate_partial_object_views
  sources:
    - "NN/g: deep links and canonical pages"
    - "Atlassian Design System: object-centric navigation"
```

```yaml
principle:
  name: Derived Data Is Labeled as Derived
  rule: >
    Stage-2 analysis fields (outcome, failure_mode, task_category, metric
    scores) always render with their provenance (machine / human_confirmed /
    human) and confidence where defined. Never present a machine label with
    the same visual authority as a human-confirmed one.
  rationale: >
    Label provenance is a consumer-facing quality dimension (judging spec).
    Consumers filter on it; hiding it in the UI while exposing it in the
    filter language makes search results inexplicable.
  examples:
    positive:
      - "outcome: failure (machine, 0.62)' rendered as badge + quiet provenance tag"
    negative:
      - "A bare 'FAILED' label indistinguishable from a human verdict"
  validation:
    - derived_labels_show_provenance
    - confidence_visible_where_stored
  sources:
    - "NN/g: communicating AI uncertainty to users"
    - "IBM Carbon for AI: AI-generated content labeling"
```

```yaml
principle:
  name: Vocabulary Is Fixed and Mirrored
  rule: >
    UI copy uses the spec's nouns verbatim and consistently: trace, span,
    upload, acquire (not buy/save/add), listed/private (not public/hidden),
    library (not purchases), outcome success/failure/indeterminate. The same
    field has the same name in tables, filters, detail pages, and exports.
  rationale: >
    Nielsen heuristic #4 (consistency and standards). The filter language is
    shared across search, subscriptions, and bounties — if the UI calls a
    field something else, users cannot construct the queries the system
    actually supports.
  examples:
    positive:
      - "Filter chip 'has errors' matches the has-errors API filter and the table's errors column"
    negative:
      - "'Purchase' button on a $0 acquisition (implies payment that doesn't exist)"
      - "'Public' badge when the system state is 'listed'"
  validation:
    - ui_terms_match_spec_vocabulary
    - filter_names_match_column_names
  sources:
    - "Nielsen heuristic #4: Consistency and standards"
    - "Shopify Polaris: product content vocabulary"
```
