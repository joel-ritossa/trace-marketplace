# Destructive Actions

Applies to: trace delete, API key revoke, subscription delete.

```yaml
principle:
  name: Destruction Is Separated, Styled, and Named
  rule: >
    Destructive actions render in danger styling (DESIGN.md error tokens),
    physically separated from constructive actions (end of menus with a
    divider, or a distinct danger section) — never adjacent to a primary
    button, never the default focus, never triggered by Enter from
    elsewhere in a form.
  rationale: >
    Slip-class errors (right intention, wrong motor action) are prevented
    by distance and visual distinction, not by confirmation dialogs alone.
    A delete button beside download is an ambush.
  examples:
    positive:
      - "GitHub 'Danger Zone': destructive actions fenced at the page bottom"
      - "Delete at the foot of the trace actions menu, divided"
    negative:
      - "Red Delete directly beside the primary Download button"
  validation:
    - destructive_actions_visually_and_spatially_separated
    - destructive_action_never_default_focus
  sources:
    - "GitHub Primer: danger zone pattern"
    - "Apple HIG: destructive button placement in action sheets"
```

```yaml
principle:
  name: Confirm With Consequences, Verb Buttons
  rule: >
    The confirmation dialog names the object ("Delete trace
    'checkout-agent-run'?"), states the real consequences (raw payload and
    spans removed; for listed traces: acquirers lose download access — say
    whatever the system actually does), and uses verb buttons ("Delete
    trace" / "Cancel"), never Yes/No or OK. Irreversibility is stated when
    true.
  rationale: >
    Generic confirms get dismissed on autopilot; consequence-specific
    content is what makes the pause worth it. Verb buttons let users
    confirm from the button text alone (HIG), catching the wrong-object
    case ("wait — that's not the trace I meant").
  examples:
    positive:
      - "'Revoke key sync-laptop? The CLI using it will stop authenticating immediately.' [Revoke key] [Cancel]"
    negative:
      - "'Are you sure?' [Yes] [No]"
  validation:
    - confirmation_names_specific_object
    - confirmation_states_real_consequences
    - buttons_are_verbs_not_yes_no
  sources:
    - "NN/g: Confirmation Dialogs Can Prevent User Errors — if not overused"
    - "Apple HIG: alert button titles are verbs"
```

```yaml
principle:
  name: Confirmation Is a Scarce Resource
  rule: >
    Confirm only what is destructive and hard to reverse: delete, revoke.
    Do NOT confirm acquire (idempotent, free), visibility back to private,
    marking notifications read, or filter clearing. Reversible acts get
    easy reversal, not interrogation. Type-to-confirm is reserved for the
    most severe case only (trace delete), if used at all.
  rationale: >
    Each unnecessary dialog trains users to click through dialogs — spending
    the attention budget needed when the dialog matters. Frequency times
    severity decides: frequent+safe = no dialog; rare+destructive = strong
    dialog.
  examples:
    positive:
      - "Acquire executes immediately; delete confirms"
    negative:
      - "'Are you sure you want to apply this filter?'"
  validation:
    - no_confirmation_on_reversible_or_idempotent_actions
    - confirmation_strength_proportional_to_severity
  sources:
    - "NN/g: overuse of confirmation dialogs destroys their protective value"
    - "anti-patterns/global.md: excessive_confirmation"
```
