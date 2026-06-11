# Accessibility

Applies to: everything. Scoped to interaction accessibility (the repo's focus); visual contrast comes from DESIGN.md tokens.

```yaml
principle:
  name: The Whole Product Works From a Keyboard
  rule: >
    Every interactive element is reachable and operable by keyboard in
    visual order with a visible focus ring (DESIGN.md focus tokens). The
    dense surfaces get explicit treatment: span tree follows tree-widget
    conventions (arrows navigate/expand, Enter selects); dialogs trap focus
    and restore it on close; Esc closes panels and dialogs; full-row links
    don't bury inner action buttons in the tab order.
  rationale: >
    The audience is developers — heavy keyboard users even without assistive
    needs. The span tree is the make-or-break surface: a tree that needs a
    mouse for 500 nodes fails both accessibility and its power users.
  examples:
    positive:
      - "Arrow-key span tree navigation with the detail panel following selection"
    negative:
      - "Focus lost to body after closing the delete confirm"
      - "Drop zone operable only by drag"
  validation:
    - all_actions_keyboard_operable
    - focus_visible_and_restored_after_dialogs
    - tree_supports_arrow_key_navigation
  sources:
    - "WAI-ARIA Authoring Practices: tree view, dialog patterns"
    - "GitHub Primer: focus management"
```

```yaml
principle:
  name: State Is Never Color Alone
  rule: >
    Every state encoding pairs color with a second channel: error spans get
    icon + tint; visibility badges carry text ("private"/"listed"), not
    just hue; outcome labels are worded; required/invalid fields get text,
    not red borders alone. Charts/timeline bars distinguishable by
    position and label, not palette.
  rationale: >
    WCAG 1.4.1, and self-interest: the product's core signals (error,
    listed, failure) are exactly the ones that must survive any viewer,
    any display, any colorblindness.
  examples:
    positive:
      - "Error span: red tint + alert icon + 'error' status text"
    negative:
      - "Green/red status dots with no text or icon"
  validation:
    - no_state_encoded_by_color_alone
    - badges_carry_text_labels
  sources:
    - "WCAG 2.x SC 1.4.1: Use of Color"
    - "trace-inspection/span_tree.md"
```

```yaml
principle:
  name: Dynamic States Announce Themselves
  rule: >
    Async status changes (ingestion polling, acquire success, bulk results,
    validation errors) are announced via live regions (polite for status,
    assertive for errors); loading states carry accessible names; icon-only
    buttons (copy, expand, bell) have aria-labels; counts ("12 selected")
    are text, not pseudo-content.
  rationale: >
    The product's feedback model leans on in-place state flips
    (global/feedback.md); without live regions, every one of them is
    invisible to screen readers — the entire async story goes silent.
  examples:
    positive:
      - "role=status region announcing 'processing' -> 'complete, 3 traces created'"
    negative:
      - "Badge flip from private to listed with no announcement"
  validation:
    - status_changes_in_live_regions
    - icon_only_controls_have_labels
  sources:
    - "WAI-ARIA: live regions"
    - "IBM Carbon: accessibility of inline notifications"
```
