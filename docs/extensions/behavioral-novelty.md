# Extension: Behavioral Novelty (Rare-Data Discovery)

The init brief names two things consumers pay for: failure modes and **rare data / rare experiences**. The base build answers failure modes thoroughly (labels, taxonomy, HIL) and serves *topic* rarity implicitly — sparse `task_category` × `failure_mode` cells are filterable and subscribable like anything else. What nothing in the base addresses is **behavioral** rarity: a trace whose counts and labels are unremarkable but whose conduct is unusual (a novel recovery strategy, an agent that gave up instantly, a brute-force enumeration). This extension adds behavioral novelty as a derived, result-set-relative ranking with an on-demand LLM explanation.

## Evidence (sandbox experiment, 2026-06-11)

Tested on 300 sessions stratified from Exgentic/agent-llm-traces (5 harnesses × 6 benchmarks × 7 models); pipeline and full writeup in `sandbox/anomaly-lab/` (`_FINDINGS.md`).

1. **Feature vectors miss behavior.** kNN novelty over embeddings vs. novelty over numeric features (call counts, errors, tokens): Spearman −0.07, top-20 overlap 1/20.
2. **Embedding the full rendering captures topic, not behavior.** Neighbor benchmark-purity 0.98; top outliers were all trivia-content traces — rare *content*. The naive Clio/Phoenix recipe inherits this.
3. **Embedding a content-stripped behavior skeleton captures behavior.** Skeletons keep roles, tool names, argument keys, result sizes, error markers — no natural-language content. Skeleton novelty is orthogonal to full-rendering novelty (Spearman 0.02) and surfaced genuine behavioral anomalies: a zero-tool conversation escalated to a human, a session dead after two spans, a 154-tool-call brute-forcer recovering from validation errors.
4. **Contrastive LLM explanation works and self-corrects.** Prompting with the flagged trace plus its 3 nearest neighbors produced grounded behavioral one-liners, and answered "not unusual" when the neighbors shared the flagged behavior — a precision filter over the statistical flag.
5. **Blind method comparison (run 2): combining distance with cluster rarity is what beats chance.** Top-10s from eight methods plus random controls, blind-judged for behavioral unusualness: rank-averaging skeleton-kNN distance with HDBSCAN cluster-size rarity scored 0.5 precision@10 vs a 0.1 base rate; every single-signal method (feature z-scores, feature kNN, transcript/skeleton kNN, k-means, cluster rarity alone) sat at 0.0–0.2. Cluster size also resolved the rare-but-clustered worry in both directions. Measured unit costs: ~$0.0001/trace to embed, ~$0.003 and ~10 s to explain a flagged trace.

## Mechanism sketch

- **Representation:** a second deterministic renderer mode — `render_skeleton(trace, config)` beside the judge rendering, same module, same versioning rules (B0's renderer owns it). The representation *is* the design decision: skeleton ⇒ behavioral novelty; transcript ⇒ topic novelty, which labels already serve.
- **Embedding:** one embedding call per trace at analysis time (env-configured model, keyless-skip with recorded reason, exactly like the judge); vector stored via pgvector. An embedding is *derivation* — matching and search stay rule-based per the locked decision; no embedding search surface exists.
- **Score:** rank-average of kNN distance and cluster-size rarity **within the consumer's current result set**, computed at query time (a deterministic function of the result set; no stored global score to go stale). Run 2 showed the combination is what beats chance — distance alone inflates small-population artifacts, cluster rarity alone misses isolated points. Once a consumer has filtered by `task_category` or query, the topic axis is controlled and skeleton geometry ranks behavior.
- **Surfaces:** an "unusual in this set" ranking/strip on marketplace search results and subscription feeds, evidence shown as chips; nothing on unfiltered lists.
- **Explanation:** on-demand "explain what's unusual" — one contrastive LLM call over the flagged trace + nearest-neighbor renderings (the on-demand-enrichment machinery; persisted as an `analyzer_results` row if kept). Never automatic, never required for the flag to render.

## Why extension, not base

- New external dependency (embedding model) and new infra (pgvector) for a read-path ranking feature; base ships the label/filter foundation it ranks over.
- The base already has a defensible rare-data answer (sparse label cells are filterable/subscribable); this sharpens it rather than unblocking it.
- A4's filter surfaces must exist before "unusual within this result set" has a result set to rank.

## Open questions (settled if/when picked up)

- ~~**Rare-but-clustered behavior**~~ — resolved by run 2: cluster size joins the score (see Evidence 5). The contrastive explanation additionally serves as the precision filter — even the winning method is ~50% false positives, so flags are verified before being *called* interesting.
- **Composition with labels (follow-on):** once judge labels exist (B2+), novelty composes with them — "behaviorally unusual *successful* traces", "novel recoveries within `failure_mode = plan_adherence_failure`" — a second extension pass after this one.
- **Harness leakage:** tool names encode the harness (`TodoWrite` ⇒ claude_code; skeleton neighbor harness-purity 0.72). Whether to normalize tool names away, and whether harness-rarity is signal or noise for a marketplace buyer.
- **Instrumentation artifacts** (span-sparse uploads) rank as anomalies. Plausibly a feature — they are data-quality anomalies — but the UI copy must not call them interesting behavior.
- Result-set size bounds: minimum n for a meaningful ranking, and the cap above which kNN moves from exact to indexed (pgvector HNSW).
- Embedding model/version bumps: vectors are per-version artifacts like judge verdicts; re-embedding policy follows the (extension-level) re-analysis story.
