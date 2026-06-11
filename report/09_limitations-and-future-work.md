# Limitations & Future Work

An honest accounting of where the trial scope ends. The system was built to be run and evaluated locally within a two-day window; this doc covers the structural gaps in what shipped, the extensions the architecture anticipates but excludes, and the hardening a production deployment would need. The concrete punch list at cutoff — in-flight work, known bugs — is [11](11_outstanding-items.md).

## Known Limitations

### Analysis quality

- **Failure-mode diagnosis lags outcome judging.** 51% any-annotated-category match and 29% root-cause exact on judge-flagged failures (73-trajectory AgentRx corpus) — versus 87.9% outcome agreement on the 200-trajectory AgentRewardBench (ARB) slice. The buildlog's disagreement analysis (`docs/buildlog/stage-2/B4/003_failure-mode-iteration.md`) attributes the residual to taxonomy-boundary ambiguity (judge and annotator describing the same mistake with different labels, verified by reading step citations) and to information that is invisible in-trace by definition (e.g. `underspecified_intent` requires the hidden task instruction). A gpt-5 probe scored the same as gpt-5-mini, so the residual is not model capability; the honest root-cause ceiling on this corpus is likely in the low-30s.
- **Outcome judging is corpus-sensitive.** The 87.9% headline is ARB web tasks; on the all-failure AgentRx corpus, decided-trace outcome agreement is 62.5% (`docs/buildlog/stage-2/B4/003_failure-mode-iteration.md`) — the judge reads a substantial share of those expert-confirmed failures as successes. The headline number does not transfer across trace domains.
- **Long traces are judged through a truncated window.** The renderer hard-bounds what the judge sees to a character budget (~15k tokens' worth by default); middle steps are elided and fields capped — marked, never silent, with `rendering_truncated` stored — but a verdict on a very long trace is a verdict on its prioritized skeleton ([explainer](../docs/explainers/trace-rendering.md), caveats section).
- **The judge model was chosen for cost, and the cheap choice is defended only against one alternative.** A gpt-5 probe on the outcome task (50 traces: the 25 gpt-5-mini misses + 25 random hits) fixed 7 misses, broke 1 hit, and netted ≈ 0 expected full-set improvement at 6.6× the per-trace cost (`docs/buildlog/stage-2/B4/002_judge-iteration.md`) — but no other models or vote counts were swept. Systematic selection is a written-up extension ([judge-model-selection](../docs/extensions/judge-model-selection.md)).

### Validation coverage

The agreement numbers are bounded by their corpora: outcome on web-agent trajectories (200-trajectory ARB slice), failure modes on AgentRx, hallucination/faithfulness on RAG QA (294-trace HaluBench slice). Coding-agent session traces — a major ingestion source via the Codex/Claude Code/Cursor importers — have no expert-labeled outcome agreement number; the only validation touching them is task-category accuracy (86.8% on the 129 defensibly-labelable of 279 mixed traces, including session fixtures). The numbers and their context: [04](04_analysis-pipeline.md#validation).

### Redaction

Detection is pattern-based only: free-text PII without a pattern — names, addresses, locations — is not caught, and there is a known list of misses (short mixed-charset secrets without key context, non-US phone formats, others) plus deliberate over-masking (high-entropy base64, Luhn-passing ids). All detection errors fail toward masking, and listing remains the consent act for anything detection misses. The full caveat list is in [06](06_privacy-and-redaction.md#honest-caveats) and the [redaction-boundary explainer](../docs/explainers/redaction-boundary.md); it is repeated here only because it is the privacy limitation an evaluator should weigh.

### Scale ceilings

- **Subscription matching is linear in subscriptions.** `match_trace` evaluates every subscription against the new trace, one SQL probe each (`app/worker/tasks/match.py`). Correct and fine at trial scale; high subscription counts would need inverted matching (index queries by predicate, not traces by query).
- **The span tree is not virtualized.** On the 5,000-span demo trace, a span-selection re-render with ~300 cards in the DOM takes ~1 s ([measured](../docs/demos/large-trace-handling.md)); the noted fix is in `docs/follow-up/trace-viewer-alternatives.md`.
- **The queue trades durability hardware for a sweep.** The Redis list broker has no acks; a lost in-flight message costs up to ~11 minutes of latency before the scheduler sweep recovers it ([explainer](../docs/explainers/trace-upload-delivery-guarantee.md)). The trade is deliberate and recorded; a latency-sensitive deployment would want an ack-based broker.

### Platform gaps

- **No session-level grouping.** One session turn = one trace; behavior that spans turns (abandonment, cross-turn loops) is invisible to analysis and search. Designed-for as [session-stitching](../docs/extensions/session-stitching.md).
- **Pricing is not built.** Acquisition is free; `price_usd` exists as a column defaulting to 0, and that is the extent of it ([05](05_marketplace.md#acquisition--downloads)).
- **Web notifications are in-app only** (a locked spec decision); there is no email or push channel. The desktop tray app fires native notifications for review requests, which covers the away-from-the-tab case only for desktop users.
- **API types are hand-mirrored, not generated.** The web app's request/response types are kept in sync with the Pydantic schemas by markers and discipline, a recorded deviation from the generate-from-OpenAPI intent ([07](07_engineering-practices.md#code-organization)).
- **CI does not run the API test suite.** The 85-function integration suite runs locally against Compose; CI builds and deploys but does not gate on it ([07](07_engineering-practices.md#testing-strategy)).

## Designed-For Extensions

The architecture anticipates a set of extensions that the base build deliberately excludes. Each has a design doc in [`docs/extensions/`](../docs/extensions/_README.md); the authoritative list is in the spec (`docs/spec/stage-2/0_README.md`, Scope: Extensions). One — similar-trace subscriptions — was built during the trial and is covered in [05](05_marketplace.md#similar-behavior-extension).

| Extension | One line |
|---|---|
| [Task bounties](../docs/extensions/task-bounties.md) | Demand side: bounties as stored queries matching historic + incoming traces, listing as fulfillment — reuses the existing filter language |
| [Few-shot exemplars](../docs/extensions/few-shot-exemplars.md) | Human-resolved traces as judge prompt exemplars, with budget and reproducibility mechanics |
| [Evaluator training](../docs/extensions/evaluator-training.md) | The exemplar pool's lifecycle: human resolutions (listed traces only) → better judge |
| [Judge model selection](../docs/extensions/judge-model-selection.md) | Systematic selection/evaluation of the judge model beyond the cheap default |
| [Session stitching](../docs/extensions/session-stitching.md) | Sessions as a first-class grouping over per-turn traces |
| [Behavioral novelty](../docs/extensions/behavioral-novelty.md) | Rare-data discovery: result-set-relative kNN novelty over behavior embeddings (validated in `sandbox/anomaly-lab/`) |

The exemplar/training pair needs no schema work — resolutions already carry provenance, votes and routing reasons are stored — so they are prompt-layer extensions, not data-model ones ([04](04_analysis-pipeline.md#feedback-loops)).

A second, explicitly *unscheduled* tier lives in [`docs/follow-up/`](../docs/follow-up/README.md): close calls that lost on scope or on the rule-based-matching principle, recorded with what would change each call. The largest is the data-engine ladder (task clustering → per-task verifiers → leaderboards → preference-pair exports), dropped as a unit because every rung depends on intent clustering producing real task groups — the load-bearing, fragile step. The base system's rule-based shadow of it is `task_category` + filter subscriptions; the ladder returns only if that proves too coarse on real data.

## What Production Would Need

Kept deliberately out of trial scope; listed so the boundary is explicit.

- **Payments** — pricing, billing, contributor payouts. The data model leaves room (`price_usd`); nothing else exists.
- **Moderation and abuse handling** — content takedown, reporting, quotas beyond per-user rate limits. The email allowlist is the current (trial-appropriate) gate on who can participate at all.
- **Observability beyond logs** — correlation-ID structured logs exist end-to-end; there are no metrics, dashboards, or alerts, and LLM cost is recorded per call but never capped — no spend budget exists.
- **Account lifecycle and compliance** — trace deletion exists (`DELETE /v1/traces/{id}`, including storage objects); account deletion and data export do not.
- **A CI test gate** — running the integration suite against a Compose stack in CI is straightforward; it was not part of the two-day budget.
- **Secret rotation and DR** — production secrets sit in SSM Parameter Store with no rotation procedure; the deployment is single-region with no tested recovery story.

## Open Questions

Product questions worth a real conversation before further investment:

- **What is the sellable unit?** Individual traces (today's model) or task-shaped datasets (the dropped data-engine arc)? The answer decides whether intent clustering is worth its fragility — and whether flat `task_category` is a permanent answer or a placeholder.
- **What does trace data cost?** Per-trace pricing, subscription access, or bounty-funded contribution ([task-bounties](../docs/extensions/task-bounties.md) is the demand-side design) — nothing in the current system constrains the choice.
- **Is pattern-based redaction plus listing-as-consent enough for a real marketplace?** The alternatives — an owner review step before listing, an NER pass despite its false-positive rate on structured JSON — trade contributor friction against residual risk in opposite directions.
- **When does accumulated human-resolution data justify crossing the feedback lines?** The base system deliberately never fine-tunes, never re-judges old traces, never builds an exemplar pool ([04](04_analysis-pipeline.md#what-feedback-never-does-by-design)). The data to justify crossing — which routing reasons end in human overrules, where exemplars would have helped — accumulates from day one; the threshold for acting on it is a judgment call not yet made.
- **How much label quality is worth paying for per trace?** gpt-5-mini's numbers are measured; whether consumers would pay for the delta a stronger judge or higher vote count buys is not.
