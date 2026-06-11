# Similar Behavior — Proposal

Status: agreed (chat, 2026-06-11). Research basis: `sandbox/behavior-similarity/_FINDINGS.md` — whole-transcript embeddings (the judge rendering) are the best single behavior retriever (blind pairwise precision 1.0 in-corpus, 0.6 cross-benchmark vs 0.13 base rate); structural representations and window matching underperform.

## What ships

1. **Embedding on analysis.** Every `analyze_trace` run embeds the trace's judge rendering (middle-out truncated to the embedding model's window) and stores the vector in a new `trace_embeddings` table (pgvector, HNSW cosine index). Same gates as the judge: skipped when the model's provider key is missing (`not_configured`) and for private traces without `allow_private_llm_analysis` (consent beats configuration). A gated run deletes any existing vector — the table is a pure function of (payload, gates), like every other derived row.
2. **Similar-traces API.** `GET /v1/traces/{id}/similar` — cosine nearest neighbors over traces visible to the caller (own + listed), each item a standard trace card plus `similarity`. Optional `min_similarity` returns the count above the cutoff (powers the subscription slider preview).
3. **Trace UI.** A "Similar behavior" action on the trace page opens a modal: ranked similar traces with similarity shown; clicking a row drills into an in-modal detail view (overview, analysis labels, conversation evidence) with back navigation and a link out to the full page.
4. **Behavior-anchored subscriptions.** A subscription may carry `similar_to_trace_id` + `similarity_threshold` (0–1 slider in the UI, with a live count of currently-matching listed traces). Anchor ANDs with the existing filter query; a subscription needs at least one predicate counting the anchor. Match evaluation stays event-driven in `match_trace`: the filter SQL plus a vector-distance check. Anchor trace deleted ⇒ anchor nulls out (`on delete set null`) and the subscription matches nothing until edited.

## Decisions

- **Representation:** judge rendering + `text-embedding-3-small` (1536 dims) via litellm — exactly what the research validated; the renderer already exists and is versioned.
- **Threshold UX:** raw 0–1 slider with live match-count preview (no calibrated presets yet — cosine cutoffs are corpus-dependent; the preview is the calibration).
- **Privacy:** embedding is an LLM-provider call, so it rides the judge's exact consent gate. Vectors are derived sensitive data: RLS mirrors trace visibility.
- **Modal depth:** overview + labels + evidence in-modal; full inspector stays on the trace page.
- **Non-goals:** window/motif features (research said no), embedding-based marketplace search, backfill tooling beyond the existing re-analysis paths.

## Costs

~$0.0001/trace at ingest (one embedding call). Similar-trace queries and subscription checks are SQL-only.
