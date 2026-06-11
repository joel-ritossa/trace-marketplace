# Follow-up

Items deliberately deferred during design discussions — close calls that lost on scope, not on merit. Each file collects the deferred candidates for one area, with enough rationale that picking one up later doesn't require re-deriving the original discussion.

Distinct from spec extensions: extensions are scoped stage-2 work we may build this round; follow-up items are explicitly *not* scheduled — they get revisited only when evidence (usage, hit rates, demand) says so.

## When to add or update

- **Add** an entry when a discussion cuts something worth remembering — record what it was, why it lost, and what would change the call.
- **Update** when the blocking condition changes (e.g. a dependency lands) or the item gets promoted into a spec.

## Index

| File | Area |
|---|---|
| [data-engine-candidates.md](data-engine-candidates.md) | The dropped stage-2 data-engine arc: task clustering, per-task verifiers, leaderboards, preference pairs/exports, environment fingerprinting |
| [judging-post-v1-candidates.md](judging-post-v1-candidates.md) | Deferred signals and analyzers from the stage-2 judging/analysis design |
| [trace-viewer-alternatives.md](trace-viewer-alternatives.md) | Alternatives to AgentPrism for the span-tree inspection UI |
