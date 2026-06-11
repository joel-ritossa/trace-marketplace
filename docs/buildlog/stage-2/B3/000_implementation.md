# B3 — Quality Metrics

Spec: `docs/spec/stage-2/6_build-order.md` (B3), `1_analysis.md` (Family 3:
buckets, applicability predicates, default-on set, storage convention;
runtime/config/degradation; privacy), `2_data-model.md` (`analyzer_results`,
`trace_analysis.metric_scores`).

**Done when:** applicable fixtures produce metric results, inapplicable
produce none; default set locked.

The downstream plumbing already exists: `MetricResult` in `models.py`, the
`trace_to_sample` adapter in `sample.py`, and the worker
(`worker/tasks/analyze.py`) runs any registered `metric:*` spec behind the
A2 LLM gate and promotes `metric_scores`. B3 is the metrics themselves:
implement, register, lock the default set.

Decisions proposed in this plan, to ratify before implementation:

1. **Default-on set locked at seven, all registered; `ANALYSIS_METRICS`
   selects what runs.** Bucket 1 critics — `hallucination`, `helpfulness`,
   `harmfulness`, `coherence`, `relevancy` (boolean flag + reason) — plus
   bucket 2 RAGAS metrics — `faithfulness`, `goal_accuracy` (0–1 floats) —
   when applicable. The env var (comma list, default = all seven) is the
   spec's "extended catalog is env-config" knob with no extra machinery:
   the registry holds every implemented metric; the setting filters which
   specs a run executes. One home for the filter
   (`enabled_metric_specs(settings)`), used by the worker's
   `_metric_specs()` and the runner alike.
2. **RAGAS v0.4 collections behind a litellm-backed LLM adapter.** The
   collections API takes an instructor-style LLM; the stock `llm_factory`
   wants a native provider client (`AsyncOpenAI`, …), which the repo rule
   forbids importing. Instead a small adapter class implements the RAGAS
   LLM interface (sync + async structured `generate(prompt,
   response_model)`) by delegating to the existing `llm.complete` —
   litellm stays the only provider-call site, and every RAGAS-internal
   call gets the same latency/tokens/cost metadata as a judge vote. The
   ragas dependency is pinned exact (`ragas==0.4.x`) per the spec;
   reference-free variants only (`Faithfulness`,
   `AgentGoalAccuracyWithoutReference`).
3. **Inputs: critics read the rendering, RAGAS reads the sample.**
   Critics consume the full `render_trace` output (the renderer is the
   one owned integration surface; same input discipline as the judge's
   outcome call). RAGAS metrics consume `trace_to_sample` fields
   (`user_input`, `response`, `retrieved_contexts`, `tool_calls`).
   Applicability predicates, per spec, evaluated over the sample:
   - critics → `response` non-null (≥1 LLM response span);
   - `faithfulness` → `response` non-null **and** `retrieved_contexts`
     non-empty;
   - `goal_accuracy` → `user_input` non-null (discernible goal).
   Inapplicable → the analyzer returns `None` → no row (the registry's
   existing path) — never a garbage score.
4. **Critic call shape mirrors the judge.** One structured-output call
   per critic: versioned prompt file + rendering → schema
   `{flag: bool, reason: str}`. Self-consistency knob
   `ANALYSIS_CRITIC_VOTES` defaults to 1 (spec: cost; critics never route
   to HIL); at N>1, majority bool wins (ties fail open to `None` — no
   row), reason taken from the first majority vote. Malformed responses
   after `llm.complete`'s one parse-retry fail open to `None`. RAGAS
   metrics run once — their decomposition is internally multi-call
   already.
5. **Additive contract change: per-call metadata rides `MetricResult`.**
   Optional `calls` list (latency_ms / input_tokens / output_tokens /
   cost_usd per LLM call, nullable fields — the `JudgeVote` meta shape
   without vote semantics) added to `MetricResult`, recording what each
   score cost (AGENTS: cost/latency in result metadata). RAGAS-internal
   calls are captured by the adapter (decision 2). Additive to the frozen
   contract, recorded here per the B0 freeze rule; worker promotion reads
   only `metric`/`value` and is untouched.
