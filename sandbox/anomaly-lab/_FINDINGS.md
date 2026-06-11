# Behavioral Novelty Detection — Experiment Report

2026-06-11 · 300 sessions from [Exgentic/agent-llm-traces](https://huggingface.co/datasets/Exgentic/agent-llm-traces) · pipeline in [_README.md](_README.md) · per-run artifacts in `results/`

## TL;DR

Can we find *rare agent behavior* in a trace corpus — the init brief's "rare data / rare experiences"?

1. Feature vectors (counts, durations) can't: they measure magnitude, not conduct. **0.0 precision** in blind evaluation.
2. The standard recipe — embed the trace transcript, flag distance outliers — measures *topic*, not behavior (its neighbor geometry is 98% benchmark-pure).
3. **What works: embed a content-stripped behavior skeleton, score by kNN distance combined with cluster-size rarity, then verify flags with a contrastive LLM call.** The combined score hit 0.5 blind precision@10 against a 0.1 base rate; nothing else beat chance.
4. Unit economics are negligible: ~$0.0001/trace to embed, ~$0.003 + ~10 s to explain a flag (on-demand, never render-blocking).

## Setup

**Data.** 300 sessions stratified across the full dataset (5 harnesses × 6 benchmarks × 7 models), text bodies truncated, rendered two ways:

- **Transcript** — chronological message list (approximates the spec's judge rendering): everything the agent said, called, and received.
- **Behavior skeleton** — the same sequence with all natural-language content stripped: roles, tool names, argument keys, result sizes, error markers, finish reasons. Geometry over skeletons can only encode *conduct*.

Both embedded with `text-embedding-3-small`.

**Methods compared** (all on the same 300 traces):

| Method | Idea |
|---|---|
| `feat_z` | Max robust z-score over counts/tokens/errors — the classic dashboard alert |
| `feat_knn` | kNN distance in z-scored feature space |
| `full_knn` / `full_kmeans` | Transcript embeddings: kNN distance / distance to own k-means centroid |
| `skel_knn` / `skel_kmeans` | Same over behavior skeletons |
| `skel_cluster_rarity` | 1 / HDBSCAN cluster size over skeletons (noise = singleton) |
| `skel_combined` | Rank-average of `skel_knn` + `skel_cluster_rarity` |

**Evaluation.** Blind panel: top-10 per method + 10 random controls (51 unique traces), each judged by `gpt-5-mini` — *is this trace behaviorally unusual?* — with the same context for every method (the trace's 3 skeleton-space neighbors). Metric: behavioral precision@10.

## Result 1 — What does embedding novelty actually measure?

| Measure | Transcript | Skeleton |
|---|---|---|
| kNN benchmark purity (share of neighbors from same benchmark) | 0.98 | 0.87 |
| kNN harness purity | 0.66 | 0.72 |
| Spearman vs feature novelty | −0.07 | — |
| Spearman transcript vs skeleton novelty | 0.02 | — |

Three near-zero correlations tell the story: feature novelty, transcript novelty, and skeleton novelty are **three different orderings of the same corpus**. Transcript geometry is essentially a benchmark/topic detector — its top outliers were all trivia-content traces. Skeleton geometry is the only one whose top outliers were behavioral: a zero-tool conversation escalated to a human, a session dead after two spans, a 154-tool-call brute-forcer recovering from validation errors.

**The representation determines what "anomalous" means.** "Embed the trace and find outliers" is an underspecified design.

## Result 2 — Blind method comparison

| Method | Behavioral P@10 |
|---|---|
| feat_z | 0.0 |
| feat_knn | 0.1 |
| full_knn | 0.1 |
| full_kmeans | 0.2 |
| skel_knn | 0.2 |
| skel_kmeans | 0.1 |
| skel_cluster_rarity | 0.2 |
| **skel_combined** | **0.5** |
| *random controls (base rate)* | *0.1* |

- **Only the combined score clearly beats chance** (~p < 0.002 binomial; n = 10 with a single judge, so indicative rather than definitive). Distance and cluster rarity each hit 0.2 alone with *different* false positives — the rank-average keeps their agreement.
- **The classic z-score dashboard found nothing** (0.0): counts fire on magnitude, which the judge correctly declines to call conduct.
- Even the winner is ~50% false positives → the **flag → LLM-verify → surface** pipeline is a requirement, not a nicety.

**What the winner surfaced** — the rare-conduct material a lab would actually buy:

- a cluster of traces ignoring an explicit developer shortlisting constraint
- brute-force phone-number enumeration until a valid voice message appeared
- state mutation with wrong credentials and no verification step
- degenerate search loops (same query, slight variants, same document back)

## Result 3 — The rare-but-clustered question, resolved

Run 1 raised a worry: if rare traces cluster together, kNN distance and neighbor-contrast both under-report them. Run 2 inverted it. The "rare" human-transfer traces actually sit in the **largest** HDBSCAN cluster (size 101), rank ~160–180/300 on every skeleton method, and the blind judge called them "the common customer-simulation pattern." Their run-1 prominence was a small-population artifact (k = 8 against only 20–31 same-benchmark traces).

Cluster size corrects both failure directions: it **demotes** common-pattern members that raw distance inflates, and **promotes** genuinely tiny clusters that distance misses. Independently, the contrastive LLM filter caught the same false positive both times.

## Result 4 — Contrastive explanation quality

Prompting with the flagged trace plus its 3 nearest neighbors ("what does this one do that the comparables don't?") produced grounded, behavior-focused explanations — e.g. *"noisily brute-forces the phone interface: many failing calls iterating through phone numbers, retrying until a valid voice message is found; the comparables use targeted single-shot searches."* Given an explicit out, it also answers **"not unusual"** when the neighbors share the flagged behavior — the explanation layer doubles as the precision filter.

## Cost / latency (measured via litellm)

| Stage | Calls | Cost | p50 | Max |
|---|---|---|---|---|
| Eval judging (~7k-token prompts) | 51 | $0.144 | 8.9 s | 23.0 s |
| Contrastive explanations | 3 | $0.011 | 12.8 s | 13.3 s |
| Embeddings (600, both variants, est.) | — | ~$0.03 | — | — |

## Caveats

- n = 10 per method, one judge model, one corpus — directionally strong, not a benchmark result.
- Harness leaks into skeletons via tool names (`TodoWrite` ⇒ claude_code; purity 0.72). Normalizing tool vocabulary is an open improvement.
- Instrumentation artifacts (span-sparse uploads) rank as anomalies. Defensible for a marketplace — they are data-quality anomalies — but UI copy must not call them interesting behavior.
- The eval judge saw skeleton-space neighbors as context for every method; a different context choice could shift absolute numbers (the *relative* ordering is what we trust).

## Recommendation

Promoted to [docs/extensions/behavioral-novelty.md](../../docs/extensions/behavioral-novelty.md):

1. **Representation:** a second deterministic renderer mode (behavior skeleton) beside the judge rendering, versioned the same way.
2. **Score:** rank-average of kNN distance + cluster-size rarity, computed within the consumer's result set at query time.
3. **Surface:** statistical flags are never shown raw — the on-demand contrastive explanation verifies before the UI calls anything unusual.
4. **Follow-on** (post-B2, once judge labels exist): compose novelty with labels — "behaviorally unusual *successful* traces", "novel recoveries within `failure_mode = plan_adherence_failure`".

## Conclusion

The experiment set out to answer whether the marketplace can surface rare agent behavior, and the answer is yes — but not with any single off-the-shelf method. The classic monitoring approach (feature z-scores) found nothing; the standard embedding recipe found the wrong thing (topic); and each statistical signal alone barely beat chance. What worked was a *composition*: a deliberately engineered behavior representation, two complementary geometric signals, and an LLM verification layer — each covering the others' failure modes.

That shape mirrors the stage-2 analysis architecture as a whole (deterministic signals + LLM judge + human review), which is reassuring: the same design principles — engineered representations, layered cheap-to-expensive signals, never surfacing an unverified machine opinion — generalize from labeling to discovery. The extension is buildable on existing machinery (the renderer gains a mode, the worker gains an embedding call, pgvector gains a column), the unit costs are negligible, and the open questions left are tuning questions, not viability questions. Rare-data discovery moves from "no answer" in the spec review to a validated, costed design.
