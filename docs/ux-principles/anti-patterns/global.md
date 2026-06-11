# Anti-Patterns — Global

Universal failures. Agents check generated UI against every entry here regardless of screen type.

```yaml
anti_pattern:
  name: competing_ctas
  description: Multiple actions on one screen state with equal visual weight (several filled buttons).
  consequence: Decision paralysis; the screen cannot communicate its purpose; misclicks on consequential actions.
  fix: Promote exactly one primary action per state; demote the rest to secondary/ghost or menus.
  see: global/hierarchy.md
```

```yaml
anti_pattern:
  name: modal_inside_modal
  description: A dialog spawning another dialog (e.g. confirm inside an edit modal).
  consequence: Focus-trap conflicts, lost context, Esc ambiguity, unreviewable z-index soup.
  fix: Flatten — one modal layer max. Replace inner layers with inline expansion, panel content, or a dedicated page.
  see: trace-inspection/detail_panel.md
```

```yaml
anti_pattern:
  name: generic_error_swallowing
  description: Rendering "Something went wrong" while the API returned a specific reason.
  consequence: Violates a normative spec rule; users cannot self-recover; support burden replaces self-service.
  fix: Render error_message/4xx detail verbatim at the point of failure; reserve generic copy for genuinely reasonless failures.
  see: global/feedback.md
```

```yaml
anti_pattern:
  name: excessive_confirmation
  description: Confirm dialogs on reversible, idempotent, or frequent actions (filters, acquire, mark-read).
  consequence: Dialog blindness — users autopilot through ALL confirms, including delete and revoke.
  fix: Confirm only destructive+hard-to-reverse acts; give reversible acts easy reversal instead.
  see: forms/destructive_actions.md
```

```yaml
anti_pattern:
  name: hidden_save
  description: Edits that commit (or discard) without a visible save/cancel affordance, or save buttons below the fold/off-screen.
  consequence: Users don't know whether work is persisted; phantom data loss.
  fix: Visible save/cancel adjacent to the edited field (inline edit) or a persistent action bar for forms.
  see: trace-inspection/metadata_header.md, forms/data_entry.md
```

```yaml
anti_pattern:
  name: toast_as_only_evidence
  description: Action success conveyed solely by a transient toast while the acted-on object's UI stays stale.
  consequence: Missed feedback; users repeat the action; UI state contradicts system state.
  fix: Flip object state in place (badge, button, row); toasts only supplement.
  see: global/feedback.md
```

```yaml
anti_pattern:
  name: blank_state_void
  description: Empty datasets rendered as nothing — bare table headers, white space, or "No data".
  consequence: Reads as breakage; first-run users dead-end; the onboarding loop (empty -> action) never starts.
  fix: Every empty state names the missing object and links the single action that fills it.
  see: global/state_handling.md
```

```yaml
anti_pattern:
  name: filter_amnesia
  description: Active filters invisible at results level; or no-results rendered as the generic empty state.
  consequence: "The product lost my data" — users mistrust counts and search instead of clearing a forgotten chip.
  fix: Active filters as removable chips, always visible; distinct no-results state showing the guilty query.
  see: search/filtering.md, global/state_handling.md
```

```yaml
anti_pattern:
  name: navigation_trap
  description: Screens reachable without a way back/out — detail pages with no return path, flows that hijack nav, auth walls that drop destination.
  consequence: Orientation loss; users use browser-back as an escape hatch and lose state.
  fix: Persistent shell nav everywhere; return paths preserve list state; auth redirects round-trip the destination.
  see: navigation/app_shell.md, navigation/routing.md
```

```yaml
anti_pattern:
  name: fabricated_progress
  description: Determinate progress bars animating on guesses; spinners pretending async jobs are synchronous.
  consequence: Trust damage when the bar parks at 90%; users can't distinguish slow from stuck.
  fix: Named real states (received/processing/...) with indeterminate indicators; determinate only with real progress data.
  see: upload/async_status.md
```

```yaml
anti_pattern:
  name: infinite_form
  description: Forms collecting fields beyond what the task consumes; multi-step wizards for single decisions.
  consequence: Completion-rate decay; validation surface bloat; harvested data nobody reads.
  fix: Every field must map to a stored, consumed value; cut until it hurts.
  see: forms/data_entry.md
```

```yaml
anti_pattern:
  name: disabled_without_reason
  description: Disabled buttons/controls with no adjacent explanation of what would enable them.
  consequence: Dead-end confusion; users click repeatedly or assume breakage; the rule is unlearnable.
  fix: Pair every disabled state with an inline reason ("acquire to download").
  see: global/hierarchy.md, marketplace/acquisition.md
```

```yaml
anti_pattern:
  name: color_only_state
  description: Status conveyed exclusively by hue (red/green dots, tinted rows) with no icon or text.
  consequence: Invisible to colorblind users and in poor viewing conditions; fails WCAG 1.4.1 on core product signals.
  fix: Always pair color with icon and/or text label.
  see: accessibility/accessibility.md
```

```yaml
anti_pattern:
  name: scroll_to_act
  description: Primary actions or critical status placed below the fold on screens whose body scrolls (long span trees, long forms).
  consequence: Hidden save actions; missed errors; users act on stale understanding of the screen.
  fix: Sticky header band for identity/status/actions; body alone scrolls.
  see: trace-inspection/metadata_header.md, global/hierarchy.md
```