6. **Keyless → `None` per metric analyzer.** Each metric checks
   `llm_configured(model)` first and returns `None`, same as the judge —
   the offline runner skips cleanly with no fake output. The worker's
   upstream gate (`not_configured` / `owner_opt_out`) is unchanged and
   remains the authority on `llm_skip_reason`; the in-analyzer check is
   the runner's (and defense-in-depth's) path.
7. **One model knob.** Metrics use `settings.judge_model` — the spec's
   env-var list has one judge/metric model, and per-metric models have
   nowhere honest to live in `analyzer_results.model_id`. The per-call
   cost metadata (decision 5) is what would justify a split later.
8. **Versioning: per-metric, version `"1"`.** Each `metric:<name>` spec
   carries its own version; critic prompt files are
   `metric_<name>_v1.md`; prompt or predicate changes bump the owning
   metric only. The ragas pin rides the lockfile and this buildlog — a
   pin bump is a version bump for the two RAGAS-backed metrics.

Ratified 2026-06-11, all eight as proposed.

## Plan

### Module layout

```
services/api/app/analysis/
  metrics.py       # NEW: predicates, critic runner, RAGAS adapter + wrappers,
                   #      enabled_metric_specs; METRIC version constants
  prompts/         # NEW: metric_hallucination_v1.md, metric_helpfulness_v1.md,
                   #      metric_harmfulness_v1.md, metric_coherence_v1.md,
                   #      metric_relevancy_v1.md
  models.py        # +MetricCall, +MetricResult.calls (additive)
  registry.py      # +seven "metric:<name>" registrations
  config.py        # +metrics, +critic_votes on AnalysisSettings
  __init__.py      # +enabled_metric_specs re-export
services/api/app/worker/tasks/analyze.py  # _metric_specs -> enabled_metric_specs
services/api/pyproject.toml               # +ragas (pinned exact)
.env.example                              # +ANALYSIS_METRICS, +ANALYSIS_CRITIC_VOTES
```

### Critic prompts (`prompts/`)

Five versioned markdown files, `{placeholder}`-formatted like the judge's,
loaded at import. Prompt text sourced/adapted per spec — openevals and
LangChain criteria descriptions (helpfulness, coherence, relevancy),
RAGAS aspect-critic phrasing (harmfulness, hallucination) — into our own
files; no openevals/DeepEval dependency. Each asks for a boolean verdict
on its criterion plus a short reason, judging the assistant's conduct
over the full rendered trace. Sourcing recorded per file in this
buildlog's Outcome.

### The metrics module (`metrics.py`)

- `enabled_metric_specs(settings) -> list[AnalyzerSpec]` — registry
  `metric:*` entries filtered by the parsed `settings.metrics` list; the
  one home for the default-set knob (decision 1).
- **Critic factory:** one `run_<critic>` closure per prompt file built by
  a shared factory — keyless check, applicability predicate, render,
  N = `critic_votes` concurrent `llm.complete` calls with the
  `{flag, reason}` schema at the judge's fixed temperature, majority
  fold, `MetricResult(metric=<name>, value=<bool>, reason=…, calls=[…])`.
- **RAGAS adapter:** `LitellmRagasLLM` implementing the v0.4 instructor
  LLM interface over `llm.complete`; accumulates `MetricCall` metadata
  across the metric's internal calls. Constructed per run (no shared
  mutable state — analyzers stay pure functions of their inputs).
