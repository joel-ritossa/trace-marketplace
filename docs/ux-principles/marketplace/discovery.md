# Marketplace Discovery

Applies to: `/marketplace`.

```yaml
principle:
  name: Cards Sell on Evidence, Not Adjectives
  rule: >
    A marketplace card carries decision-grade facts: name, contributor
    display name, listed date, model/provider, span + error counts,
    duration, and (stage 2) outcome label with provenance. No editorial
    copy, star ratings, or invented quality scores. If a quality signal
    isn't a stored field, it doesn't render.
  rationale: >
    Consumers here are buying training/eval data; the evidence IS the
    pitch. Derived fields with provenance are the system's honest quality
    vocabulary — decorating beyond it erodes the trust the marketplace
    depends on.
  examples:
    positive:
      - "Card: 'checkout-agent-run · gpt-4o · 214 spans · 3 errors · 41s · listed May 4 by @ana'"
    negative:
      - "'⭐ Premium quality trace!' banner with no backing field"
  validation:
    - card_fields_map_to_stored_columns
    - contributor_and_listed_date_present
  sources:
    - "NN/g: e-commerce listing pages — comparison-relevant attributes"
    - "global/information_architecture.md: derived data labeled as derived"
```

```yaml
principle:
  name: Acquired State Visible Before the Click
  rule: >
    Cards for traces already in the caller's library carry the
    in-your-library badge in the results list itself, and remain visible
    (not filtered out) — discovery doubles as "have I already got this?".
  rationale: >
    Without the badge, users re-open detail pages to learn they already own
    something — a wasted hop per card. Hiding acquired traces breaks
    re-finding and makes search counts inexplicable across sessions.
  examples:
    positive:
      - "Badge on the card, identical to the detail-page badge"
    negative:
      - "Acquired traces silently excluded from marketplace results"
  validation:
    - acquired_badge_rendered_in_results
    - acquired_traces_not_hidden_from_results
  sources:
    - "docs/spec/stage-1/4_pages.md: in-your-library badge on cards"
    - "Nielsen heuristic #6: recognition over recall"
```

```yaml
principle:
  name: Discovery Defaults to Fresh
  rule: >
    Default sort is listed-date descending, stated visibly. Search ranks by
    relevance while filters keep the recency order. The default view (no
    query) must be useful: newest listings, not an empty prompt to search.
  rationale: >
    A young marketplace's inventory changes weekly; recency is the only
    default that rewards return visits. An empty "search to begin" page
    hides inventory the product needs to show off.
  examples:
    positive:
      - "Landing on /marketplace shows newest listed traces immediately"
    negative:
      - "Blank results until the user types a query"
  validation:
    - default_view_shows_results_without_query
    - sort_order_visible_and_stated
  sources:
    - "NN/g: browse-first vs search-first discovery"
    - "Material Design: meaningful default content"
```
