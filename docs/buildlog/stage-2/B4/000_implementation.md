# B4 — Validation

Spec: `docs/spec/stage-2/6_build-order.md` (B4), `1_analysis.md` (Validation:
benchmark→OTLP converter, agreement script, headline claim; failure_mode
taxonomy adopted wholesale from AgentRx).

**Done when:** one command produces the agreement report; converter output
ingests cleanly.

Dataset facts established before planning (2026-06-11):

- **AgentRewardBench** (`McGill-NLP/agent-reward-bench`, HF): open access, no
  auth. `annotations` config = 1,408 expert rows (`trajectory_success` ∈
  Successful 395 / Unsuccessful 1,012 / Unsure 1; plus side-effect, optimality,
  looping) across webarena 501 / workarena 475 / visualwebarena 300 /
  assistantbench 132, four agents. Full trajectories live as per-task JSON
  under `cleaned/<benchmark>/<agent>/<exp_name>/` — per-step `reasoning`,
  `action`, `axtree_pruned`, `url`, `last_action_error`, token/cost stats,
  plus the task `goal`. ~2 MB/file (the heavy `axtree_obj`/screenshot fields
  are dropped at conversion).
- **AgentRx** (`microsoft/AgentRx`, HF): **click-through gated** (auto-approved
  after accepting conditions; CC-BY-4.0). 115 failed trajectories in two
  splits (`tau_retail`, `magentic_one`): `*_dataset.jsonl` = trajectories,
  `tau_retail.jsonl`/`magentic_one.jsonl` = annotations (`failures[]` with
  `step_number`/`failure_category`/reasons + a designated `root_cause`).
  ~5 MB total. Downloading requires an HF token.
- **TRAIL** is gated as of 2026-06 (recorded in the candidate-datasets
  archive when the spec was shaped).

Decisions proposed in this plan, to ratify before implementation:

1. **Two converters in `tools/`, devdata pattern.** `arb_to_otlp.py` and
   `agentrx_to_otlp.py` beside the existing `exgentic_to_otlp.py`, sharing
   `_otlp.py`: stdlib-only scripts that fetch from HF and write one OTLP JSON
   file per trajectory into `devdata/benchmarks/arb/` and
   `devdata/benchmarks/agentrx/` (git-ignored — real benchmark data never
   committed, per AGENTS). Deterministic trace ids (sha256 of the trajectory
   identity) so re-runs and re-ingests are idempotent.
2. **Each converter also writes a `labels.json` sidecar** in its output
   directory: `source_trace_id → ground truth` (ARB: outcome mapped
   Successful→`success` / Unsuccessful→`failure`, plus `looping` and
   provenance benchmark/task/agent; AgentRx: root-cause `failure_category`
   plus the full annotated failure list). The agreement script joins on it;
   it lives and dies with the converted slice, never committed.
3. **ARB slice: default 60, stratified.** Trajectories grouped per
   (benchmark, agent, task); duplicate-annotator conflicts on
   `trajectory_success` are excluded, the single `Unsure` row is excluded.
   The converter samples evenly across the four benchmarks and both outcome
   labels (`--count`, `--benchmark` flags to override). Spec says "a slice";
   60 balances signal against judge cost (~9 LLM calls/trace).
4. **ARB trajectory → OTLP mapping.** One root `invoke_agent` span (goal,
   benchmark/task/agent attrs, synthesized-root marker — the exgentic
   convention); one `chat` LLM span per step: `gen_ai.input.messages` = the
   goal (step 0) and the step's observation (capped `axtree_pruned` +
   `last_action_error` as user content), `gen_ai.output.messages` = the
   step's `reasoning` + `action` as assistant text, token usage from step
   stats, model from the trajectory header. A non-empty `last_action_error`
   marks the span errored. This renders through the existing
   renderer/importer conventions (`gen_ai.operation.name: chat` → kind
   `llm`) with no analysis-package changes.
5. **AgentRx mapping verified at implementation.** The trajectory files are
   gated, so the exact span mapping (tau message logs and magentic_one event
   logs → chat/tool spans) is pinned against the real files once a token is
   in hand; same root-span + deterministic-id conventions as ARB. Deviations
   recorded as drift. **Dependency: you accept the AgentRx conditions on HF
   and put a read token in `.env.local` (`HF_TOKEN`)**; the converter sends
   it as a bearer header and fails with a clear message when absent. ARB
   needs no token.
