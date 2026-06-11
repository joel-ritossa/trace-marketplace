# Spec Shaping

Converging the finalized stage-2 direction into a requirements spec. The goal of this directory: establish **what we know is concretely required** vs. **what still needs to be figured out**, drill into each open area in its own doc, and only then write the normative `spec/stage-2/`.

## Documents

| Doc | Status |
|---|---|
| [requirements.md](requirements.md) | The requirements snapshot: locked decisions, base + extensions, the rule-based-matching principle. Written while judging was still open — its "placeholder" framing for judging/exports was superseded by `judging/` before promotion. |
| [infra.md](infra.md) | Settled: the six infra components (sync CLI, API keys, notifications, review-queue plumbing, subscriptions + bulk acquire, analysis plumbing) plus upload-source provenance. |
| [judging/](judging/README.md) | Settled: cross-cutting decisions (label model, storage, HIL routing, feedback loop, validation, exports) in the README; one doc per analyzer family — [deterministic signals](judging/1_deterministic-signals.md), [outcome judge](judging/2_outcome-judge.md), [quality metrics](judging/3_quality-metrics.md). |
| [ui-deltas.md](ui-deltas.md) | Settled: mutations to existing stage-1 pages plus stage-1 gaps stage 2 turns critical. Its declared infra deltas were folded directly into `spec/stage-2/` at promotion, not into `infra.md`. |
| [ui-new.md](ui-new.md) | Settled: the new stage-2 surfaces (review, notifications, subscriptions, settings, uploads), page by page. |

## Working order

1. ~~Infra discussion → document~~ Done ([infra.md](infra.md)).
2. ~~Judging/analysis discussion → structure + family drafts~~ Done ([judging/](judging/README.md)); drill each family's open questions.
3. ~~Promote the combined result to `spec/stage-2/`~~ Done — `spec/stage-2/` is now normative; this directory is historical.
