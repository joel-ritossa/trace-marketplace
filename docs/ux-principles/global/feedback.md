# Feedback & System Status

Applies to: every interaction; especially upload, acquire, visibility toggle, resolve, bulk actions.

```yaml
principle:
  name: Verbatim Errors, Never Generic
  rule: >
    When the API supplies a reason (error_message, parse_warnings, 4xx
    detail), render it verbatim near the point of failure. "Something went
    wrong" is only allowed when the system genuinely has no reason
    (network drop, 500 without detail).
  rationale: >
    This is a spec-level rule (4_pages.md cross-cutting). The product's
    users are developers debugging their own instrumentation; the error
    message IS the product in the failure path.
  examples:
    positive:
      - "Upload failed state shows the importer's error_message verbatim with the failed filename"
      - "Duplicate upload shows a link to the existing upload, not just 'upload failed'"
    negative:
      - "Toast: 'Upload failed. Please try again.' while the API returned a parse error with line numbers"
  validation:
    - api_error_detail_rendered_verbatim
    - failure_states_link_to_remediation_when_known
  sources:
    - "Nielsen heuristic #9: Help users recognize, diagnose, recover from errors"
    - "NN/g: Error-Message Guidelines (precise, constructive, human)"
```

```yaml
principle:
  name: Response-Time-Appropriate Feedback
  rule: >
    <100ms: no indicator. 100ms-1s: subtle inline pending state (button
    spinner). >1s or async jobs (ingestion, analysis): explicit status with
    the real state name (received / processing / complete / failed), not an
    indeterminate spinner alone.
  rationale: >
    Nielsen's response-time thresholds. Ingestion is genuinely asynchronous
    (queue + worker), so the UI must show queue truth, not pretend
    synchronicity.
  examples:
    positive:
      - "Upload page polls GET /v1/uploads/{id} and shows 'processing' with status text until terminal"
      - "Acquire button shows pending state, then flips to 'In your library'"
    negative:
      - "Infinite spinner with no status word during ingestion"
      - "Optimistically showing 'complete' before the poll confirms it"
  validation:
    - async_jobs_show_named_status_not_bare_spinner
    - terminal_states_always_reachable_no_stuck_spinner
  sources:
    - "NN/g: Response Times: The 3 Important Limits"
    - "NN/g: Progress Indicators (percent-done vs spinner)"
```

```yaml
principle:
  name: Confirmation Where the Action Happened
  rule: >
    Success feedback appears in the context of the acted-on object (badge
    flips, row updates, button label changes), not only as a detached toast.
    Toasts may supplement; they never carry the only evidence.
  rationale: >
    Toasts vanish; state changes persist. Acquire must visibly become
    "in your library" on the page; visibility toggle must visibly flip the
    badge everywhere the trace renders.
  examples:
    positive:
      - "After listing, the private badge becomes listed in the header immediately"
      - "Bulk acquire: each selected row gains the in-your-library badge"
    negative:
      - "Toast 'acquired!' while the button still says Acquire until refresh"
  validation:
    - object_state_updates_in_place_after_action
    - no_action_whose_only_feedback_is_a_toast
  sources:
    - "Nielsen heuristic #1: Visibility of system status"
    - "Material Design: snackbars are low-priority, supplemental feedback"
```

```yaml
principle:
  name: Partial Success Is a First-Class State
  rule: >
    When an operation partially succeeds (upload completes with
    parse_warnings, bulk acquire with some failures), show success AND the
    warnings together, itemized. Never collapse to all-good or all-bad.
  rationale: >
    The spec requires parse_warnings shown next to the success state.
    Trace data is messy; partial outcomes are the common case, and hiding
    warnings silently degrades the dataset users think they uploaded.
  examples:
    positive:
      - "'Complete - 3 traces created' with an expandable '2 warnings' list inline"
      - "Bulk acquire: '8 acquired, 2 failed' with per-trace reasons"
    negative:
      - "Green checkmark that hides dropped spans"
  validation:
    - warnings_rendered_adjacent_to_success
    - bulk_results_itemize_failures
  sources:
    - "Shopify Polaris: banner with mixed-status content"
    - "NN/g: visibility of system status for batch operations"
```
