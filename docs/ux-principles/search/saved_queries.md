# Saved Queries / Subscriptions (Stage 2)

Applies to: subscription create/manage, subscription detail feed.

```yaml
principle:
  name: Save the Search You Can See
  rule: >
    A subscription is created by saving the current, visible search state
    ("Save as subscription" from a filtered list), then naming it. Creation
    shows what the query currently matches (backfill preview) before
    confirming. No blank-slate query builder as the primary path.
  rationale: >
    Users can't author a good rule in the abstract; they can recognize one
    by its results. The stored query IS the live search (same vocabulary),
    so the search page is already the builder — reuse it.
  examples:
    positive:
      - "Filter to 'provider: openai AND has_errors', see 41 results, Save as subscription, name it"
    negative:
      - "Subscriptions page with an empty form of dropdowns as the only creation path"
  validation:
    - subscription_creation_starts_from_live_search_state
    - match_preview_shown_before_save
  sources:
    - "NN/g: recognition over recall"
    - ".archive/stage-2-planning/spec-shaping/infra.md §5: stored query = filter vocabulary"
```

```yaml
principle:
  name: A Subscription Shows Its Own Rule
  rule: >
    Subscription list rows and the feed header render the query as the same
    filter chips used in search, plus match count and last-match time. The
    feed page executes the stored query live, marks new-since-last-seen, and
    allows editing the query (which visibly re-runs the feed).
  rationale: >
    A feed whose rule is invisible becomes inexplicable as derived fields
    update (a trace may start matching only after analysis fills a field).
    Showing the rule as chips makes "why is this here?" self-answering.
  examples:
    positive:
      - "Feed header: name + chips + '3 new since last visit' divider in the list"
    negative:
      - "Feed listing traces with no indication of the matching rule"
  validation:
    - feed_displays_query_as_chips
    - new_since_last_seen_marker_present
  sources:
    - "GitHub: saved search / notification filter patterns"
    - "Nielsen heuristic #1"
```

```yaml
principle:
  name: Subscriptions Are Manageable Objects
  rule: >
    The subscriptions list shows each saved query with name, chips, match
    stats, and inline rename/edit/delete. Deleting asks for confirmation
    naming the subscription, and states the consequence (no more match
    notifications; already-acquired traces unaffected).
  rationale: >
    Saved automations users can't audit breed notification distrust — the
    path to "I turned them all off". Consequence-stating deletion prevents
    the wrong mental model that deleting a subscription removes traces.
  examples:
    positive:
      - "'Delete checkout failures? You'll stop receiving match notifications. Your library is unaffected.'"
    negative:
      - "Mystery notifications from a subscription with no management page"
  validation:
    - subscriptions_listed_with_query_and_stats
    - delete_confirmation_states_consequences
  sources:
    - "Shopify Polaris: destructive action confirmation content"
    - "forms/destructive_actions.md"
```
