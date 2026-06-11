# App Shell & Primary Navigation

Applies to: the authenticated `(app)` layout wrapping all signed-in pages.

```yaml
principle:
  name: Top Bar, Not Sidebar
  rule: >
    The shell is a single top header bar: wordmark on the left, flat
    horizontal section links beside it, utilities (bell, account menu) at
    the right edge. No sidebar exists. Secondary surfaces (/uploads
    history) get contextual links from related pages, not nav slots.
    Reconsider only if a future stage adds nested navigation (orgs,
    projects) or pushes past ~7 top-level destinations — that trigger, not
    preference, reopens this decision.
  rationale: >
    The nav inventory is small and flat (4 sections in stage 1, ~6 in
    stage 2) with no contextual trees — below the threshold where a
    sidebar earns its keep. Horizontal width is the scarcest resource on
    the product's most important screens: the span tree + detail panel
    split on /traces/[id] and the review resolve view that embeds it; a
    permanent ~240px sidebar taxes exactly those (inspection tools —
    DevTools, Jaeger — go full-width for the same reason). DESIGN.md's
    Vercel-derived language is itself a top-header-plus-tabs system.
  examples:
    positive:
      - "apps/web (app)/layout.tsx: h-16 header — wordmark + NavLinks left, account right"
      - "Vercel dashboard: top header with horizontal tabs, content full-width below"
    negative:
      - "A 240px sidebar squeezing the span-tree waterfall on trace detail"
      - "Promoting /uploads history into primary nav 'for completeness'"
  validation:
    - shell_is_top_header_no_sidebar
    - inspection_surfaces_get_full_viewport_width
  sources:
    - "Material Design: top app bar suits few flat destinations; rail/drawer only past that"
    - "Apple HIG: information density — chrome must not tax content-dense surfaces"
```

```yaml
principle:
  name: Persistent Flat Navigation
  rule: >
    Primary navigation (Upload, My Traces, Marketplace, Library; stage 2
    adds Review and Subscriptions — Settings and the notification bell are
    utilities, not sections) is persistent on every authenticated screen,
    flat (no nesting), and never collapses behind a hamburger at desktop
    widths. Any major section is reachable in one interaction from
    anywhere.
  rationale: >
    Seven-ish top-level destinations fit a flat structure; the product's
    core loop hops constantly between sections (upload -> traces -> detail
    -> marketplace). Hiding nav adds a tax to every hop.
  examples:
    positive:
      - "Linear / GitHub: workspace nav visible during all primary workflows"
    negative:
      - "Nav that disappears on the trace detail page to 'maximize' the span tree (use collapsible panels inside the page instead)"
  validation:
    - nav_visible_on_all_authenticated_routes
    - any_section_reachable_in_one_interaction
    - nav_item_count_at_most_7_plus_utilities
  sources:
    - "NN/g: navigation visibility; 'hamburger menus hurt discoverability on desktop'"
    - "Material Design: navigation rail/drawer for 3-7 destinations"
```

```yaml
principle:
  name: Current Location Always Marked
  rule: >
    The active section is visually distinct in the nav (active state from
    DESIGN.md tokens), and the page header repeats the section/page name.
    Detail pages mark their parent section active (trace detail highlights
    the section the user came from semantically: My Traces).
  rationale: >
    Nielsen heuristic #1 applied to wayfinding: "where am I" must be
    answerable from the chrome alone, because the three list pages
    (/traces, /marketplace, /library) render near-identical result lists.
  examples:
    positive:
      - "Marketplace and Library lists look similar but their headers and active nav state differ unmistakably"
    negative:
      - "Identical 'Traces' header on all three list pages"
  validation:
    - active_nav_state_present_on_every_route
    - page_title_unique_per_section
  sources:
    - "Nielsen heuristic #1"
    - "NN/g: 'You are here' indicators"
```

```yaml
principle:
  name: Utilities Live in the Shell Edge
  rule: >
    Account menu (with Settings and sign-out) and the notification bell
    (stage 2) live at the header's right edge, separated from primary
    sections. The bell shows an unread count badge; it never blocks
    navigation or auto-opens.
  rationale: >
    Mixing utilities into the section list inflates it past scannability
    and confuses object navigation with account management. Standard
    placement (top-right) is where users already look.
  examples:
    positive:
      - "Bell with unread count top-right; clicking navigates to /notifications, where each item links to its object"
    negative:
      - "'Sign out' as a sidebar item between Marketplace and Library"
  validation:
    - utilities_visually_separated_from_sections
    - notification_bell_shows_unread_count
  sources:
    - "Atlassian Design System: app header layout"
    - "GitHub Primer: global header conventions"
```
