# Visual & Action Hierarchy

Applies to: every screen.

```yaml
principle:
  name: One Primary Action Per Screen
  rule: >
    Each screen state has exactly one visually dominant action. All other
    actions are secondary (outline/ghost) or demoted into menus.
  rationale: >
    Hick's Law: decision time grows with the number of equally-weighted
    choices. A screen that cannot say what it most wants the user to do
    forces the user to decide for it.
  examples:
    positive:
      - "/upload idle state: the file drop zone / submit is the only primary action"
      - "/traces/[id] as non-owner of a listed trace: Acquire is the single primary button; Download renders disabled with 'acquire to download'"
      - "Review resolve view: Resolve is primary; skip/back are quiet"
    negative:
      - "Trace detail rendering Download, Acquire, Delete, and List all as filled buttons"
      - "Empty library showing both 'Browse marketplace' and 'Upload a trace' with equal weight"
  validation:
    - exactly_one_primary_button_per_screen_state
    - destructive_actions_never_primary_styled
  sources:
    - "NN/g: Visual Hierarchy in UX"
    - "Shopify Polaris: Actionable language / button hierarchy"
```

```yaml
principle:
  name: Entitlement Drives Prominence
  rule: >
    Action prominence on a trace must follow the API's is_owner / acquired /
    can_download flags. Owner sees manage actions; non-owner-not-acquired sees
    Acquire as primary; acquired sees Download as primary plus an
    "in your library" badge. Never render an action the flags do not permit
    as if it were available.
  rationale: >
    The UI never enforces access itself (spec rule) but it must *communicate*
    access truthfully. A clickable button that 403s is a broken promise;
    a hidden capability is undiscoverable.
  examples:
    positive:
      - "Disabled Download with inline reason 'acquire to download'"
    negative:
      - "Enabled Download that fails with a toast after click"
      - "Hiding Download entirely for non-acquirers (user can't learn the rule)"
  validation:
    - actions_match_entitlement_flags
    - disabled_actions_carry_inline_reason
  sources:
    - "Nielsen heuristic #1: Visibility of system status"
    - "GitHub Primer: disabled states must explain themselves"
```

```yaml
principle:
  name: Status Before Content
  rule: >
    Identity and status (name, ingestion status, visibility badge, outcome
    label) render at the top of any trace surface, before metrics or body
    content. Scanning order is: what is it -> what state is it in ->
    what can I do -> details.
  rationale: >
    Users scan in an F-pattern; the first fixation must answer "am I in the
    right place and is anything wrong". Status buried below the fold gets
    missed exactly when it matters (failed ingestion, private trace about
    to be shared).
  examples:
    positive:
      - "Trace detail header: name + status + visibility badge + duration/span/error counts in one band"
    negative:
      - "Visibility badge only shown inside a settings tab"
      - "Error count only discoverable by expanding the span tree"
  validation:
    - status_and_visibility_badges_above_fold
    - identity_block_first_in_dom_order
  sources:
    - "NN/g: F-Shaped Pattern of Reading"
    - "IBM Carbon: page header pattern"
```

```yaml
principle:
  name: Density Calibrated to Task
  rule: >
    Inspection surfaces (span tree, attributes JSON, review resolve) are
    dense: monospace, compact rows, maximal information per screen.
    Decision surfaces (marketplace cards, upload, consent dialogs) are
    sparse: few elements, generous spacing.
  rationale: >
    Developers inspecting traces are in "expert scanning" mode and punish
    whitespace-padded inspectors; consumers making acquire/list decisions
    need reduced load. One density everywhere fails both.
  examples:
    positive:
      - "Span detail panel pretty-prints full raw attributes without truncating"
      - "Marketplace card shows ~6 fields, not 20"
    negative:
      - "Card-styled span tree with 80px-tall rows (500-span traces become unscannable)"
      - "Listing consent dialog stuffed with metadata tables"
  validation:
    - list_rows_compact_enough_for_20_visible_items
    - decision_dialogs_under_8_elements
  sources:
    - "Apple HIG: information density"
    - "Microsoft Fluent: density modes for data-heavy surfaces"
```
