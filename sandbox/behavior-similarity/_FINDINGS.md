# Behavior Similarity — Experiment Report

2026-06-11 · 300 sessions from [Exgentic/agent-llm-traces](https://huggingface.co/datasets/Exgentic/agent-llm-traces) (reusing [anomaly-lab](../anomaly-lab/_FINDINGS.md)'s corpus) · pipeline in [_README.md](_README.md) · per-run artifacts in `results/`

## TL;DR

Can we retrieve traces with *similar behavior* — "this trace brute-forces / escalates / loops, find me more like it"?

1. **Yes, and it is much easier than novelty detection.** Every method beat random by 2–4× on tag-based retrieval, and every method's top retrieved pairs passed a strict blind "same conduct?" judge at 0.7–1.0 precision against a 0.13 random base rate.
2. **The surprise: the plain transcript embedding is the best single behavior retriever — even after removing the topic shortcut.** Anomaly-lab correctly showed transcript geometry is benchmark-pure and useless for *novelty*; but for *retrieval*, conduct is also written in the content (error strings, confirmation prompts, escalation phrases), and that signal outweighs what skeletons preserve. The two results are consistent: representation determines what geometry encodes, and retrieval can exploit content that novelty scoring is poisoned by.
3. Window-level (locality-aware) matching and unsupervised motif clustering both underperformed: local windows match boilerplate, and 29/32 motif clusters were single-benchmark — clustering rediscovers task structure, it does not discover rare conduct (same Clio caveat as anomaly-lab, from the other direction).
4. The practical recipe for the marketplace: **retrieve with the embedding we already store, make behavior explicit with cheap closed-coding tags (~$0.0016/trace), and verify pairs at the surface with a strict contrastive judge (~$0.003/pair)** — never claim "behaves the same" from geometry alone.

## Setup

**Corpus.** Anomaly-lab's 300 stratified sessions (5 harnesses × 6 benchmarks × 7 models), with its transcript renderings, behavior skeletons, and both whole-trace embeddings reused as-is.

**Ground truth — two-stage behavioral coding.** No labels for "behavior" exist, so we built a reference standard the qualitative-research way: open coding (gpt-5-mini free-describes the conduct of a 60-trace stratified sample; $0.09) → hand consolidation into a 16-tag multi-label taxonomy (`tag.py`) → closed coding of all 300 traces ($0.49). Tag distribution: dominant conduct (`self_verification` 170, `error_recovery` 156, `clean_linear` 154) excluded from scoring as uninformative; informative tags range from `repeated_calls` (69) down to `policy_refusal` (4); "rare" = 5–30 carriers (`human_escalation` 29, `parallel_calls` 19, `brute_force` 16, `error_persistence` 14, `no_verification` 5). Retrieval methods never see the tags.

**Methods.** Six similarity matrices (`methods.py`): `feat_cos` (numeric features), `full_emb` (transcript embedding), `skel_emb` (skeleton embedding), `ngram_tfidf` (TF-IDF over action-token 1–3-grams), `seq_align` (normalized indel over action-token sequences), `win_chamfer` (symmetric best-window-match over 2 020 sliding-window skeleton embeddings), plus all rank-averaged hybrids.

**Evaluations.**
- *Tag-based retrieval*: P@5 (any shared informative tag), macro mAP over informative tags, mAP over rare tags; same-benchmark@5 as the topic-leak diagnostic. Run twice: in-corpus, and **cross-benchmark** (candidates from the query's own benchmark excluded — behavior tags are confounded with benchmark, e.g. tau2 ⇒ confirmation conduct, so this removes the topic shortcut entirely).
- *Blind pairwise verification*: each method's top-10 pairs (overall and cross-benchmark) + 15 random controls, judged by gpt-5-mini with a forced procedure (list each trace's patterns, then verdict specific/generic/none). Independent of our tags — this hedges the circularity risk that the tagger saw the same transcripts `full_emb` embeds.

## Result 1 — Behavior retrieval works; the content embedding wins

Tag-based retrieval (300 queries; `random` = Monte-Carlo base rate):

| method | P@5 inf | mAP rare | bench@5 | | P@5 inf (cross-bench) | mAP rare (cross-bench) |
|---|---|---|---|---|---|---|
| feat_cos | 0.45 | 0.16 | 0.66 | | 0.28 | 0.10 |
| **full_emb** | 0.60 | **0.26** | 0.99 | | **0.55** | **0.18** |
| skel_emb | 0.58 | 0.24 | 0.89 | | 0.37 | 0.13 |
| ngram_tfidf | 0.61 | 0.20 | 0.88 | | 0.38 | 0.11 |
| seq_align | 0.59 | 0.22 | 0.84 | | 0.34 | 0.11 |
| win_chamfer | 0.61 | 0.17 | 0.88 | | 0.36 | 0.08 |
| random | 0.21 | 0.07 | 0.20 | | 0.16 | 0.05 |

The blind pairwise judge agrees (precision of top-10 pairs, random base rate 0.13):

| selection | full_emb | skel_emb | ngram_tfidf | seq_align | win_chamfer | feat_cos |
|---|---|---|---|---|---|---|
| top pairs, overall | **1.00** | 0.90 | 0.80 | 0.90 | 0.70 | 0.80 |
| top pairs, cross-benchmark | **0.60** | 0.20 | 0.40 | 0.30 | 0.10 | 0.30 |

(n = 10 per cell, single judge — indicative. 6/10 vs 2/15 control is still p ≈ .03 by Fisher's exact.)

`full_emb`'s winning cross-benchmark pairs are genuinely behavioral, e.g. four of its top ten pairs share *"on `MCP error -32000: Connection closed`, the agent immediately re-sends the same message and continues"* — the same recovery conduct across tau2_airline/retail/telecom tasks. That pattern lives in **content** (the error string), which no skeleton method can see.

**Reconciliation with anomaly-lab.** Anomaly-lab: transcript embeddings are a *topic detector* (0.98 benchmark-pure neighborhoods) and fail at surfacing rare behavior. This lab: those same embeddings are the *best* behavior retriever. Both are true. Novelty asks "is this far from everything?" — there, distance is dominated by the topic axis and behavior drowns. Retrieval asks "what is nearest?" — and the nearest neighbors inside a topic-shaped manifold still sort by the conduct written into the content (error strings, confirmation phrasing, escalation language). Same geometry, different question, opposite verdict. The benchmark-purity caveat survives intact: in-corpus, `full_emb`'s top-5 are 0.99 same-benchmark, so its "similar behavior" is heavily same-domain unless you explicitly filter — which is exactly what the cross-benchmark column simulates (and where it loses 0.26 → 0.18 mAP, the largest absolute drop of any method).

## Result 2 — Where structure does and doesn't help

Per-tag AP, cross-benchmark, best methods:

| tag | full_emb | skel_emb | ngram_tfidf | what carries the signal |
|---|---|---|---|---|
| human_escalation (29) | **0.42** | 0.21 | 0.27 | "transfer to human" language |
| confirm_before_action (57) | **0.41** | 0.25 | 0.26 | confirmation phrasing |
| brute_force (16) | 0.27 | **0.27** | 0.09 | both: sweep text *and* call-storm structure |
| plan_tracking (47) | 0.31 | 0.34 | **0.44** | structural: TodoWrite call rhythm |
| error_persistence (14) | 0.05 | 0.06 | 0.04 | nobody — needs *semantic sameness of repeated errors* |

Language-expressed conduct goes to the content embedding; bookkeeping rhythms go to action n-grams; and `error_persistence` (same error, no adaptation — arguably the most valuable failure pattern for a marketplace) is missed by everything, because detecting it requires knowing that consecutive errors are *the same* error, which content embeddings dilute and skeletons erase. That is a representation gap, not a metric gap: a targeted feature (consecutive identical error signatures) would likely beat all six methods on this tag.

Hybrids: best pair (`full_emb+skel_emb`) ties `full_emb` alone (mAP rare 0.262 vs 0.258 in-corpus, 0.176 vs 0.180 cross-benchmark). Unlike novelty — where combining distance and cluster rarity was the difference between chance and 0.5 precision — retrieval composition bought nothing here. Honest null result.

## Result 3 — Locality and motif clustering both disappoint (RQ2, RQ3)

- `win_chamfer` (best-window matching) was the *worst* cross-benchmark method (blind precision 0.10 ≈ the 0.13 base rate; mAP rare 0.08). Local windows match harness boilerplate — the loop *shape* without the context that makes it the same behavior. Whole-trace context matters more than locality, at least at this corpus size.
- HDBSCAN over the 2 020 window embeddings: 32 clusters, **29 of them single-benchmark**. The three cross-benchmark motifs are verbosity/format styles ("concise assistant", "lengthy iterative responses") and one harness artifact. Unsupervised motif discovery mostly rediscovers task structure — consistent with anomaly-lab's Clio caveat (clustering structurally misses rare patterns). The genuinely interesting recurring behavior in this corpus (the MCP connection-closed retry) was found by *pairwise retrieval*, not by clustering.

## Methodology note — judges must be forced to discriminate

The first pair-judge prompt ("do these share a distinctive behavior? yes/no") said yes to **67%** of random pairs, putting every method at a useless 1.0. Rewriting it as a forced procedure — list each trace's patterns separately, then classify the overlap as specific/generic/none, with "expect specific to be rare" — dropped the random base rate to 0.13 while keeping real signal. Single-call leniency, not model capability, was the failure. (Anomaly-lab hit the same wall from the other side: its explanation layer needed an explicit "nothing unusual" out.)

## Cost (measured via litellm)

| Stage | Calls | Cost | p50 |
|---|---|---|---|
| Open coding (60) | 60 | $0.09 | 5.4 s |
| Closed coding (300) | 300 | $0.49 | 6.9 s |
| Pair judging | 95 | $0.26 | 15.8 s |
| Motif naming | 15 | $0.02 | ~8 s |
| Window embeddings (2 020) | — | ~$0.01 | — |

## Caveats

- One corpus, one tagger model, n = 10 per blind cell. Orderings are trustworthy; absolute numbers are not benchmarks.
- The closed-coding tags are LLM-produced; the tagger saw transcript excerpts, which shares representation with `full_emb`. The blind pairwise eval (procedure-forced, tag-independent) reproduced the same method ordering, so the conclusion doesn't rest on the tags alone — but a human-labeled subset would be the next rigor step.
- Tags are confounded with benchmark by construction of the corpus (tau2 tasks *elicit* confirmation conduct). The cross-benchmark split controls for this in evaluation, but a deployed "similar behavior" feature over a homogeneous corpus will inherit whatever confounds that corpus has.
- Skeleton methods inherit anomaly-lab's harness leak (tool names ⇒ harness; harness@5 0.62–0.67 cross-benchmark). Tool-vocabulary normalization remains the obvious unexplored improvement, and would likely close some of the skeleton–content gap.

## Recommendation

For the marketplace's "find similar behavior" feature:

1. **Retrieve with the transcript embedding we already plan to store** (judge-rendering embedding in pgvector). No new renderer mode, no new index — `full_emb` is the best single retriever and the infrastructure exists for the novelty extension already.
2. **Make behavior explicit with closed-coding tags** at analysis time (~$0.0016/trace, one gpt-5-mini call alongside the existing judge): tags make "similar behavior" filterable/facetable ("show me `human_escalation` traces across all domains"), which retrieval geometry alone can never guarantee — and they fix the same-domain bias by letting the user pivot on conduct directly.
3. **Verify before claiming.** Surface "behaves similarly" only after the strict pairwise judge confirms (~$0.003, ~16 s, on-demand) — the same flag → verify → surface discipline the novelty extension and the stage-2 analysis pipeline already use.
4. **Targeted features for high-value patterns** the geometry misses: `error_persistence` needs an engineered signal (consecutive identical error signatures), not a better embedding.
5. **Skip for now:** window-level matching and unsupervised motif clustering — both underperformed whole-trace retrieval on this corpus and neither is needed for the product feature.
