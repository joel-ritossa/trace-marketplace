# Routing & Deep Links

Applies to: all routes; URL state on list pages; auth gating.

```yaml
principle:
  name: URL Carries View State
  rule: >
    Search terms, filters, and pagination on list pages serialize into the
    URL (query params). Refreshing, sharing, or back-navigating reproduces
    the exact view. Span selection on trace detail may use a param so a
    specific span is linkable.
  rationale: >
    The filter language is the product's matching primitive (search ->
    subscriptions -> bounties share one vocabulary). A URL-serializable
    query is also the natural seed for "save as subscription". Developers
    share links to specific failing spans when debugging together.
  examples:
    positive:
      - "/marketplace?q=checkout&provider=openai&has_errors=true survives refresh"
      - "'Save as subscription' pre-fills from the current URL query"
    negative:
      - "Filters in component state only; back button loses the query"
  validation:
    - list_state_round_trips_through_url
    - back_button_restores_previous_query
  sources:
    - "NN/g: URL as UI"
    - "Next.js App Router conventions: searchParams as state"
```

```yaml
principle:
  name: Auth Gate Preserves Destination
  rule: >
    Hitting a protected route signed-out redirects to sign-in and returns
    to the originally requested URL after success. Signed-in users hitting
    `/` go straight to their library.
  rationale: >
    Stage-2 notifications and subscription matches will deep-link users
    into the app from outside a session; losing the destination at the
    auth wall breaks every such link.
  examples:
    positive:
      - "Open /traces/abc signed out -> sign in -> land on /traces/abc"
    negative:
      - "Every sign-in dumps the user at /library regardless of intent"
  validation:
    - post_auth_redirect_to_requested_url
    - signed_in_root_redirects_to_library
  sources:
    - "NN/g: login walls and interruption cost"
    - "docs/spec/stage-1/4_pages.md: '/' behavior"
```

```yaml
principle:
  name: Context Return Paths
  rule: >
    Detail and resolve pages provide an explicit path back to the list/queue
    they came from, preserving its state. With cross-section entry points
    into /traces/[id] (my traces, marketplace, library, notifications), the
    back affordance returns to the actual origin — rely on browser back plus
    a labeled in-page return link; do not hardcode 'Back to marketplace'.
  rationale: >
    The same canonical page serves four entry contexts. A hardcoded parent
    breadcrumb lies in three of them; a lost filter state on return makes
    multi-trace triage (open, inspect, back, next) miserable.
  examples:
    positive:
      - "Review resolve: 'Back to queue' returns to the queue with position preserved, plus next/previous item controls"
    negative:
      - "Trace detail breadcrumb always claiming Marketplace as parent"
  validation:
    - return_navigation_restores_list_state
    - queue_items_offer_next_previous
  sources:
    - "NN/g: breadcrumbs show location, not path — omit when ancestry is ambiguous"
    - "Apple HIG: navigation should reflect how the user got there"
```
