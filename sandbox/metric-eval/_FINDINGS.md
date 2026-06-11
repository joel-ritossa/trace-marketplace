# Metric Eval — Experiment Report

2026-06-11 · Family-3 quality metrics (hallucination critic + RAGAS faithfulness) validated on [PatronusAI/HaluBench](https://huggingface.co/datasets/PatronusAI/HaluBench) (294-trace stratified slice of 14,900 human-verified PASS/FAIL hallucination labels, six sources) · converter `tools/halubench_to_otlp.py` · runner `app.cli.analyze metrics-agreement` · canonical record in `docs/buildlog/stage-2/B5/000_implementation.md`, demo in `docs/demos/metric-agreement.md`. The family-3 sibling of `../judge-eval/_FINDINGS.md`.

## TL;DR

How good are the hallucination/faithfulness labels, and what actually moves them?

1. **Hallucination critic: 88.8% balanced accuracy / 90.4% precision** vs human labels (gpt-5-mini, prompt **V3**, the pinned version, 294 traces, 0% abstention). Faithfulness (RAGAS) separates the two classes at **AUC 0.77** (mean 0.71 faithful vs 0.32 hallucinated).
2. **Prompt iteration moved the error *balance*, not the ceiling.** V1 was over-strict (flagged reasonable inference as fabrication; precision 87.7%). V2 drew the fabrication-vs-inference line (precision → 89.3%, recall slipped). V3 kept conclusion-tolerance but restored per-claim discipline on concrete specifics — **precision → 90.4%, the marginal-best 88.8%**. Pinned.
3. **The ceiling is label semantics, not the prompt.** The critic judges *grounding* (per spec: "not whether the answer is complete or correct for the question"). ~8 of V3's 19 false-negatives are halueval non-answers — grounded-but-evasive answers the dataset marks "hallucinated" — which the critic correctly passes. Several false-positives are arguably correct catches where the human label is wrong. Same structural plateau as the outcome judge (~88–89%).
4. **Faithfulness is a ranking signal, not a clean separator.** AUC 0.77 with a best-threshold accuracy of 71% — usable to sort/triage, not to gate. The iteration budget went to the boolean critic where the error analysis was actionable.

## Setup

- Each HaluBench row (passage, question, answer + PASS/FAIL) → one single-turn RAG trace through the **shipped pipeline**: synthesized `invoke_agent` root, a RETRIEVER span carrying the passage, a chat span with the question in and the answer out. The critic sees exactly the evidence the answering model saw, rendered by the real renderer. Ground truth lives only in `labels.json`; it never leaks into traces. Over-cap passages are skipped, not truncated (a cut passage invalidates its label).
- `app.cli.analyze metrics-agreement` is the production-path harness: runs the metrics, folds a critic confusion matrix (precision/recall/balanced accuracy) and a score fold (AUC, best threshold) vs the labels sidecar. Per-trace results cache atomically, **version-stamped per metric** — a prompt rev on hallucination re-runs only hallucination and reuses faithfulness (that is what made V2/V3 cheap).
- `metric_errors.py` (this dir) dumps disagreements for reading — confusion breakdown by source + per-trace critic reason against the raw question/answer/passage.
- The metric runner parallelizes independent metrics per trace (`run_metric_set`, `app/analysis/registry.py`), in both the worker and this harness — same settle-then-raise error discipline as the judge's vote gathering.

## Reproduce

```sh
# Convert a stratified slice (git-ignored devdata/; raw rows cache locally).
python3 tools/halubench_to_otlp.py            # --count/--source/--seed

# Run the metrics over every trace, fold agreement vs labels.
cd services/api
uv run python -m app.cli.analyze metrics-agreement \
    ../../devdata/benchmarks/halubench/traces/*.json \
    --labels ../../devdata/benchmarks/halubench/labels.json \
    --out ../../out/halubench --concurrency 8

# Read the disagreements (add --full for question/answer/passage).
python3 sandbox/metric-eval/metric_errors.py out/halubench
```

## Result 1 — Hallucination prompt ladder (HaluBench, 294 traces)

| prompt | balanced acc | precision | recall | false-neg | false-pos |
|---|---|---|---|---|---|
| V1 | 88.4% | 87.7% | 90.1% | 15 | 19 |
| V2 (fabrication ≠ inference) | 88.4% | 89.3% | 88.1% | 18 | 16 |
| **V3 (per-claim specifics)** | **88.8%** | **90.4%** | 87.4% | 19 | 14 |

V3 pinned: `METRIC_VERSIONS["hallucination"] = "3"`, `_CRITIC_PROMPTS["hallucination"] = hallucination.V3`. V1/V2 retained in the prompt module with rationale (never-edit-in-place). The shift V1→V3 is precision +2.7pts at −2.7pts recall — a deliberate trade toward fewer false alarms, since a contributed trace wrongly flagged as hallucinated is the costlier error for the marketplace.

## Result 2 — Faithfulness (RAGAS, unchanged across runs)

| metric | mean (faithful) | mean (hallucinated) | AUC | best threshold |
|---|---|---|---|---|
| faithfulness V1 | 0.71 | 0.32 | 0.77 | 0.768 → 71.4% acc |

A real ranking signal (faithful answers score ~2.2× the hallucinated ones on average) but the distributions overlap enough that no single threshold cleanly separates them on this corpus. Left as-is.

## Result 3 — Where the remaining misses live

- **Grounding ≠ answer-correctness (the dominant false-negative class).** halueval labels grounded-but-evasive non-answers as hallucinated — Q "Are both Robin McKinley and Anita Diamant American authors?" → A "Robin McKinley is an author." Nothing is fabricated; the critic correctly passes; the spec says completeness is out of scope. These are the label encoding a different task, not critic errors.
- **False-positives are mostly correct catches.** Several V3 "false-positives" (a PayPal Q2 year-assignment the passage never labels; a "nicotine stimulates lytic HCMV replication" claim absent from the abstract) are defensible flags where the human label is arguably wrong — confirmed by reading the critic's cited reason against the passage.
- **Genuine misses are sparse and noisy.** A few RAGTruth answers add a plausible inference the passage doesn't support (the kind V3 targets) survive at votes=1; single-trace deltas between revs are within sampling noise.
- **Practical recipe:** the hallucination flag is a high-precision (90%) signal good enough to filter/badge on; faithfulness is a triage sort, not a gate; both feed the same HIL routing as the judge for the uncertain tail.

## Cost

Full 294-trace run: 882 LLM calls, ~1.7M tokens, **$1.75** (gpt-5-mini, critic_votes=1). Per-metric caching makes a prompt-rev re-run cost only the changed metric's share (~half).
