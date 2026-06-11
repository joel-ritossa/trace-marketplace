# Stage 2 Ideation — Session 5: Task Bounties (Demand Side)

Fifth ideation session, extending [sessions 3–4](ideation-session-3.md)'s data engine + edge listener with a demand-side mechanism: **task bounties**. Explicitly an extension — future-work tier, not trial scope. Non-normative, raw thinking; stage 2 gets a real `spec/stage-2/` before any code.

## The idea (three compounding pieces)

1. **Bounties.** Consumers request tasks they'll pay a premium for: "I need 50 labeled attempts at multi-step refund processing on a CRM."
2. **Auto-matching.** Incoming traces are automatically checked against open bounties and collected into the bounty group, with a contributor human-in-the-loop confirming task-bounty alignment.
3. **Background fulfillment.** It can all happen server-side: a consumer registers a bounty, which gets filled from historic data and/or continuously updated as new traces arrive. Only if volume is low does the bounty get published to users for active solicitation.

## Why it matters

**The missing demand-side half of the flywheel.** Everything in sessions 3–4 is supply-push (contributors emit traces; the system refines what shows up). Bounties make it demand-pull: contributors learn *what to run their agents on*, and the marketplace starts steering data generation rather than just sorting exhaust. Notably close to Fleet's "real-world challenges drawn from authentic enterprise contexts" — sourced on demand.

**A bounty is a task cluster created before its traces exist.** Matching a trace to a bounty is the exact same intent-embedding operation as session 3's task clustering; the only difference is whether the cluster was mined from supply or declared by demand. One mechanism, two origins — when a trace arrives it's checked against discovered tasks *and* open bounties in the same code path, with the same uncertainty thresholds. Bounties are also the first place real pricing pressure naturally appears.

## Fulfillment as a cost ladder

A registered bounty is a **standing query over the corpus**, escalating through three tiers:

1. **Historic backfill** — on registration, match against existing traces. Instant gratification if inventory exists; reuses the clustering machinery verbatim.
2. **Continuous matching** — every new arrival is checked against open bounties inside the ingest/enrichment pipeline (architecturally: one more enricher). The bounty fills itself as supply flows.
3. **Active solicitation** — only when flow is too low does the bounty get *published*: surfaced in the marketplace UI and pushed as edge-listener prompts ("this trace looks like it fulfills bounty X, premium $Y — submit? [y/n]").

Cheapest channel first, humans only when the market actually needs them — the same design philosophy as the labeling judge (heuristics → LLM → human), applied to demand fulfillment.

## The human-in-the-loop confirmation does real work

- **Consent.** Bounty submission implies listing/sharing, so it can't be silent — private-by-default is a stage-1 invariant. The HIL prompt *is* the ownership-confirmation checkbox, relocated to the edge. Background auto-fill draws only from *listed* traces; historic *private* matches become passive-monetization nudges to the owner: "you have 12 private traces matching an open bounty — list them to fill it?"
- **Match quality.** Embeddings will produce plausible-but-wrong matches; a human keystroke catches them before they pollute a paid bounty.
- **Fraud-lite.** Nobody's traces get auto-shoveled into paid buckets; the judge-vs-contributor disagreement audit from session 4 extends naturally to bounty submissions.

The HIL keeps relocating to wherever consent is needed — a sign the design is right.

## The deliverable becomes a feed, not a file

"Continuously updated" means a consumer isn't buying a snapshot — they're subscribed to a growing dataset ("all new human-labeled attempts at task X"). A materially different product and pricing model than per-trace or per-set acquisition, and closer to how a training-pipeline customer actually consumes data: flowing into eval/training runs as it's generated.

## The full loop

Consumer registers a bounty → backfilled from listed inventory → continuously fed by the ingest pipeline → if thin, published to contributors via marketplace + edge prompts → contributor does their normal work, gets a one-keystroke prompt to confirm, label, and monetize → consumer's dataset grows as a living feed. Passive labeling *and* passive earning through the same prompt channel; demand and supply meet without either side doing extra work.

## Status

Future-work tier, not trial scope. Spec material: worth a section in `spec/stage-2/` future work (or a stage-3 sketch) — even unbuilt, it's the strongest "what would you do next" answer because every piece reuses machinery sessions 3–4 already define (intent matching, uncertainty thresholds, edge prompts, provenance).