- **RAGAS wrappers:** `metric:faithfulness` → `Faithfulness(llm=adapter)
  .ascore(user_input, response, retrieved_contexts)`;
  `metric:goal_accuracy` → `AgentGoalAccuracyWithoutReference` fed from
  the sample (exact kwargs verified against the pinned version — the
  spec's "verify RAGAS against our trace shapes" item). RAGAS
  `MetricResult.value`/`.reason` map onto our `MetricResult`; scores
  clamp to [0, 1]. A RAGAS-internal failure that is structurally
  permanent surfaces as `PermanentAnalysisError` via the adapter;
  transient provider errors propagate to the worker's retry machinery,
  same classification as the judge.
- **Privacy:** like `llm.py` and `judge.py`, the module never logs —
  prompts, samples, and raw outputs exist only in memory; only the
  structured result leaves.

Registration: `AnalyzerSpec(name="metric:<name>", version=…,
result_model=MetricResult, run=…, model_id=settings.judge_model)`;
envelope `confidence` stays `None` (metric scores are not labels and
carry no confidence semantics).

### Config + env (`config.py`, `.env.example`)

`AnalysisSettings` gains `metrics: str =
"hallucination,helpfulness,harmfulness,coherence,relevancy,faithfulness,goal_accuracy"`
(parsed, order-preserving, unknown names rejected at parse) and
`critic_votes: int = 1` (≥1). `.env.example` documents both under the
Analysis section.

### Worker (`worker/tasks/analyze.py`)

`_metric_specs()` delegates to `enabled_metric_specs(settings)` — the
only worker change. Run order, gating, promotion, and skip reasons are
untouched (A2's machinery; metrics land by registration as designed).

### Tests (offline, no compose, no network)

`tests/unit/test_metrics.py`, reusing the `FakeLLM`/`patch_llm` pattern
from `test_judge.py` and `analysis_factories.make_trace`:

- **Applicability matrix:** no LLM response span → every critic returns
  `None`; LLM span but no retriever spans → `faithfulness` `None` while
  critics run; no first user message → `goal_accuracy` `None`; fully
  shaped trace → all seven produce results. No row is ever emitted for
  an inapplicable metric (registry path asserted via `run_analyzer`).
- **Critic calls:** flag + reason land in `MetricResult`; `calls`
  metadata populated; prompt seen by the fake contains the rendering;
  N=3 majority fold (2-1, 3-0), tie at N=2 → `None`, malformed response
  → `None`.
- **RAGAS wrappers:** `llm.complete` monkeypatched so the adapter drives
  the pinned RAGAS prompt classes for real — score lands as float in
  range, reason captured, adapter accumulates per-call metadata. (If the
  pinned internals prove too fiddly to script, fall back to
  monkeypatching the scorer's `ascore` and test the adapter separately —
  recorded as drift if so.)
- **Keyless:** `llm_configured` false → every metric returns `None`.
- **Filter:** `enabled_metric_specs` honors subsets and rejects unknown
  names; default settings yield all seven.
- **Contract:** `MetricResult` with `calls` round-trips the
  `AnalyzerRun` envelope JSON-safely (extend `test_analysis_contract.py`
  parametrization).

### Verification (done-when walkthrough)

1. Unit suite green; ruff check + format clean on slice files.
2. With a key in `.env.local`:
   `uv run python -m app.cli.analyze run --analyzer all fixtures/*.json`
   and over `devdata/*.json` — applicable traces produce one envelope
   per metric with score + reason + per-call cost; inapplicable produce
   the runner's skip note and no envelope (`minimal.json` must skip
   `faithfulness`; `agent-session.json`, which has retrieval content,
   must produce it).
3. RAGAS shape verification: confirm `Faithfulness` and
   `AgentGoalAccuracyWithoutReference` behave sensibly on our sample
   shapes (scores discriminate between the success/failure fixtures, no
   crashes on tool-heavy traces); findings recorded in Outcome.
4. Keyless run → all metric analyzers skip cleanly (stderr notes, exit
   0, no envelopes).
5. Default set locked: the seven names + per-metric applicability rules
   recorded in Outcome; `ANALYSIS_METRICS` default frozen.

## Drift

1. **Prompt storage convention replaced repo-wide (user decision during
   implementation).** Not `.md` files: `prompts/` is now a Python package —
   one subpackage per analyzer family, one module per prompt, all of a
   prompt's versions as `V1`, `V2`, … constants in its module
   (`prompts/judge/outcome.py`, `prompts/critics/hallucination.py`). The
   consumer pins a version at the reference (`outcome.V1`) next to its own
   version constant. B2's three judge prompts migrated in the same pass
   (one pattern repo-wide, no coexistence); `judge.py` lost its file
   loader; prompt text unchanged, so `JUDGE_VERSION` stays `"1"`. The
   spec's "versioned prompt files" reads naturally as either format;
   decision 8's `metric_<name>_v1.md` naming is superseded accordingly.
2. **Shared constants got one home each.** The flat prompt-surface form of
   a rendering moved from a judge-private helper to
   `rendering.rendering_text` (critics send the same surface), and the
   fixed sampling temperature moved to `llm.SAMPLING_TEMPERATURE` (judge
   and critics share it; RAGAS calls use a separate deterministic 0.0 —
   they have no voting to sample for).
3. **New committed fixture `retrieval-qa.json`.** No existing fixture
   carried retrieval *content* (agent-session's retriever span has only a
   document count), so faithfulness had no applicable committed fixture
   and the done-when's "applicable fixtures produce metric results" leg
   couldn't be shown offline. A three-span RAG trace (user question →
   retriever with two document contents → grounded LLM answer) makes all
   seven metrics applicable; added to the importer golden list (existing
   goldens regenerated byte-identical).
