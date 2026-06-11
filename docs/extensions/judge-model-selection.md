# Extension: Judge Model Selection / Evaluation

Base ships with a single cheap judge model (env-var tunable, mini/haiku/flash-class default — see [`2_outcome-judge.md`](../.archive/stage-2-planning/spec-shaping/judging/2_outcome-judge.md)). Available providers: **OpenAI, Anthropic, and OpenRouter** — so candidate coverage is wide and switching is config, not code. This extension makes the model choice evidence-based instead of default-based: **we will run evaluations against a labeled dataset at some point**; this doc is where that work is scoped.

## What it is

- **A model bake-off harness** reusing the validation setup: run each candidate model over the converted labeled slices (AgentRewardBench; AgentRx benchmark and TRAIL as failure-mode material), report agreement-vs-expert-labels per model, broken down by `task_category` and `failure_mode`.
- **Cost/latency table per candidate** — tokens per verdict × price, p50/p95 latency — so the accuracy/cost trade-off is explicit.
- **Calibration check:** self-reported confidence vs actual agreement per model (a judge whose 0.9 means 70% right needs different routing thresholds than one whose 0.9 means 95%). Threshold defaults (the 0.7 knob) may become per-model.

## Candidate follow-on: escalation routing

Cheap-first routing — run the cheap model, escalate to a stronger model only when confidence is below threshold or family 1 disagrees — before falling through to HIL. Cuts review-queue volume at bounded cost. Only worth it if the bake-off shows the strong model actually resolves the cheap model's uncertain cases.

## Relationship to other surfaces

- The relevant findings ("no single LLM judge wins everywhere") motivate measuring rather than assuming.
- Pairs with the **judge observability** extension (human-agreement rate over time): observability tells you *when* the current model underperforms; this extension tells you *what to switch to*.
- Analyzer versioning already records which model produced each verdict (model id belongs in the analyzer version/result metadata), so historical comparison is free.

## Open questions (settled if/when picked up)

- Candidate model list and the bar for switching defaults (accuracy delta vs cost multiple).
- Whether thresholds become per-model config or stay one global knob.
- Whether escalation routing is worth the added pipeline branch at demo scale.
