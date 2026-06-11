# UI States

Applies to: every screen. The spec enumerates required states per page; this file defines how to render them.

```yaml
principle:
  name: Every Screen Declares Its Full State Set
  rule: >
    Before implementation, enumerate the screen's states. Minimum set for
    any data view: loading, empty, results, error. Lists with search add
    no-results-for-query. Detail pages add not-found. Async flows add each
    named job status. A screen missing a state from its spec list is
    incomplete, not "edge-case polish".
  rationale: >
    The stage-1 spec lists states per page as acceptance criteria
    (4_pages.md). State gaps are where trust dies: a blank screen during
    loading reads as broken; an unhandled empty list reads as data loss.
  examples:
    positive:
      - "/upload renders: idle, uploading, received/processing, complete, failed, duplicate, partial-success"
    negative:
      - "Results-only implementation that renders [] as a blank page"
  validation:
    - all_spec_listed_states_implemented
    - loading_empty_error_states_present_on_every_data_view
  sources:
    - "docs/spec/stage-1/4_pages.md (normative state lists)"
    - "Scott Hurff: the UI stack (blank, loading, partial, error, ideal)"
```

```yaml
principle:
  name: Empty States Teach and Cross-Link
  rule: >
    An empty state names what would live here, explains how it gets here,
    and links to the one action that fills it. My Traces -> /upload.
    Library -> /marketplace. Review queue empty -> "nothing needs review"
    (a positive, not a dead end). Never render a bare "No data".
  rationale: >
    Empty states are the onboarding surface of this product — there is no
    separate tutorial. The first-run loop (sign up -> empty traces ->
    upload -> first trace) is carried entirely by empty-state links.
  examples:
    positive:
      - "Empty /traces: 'Upload your first trace' linking to /upload, one sentence on accepted format"
      - "Empty marketplace: explains traces appear when contributors list them"
    negative:
      - "Empty table body with just column headers"
      - "Empty state with three competing CTA buttons"
  validation:
    - empty_state_has_single_cta_to_filling_action
    - empty_state_copy_names_the_missing_object
  sources:
    - "GitHub Primer: Blankslate pattern"
    - "Shopify Polaris: empty state component guidance"
```

```yaml
principle:
  name: No-Results Shows the Active Query
  rule: >
    No-results-for-query is distinct from empty: it must display the active
    search terms and filter chips that produced zero results and offer
    one-click clearing (per chip and clear-all). Never show the generic
    empty state while filters are active.
  rationale: >
    Users blame the product for "losing" data that a forgotten filter is
    hiding. The spec distinguishes empty from no-results-for-query for
    exactly this reason.
  examples:
    positive:
      - "'No traces match provider: openai, has-errors' with removable chips and Clear all"
    negative:
      - "'Upload your first trace' shown because a date filter excluded everything"
  validation:
    - no_results_state_displays_active_filters
    - filters_clearable_from_no_results_state
  sources:
    - "NN/g: No Results Found pages"
    - "Atlassian Design System: filter feedback"
```

```yaml
principle:
  name: Not-Found Is Indistinguishable From No-Access
  rule: >
    A private trace the caller cannot see returns the same not-found UI as
    a nonexistent ID. The not-found page offers navigation back to
    marketplace/library; it never hints "this exists but is private".
  rationale: >
    Spec: "not found (covers no-access by design)". Distinguishing 403 from
    404 leaks the existence of private traces — a privacy boundary, not a
    UX nicety. The UI renders what the API returns.
  examples:
    positive:
      - "Uniform 'Trace not found' with links to /marketplace and /library"
    negative:
      - "'You don't have permission to view this trace' (confirms existence)"
  validation:
    - single_not_found_rendering_for_404_and_no_access
    - not_found_offers_recovery_navigation
  sources:
    - "docs/spec/stage-1/4_pages.md"
    - "OWASP: object existence non-disclosure"
```

```yaml
principle:
  name: Skeletons Match the Shape They Load
  rule: >
    Loading states mirror the layout they resolve into (table skeleton for
    tables, header+tree skeleton for trace detail). No full-page spinners
    on navigations; no layout shift when content arrives.
  rationale: >
    Shape-preserving skeletons keep orientation and make perceived latency
    shorter; layout shift on resolve makes users misclick row actions.
  examples:
    positive:
      - "Trace list loading: 8 skeleton rows with the real column widths"
    negative:
      - "Centered spinner replacing the whole app shell"
  validation:
    - loading_state_preserves_destination_layout
    - no_cumulative_layout_shift_on_data_arrival
  sources:
    - "NN/g: Skeleton Screens 101"
    - "Material Design: progress indicator placement"
```
