# Judge Agreement — Validating the Outcome Judge Against Human Annotators

The headline claims: the LLM judge agrees with expert human annotators on
**87.9% of decided traces** for outcome (0.5% abstention; 200-trajectory
AgentRewardBench slice, gpt-5-mini), and on judge-flagged failures its
failure-mode category matches an expert-annotated category on **51%** of
traces (root cause exactly: 29%; 73-trajectory AgentRx corpus). This demo
produces both numbers on real annotated benchmark trajectories —
AgentRewardBench (1,408 expert outcome labels) and AgentRx (73 annotated
failed trajectories with failure-category annotations, the taxonomy our
`failure_mode` adopts wholesale). The full measurement history — error
taxonomy, prompt iterations, stronger-model probes — is in
`docs/buildlog/stage-2/B4/002_judge-iteration.md` (outcome) and
`003_failure-mode-iteration.md` (failure mode).

## Steps

Requires an LLM key in `.env.local` (judge model defaults to
`ANALYSIS_JUDGE_MODEL`). AgentRx additionally needs a HuggingFace read token
(`HF_TOKEN` in `.env.local`) after accepting the dataset's conditions at
<https://huggingface.co/datasets/microsoft/AgentRx>; AgentRewardBench is
open access.

```sh
# 1. Convert the benchmark slices into OTLP JSON + ground-truth sidecars
#    (git-ignored devdata/benchmarks/; ~200 ARB + 73 AgentRx files).
python3 tools/arb_to_otlp.py                 # --count/--benchmark/--seed to vary
python3 tools/agentrx_to_otlp.py             # --split tau_retail|magentic_one

# 2. One command per slice: judge every trace, fold agreement vs labels.
cd services/api
uv run python -m app.cli.analyze agreement ../../devdata/benchmarks/arb/traces/*.json \
    --labels ../../devdata/benchmarks/arb/labels.json --out ../../out/arb
uv run python -m app.cli.analyze agreement ../../devdata/benchmarks/agentrx/traces/*.json \
    --labels ../../devdata/benchmarks/agentrx/labels.json --out ../../out/agentrx
```

The command prints the report and writes `report.json`: the human × judge
outcome confusion matrix, agreement on judge-decided traces, abstention
rate, failure-mode match rates vs AgentRx (root-cause and any annotated
category), the share of judge-wrong traces that carried routing reasons,
a looping-signal sanity check against ARB's human looping annotations, and
what the run cost.

Each judged trace caches its full verdict (votes, reasoning, routing) in
`--out`; interrupt and re-run to resume — only uncached traces hit the LLM.

To see the same data in the product instead of a report: the converted
files are ordinary OTLP — sync them through the machine door
(`docs/demos/cli-sync.md`) and the platform analyzes them, labels them, and
routes the uncertain ones to `/review`.

## What was solved

The judge produces labels consumers filter and pay on — "trust me" isn't a
defensible answer to *how good are the labels?* Benchmarks with expert
annotations exist, but their trajectories are framework-native logs
(browsergym steps, tau message logs), not OTLP. The converters make them
first-class traces that flow through the same importer, renderer, and judge
as any contributed data, so the agreement number measures the *shipped*
pipeline, not a lab harness.

## Why it's interesting

- **The validation set never gets special treatment.** Converted
  trajectories take the exact ingestion path (`tools/arb_to_otlp.py` emits
  plain GenAI-semconv OTLP; the runner loads it through the real importer)
  — rendering caps, signal extraction, and prompt composition are all under
  test, not just the model.
- **Agreement is a pure fold** (`app/analysis/validation.py`): verdicts ×
  labels → typed report, exhaustively unit-tested; the LLM run and the
  arithmetic can't contaminate each other.
- **Abstention is honest, and reported.** The judge's `indeterminate` is a
  designed outcome, so the report shows agreement both ways: over decided
  traces and strict (abstention = miss).
- **The routing claim is measured, not asserted.** The report computes the
  share of judge-wrong traces that produced HIL routing reasons — the
  system's safety net for exactly these misses (`docs/demos/hil-loop.md` is
  the product side of that loop).
- **Free signals validation rides along:** ARB's human "looping" annotation
  is compared against the deterministic `has_retry_loop` signal — two
  analyzer families checked against humans in one run.
