# Data Entry

Applies to: auth forms, tag/description editing, subscription naming, API key naming, review resolve inputs.

```yaml
principle:
  name: Forms Stay Minimal — This Product Barely Has Any
  rule: >
    Every form field must justify itself against the task. The product's
    forms are deliberately tiny (auth: email+password; key mint: name;
    subscription: name over a saved query; trace edit: tags+description).
    Resist field creep: no optional metadata harvesting, no multi-step
    wizards for one-decision flows.
  rationale: >
    Every field added costs completion rate and adds a validation surface.
    The system derives everything it can server-side (the CLI "sends raw
    bytes and nothing else" — the web should match that spirit).
  examples:
    positive:
      - "Mint API key: one name field, one button"
    negative:
      - "Upload form asking for title, category, license, and tags before the file is even parsed"
  validation:
    - every_field_maps_to_a_stored_consumed_value
    - single_decision_flows_are_single_step
  sources:
    - "NN/g: Website Forms Usability — remove fields until it hurts"
    - ".archive/stage-2-planning/spec-shaping/infra.md §1"
```

```yaml
principle:
  name: Labels Above, Validation At the Field, Timing Polite
  rule: >
    Labels sit above inputs (never placeholder-as-label); constraints
    appear as helper text before errors do; validation runs on blur or
    submit, not per keystroke while the user is still typing; error text
    is specific and stays adjacent to its field until fixed.
  rationale: >
    Placeholder labels vanish on focus and fail recall mid-form. Premature
    keystroke validation yells at users for unfinished input; on-blur
    catches errors while context is fresh. Top labels scan fastest for
    short forms.
  examples:
    positive:
      - "'Name' label above the key-name input, 'Used to identify this key later' helper"
    negative:
      - "Email turning red on the first typed character"
  validation:
    - labels_persist_outside_inputs
    - validation_on_blur_or_submit_not_keystroke
    - error_messages_adjacent_to_field
  sources:
    - "NN/g: form label placement; placeholder-as-label harm"
    - "Material Design: text field validation timing"
```

```yaml
principle:
  name: Submit States Are Honest
  rule: >
    Submit buttons name the action's verb ("Create key", "Save", "Resolve"),
    disable and show pending during the request, and re-enable with the
    error displayed on failure. Input is never cleared on failure. Enter
    submits single-field forms.
  rationale: >
    Generic "Submit" labels force re-reading the form to know what happens.
    Cleared-on-failure inputs (especially passwords typed twice) are the
    fastest way to lose a user mid-flow.
  examples:
    positive:
      - "'Acquire' button: pending spinner inside button, error rendered above on failure, input state intact"
    negative:
      - "Form resetting to blank after a 422"
  validation:
    - buttons_labeled_with_specific_verbs
    - input_preserved_on_submit_failure
    - pending_state_prevents_double_submit
  sources:
    - "Nielsen heuristic #5: error prevention (double-submit)"
    - "Shopify Polaris: actionable language"
```
