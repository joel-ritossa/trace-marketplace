# Acquisition & Download

Applies to: `/traces/[traceId]` actions, `/library`, bulk acquire surfaces.

```yaml
principle:
  name: Free Is Stated, Not Implied
  rule: >
    The acquire action is labeled as a free acquisition ("Acquire (free)" or
    equivalent) per spec. No payment iconography (carts, price tags beyond
    the $0 semantics), no "buy" verbs. Post-acquire, the button region flips
    to Download + in-your-library badge without navigation.
  rationale: >
    Acquisition is an entitlement object, not a transaction. Commerce
    framing creates hesitation ("will I be charged?") on an action the
    product wants to be frictionless, and misrepresents the stage-1 system.
  examples:
    positive:
      - "'Acquire — free' -> instant flip to 'Download' + badge"
    negative:
      - "'Add to cart' for a $0 entitlement"
  validation:
    - acquire_labeled_free
    - acquire_flips_to_download_in_place
  sources:
    - "docs/spec/stage-1/4_pages.md: labeled as a free acquisition"
    - "global/feedback.md: confirmation where the action happened"
```

```yaml
principle:
  name: The Gate Explains Itself
  rule: >
    For a listed trace the caller hasn't acquired, Download renders disabled
    with the inline reason "acquire to download" adjacent to the enabled
    Acquire button. The full inspection surface (metadata, complete span
    tree) stays open — only the raw payload is gated.
  rationale: >
    Inspect-before-acquire is the marketplace's trust model: consumers
    evaluate complete data, then take it. Hiding the download button
    (instead of disabling with reason) would leave users unable to learn
    the rule; gating inspection would force blind acquisition.
  examples:
    positive:
      - "Disabled Download with caption, next to primary Acquire"
    negative:
      - "Span tree blurred behind an 'acquire to view' overlay"
  validation:
    - inspection_ungated_for_listed_traces
    - disabled_download_carries_reason
  sources:
    - "docs/spec/stage-1/0_README.md: listed traces fully inspectable"
    - "global/hierarchy.md: entitlement drives prominence"
```

```yaml
principle:
  name: Download Delivers the Original
  rule: >
    Download copy says what the artifact is: the original raw uploaded
    payload (and stage 2: plus labels.jsonl for bulk exports). Filename is
    meaningful (trace name/id, not a hash). Library cards offer direct
    download without forcing a detail-page visit.
  rationale: >
    "Raw payload preserved verbatim" is a core platform guarantee —
    surfacing it at the download moment is what makes the guarantee
    legible. Consumers download many traces; per-card download in the
    library respects the batch workflow.
  examples:
    positive:
      - "'Download original payload (.json)' producing checkout-agent-run.json"
    negative:
      - "Unlabeled download yielding 3f9a2c…json with no hint of contents"
  validation:
    - download_states_artifact_identity
    - library_offers_per_card_download
  sources:
    - "docs/spec/stage-1/0_README.md: download original raw payload"
    - "NN/g: setting expectations for file downloads"
```
