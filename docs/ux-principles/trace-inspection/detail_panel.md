# Span Detail Panel (Master-Detail)

Applies to: `/traces/[traceId]` — span selection opening the detail panel (agent-prism DetailsView).

```yaml
principle:
  name: Selection Opens Beside, Not Over
  rule: >
    Selecting a span opens its detail in a side panel next to the tree
    (resizable split), never a modal. The tree stays visible and
    interactive; the selected node stays highlighted; selecting another
    span swaps the panel content in place.
  rationale: >
    Span inspection is comparative — users hop between sibling spans,
    parent and child, request and response. A modal forces
    open/close/reorient per hop; side-by-side keeps the structural context
    that gives the detail meaning.
  examples:
    positive:
      - "DevTools network panel: request list + detail pane; agent-prism TraceViewer desktop layout"
    negative:
      - "Span detail in a modal that hides the tree"
      - "Detail replacing the tree entirely (navigation instead of selection)"
  validation:
    - tree_remains_visible_and_interactive_with_panel_open
    - selected_node_visibly_highlighted
    - panel_swaps_in_place_on_new_selection
  sources:
    - "Apple HIG: prefer non-modal presentation; inspectors beside content"
    - "NN/g: master-detail keeps list context during inspection"
```

```yaml
principle:
  name: Tabs Order by Question Frequency
  rule: >
    Panel content tabs order: Input/Output (what the span did), Attributes
    (full raw JSON, pretty-printed), Events, Raw data. The default tab is
    the most semantic view available for the span kind; raw is always
    reachable, never the forced default. Timings, status, status message,
    error type, model/provider/tool, and token counts render in the panel
    header area on every tab.
  rationale: >
    "What was the prompt and what came back" is the first question for LLM
    spans; "what exactly is in this span" is the audit question. Constants
    (status, timing) belong outside the tabs so switching tabs never hides
    the basics. No span data hidden — but raw JSON as default punishes the
    common case.
  examples:
    positive:
      - "LLM span defaults to Input/Output; tool span defaults to Attributes"
    negative:
      - "Status message only visible inside the Raw tab"
  validation:
    - status_timing_visible_regardless_of_active_tab
    - full_attributes_and_events_reachable
    - semantic_tab_default_when_available
  sources:
    - "docs/spec/stage-1/4_pages.md: span detail contents"
    - "NN/g: tab ordering by usage frequency"
```

```yaml
principle:
  name: Inspection Data Is Extractable
  rule: >
    Every value a developer would reuse — span id, attribute values, JSON
    blocks, error messages — is selectable text with copy buttons on
    block-level content. JSON is pretty-printed, syntax-highlighted, with
    expand/collapse for nested objects; long values wrap or scroll within
    the panel, never truncate silently.
  rationale: >
    The panel feeds external workflows: grepping logs, filing issues,
    reproducing failures. Un-copyable or silently truncated data forces
    re-typing — error-prone exactly where precision matters (ids, hashes).
  examples:
    positive:
      - "agent-prism CopyButton on JSON blocks; collapsible nested attributes"
    negative:
      - "Attribute values cut with CSS ellipsis and no expansion or title"
  validation:
    - copy_affordance_on_json_blocks_and_ids
    - no_silent_truncation_of_values
  sources:
    - "GitHub Primer: code block copy affordances"
    - "global/progressive_disclosure.md: no truncation without full view"
```
