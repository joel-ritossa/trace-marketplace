# Anti-Patterns — Trace Marketplace Specific

Failures specific to this product's domain rules. Several of these violate normative spec, not just taste.

```yaml
anti_pattern:
  name: invisible_visibility
  description: A trace rendered anywhere (row, card, header, notification) without its private/listed badge.
  consequence: Violates the spec rule "visibility is always visible"; users lose track of what they've published — a consent failure, not a styling bug.
  fix: The visibility badge is part of the trace's identity rendering, included in every trace component by construction.
  see: tables/trace_lists.md
  severity: spec_violation
```

```yaml
anti_pattern:
  name: consent_as_speed_bump
  description: The private->listed flow reduced to a frictionless toggle, a pre-checked box, or bundled into upload success.
  consequence: Users publish raw prompts/outputs without informed consent — stage 1 has no redaction layer to catch it; trust is unrecoverable after one incident.
  fix: Unchecked checkbox + consequence copy + explicit confirm, in its own deliberate flow. Asymmetric friction (un-listing stays one click).
  see: forms/consent_confirmation.md
  severity: spec_violation
```

```yaml
anti_pattern:
  name: existence_leak
  description: Distinct UI for "no access" vs "doesn't exist" on private traces (403 copy, 'private trace' teasers in lists or search).
  consequence: Confirms existence of private data to non-owners — an information leak via UI copy.
  fix: One uniform not-found rendering; private traces appear nowhere a non-owner looks.
  see: global/state_handling.md
  severity: spec_violation
```

```yaml
anti_pattern:
  name: client_side_gatekeeping
  description: UI implementing its own access rules — hiding/showing actions on locally computed logic instead of the API's is_owner/acquired/can_download flags.
  consequence: UI and API drift; buttons 403 after click or capabilities vanish wrongly. The spec says the UI renders what the API returns.
  fix: Action rendering is a pure function of API entitlement flags.
  see: global/hierarchy.md, marketplace/acquisition.md
  severity: spec_violation
```

```yaml
anti_pattern:
  name: span_data_paternalism
  description: Truncating, summarizing-without-expansion, or omitting span attributes/events "for cleanliness" for users with access.
  consequence: Violates "no span data is hidden"; breaks debugging (the truncated byte is always the one needed); undermines the inspect-before-acquire trust model.
  fix: Progressive disclosure — default-render little, but every byte reachable and copyable.
  see: trace-inspection/detail_panel.md, global/progressive_disclosure.md
  severity: spec_violation
```

```yaml
anti_pattern:
  name: machine_label_passing_as_human
  description: Rendering derived labels (outcome, failure_mode, scores) without provenance/confidence, styled with the same authority as verified facts.
  consequence: Consumers buy on labels the system itself only half-trusts; the provenance quality dimension the architecture carefully stores is squandered.
  fix: Provenance tag and confidence accompany every derived label rendering.
  see: global/information_architecture.md, review-queue/labeling.md
```

```yaml
anti_pattern:
  name: commerce_cosplay
  description: Payment-flavored UI on $0 acquisitions — "Buy", carts, checkout steps, price placeholders, "order complete".
  consequence: Hesitation on an action meant to be frictionless; misrepresents the system (no payment exists); sets false expectations for stage-2 pricing.
  fix: "Acquire (free)" verb; instant entitlement flip; library framing, not purchase-history framing.
  see: marketplace/acquisition.md
```

```yaml
anti_pattern:
  name: duplicate_punished_as_failure
  description: Styling the sha-256 duplicate-upload response as a red error without linking the existing upload.
  consequence: Users perceive idempotent dedupe (a feature, CLI-critical) as breakage; re-sync workflows feel broken.
  fix: Neutral informational state: "already uploaded", link to the existing upload.
  see: upload/file_upload.md
```

```yaml
anti_pattern:
  name: review_guilt_machine
  description: Framing the HIL queue as blocking work — red "action required" badges, alarm counts, nag notifications for unresolved items.
  consequence: Contradicts the system (low confidence blocks nothing); drives rushed, low-quality labels or wholesale bell-muting — both poison the feedback loop.
  fix: Advisory framing, positive empty state, digest notifications.
  see: review-queue/queue.md, notifications/notifications.md
```

```yaml
anti_pattern:
  name: granularity_invention
  description: Label inputs with granularity the model doesn't store — quality sliders, star ratings, free-text tags on the resolve form.
  consequence: Collects unreliable data ("humans are unreliable at 0.7") that the closed-vocabulary system throws away; mushy rules downstream.
  fix: The form mirrors the label model exactly: ternary outcome, closed taxonomies, nothing free-form.
  see: review-queue/labeling.md
```

```yaml
anti_pattern:
  name: auto_acquire_smuggling
  description: Any mechanism acquiring traces without a per-instance human selection — "auto-acquire matches" toggles, opt-out bulk inclusion.
  consequence: Violates the locked "no auto-acquire" decision; libraries fill with unvetted data; consent-by-default in reverse.
  fix: Selection is always explicit; subscriptions notify, humans multi-select, bulk acquire confirms the count.
  see: tables/bulk_selection.md
  severity: spec_violation
```

```yaml
anti_pattern:
  name: secret_reshow_pretense
  description: API key UI implying stored keys can be viewed again (eye icons on hashed keys, "view key" actions), or auto-dismissing the one-time reveal.
  consequence: Either a security lie (only the hash exists) or a lost secret and a support ticket; both erode trust in key handling.
  fix: One-time reveal with explicit warning, user-dismissed only; thereafter name + prefix only.
  see: settings/api_keys.md
```

```yaml
anti_pattern:
  name: analysis_pending_as_absence
  description: Unanalyzed traces (no trace_analysis row) rendering blank label areas or silently vanishing from derived-field filters with no disclosure.
  consequence: "NULL never matches" surprises users as data loss; blank labels are misread as "judged: nothing notable".
  fix: Explicit "analysis pending" placeholder; filtered views disclose excluded-pending counts.
  see: search/filtering.md
```