4. **langchain constraint pins ride the ragas pin.** ragas 0.4.3 declares
   unbounded langchain deps but imports modules removed in langchain 1.x;
   `tool.uv.constraint-dependencies` pins `langchain<1`,
   `langchain-community<0.4`, `langchain-core<1` so the resolver lands on
   the 0.3-era packages ragas was built against.
5. **`enabled_metric_specs` lives in `registry.py`, not `metrics.py`.**
   The plan placed it in the metrics module; it filters registry entries,
   so putting it beside `ANALYZERS` avoids a metrics→registry import
   cycle. One home for the knob either way (decision 1 holds).

## Outcome

Done-when met (2026-06-11):

1. **Applicable fixtures produce metric results, inapplicable produce
   none.** Keyed offline-runner pass over all seven committed fixtures ×
   all seven metrics (gpt-5-mini): `retrieval-qa` produced all seven
   (faithfulness 0.667 — 2 of 3 extracted statements grounded;
   goal_accuracy 1.0; critics with step-citing reasons);
   `agent-session` produced the five critics + goal_accuracy 1.0 with
   faithfulness correctly skipped (its retriever span carries only a
   document count, no content); `failure-trace`, `minimal`,
   `malformed-spans`, and both redaction fixtures produced nothing for
   every metric (no extractable LLM response) — skip notes on stderr,
   exit 0, no garbage scores anywhere. Every result row carries per-call
   latency/tokens/cost (critic ≈ $0.001/run; RAGAS pair 2 calls,
   ≈ $0.002–0.005 on fixtures).
2. **Default set locked:** `hallucination`, `helpfulness`, `harmfulness`,
   `coherence`, `relevancy` (booleans) + `faithfulness`, `goal_accuracy`
   (0–1 floats) — `METRICS` in `models.py`, the only valid
   `metric_scores` keys (the B3→A4 surface). `ANALYSIS_METRICS` defaults
   to the full catalog. Applicability rules as ratified (decision 3),
   with the two predicate extensions recorded in the code: faithfulness
   also requires the question + response the pinned scorer validates;
   goal_accuracy also requires some workflow (a response or tool calls)
   for an end state to be inferable from.
3. **RAGAS verified against our trace shapes** (the spec's sanity item):
   the litellm adapter drives the pinned collections classes end to end —
   unit tests run the real RAGAS prompt pipelines against scripted
   responses; live, goal_accuracy discriminates on real Claude Code dev
   traces (appworld session → 1.0, browsecompplus session → 0.0; 2 calls,
   ≈ 19–29s, ≈ $0.005–0.025 on 29–51-span traces) and faithfulness is
   honestly inapplicable there (Claude Code traces have no retriever
   spans) — expected, recorded, and exactly what the predicate is for.
   RAGAS's NaN no-statements path fails open to no row.
4. **Keyless run skips cleanly:** with `.env.local` moved aside and
   provider vars scrubbed, metric runs print per-trace "not applicable,
   skipped" notes and exit 0 with no envelopes.

31 new unit tests (applicability matrix, critic folds and fail-open
paths, keyless, the default-set knob, RAGAS adapter + both wrappers,
contract round-trip with `MetricCall`); full unit suite green at close
(245 tests). Ruff check + format clean.

**Critic prompt sourcing** (decision on file per `prompts/critics/`
docstring): helpfulness / harmfulness / coherence adapted from LangChain's
criteria-eval descriptions, hallucination from openevals + RAGAS
faithfulness framing, relevancy from RAGAS response-relevancy framing —
all owned text, no evaluator-framework dependency.

**Recorded caveat — critics are strict on partial completions:** on
`retrieval-qa`, helpfulness and relevancy came back `false` because the
response answers the question but is thin as the requested "plan". The
flags are defensible readings and the reasons say exactly that; worth
remembering when interpreting critic flags as filter predicates —
they grade the response against the full request, not against effort.
