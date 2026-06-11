# Demos

Walkthroughs that show off specific things the system handles well — the
parts worth demonstrating to an evaluator, not the happy path the README
already covers.

Each demo is one slug-named file with three sections:

1. **Steps** — brief, copy-pasteable instructions to run the demo locally.
2. **What was solved** — the problem behind the demo, concretely.
3. **Why it's interesting** — the design choices that make it work, with
   code pointers.

## When to add or update

- **Add** one when a slice ships behavior that is non-obvious to exercise
  but valuable to see working (failure handling, scale edges, reliability
  mechanics).
- **Update** in the same pass as any change that breaks the demo's steps
  or alters what it shows. A demo that doesn't run is worse than none.
- Demos use local data and fixtures only; never include real private trace
  content in steps or screenshots.

## Index

| Demo | Shows | Status |
|---|---|---|
| `large-trace-handling.md` | A 5,000-span trace ingests and inspects smoothly: light span-list API + per-span detail fetch + capped default expansion | Live |
| `cli-sync.md` | The machine door on your own Codex/Claude/Cursor sessions: API-key auth, stateless sync + watch, server-side dedupe, live `/uploads`, honest unattended failures | Live |
| `hil-loop.md` | Uncertain verdicts route to a review queue with reasons: per-upload digest notifications, split-view resolve with human provenance, supersede-never-duplicate, keyless via canned-verdict fault | Live |
| `judge-agreement.md` | The judge scored against expert human labels on real benchmarks (AgentRewardBench, AgentRx): benchmark→OTLP converters, one-command agreement report, routing-on-miss measured | Live |
| `metric-agreement.md` | The hallucination critic and faithfulness score validated against human PASS/FAIL labels (HaluBench): same converter → agreement-fold pattern as the judge, per-metric caching | Live |
| `subscriptions.md` | Saved searches that watch the marketplace: event-driven matching, notify-once digests, new-since-last-seen feed, bulk acquire → labeled zip download | Live |
