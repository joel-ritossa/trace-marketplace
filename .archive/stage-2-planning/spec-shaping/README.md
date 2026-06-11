# Spec Shaping

Converging the finalized stage-2 direction into a requirements spec. The goal of this directory: establish **what we know is concretely required** vs. **what still needs to be figured out**, drill into each open area in its own doc, and only then write the normative `spec/stage-2/`.

## Documents

| Doc | Status |
|---|---|
| [requirements.md](requirements.md) | The requirements snapshot: locked decisions, base + extensions, the rule-based-matching principle, and the placeholder inventory for judging/analysis. |
| [infra.md](infra.md) | Settled: the six infra components (sync CLI, API keys, notifications, review-queue plumbing, subscriptions + bulk acquire, analysis plumbing) plus upload-source provenance. No judging dependency. |
| [judging/](judging/README.md) | Drafted, drilling per family: cross-cutting decisions (label model, HIL routing, feedback loop, validation, exports, enrichment extension) in the README; one doc per analyzer family — [deterministic signals](judging/1_deterministic-signals.md), [outcome judge](judging/2_outcome-judge.md), [quality metrics](judging/3_quality-metrics.md). |

## Working order

1. ~~Infra discussion → document~~ Done ([infra.md](infra.md)).
2. ~~Judging/analysis discussion → structure + family drafts~~ Done ([judging/](judging/README.md)); drill each family's open questions.
3. Promote the combined result to `spec/stage-2/`.
