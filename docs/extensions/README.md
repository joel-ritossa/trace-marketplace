# Extensions

Design docs for scoped stage-2 extensions — work we may build this round, on top of the base, when an extension is big enough to need its own doc. The authoritative extension *list* lives in the normative spec (`docs/spec/stage-2/0_README.md`, Scope: Extensions); this directory holds the designs.

Distinct from [`docs/follow-up/`](../follow-up/README.md): follow-up items are explicitly *not* scheduled and wait on evidence; extensions are on the menu for this round.

## Index

| File | Extension |
|---|---|
| [task-bounties.md](task-bounties.md) | Demand side: bounties as stored queries matching historic + incoming traces (private included), owner-only alerts, listing as fulfillment |
| [few-shot-exemplars.md](few-shot-exemplars.md) | Exemplars in the judge prompt: static seed phase + dynamic pool phase, budget and reproducibility mechanics |
| [evaluator-training.md](evaluator-training.md) | The feedback loop: human resolutions → exemplar pool (listed traces only) → better judge |
| [judge-model-selection.md](judge-model-selection.md) | Systematic selection/evaluation of the judge model beyond the cheap default |
| [session-stitching.md](session-stitching.md) | Sessions as a first-class grouping over per-turn traces (stage 1 has no session concept) |

Spec-listed extensions still without a design doc (sketch-level in the spec/shaping docs, written up if/when picked up): desktop notifications, similar-trace subscriptions, on-demand enrichment (sketch in `.archive/stage-2-planning/spec-shaping/judging/3_quality-metrics.md`), judge observability.
