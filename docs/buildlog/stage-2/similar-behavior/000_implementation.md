# Similar Behavior — implementation pass

Proposal: `docs/proposals/similar-behavior.md`. Research: `sandbox/behavior-similarity/_FINDINGS.md`.

## Plan

Backend (services/api):

1. Migration `00000000000013_similar_behavior.sql`: `create extension vector`; `trace_embeddings (trace_id pk → traces on delete cascade, embedding vector(1536), model, renderer_version, created_at)` + HNSW cosine index + RLS (visible when the trace is visible); `subscriptions` gains `similar_to_trace_id uuid references traces on delete set null` and `similarity_threshold real check (0–1)`.
2. `analysis/config.py`: `embedding_model` (default `openai/text-embedding-3-small`), `embedding_budget_tokens` (default 8000 — the model's 8191 window minus headroom; the judge rendering budget is 15k so re-truncation is required, middle-out).
3. `analysis/llm.py`: `embed(model, text) -> (vector, CallMeta)` — same env bootstrap and permanent/transient error classification as `complete()`.
4. `analysis/embedding.py`: `render → truncate → embed`; pure, returns the vector.
5. `queries/embeddings.py`: `upsert` / `delete` (vector passed as pgvector text literal — no new client dep), `similar_traces` (visibility-scoped cosine kNN returning list-card rows + similarity, plus count above an optional cutoff), `meets_threshold` (anchor/candidate pair check for matching).
6. `worker/tasks/analyze.py`: embedding stage after the rewrite, gated identically to the judge (`owner_opt_out` / `not_configured`); gated or failed-permanent ⇒ delete the row. Embedding failure must not fail the analysis run (labels are the product; the vector is an enhancement) — log + dead-letter-free, the next analyze run retries it.
7. Routers: `GET /v1/traces/{id}/similar` (404-not-403 via `get_visible`; `anchor_embedded` false + empty when no vector); subscriptions create/patch accept + return anchor fields (anchor must be visible to the owner at write time; threshold required with anchor; "at least one predicate" now counts the anchor).
8. `worker/tasks/match.py` + `queries/subscriptions.py`: match = listed ∧ filter clauses ∧ (no anchor ∨ cosine ≥ threshold); `live_match_count` same.

Frontend (apps/web):

9. `lib/api/traces.ts`: `getSimilarTraces`; `lib/api/subscriptions.ts`: anchor fields.
10. `components/traces/similar-traces.tsx`: header-action button + dialog — ranked list with similarity, in-modal drill-down (overview + labels + `TraceEvidence`), link out, "Subscribe to this behavior" (name + threshold slider with debounced live count via `min_similarity`).
11. Subscriptions UI: anchor chip + threshold editing on the feed page; subscription cards show the anchor.

Tests: unit (truncation, gate logic), integration (embedding row lifecycle incl. opt-out delete, similar endpoint visibility + ordering, anchored subscription matching incl. threshold boundary and missing-embedding cases) with a stubbed embedding call.

## Drift

- `embedding_budget_tokens` default landed at 6000, not 8000 — the heuristic token estimate (chars/4 with a per-message floor) undercounts real tokenization enough that 8000 tripped the model's 8192 hard limit on dense fixtures. 6000 buys the headroom.
- `meets_threshold` never materialized as its own query; matching composes `anchor_clauses` (in `queries/traces.py`, shared with the feed/live-count paths to avoid an embeddings↔traces circular import) into the same SQL the filter clauses use.
- `SubscriptionQuery` lost its "at least one predicate" validator; the rule moved up to `SubscriptionCreateRequest`/`SubscriptionPatchRequest`, where the anchor can satisfy it (an anchor-only subscription has an empty query).
- Integration tests seed geometry into `trace_embeddings` directly instead of stubbing the embed call — retrieval/matching semantics are what these tests own. Each test seeds inside a fresh random orthonormal plane so vectors from earlier runs (the local stack persists) and real worker-produced embeddings are near-orthogonal noise rather than pollution.
- The worker's embedding stage races the seeds on a keyed stack: seeding waits for the analyze run to settle first, and the `relist` helper only waits out a re-analysis when the pre-listing state was an `owner_opt_out` skip (consenting owners' listings fire match directly and leave seeds intact).

## Outcome

- Unit: 333 passed (`tests/unit`, includes `test_embedding.py` truncation/literal/anchor-validation cases).
- Integration: `tests/integration/test_similar_behavior.py` — 3 passed against the live compose stack with a real key (similar-endpoint visibility + ordering + `total_above`, anchored subscription matching end-to-end through listing → match → digest notification incl. strict-threshold non-match and PATCH validation, anchor visibility/pairing 422s).
- Worker logs show the embedding stage running per analyze (~150–550ms) and `match_trace` firing on listing.
- Web: `tsc --noEmit` clean; `pnpm lint` clean for this feature's files (one pre-existing error in untracked `trace-evidence.tsx` from the parallel ui-redesign stream).
