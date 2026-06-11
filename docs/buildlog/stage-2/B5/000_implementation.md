# B5 — Quality-metrics validation: HaluBench converter, agreement harness, hallucination prompt iteration

The family-3 counterpart of B4. B4 validated the outcome judge against
AgentRewardBench/AgentRx; B5 does the same for the quality metrics — a
labeled corpus, an agreement fold, a baseline number, prompt iteration under
the per-metric versioning convention, and a concurrency pass on the metric
runner. Spec amendment recorded first (`6_build-order.md` B5,
`1_analysis.md` Validation).

## Dataset

PatronusAI/HaluBench (HF, open access): 14,900 single-turn RAG QA rows
(passage, question, answer) with human-verified PASS/FAIL hallucination
labels, aggregated from six sources (RAGTruth, FinanceBench, PubMedQA,
CovidQA, DROP, halueval). One row maps 1:1 onto the repo's single-turn RAG
trace shape (`fixtures/retrieval-qa.json`): a synthesized `invoke_agent`
root, one RETRIEVER span carrying the passage as an indexed document, and one
chat LLM span whose input messages carry the passage as RAG system context +
the question as the user message, and whose output is the answer. The critic
sees exactly the evidence the answering model saw.

`tools/halubench_to_otlp.py --count 300 --seed 0` → 294 traces, stratified
even across the six sources and balanced PASS/FAIL within each (covidQA's
PASS pool exhausts at 18, hence 294 not 300). Ground truth never leaks into
the trace: PASS/FAIL lives only in `labels.json` (trace_id → {hallucinated,
source, case_id}). Rows over the passage cap are skipped, not truncated —
cutting evidence would invalidate the label. Raw rows cache page-by-page in
`raw_rows.jsonl` so a rate-limited pull resumes and a re-slice never
re-fetches.

Conversion verified before any evaluation: all 294 import cleanly through the
stage-1 importer (one trace/file, RETRIEVER span carries the passage as
`retrieved_contexts`, chat span's rendered input shows passage-as-context +
question, output shows the answer); labels sidecar 1:1 with files. The one
adapter quirk found and accounted for: `trace_to_sample` prefixes responses
with `"assistant: "`, which the strict round-trip check has to strip; the
remaining handful of diffs were expected PII-redaction placeholders on
number-like tokens, confirming the traces take the real ingestion path.

## Harness

New `metrics-agreement` subcommand (`cli/analyze.py`), the family-3 sibling of
`agreement`:

- runs the requested metrics (default `hallucination,faithfulness`) over a
  converted slice and folds agreement vs the labels sidecar;
- **critic fold** (`CriticAgreement`): confusion matrix (human × critic
  flag), decided/strict agreement, precision/recall/balanced accuracy,
  abstention rate;
- **score fold** (`ScoreAgreement`): mean score per class, AUC vs the binary
  label, best-threshold accuracy;
- cost fold across all metric LLM calls.

Cache discipline matches `agreement` but at **per-metric granularity**: each
trace's results cache as a `MetricsReport` stamped with per-metric versions +
model, atomic temp-file+rename write, resumable. A prompt rev on one metric
invalidates only that metric's entries — iterating hallucination never
re-pays faithfulness (the V2/V3 reruns reused the faithfulness cache, ~half
the calls). `metric_agreement_report` and its folds are unit-tested
(`test_validation.py`); the error-mining scratch tool and the scratch
findings report are in `sandbox/metric-eval/`.

## Reliability / concurrency change (no semantic change)

`run_metric_set` (`analysis/registry.py`): runs all enabled, applicable
metrics for a trace concurrently via `asyncio.gather`, filtering
inapplicable ones first and settling all before the first error re-raises
(same convention as the judge's vote/branch gathering — typed
permanent/transient classification survives, no sibling calls leak). Wired
into both the worker (`worker/tasks/analyze.py`) and the offline runner's
`run --analyzer all`, replacing the sequential per-metric loop. Independent
metrics no longer serialize; on the default two-metric set that roughly halves
per-trace metric wall time. Unit-tested for concurrency, applicability
filtering, and error propagation (`test_metrics.py`). Full unit suite green
for the touched scope (`app/analysis`, `app/cli`, `app/worker`).

## Baseline + prompt iteration (gpt-5-mini, critic_votes=1, 294 traces)

