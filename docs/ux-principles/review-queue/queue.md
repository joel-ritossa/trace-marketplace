# Review Queue (Stage 2)

Applies to: the HIL queue page listing traces with uncertain analysis outcomes.

```yaml
principle:
  name: The Queue Says Why Each Item Is Here
  rule: >
    Every queue row states its routing reason in plain language: judge said
    indeterminate; low confidence (with the value); deterministic signals
    disagree with the judge; uncertain category. Plus the trace identity,
    the machine's current verdict, and item age. Sort oldest-first by
    default.
  rationale: >
    The reviewer's first question is "what am I being asked and why does
    the machine need me". Routing reasons differ in what the human should
    look at (disagreement -> check the error spans; low-confidence category
    -> check the task shape). Hiding the reason makes every review start
    from zero.
  examples:
    positive:
      - "Row: 'checkout-agent-run — machine: success (0.55) — flagged: heuristic suspects failure — 2d ago'"
    negative:
      - "Bare list of trace names with 'Review' buttons"
  validation:
    - routing_reason_rendered_per_item
    - machine_verdict_and_confidence_visible_in_queue
  sources:
    - ".archive/stage-2-planning/spec-shaping/judging/README.md: HIL routing triggers"
    - "NN/g: queue/inbox patterns — triage needs metadata at list level"
```

```yaml
principle:
  name: Nothing Is Blocked, and the Queue Says So
  rule: >
    The queue communicates that review is advisory, not gating: unresolved
    items leave traces machine-labeled and fully usable. No alarm styling
    on the queue count, no "action required" framing. The empty queue is a
    positive state ("Nothing needs review").
  rationale: >
    The judging spec is explicit: low confidence blocks nothing. Framing
    review as obligation creates guilt-driven churn through items; framing
    it as label-quality improvement attracts exactly the careful attention
    labels need.
  examples:
    positive:
      - "'12 traces would benefit from your judgment' over ': 12 ITEMS REQUIRE ACTION'"
    negative:
      - "Red badge styling implying the pipeline is stuck on the human"
  validation:
    - queue_copy_advisory_not_blocking
    - empty_queue_rendered_as_positive_state
  sources:
    - ".archive/stage-2-planning/spec-shaping/judging/README.md: low confidence blocks nothing"
    - "global/state_handling.md: empty states"
```

```yaml
principle:
  name: Batches Stay Digestible
  rule: >
    A large sync producing many review items groups them by upload in the
    queue ("12 from upload X", expandable), mirroring the notification
    digest. Within a group, sequential flow (resolve -> auto-advance to
    next) is offered so a batch is a session, not n page loads.
  rationale: >
    Flood control is designed into notifications (digest per upload); the
    queue must match, or one CLI sync renders a 200-row wall. Auto-advance
    converts review from navigation work into judgment work.
  examples:
    positive:
      - "Resolve screen: 'Resolve & next' as primary; queue shows grouped uploads"
    negative:
      - "200 ungrouped rows; each resolve returns to the queue top"
  validation:
    - queue_groups_by_upload_when_bulk
    - resolve_and_next_flow_available
  sources:
    - ".archive/stage-2-planning/spec-shaping/judging/README.md: flood control"
    - "Material Design: sequential task flows"
```
