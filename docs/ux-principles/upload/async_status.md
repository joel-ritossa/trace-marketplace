# Async Ingestion Status

Applies to: `/upload` post-submit; any surface showing upload/analysis job state (stage 2 adds analysis jobs).

```yaml
principle:
  name: Show Queue Truth
  rule: >
    Render the job's real lifecycle states by name — received, processing,
    complete, failed — as the poll reports them. The status word, not just
    a spinner, is always visible. Terminal states stop the polling UI and
    present next actions.
  rationale: >
    Ingestion is genuinely async (Redis queue + worker, retries, DLQ).
    Pretending synchronicity means the UI lies during the exact window
    (queue backlog, worker retry) when truth matters. Named states also
    make support conversations possible ("stuck in processing").
  examples:
    positive:
      - "Spinner + 'processing' text, flipping to 'Complete — 3 traces created' with links"
    negative:
      - "Progress bar animating to 90% and parking (fabricated progress)"
  validation:
    - current_status_name_rendered_during_polling
    - terminal_state_replaces_polling_ui
    - no_fabricated_progress_percentages
  sources:
    - "Nielsen heuristic #1: visibility of system status"
    - "NN/g: Progress Indicators — never fake determinate progress"
```

```yaml
principle:
  name: Terminal States Hand Off Forward
  rule: >
    complete links to each created trace (and My Traces); failed shows the
    verbatim error_message with a 'try another file' action that resets to
    idle; partial success shows created traces AND parse_warnings adjacent.
    The user never dead-ends on a terminal state.
  rationale: >
    Upload is a means, not a destination. The success path's next intent is
    always "inspect what I just made"; the failure path's is "fix and
    retry". Both must be one click.
  examples:
    positive:
      - "'Complete' state lists created trace names as links"
      - "'Failed: invalid OTLP: missing resourceSpans' + reset action"
    negative:
      - "Success state that just says 'Done' with no links"
  validation:
    - complete_state_links_to_created_traces
    - failed_state_shows_verbatim_error_and_retry
    - warnings_shown_adjacent_to_success
  sources:
    - "NN/g: confirmation pages should bridge to the next task"
    - "docs/spec/stage-1/4_pages.md: required upload states"
```

```yaml
principle:
  name: Leaving Doesn't Lose the Job
  rule: >
    The job runs server-side; the UI says so. Users may navigate away
    during processing without warning dialogs — the upload's status remains
    findable (via My Traces / the upload's traces appearing when done, and
    stage-2 notifications for analysis). Do not block navigation with
    "upload in progress" confirms after the POST has been accepted.
  rationale: >
    Once the API has the payload, the browser tab is irrelevant. Teaching
    users they must babysit a spinner trains false mental models and breaks
    the CLI-parity story (sync CLI fires and exits).
  examples:
    positive:
      - "Navigating to /traces during processing; the new traces appear when ingestion completes"
    negative:
      - "beforeunload alert: 'Your upload will be lost!' (it won't)"
  validation:
    - no_navigation_blocking_after_accepted_post
    - job_outcome_discoverable_after_leaving_page
  sources:
    - "Apple HIG: don't make users wait on work the system can do alone"
    - "docs/spec/stage-1/6_architecture.md: async job lifecycle"
```
