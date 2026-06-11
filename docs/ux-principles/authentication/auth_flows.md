# Authentication

Applies to: `/`, `/auth/sign-in`, `/auth/sign-up`, session expiry anywhere.

```yaml
principle:
  name: Minimal Friction, Single Account Type
  rule: >
    Sign-up asks only what Supabase auth needs (email-based). No role
    selection, no plan choice, no onboarding wizard. Sign-in and sign-up are
    sibling pages with mutual links and identical layout.
  rationale: >
    The spec defines one account type that both contributes and consumes;
    any "I am a buyer / I am a seller" step would encode a distinction the
    system doesn't have. Trial evaluators must reach the product in
    seconds.
  examples:
    positive:
      - "Email + password, one button, link to the sibling flow, done"
    negative:
      - "Multi-step signup asking for company, use case, and role"
  validation:
    - signup_fields_limited_to_auth_requirements
    - sign_in_and_sign_up_cross_linked
  sources:
    - "NN/g: signup walls and form friction"
    - "docs/spec/stage-1/0_README.md: one account type"
```

```yaml
principle:
  name: Auth Errors Are Specific and Safe
  rule: >
    Validation errors render inline at the offending field (bad email
    format, weak password) before submit where possible. Credential
    failures render a single non-attributing message ("email or password
    is incorrect") — never disclose which half failed or whether an email
    is registered.
  rationale: >
    Inline specificity for fixable errors (Nielsen #9); deliberate vagueness
    where specificity is an account-enumeration vector. These coexist: be
    precise about format, vague about existence.
  examples:
    positive:
      - "Invalid email format flagged inline on blur; wrong password -> generic credential message above the form"
    negative:
      - "'No account exists for this email' on sign-in"
  validation:
    - field_format_errors_inline
    - credential_errors_non_enumerating
  sources:
    - "NN/g: Error-Message Guidelines"
    - "OWASP: authentication error message non-disclosure"
```

```yaml
principle:
  name: Session Expiry Is Recoverable In Place
  rule: >
    When a session expires mid-task, preserve the route (and unsaved input
    where feasible), explain why re-auth is needed, and return the user to
    where they were. Never silently swallow API 401s into blank screens.
  rationale: >
    Trace inspection sessions run long; review-queue work is interruptible
    by design. Losing a half-written description or queue position to an
    expired JWT punishes exactly the engaged users.
  examples:
    positive:
      - "401 -> redirect to sign-in with message 'session expired' -> return to /review/item-7"
    negative:
      - "Edit form that silently fails to save on expired session"
  validation:
    - expired_session_message_shown
    - post_reauth_returns_to_interrupted_route
  sources:
    - "Nielsen heuristic #9"
    - "Apple HIG: preserve user work across interruptions"
```
