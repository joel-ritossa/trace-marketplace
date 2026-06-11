# Consent Confirmation (Listing a Trace)

Applies to: the private -> listed visibility toggle. Product-specific: this interaction IS the privacy model.

```yaml
principle:
  name: Listing Is a Deliberate, Informed Act
  rule: >
    Flipping private -> listed requires the ownership-confirmation checkbox
    ("this data is yours to share") plus an explicit confirm button — the
    checkbox is never pre-checked, the confirm is disabled until checked.
    The dialog states what listing means concretely: any signed-in user can
    find, fully inspect, and acquire this trace, including all span
    attributes, prompts, and outputs.
  rationale: >
    Stage 1 ships no redaction or secret detection; the explicit
    contributor confirmation is the entire privacy subsystem. The UI must
    therefore carry the full informational weight: the user must understand
    they are publishing raw payloads. This is informed consent, not a
    speed bump.
  examples:
    positive:
      - "Dialog: consequence paragraph + unchecked checkbox + disabled 'List trace' until checked"
    negative:
      - "One-click toggle that lists instantly"
      - "Pre-checked consent box"
  validation:
    - consent_checkbox_unchecked_by_default
    - confirm_disabled_until_checkbox_checked
    - dialog_states_exposure_scope_concretely
  sources:
    - "docs/spec/stage-1/0_README.md: listing requires explicit contributor confirmation"
    - "GDPR-style consent UX: affirmative, informed, unbundled"
```

```yaml
principle:
  name: Asymmetric Friction by Direction
  rule: >
    listed -> private (reducing exposure) is one click with inline feedback,
    no dialog. private -> listed (increasing exposure) carries the consent
    flow. Friction is proportional to consequence, and always favors the
    safe direction. Note honestly what un-listing does NOT undo: existing
    acquirers keep their library access (render this in the un-list
    feedback if true in the system).
  rationale: >
    Symmetric friction teaches users that all toggles are bureaucratic
    noise; asymmetry encodes the actual risk gradient. Overpromising that
    un-listing "makes it private again" when acquisitions persist would be
    a consent lie — the worst kind of copy bug in this product.
  examples:
    positive:
      - "Un-list: immediate, with note 'Users who already acquired this trace keep access'"
    negative:
      - "Same scary dialog in both directions"
  validation:
    - unlist_is_single_click
    - unlist_feedback_states_persistence_of_existing_acquisitions
  sources:
    - "Apple HIG: friction proportional to consequence"
    - "forms/destructive_actions.md: confirmation is a scarce resource"
```

```yaml
principle:
  name: No Dark Patterns Around Consent
  rule: >
    Never bundle listing into another flow (e.g. "list this trace?"
    defaulting on during upload success), never nag un-listed traces with
    repeated prompts, never style 'keep private' as the visually demoted
    option. The listed state, once set, is permanently visible via the
    badge on every rendering.
  rationale: >
    The marketplace's supply incentive is to maximize listings; consent UX
    exists precisely to resist that incentive. Trust lost to one
    accidentally-listed sensitive trace outweighs any listing-rate gain.
  examples:
    positive:
      - "Upload success links to the trace where listing is available, unprompted"
    negative:
      - "Post-upload modal: 'Share with the community!' [big primary] / 'keep private' [tiny gray text]"
  validation:
    - listing_never_bundled_into_other_flows
    - private_option_never_visually_demoted
  sources:
    - "Deceptive patterns literature (Brignull): confirmshaming, preselection"
    - "docs/spec/stage-1/4_pages.md: visibility always visible"
```
