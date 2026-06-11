# Settings — API Keys (Stage 2)

Applies to: the settings page minting/revoking API keys for the sync CLI.

```yaml
principle:
  name: The Secret Shows Once, and Says So
  rule: >
    On mint, the plaintext key displays exactly once in a dedicated reveal
    state: monospace, copy button, and the explicit warning "you won't be
    able to see this key again". The state persists until the user
    dismisses it deliberately (no auto-dismiss, no navigation stealing it).
    Afterward the key renders only as name + prefix/last-4 + dates.
  rationale: >
    key_hash storage means the system genuinely cannot re-show the key.
    The UI must transfer that constraint to the user at the only moment it
    can act on it. Auto-dismissing the one chance to copy a secret is an
    unforgivable flow bug.
  examples:
    positive:
      - "GitHub PAT creation: one-time green reveal banner with copy"
    negative:
      - "Key shown in a toast that fades after 5s"
      - "Key list attempting to show full keys later"
  validation:
    - plaintext_key_shown_only_at_mint
    - one_time_warning_present
    - copy_button_on_reveal
    - reveal_dismissed_only_by_user_action
  sources:
    - "GitHub / Stripe API key UX conventions"
    - ".archive/stage-2-planning/spec-shaping/infra.md §2"
```

```yaml
principle:
  name: Keys Are Auditable at a Glance
  rule: >
    The key list shows per key: name, created date, last_used_at ("never
    used" explicitly), and scope (upload-only — stated, since least
    privilege is a feature). Revoke sits per-row with danger styling and a
    consequence-stating confirm; revoked keys either vanish or show
    clearly as revoked, never as ambiguous rows.
  rationale: >
    last_used_at is the user's only tool for "is this old key still in
    use somewhere / has it leaked". Stating the upload-only scope converts
    an invisible security property into user-visible reassurance.
  examples:
    positive:
      - "'sync-laptop · created May 2 · last used 3h ago · upload-only' [Revoke]"
    negative:
      - "List of key names with no usage signal"
  validation:
    - last_used_at_rendered_per_key
    - scope_stated_in_ui
    - revoke_confirms_with_consequence
  sources:
    - "Stripe dashboard: key management surface"
    - "forms/destructive_actions.md"
```

```yaml
principle:
  name: Mint Bridges to the CLI
  rule: >
    The mint-success state shows the key in context: the actual CLI usage
    snippet (env var / flag with the key inlined for copy) — because the
    only reason a key exists is configuring the CLI. Settings page links
    to CLI setup docs.
  rationale: >
    The key is mid-task, not end-task: the user's goal is a working sync.
    Showing a bare token forces them to go find what to do with it;
    showing the command completes the workflow at the moment of highest
    context.
  examples:
    positive:
      - "Reveal state includes: TRACE_API_KEY=tm_… trace-sync watch ./traces"
    negative:
      - "Token string alone, docs three clicks away"
  validation:
    - mint_success_includes_usage_snippet
    - cli_docs_linked_from_settings
  sources:
    - "NN/g: bridge confirmation states to the next task"
    - ".archive/stage-2-planning/spec-shaping/infra.md §1: CLI config"
```