| run | prompt | decided / balanced acc | precision | recall | false-neg | false-pos |
|---|---|---|---|---|---|---|
| `out/halubench-m1` | V1 | 88.4% | 87.7% | 90.1% | 15 | 19 |
| `out/halubench-m2` | V2 | 88.4% | 89.3% | 88.1% | 18 | 16 |
| `out/halubench-m3` | V3 | **88.8%** | **90.4%** | 87.4% | 19 | 14 |

Faithfulness (RAGAS, V1, unchanged across runs): mean 0.71 faithful / 0.32
hallucinated, **AUC 0.77**, best threshold 0.768 → 71% accuracy. A usable
ranking signal but not a clean separator on this corpus; left as-is (the
prompt-iteration budget went to the boolean critic, where the error analysis
was actionable).

### Error analysis driving the prompt revs (all disagreements read)

- **V1 → V2.** V1's dominant error was over-strictness: it flagged answers
  that drew a reasonable conclusion or synthesis from the evidence as
  hallucinations (the pubmedQA/FinanceBench false-positive cluster — 19 FPs,
  many human-faithful answers). V2 drew the line explicitly:
  fabrication/contradiction is a hallucination, interpretation/inference that
  follows from the evidence is not. Effect: precision 87.7%→89.3%, FPs 19→16
  — but the "inference is fine" license was too broad and recall slipped
  90.1%→88.1% (V2 began excusing a fabricated specific buried in an
  otherwise-grounded summary). Net wash on balanced accuracy.
- **V2 → V3.** V3 keeps V2's conclusion-tolerance but restores per-claim
  discipline: a qualitative conclusion may be inferred, but every concrete
  specific (number, range, name, date, entity, quantity) must still check out,
  and one invented specific flags regardless of how grounded the rest is.
  Effect: precision 89.3%→90.4% (FPs 16→14), recall holds at 87.4%, balanced
  accuracy 88.4%→88.8% — the marginal best. Pinned: `METRIC_VERSIONS
  hallucination = "3"`, `_CRITIC_PROMPTS hallucination = hallucination.V3`.
  V1/V2 retained in the module with rationale (never-edit-in-place).

### The honest read: ~88–89% is the plateau, and the ceiling is label semantics

The residual disagreement is dominated by HaluBench labeling that conflicts
with our **deliberate** critic definition ("judge grounding only — not whether
the answer is complete or correct for the question"):

- **halueval non-answers (8 of V3's 19 false-negatives).** halueval labels a
  grounded-but-evasive answer as hallucinated: Q "Are both Robin McKinley and
  Anita Diamant American authors?" → A "Robin McKinley is an author." The
  answer invents nothing — every claim is in the passage — so the critic
  correctly returns not-hallucinated; halueval marks it FAIL for not answering
  the question. By our spec ("a grounded answer that fails to fully answer the
  question is not a hallucination") the critic is right and the label
  encodes a different task (answer correctness, not grounding). We are not
  going to chase these without contradicting the spec.
- **RAGTruth subtle additions.** A few genuine misses where the answer adds a
  plausible inference the passage doesn't support (the kind V3 is meant to
  catch) survive at votes=1; sampling noise at N=1 is ±a few traces, so
  single-trace deltas between revs are not signal.
- **False-positives are mostly correct catches.** Several V3 "false-positives"
  (e.g. the PalPal Q2 year-assignment with no year labels in the passage, the
  nicotine "cofactor to stimulate lytic replication" claim absent from the
  abstract) are defensible hallucination flags where the human label is
  arguably the wrong one — confirmed by reading the critic's cited reason
  against the passage.

So the prompt iteration moved the error *balance* the intended direction
(over-strict → calibrated, precision 87.7→90.4) and bought a marginal
accuracy gain, but the headline number is capped by the corpus, not the
prompt. Same shape as the B4 judge plateau: roughly half the residual is the
benchmark encoding information or a task definition the grounding critic
deliberately does not use.

## Outcome

- HaluBench converter + `metrics-agreement` harness land; one command
  produces the metric agreement report from a converted slice, version-stamped
  and resumable at per-metric granularity.
- Metric execution parallelized in the worker and offline runner via
  `run_metric_set`; no semantic change, full unit suite green for scope.
- Pinned hallucination V3 (`METRIC_VERSIONS = "3"`); the precision-recall
  trade is recorded with the prompt versions retained.
- Headline for the demo: **88.8% balanced accuracy (90.4% precision) against
  human hallucination labels on 294 HaluBench RAG-QA traces across six
  sources**, with the honest caveat that the ceiling is label semantics — the
  critic judges grounding, several "errors" are non-answers or
  answer-correctness disagreements the spec intentionally excludes.
