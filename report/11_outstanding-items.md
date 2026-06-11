# Outstanding Items

What was in flight or consciously left open when the trial ended — the concrete punch list, as distinct from the structural limitations in [09](09_limitations-and-future-work.md). Everything here is grounded in the working tree, a buildlog entry, or an audit record an evaluator can open.

## In Flight at Cutoff

The working tree at cutoff holds one finished-but-uncommitted pass and one slice that is spec'd but not coded (all of it visible in `git status` against the last commit):

- **B4 pass 4 — task-category iteration (finished, uncommitted).** The evidence fix that makes session-trace asks visible to the judge (`first_user_message` falls back to OpenInference `input.value`), `JUDGE_VERSION` 5→6 and `RENDERER_VERSION` 1→2, the category eval harness (`sandbox/judge-eval/cat_eval.py`) with its results recorded, and a spec-vs-code fix the backfill exposed: a re-run that resolves the uncertainty now supersedes the stale open review item instead of leaving it dangling (integration test `test_clean_rerun_supersedes_stale_item`). The HIL demo and trace-rendering explainer were updated in the same pass. Record: `docs/buildlog/stage-2/B4/004_task-category-iteration.md`.
- **task-scope slice — spec'd, not implemented.** A user-approved follow-up to pass 4: grow `task_category` from 8 to 50 grouped values and let owners hard-scope the judge's category vocabulary to the categories they actually work in. The spec sections ([1_analysis.md](../docs/spec/stage-2/1_analysis.md) taxonomy table and scoping rules, plus data-model, API, and pages), the migration (`supabase/migrations/00000000000015_task_scope.sql`), and the buildlog plan (`docs/buildlog/stage-2/task-scope/000_implementation.md`) exist; no code does — `JUDGE_VERSION` is still 6, and `task_categories` appears nowhere outside spec and migration. The migration is additive with a default, so applying it ahead of the code is harmless.
- **Small tie-ups in the same tree**: the conversation view now renders `gen_ai.reasoning` (closing a gap noted in the A6 audit), the review queue refetches on realtime changes, web realtime channels get per-instance topics (two subscribers to one table no longer collide), a desktop-app download link in the account menu, the subscription dialog reordered to put the name field first, and a `make web-dev` hot-reload target.
- **Production lag.** None of the above is committed, so the deployed [trace-mp.com](https://trace-mp.com) stack runs the previous build: judge v5 still judges session-trace categories without seeing the ask (so its review queue accumulates the routing noise pass 4 fixed), and the old supersede rule still applies. Landing the tree, deploying, and re-running the backfill there closes this; the local stack already had it applied (38 stale items requeued → 32 cleared).

## Known Bugs & Rough Edges

- **Stale-analysis race** (accepted in `docs/buildlog/stage-2/A2/001_audit.md`): an in-flight analyze run that read old content can finish after a re-ingest's fresh run and overwrite it with analysis of the pre-rewrite content. Tight window, recoverable with `requeue trace`; serializing analysis against ingest wasn't worth the machinery at this scale.
- **Codex `thread_rolled_back` is not honored**: rolled-back turns stay in the converted per-turn traces (1 occurrence in the audited sample; `docs/buildlog/stage-2/A6/002_harness-parsing-audit.md`).
- **Two integration tests assume a keyless stack** (`docs/buildlog/stage-2/A4/001_audit.md`): with a real LLM key configured they fail by construction — one expects a `not_configured` skip, the other's analysis-wait timeout stretches under live-judge latency. Run them keyless for the strict result.
- **Residual category routing on mid-session turns**: after the pass-4 backfill, 5 session traces still routed *with the ask visible* — single-turn asks like "is there a PR for it?" are genuinely ambiguous without session context. This is the confidence knob working as designed, but it is queue noise an owner sees (`docs/buildlog/stage-2/B4/004_task-category-iteration.md`).
- **The reasoning card has no live data exercising it**: real Codex rollouts carry only encrypted reasoning (0/818 sampled items had summary text) and the synced Cursor sessions have no thinking blocks, so the new `gen_ai.reasoning` rendering is pinned only by the golden corpus.
- **Cosmetic**: the `/review/[itemId]` width-breakout uses `100vw`, which can produce a sliver of horizontal scroll on scrollbar-bearing platforms (accepted in `docs/buildlog/stage-2/A3/001_audit.md`).

## Deferred Decisions

- **Widening the category goal surface.** Mid-session turns are ambiguous from the first user message + tool names alone, and the trace carries a strong prior (`gen_ai.agent.name`, `workspace.cwd`) the surface deliberately excludes. Widening it is a spec change to [1_analysis.md](../docs/spec/stage-2/1_analysis.md), parked until the residual routing rate bothers someone in practice (`docs/buildlog/stage-2/B4/004_task-category-iteration.md`). The task-scope slice above attacks the same queue noise from the other side and was the approved next step.
- **Mining resolution outcomes** — which routing reasons most often end in a human overrule — is deferred, as noted in [04](04_analysis-pipeline.md); the data for it accumulates from day one.

## Cleanup & Debt

- **Demo-scale N+1 queries** stay until query evidence demands batching (accepted in `docs/buildlog/stage-2/A4/001_audit.md`).
- **Claimed-vs-actual unit coverage**: the A2 plan promised middleware unit tests mirroring stage 1's `retry_dlq` coverage; they were never written. The behavior is covered by the integration suite (transient retry, permanent fast-path, dead-letter shape, requeue), so the gap is the claim, not the coverage (`docs/buildlog/stage-2/A2/001_audit.md`).
- **Vendored `agent-prism` trace components** (`apps/web/src/components/agent-prism/`) carry two upstream TODO comments (responsive breakpoints in `shared.ts`, the `IconButton` API) — cosmetic.