6. **Taxonomy is checked, not mapped.** AgentRx `failure_category` values are
   normalized to snake_case and must land in our `FAILURE_MODES` exactly
   (spec: same taxonomy, no mapping layer); an out-of-vocabulary category is
   a converter error, never a silent remap.
7. **Agreement is a runner subcommand + a pure fold.**
   `python -m app.cli.analyze agreement <files…> --labels labels.json --out
   <dir>` runs signals + judge (finalized) + route per trace through the
   existing fixture path, then folds verdicts × labels via
   `agreement_report(...)` in a new `app/analysis/validation.py` (pure,
   unit-tested, returns an `AgreementReport` Pydantic model). One command,
   one report — the done-when surface.
8. **Long-run ergonomics: cache + bounded concurrency.** Per-trace verdict
   envelopes are written into `--out` and existing ones are skipped on
   re-run (175 traces × N=3 votes is an interruptible half-hour LLM job;
   resume is cheap insurance, and the cached envelopes are the audit
   artifact). `--concurrency` (default 4) bounds traces in flight; votes
   within a call already run concurrently. Keyless → stderr note, no
   report, exit 1 (unlike `run`/`route`, the command's entire point is the
   report).
9. **Report contents** (`report.json` + a readable stdout/markdown summary):
   - counts: converted / judged / skipped per dataset;
   - **outcome agreement (ARB + AgentRx):** human × judge confusion matrix,
     agreement on judge-decided traces, judge abstention (`indeterminate`)
     rate, and strict agreement counting abstentions as misses;
   - **failure_mode agreement (AgentRx):** share of true failures the judge
     called `failure`, and among those, match rate vs the root-cause
     category and vs any annotated category;
   - **routing check (the headline's second half):** share of judge-wrong
     traces that produced ≥1 routing reason, and the overall routing rate;
   - **looping cross-check (ARB):** `trajectory_looping` vs our
     `has_retry_loop` — a free deterministic-signals validation riding the
     same labels;
   - cost: total LLM calls, tokens, dollars, wall time.
10. **TRAIL is dropped from B4.** Gated since the spec was written; it was a
    span-level sanity check, not part of either done-when clause. The ARB
    looping cross-check (decision 9) covers the "sanity-check signals
    against human annotations" intent. Spec line amended in this pass
    (1_analysis.md Validation) — recorded here per the spec-first rule.
11. **Demo doc.** `docs/demos/judge-agreement.md`: how to convert, ingest,
    run the agreement command, and read the report — the headline claim is
    the demo. Indexed in `docs/demos/README.md`.

Ratified 2026-06-11, all eleven as proposed, with one revision: judge cost
is explicitly not a constraint (user), so the ARB slice default rises from
60 to 200 (50 per benchmark, outcome-stratified) — still "a slice", but a
tighter agreement number. Cost/wall-time estimates scale ~3×; the cache +
resume design (decision 8) is what makes the bigger run comfortable.

## Plan

### Module layout

```
tools/arb_to_otlp.py                      # NEW: ARB slice → devdata/benchmarks/arb/ + labels.json
tools/agentrx_to_otlp.py                  # NEW: AgentRx → devdata/benchmarks/agentrx/ + labels.json
tools/_otlp.py                            # shared builders (unchanged or minor additions)
services/api/app/analysis/validation.py   # NEW: labels model, AgreementReport, agreement_report fold
services/api/app/analysis/__init__.py     # +agreement_report, AgreementReport re-exports
services/api/app/cli/analyze.py           # +agreement subcommand
services/api/tests/unit/test_validation.py # NEW: fold + labels parsing tests
docs/spec/stage-2/1_analysis.md           # TRAIL line amended (decision 10)
docs/demos/judge-agreement.md             # NEW + README index entry
```

No contract changes; no new dependencies; no schema changes.

### Converters (`tools/`)

- **`arb_to_otlp.py`:** pull the `annotations` config via the HF
  datasets-server rows API (the exgentic precedent), dedupe/stratify per
  decision 3, fetch each selected trajectory JSON from
  `cleaned/<benchmark>/<agent>/<exp_name>/<task>.json` via `resolve/main`,
  convert per decision 4, write OTLP + accumulate `labels.json`. Flags:
  `--count` (default 200, per ratification), `--benchmark`, `--seed`
  (sampling is deterministic by default).
- **`agentrx_to_otlp.py`:** fetch the four jsonl files with `HF_TOKEN`,
  join trajectories to annotations per split, convert per decision 5,
  validate categories per decision 6, write OTLP + `labels.json`. Flag:
  `--split` (default both).
- Both: per-field char caps on observation content keep files ingestable
  (stage-1 size limits); heavy ARB fields (`axtree_obj`, screenshots,
  bounding boxes) never leave the converter.

### Validation module (`app/analysis/validation.py`)

- `TraceLabel` (outcome, failure_categories, root_cause_category, looping,
  provenance fields — optional per dataset) + `load_labels(path)`.
- `agreement_report(entries: list[(TraceLabel, SignalsResult, JudgeVerdict |
  None, list[RoutingReason])]) -> AgreementReport` — pure fold computing
  decision 9's numbers; no I/O, no LLM.
- `AgreementReport.render_text()` for the human-readable summary (mirrors
  the signals-report precedent of formatting living beside the model).

### Runner (`app/cli/analyze.py`)

`agreement` subcommand: load fixtures (existing `_load`), for each trace —
cached envelope in `--out` or run signals + judge + route (semaphore-bounded
per decision 8) — then fold and emit `report.json` + summary text. Reuses
`run_signals` / `run_judge` / `route` exactly as `route` does; traces whose
ids miss the sidecar fail loudly (a converter/labels mismatch is a bug, not
data).

### Tests (offline, no network, no LLM)

`tests/unit/test_validation.py`:

- labels sidecar round-trip; unknown outcome value rejected;
- confusion matrix + agreement/abstention arithmetic on synthetic
  verdict/label sets (incl. all-indeterminate and empty edge cases);
- failure_mode match rates (root-cause vs any-category) computed only over
  judge-`failure` traces;
- routing stats: judge-wrong traces with/without reasons;
- looping cross-check arithmetic;
- report JSON round-trip.

Converters stay manual-verified like the existing devdata converters: their
correctness check is the done-when itself (output ingests cleanly; one
trajectory per dataset eyeballed against its rendering), recorded in
Outcome.

### Verification (done-when walkthrough)

1. Unit suite green; ruff check + format clean on slice files.
2. `python3 tools/arb_to_otlp.py` → 60 files + labels;
   `python3 tools/agentrx_to_otlp.py` (HF token in `.env.local`) → 115
   files + labels.
3. **Ingests cleanly:** fresh compose up → CLI-sync `devdata/benchmarks/`
   → all uploads `completed`, spot-check trace detail renders sensibly.
4. **One command, one report:** `uv run python -m app.cli.analyze agreement
   devdata/benchmarks/arb/*.json --labels devdata/benchmarks/arb/labels.json
   --out out/arb/` (and agentrx equivalent) with a key → `report.json` +
   summary; numbers recorded in Outcome (the headline claim). Estimated
   judge cost for the full 175-trace run ≈ $5–15 at gpt-5-mini (B2 measured
   $0.38/21 small traces; these render larger).
5. Keyless agreement run → clear stderr message, exit 1, no report.
6. Resume check: interrupt a run, re-run, cached verdicts skip.
7. Demo doc steps pass as written; B2's recorded caveat (judge generosity on
   cut-off traces) re-measured against the ARB numbers and noted in Outcome.

## Drift

1. **ARB actions are embedded tool calls, not prose.** The plan had step
   outputs as assistant text; implemented as the message-embedded
   `tool_call` part shape (browsergym actions *are* tool invocations:
   `fill('147', …)` → name + args), with the next step's observation paired
   back as a `tool_call_response`. Loop detection and `tool_call_count` see
   the actions (first pass rendered them invisible to family 1 — the ARB
   looping cross-check compared zero traces), and the judge gets the same
   structure real Claude-Code-shaped traces have.
2. **Converter output layout: `traces/` subdir + `labels.json` beside it.**
   The plan put both in one directory; `*.json` globs then fed the sidecar
   to the importer. The OTLP files live in `traces/`, the sidecar outside
   the glob.
3. **Converters retry transient network errors and resume.** A 200-file CDN
   pull reliably hits an SSL hiccup; three attempts with backoff, files
   already on disk are skipped, and the labels sidecar is rewritten
   incrementally so an interrupted run loses nothing.

## Outcome

Recorded at slice close against the done-when.
