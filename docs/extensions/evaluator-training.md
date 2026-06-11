# Extension: Evaluator Training

Use human review resolutions to improve the outcome judge — no fine-tuning, no training infra. This doc owns the **feedback loop and exemplar sourcing**; the prompt mechanism (how exemplars enter the judge) is [few-shot exemplars](few-shot-exemplars.md).

Base context: the judge ([`2_outcome-judge.md`](../.archive/stage-2-planning/spec-shaping/judging/2_outcome-judge.md)) runs zero-shot on rubric + trace rendering. This extension is the only feedback path from HIL labels back into judge behavior.

## The loop

human labels (review resolutions) → exemplar pool → exemplars in judge prompts → verdicts align with marketplace standards → less disagreement → fewer review items.

## The pool

- **A query, not a table:** traces with `human` / `human_confirmed` provenance, **listed traces only**. Exemplars inject trace content into prompts judging *other users'* traces; listing is the consent act, so private uploads never become exemplars. This privacy constraint is non-negotiable.
- Selection at judge time (most recent N, same-`task_category` preference) and prompt-budget rules are specified in [few-shot exemplars](few-shot-exemplars.md).

## Why extension, not base

- Zero-shot must ship and be measured first; the pool is empty on day one (cold start — the static seed phase of few-shot exemplars covers it).
- Effectiveness is only measurable against the zero-shot validation baseline.

## Open questions (settled if/when picked up)

- Pool hygiene: do relabeled traces (owner corrections) update their exemplar, and do disputed labels exit the pool?
- Whether the pool needs per-category minimums before same-category preference helps rather than starves.
- Measurement cadence: re-run the validation slice per analyzer version, or continuously via the judge-observability extension.
