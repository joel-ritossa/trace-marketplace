# B4 pass 4 — task-category iteration

Goal: the category call shipped as V1 and was never independently measured
(passes 2–3 covered outcome and failure mode only; the spec's
"final `task_category` values, validated against datasets" finalize-at-build
item was never done). Meanwhile ~35% of open review items (40/113 on the
live local stack) exist *only* because of `low_task_category_confidence`.

## Diagnosis (live data, before any change)

- Category confidence is bimodal: unanimous (1.0) or a 2/3 split (0.67).
  With the 0.7 threshold, one dissenting vote out of three routes the trace.
- 17 of 22 splits are `coding` vs `other`; 39 of the 40 routed traces are
  session-ingested (`codex_jsonl` / `anthropic_jsonl`).
- Every `other` vote gives the same reasoning: *"No user request was
  recorded and only the generic 'exec_command' tool was used…"* — the
  category call's goal surface is `first_user_message + tool_names`, and
  `content.first_user_message` only reads `gen_ai.input.messages` /
  `gen_ai.prompt.N.*`. Session importers store the ask in OpenInference
  `input.value` on the first llm span, so the judge sees "(none recorded)"
  while the trace title literally contains the ask.
- Same lesson as pass 3: an **evidence bug, not a prompt or capability
  problem**. `content.py`'s module docstring promises the OpenInference
  fallback chain; `first_user_message` just never implemented it.

## Plan

1. **Evidence fix**: `first_user_message` falls back to the generic input
   keys (`input.value`, `traceloop.entity.input`) — user-role mining when
   the value is a JSON message payload, the raw string otherwise. This also
   repairs the outcome rendering's pinned user message and the family-3
   sample adapter's `user_input` on session traces. Bump `JUDGE_VERSION`
   5 → 6 (prompt-surface change).
2. **Independent eval** (`sandbox/judge-eval/cat_eval.py`): run the category
   call on the production input path over the existing benchmark corpora
   (arb 200 + agentrx 73) plus session-fixture turns (`fixtures/golden/*`),
   cached per (prompt, model, input-text) so the evidence fix naturally
   invalidates only affected traces. Score:
   - accuracy on the defensibly-labelable subset — wholesale benchmark
     mappings only: `tau_retail → customer_ops`,
     `assistantbench → web_research`, `magentic_one → web_research`
     (verified by sampling instructions), session fixtures → `coding`.
     webarena / visualwebarena / workarena are task-level mixed and stay
     unlabeled rather than mislabeled.
   - routing rate (confidence < 0.7) over the *whole* corpus — the metric
     the review queue actually feels — before vs after the fix.
   - missing-goal-surface rate (`first_user_message` is None).
3. **Prompt iteration only if the data demands it** — pass 3 showed
   iteration past the evidence fix churns within noise.
4. **Backfill**: re-analyze the affected session traces on the live stack;
   fresh verdicts supersede the junk review items.

## Drift

- `RENDERER_VERSION` bumped 1 → 2 alongside `JUDGE_VERSION` 5 → 6: the
  fallback also changes the rendering's pinned user message (it is a pure
  function of (trace, renderer version, config)), not just the category
  surface. Renderer goldens regenerated (only the version stamp moved —
  the unit fixtures already used role-attributed messages).
- The backfill exposed a spec-vs-code gap: `1_analysis.md` says "a re-run
  supersedes the open item", but the rewrite only superseded when *new*
  reasons survived — a re-run that resolved the uncertainty left the stale
  open item dangling forever. Fixed per spec: a run that produced a verdict
  always supersedes the open item; a fresh one is created only when kept
  reasons exist (`review_items_q.supersede_open`, integration test
  `test_clean_rerun_supersedes_stale_item`). The hil-loop demo and
  trace-rendering explainer updated in the same pass.
- No prompt iteration: category V1 ships unchanged — the eval showed the
  residual routing is honest ambiguity (mixed webarena tasks, the
  web_research/data_analysis boundary), exactly what the confidence knob
  exists to route.

## Outcome

cat-eval (`sandbox/judge-eval/cat_eval.py`, 279 traces: arb 200 + agentrx
73 + 6 golden-fixture session turns, gpt-5-mini, 3 votes):

| corpus state | routing rate | labeled acc (n=129) | sessions (n=6) |
|---|---|---|---|
| pre-fix (shipped V1) | 11.5% | 84.5% | 50% acc, 3/6 routed |
| post-fix | **10.4%** | **86.8%** | **100% acc, 0/6 routed** |

Live stack backfill: 38 open category-routed items requeued under judge
v6 → 32 cleared (superseded with no fresh item), 5 still route *with the
ask visible* (genuinely ambiguous single-turn asks like "is there a PR for
it?" — per-turn session traces lack session context by construction), 1
re-routed on outcome grounds. Open category-only review items dropped
~47 → ~20 (the live stack keeps syncing new sessions, so totals move).

Known residual, recorded not fixed: mid-session turns ("Run plan again now
pls") are ambiguous from the first user message + tool names alone. The
trace carries a strong prior (`gen_ai.agent.name`, `workspace.cwd`) the
category surface deliberately excludes — widening it is a spec change
(`1_analysis.md` fixes the goal surface) to take up with the user if the
residual rate bothers anyone in practice.
