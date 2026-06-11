# Extension: Few-Shot Exemplars

Labeled example traces injected into the outcome judge's prompt. Base is deliberately zero-shot (rubric only); this extension is the single place the few-shot mechanism is designed — it has been deferred from several discussions, so it gets its own doc.

An **exemplar** = a trace's compact rendering (same renderer as the judge input, tighter caps) + its verdict (outcome, failure_mode, category).

## Two phases

1. **Static seed.** A hand-curated set (synthetic or scrubbed traces + verdicts) baked into the rubric. Solves the cold start, cheap to ship, no pool query. Curation before real data exists is guesswork — which is why it isn't base — but as phase one of this extension it sets the prompt mechanics the dynamic phase reuses.
2. **Dynamic pool.** Exemplars selected at judge time from human-resolved traces — sourcing, privacy constraints (listed traces only), and the feedback loop are owned by [evaluator training](evaluator-training.md). Selection: most recent N, preferring same `task_category`.

## Mechanics (shared by both phases)

- **Prompt budget interaction:** exemplars compete with the judged trace's rendering for tokens. Exemplar renderings get tighter elision/caps than the judged trace; the judged trace always wins ties.
- **Reproducibility:** exemplar-assisted verdicts are a distinct analyzer version, and the exemplar set (trace ids, or seed-set version for static) is logged with the result row — a verdict is only auditable if you know what examples were in the prompt.
- **Placement:** exemplars sit in the rubric section, clearly delimited from the judged trace, each as rendering → verdict → one-line rationale (few-shot with rationales is the documented stronger pattern).
- **Composed-call scope:** exemplars apply to the outcome call (and failure-mode call, with failure exemplars). The category call doesn't need them — it's a thin classification.

## Success metric

Agreement-vs-human delta on the validation slice, with and without exemplars; secondarily, HIL-routing rate drop. If exemplars don't move agreement, they're just cost.

## Open questions (settled if/when picked up)

- N per call; recency vs diversity in dynamic selection; minimum pool size before the dynamic phase activates.
- Static seed composition: per-category coverage? failure-heavy (failures are where the judge errs)?
- Whether exemplars are cached as pre-rendered text (renderer version pinning) or re-rendered per judge run.
