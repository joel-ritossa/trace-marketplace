# Metric Agreement — Validating the Hallucination Critic Against Human Labels

The headline claim: the hallucination critic agrees with human PASS/FAIL
labels on **88.8% of traces (90.4% precision)** across a six-source HaluBench
RAG-QA slice (294 traces, gpt-5-mini), and the RAGAS faithfulness score
separates the two classes at **AUC 0.77**. This demo produces both numbers on
real human-labeled trajectories — HaluBench (14,900 human-verified
hallucination labels over RAGTruth, FinanceBench, PubMedQA, CovidQA, DROP,
halueval). It is the family-3 sibling of `judge-agreement.md`: same converter
→ agreement-fold pattern, applied to the quality metrics instead of the
outcome judge. The full measurement history — prompt iterations V1→V2→V3,
error taxonomy, the label-semantics ceiling — is in
`docs/buildlog/stage-2/B5/000_implementation.md`.

## Steps

Requires an LLM key in `.env.local` and a HuggingFace read token (`HF_TOKEN`);
HaluBench is open access (no gate to accept).

```sh
# 1. Convert a stratified HaluBench slice into OTLP JSON + a labels sidecar
#    (git-ignored devdata/benchmarks/halubench/; ~294 files, even across the
#    six sources, balanced PASS/FAIL within each). Raw rows cache locally, so
#    a re-slice never re-fetches.
python3 tools/halubench_to_otlp.py            # --count/--source/--seed to vary

# 2. One command: run the metrics over every trace, fold agreement vs labels.
cd services/api
uv run python -m app.cli.analyze metrics-agreement \
    ../../devdata/benchmarks/halubench/traces/*.json \
    --labels ../../devdata/benchmarks/halubench/labels.json \
    --out ../../out/halubench --concurrency 8
```

The command prints the report and writes `report.json`: the human × critic
confusion matrix with decided/strict agreement and precision/recall/balanced
accuracy for the boolean hallucination critic, plus mean score per class,
AUC, and best-threshold accuracy for the faithfulness score. `--metrics`
selects which metrics run (default `hallucination,faithfulness`).

Each trace caches its per-metric results in `--out`, stamped with each
metric's version and the model; interrupt and re-run to resume — and a prompt
rev on one metric re-runs only that metric, reusing the rest. That is what
made the V2/V3 hallucination iterations cheap: faithfulness was computed once
and reused across all three runs.

## What was solved

The quality metrics produce the boolean labels and 0–1 scores consumers
filter and subscribe on. "Trust the critic" is no more defensible than
"trust the judge" — both need a number against human ground truth on the
*shipped* pipeline. HaluBench's rows are framework-native QA tuples, not
OTLP; the converter turns each into a single-turn RAG trace (synthesized
`invoke_agent` root, a RETRIEVER span carrying the passage, a chat span with
the question in and the answer out) so the critic sees exactly the evidence,
rendered by the same renderer, as any contributed trace.

## Why it's interesting

- **The critic judges grounding, and the number is honest about it.** ~88–89%
  is the plateau, and the ceiling is label semantics, not the prompt:
  halueval marks grounded-but-evasive non-answers as hallucinated, which the
  critic (correctly, per spec — "judge grounding only, not completeness")
  passes. The buildlog reads every disagreement and shows several "errors"
  are the label being arguably wrong. We don't game the corpus.
- **Prompt iteration is versioned and measured.** V1 was over-strict
  (flagged reasonable inference; precision 87.7%); V2 drew the
  fabrication-vs-inference line (precision →89.3%, recall slipped); V3 kept
  conclusion-tolerance but restored per-claim discipline on concrete
  specifics (precision →90.4%, the pinned version). Superseded prompts stay
  in the module with their rationale (`prompts/critics/hallucination.py`).
- **Agreement is a pure fold** (`app/analysis/validation.py`
  `metric_agreement_report`): results × labels → typed report, with separate
  critic (confusion matrix) and score (AUC, threshold) folds, exhaustively
  unit-tested. The LLM run and the arithmetic can't contaminate each other.
- **Metrics run concurrently** (`run_metric_set`,
  `app/analysis/registry.py`): independent metrics for a trace fire together
  via `asyncio.gather` with the judge's settle-then-raise error discipline —
  the same path in the worker and this runner, so the demo exercises the
  shipped concurrency, not a one-off.
- **Ground truth never leaks into the trace:** PASS/FAIL lives only in the
  labels sidecar; spans carry no label-derived signal, and over-cap passages
  are skipped rather than truncated (a cut passage would invalidate its
  label).
