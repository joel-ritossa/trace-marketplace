# Span Tree

Applies to: `/traces/[traceId]` section 2 — the core inspection surface (agent-prism TreeView/SpanCard).

```yaml
principle:
  name: Structure Readable at a Glance
  rule: >
    The tree renders the full hierarchy reconstructed from parent IDs with
    explicit connectors and indentation; every node shows name, kind badge,
    duration, and status in fixed columns. Roots expanded by default;
    expand/collapse-all controls present. Orphaned spans (broken parent
    refs) render in a visible "unparented" group, never dropped.
  rationale: >
    The tree's job is answering "what did this agent do, in what order,
    and where did it go wrong" without opening a single span. Fixed
    columns make 500 rows scannable; silently dropping orphans violates
    the every-span-shown spec rule and hides exactly the malformed data
    a trace marketplace must expose.
  examples:
    positive:
      - "agent-prism SpanCard rows: name, kind badge, duration, status dot, timeline bar"
    negative:
      - "Spans with missing parents silently excluded from the tree"
  validation:
    - every_span_rendered_including_orphans
    - node_shows_name_kind_duration_status_without_interaction
    - expand_collapse_all_available
  sources:
    - "docs/spec/stage-1/4_pages.md: full hierarchy, every span shown"
    - "NN/g: tree views — visible structure beats hover-revealed structure"
```

```yaml
principle:
  name: Errors Are Visible From Orbit
  rule: >
    Error-status spans are flagged with a persistent visual marker (status
    color + icon, not color alone) visible at every zoom: on the node, on
    collapsed ancestors as a rolled-up count, and in the header's error
    count. A user must locate all failures without expanding anything.
  rationale: >
    Failure inspection is the product's chief value ("error spans visually
    flagged" is normative; stage-2 judging revolves around failure modes).
    If finding the failing span requires expansion archaeology, the core
    use case fails.
  examples:
    positive:
      - "Collapsed parent shows '2 errors' chip; error rows tinted with icon"
    negative:
      - "Error indicated only by a slightly different shade of gray"
  validation:
    - error_spans_flagged_with_icon_plus_color
    - collapsed_ancestors_roll_up_error_counts
    - error_locatable_without_expanding_tree
  sources:
    - "docs/spec/stage-1/4_pages.md"
    - "WCAG 1.4.1: never color as the only signal"
```

```yaml
principle:
  name: Time Is a Dimension, Not Just a Number
  rule: >
    Each span row carries a proportional timeline bar (offset + duration
    relative to the trace) alongside the duration number. Bars align to a
    shared time axis so concurrency, gaps, and the long pole are visible
    as shape.
  rationale: >
    "Which span dominated the 40s trace" is a perception task, not an
    arithmetic task. Waterfall bars answer it preattentively; a duration
    column alone forces mental math across hundreds of rows.
  examples:
    positive:
      - "agent-prism SpanCardTimeline: per-row bar on a shared axis"
    negative:
      - "Duration as text only; no way to see parallel tool calls overlap"
  validation:
    - timeline_bars_share_one_time_axis
    - duration_number_and_bar_both_present
  sources:
    - "Chrome DevTools / Jaeger waterfall conventions"
    - "Tufte: small multiples on a common scale"
```

```yaml
principle:
  name: Big Traces Degrade Gracefully
  rule: >
    Past ~500 spans, the tree paginates/lazy-loads (per spec) while keeping
    structure honest: counts state the whole truth ("showing 500 of 2,310
    spans"), error rollups cover unloaded regions, and loading more never
    collapses what's already open or loses selection.
  rationale: >
    The spec names the large-trace state explicitly. Lazy loading that
    hides counts or resets expansion turns deep traces — the most valuable
    ones — into the worst experience in the product.
  examples:
    positive:
      - "'Load more spans' boundary preserving scroll, expansion, and selected span"
    negative:
      - "Virtualized tree that re-collapses on every fetch"
  validation:
    - span_truncation_states_total_count
    - expansion_and_selection_survive_lazy_loading
  sources:
    - "docs/spec/stage-1/4_pages.md: large trace state"
    - "Material Design: progressive loading of large collections"
```
