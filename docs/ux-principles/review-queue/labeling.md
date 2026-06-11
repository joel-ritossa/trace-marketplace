# Review Resolve View — Labeling (Stage 2)

Applies to: the per-item resolve view where a human judges a trace.

```yaml
principle:
  name: Evidence and Verdict Share the Screen
  rule: >
    The resolve view is a split: trace evidence (metadata header + span
    tree, the same inspection components as /traces/[id]) beside the
    verdict form (outcome, failure_mode, task_category). The reviewer never
    leaves the screen to inspect. The machine's current verdict, its
    confidence, and the routing reason render with the form as context —
    visually framed as "the machine's take", distinct from the human's
    controls.
  rationale: >
    Judging a trace requires reading it; any flow that separates reading
    from labeling doubles the work and degrades label quality. Showing the
    machine verdict is honest context (the human is correcting, not
    guessing blind) — but it must not look like a default the human is
    rubber-stamping.
  examples:
    positive:
      - "Left: span tree with errors flagged. Right: verdict form + 'Machine: failure / tool_error (0.58), flagged for low confidence'"
    negative:
      - "Resolve form on its own page with just a link to the trace"
      - "Machine verdict pre-selected in the human's radio group"
  validation:
    - trace_inspection_embedded_in_resolve_view
    - machine_verdict_shown_but_not_preselected
  sources:
    - ".archive/stage-2-planning/spec-shaping/judging/2_outcome-judge.md"
    - "Labeling-tool convention (Label Studio, Scale): evidence beside annotation"
```

```yaml
principle:
  name: The Form Mirrors the Label Model Exactly
  rule: >
    Outcome is a ternary choice — success / failure / indeterminate — all
    three equally selectable; indeterminate is presented as a valid answer
    ("can't tell from this trace"), not a skip or failure-to-answer.
    failure_mode (closed 10-category taxonomy, with one-line descriptions
    available at selection) appears only when failure is chosen.
    task_category is selectable independently. No free-text labels, no
    5-star scales, no sliders.
  rationale: >
    The label model is settled: ternary because humans are reliable at
    binary and unreliable at "this is a 0.7"; closed vocabularies because
    open tags make rule matching mushy. The UI inventing a granularity the
    system doesn't store would collect data that gets thrown away.
  examples:
    positive:
      - "Three radio options; choosing failure reveals the 10-mode select with descriptions"
    negative:
      - "A 0-100 quality slider"
      - "Free-text 'add tags' input on the resolve form"
  validation:
    - outcome_choices_exactly_ternary
    - indeterminate_framed_as_valid_resolution
    - failure_mode_conditional_on_failure
    - no_free_form_label_inputs
  sources:
    - ".archive/stage-2-planning/spec-shaping/judging/README.md: label model"
    - "NN/g: match between system and the real world"
```

```yaml
principle:
  name: Resolution Effects Are Stated
  rule: >
    The resolve action commits the human answer with provenance — reflect
    that: after resolve, show the updated labels with their new provenance
    (human / human_confirmed) and confidence 1.0. Partial resolution is
    allowed where the model allows it (resolving outcome without touching
    category); untouched fields keep machine provenance. Owner-initiated
    relabel from the trace page reuses this same view.
  rationale: >
    Provenance is per-field and consumer-facing; reviewers deserve to see
    their effect (it is also the feedback that makes review feel
    consequential). One resolve surface for queue items and owner relabels
    is the one-source-of-truth rule applied to UI.
  examples:
    positive:
      - "Post-resolve: 'outcome: failure (human) · category: data_extraction (machine, 0.81)'"
    negative:
      - "Resolve silently overwriting category the human never looked at"
  validation:
    - post_resolve_shows_per_field_provenance
    - partial_resolution_supported
    - relabel_reuses_resolve_view
  sources:
    - ".archive/stage-2-planning/spec-shaping/judging/README.md: per-field provenance, owner relabel"
    - "global/feedback.md"
```
