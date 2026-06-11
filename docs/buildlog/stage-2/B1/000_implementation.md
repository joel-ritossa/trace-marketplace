# B1 — Deterministic Signals

Spec: `docs/spec/stage-2/6_build-order.md` (B1), `1_analysis.md` (Family 1:
catalog, loop detection, `failure_suspected`, hit-rate-gated promotion),
`2_data-model.md` (`trace_analysis` signal columns).

**Done when:** golden tests pass; hit-rate report exists; the runner emits
signals for every dev-dataset trace.

Decisions proposed in this plan, to ratify before implementation:

1. **Action extraction falls back to message-embedded tool calls.** The spec
   says loop detection runs "per tool span", but the entire real dev dataset
   (Claude Code/Exgentic traces) has zero tool-kind spans — tool calls are
   `tool_call` parts inside LLM spans' `gen_ai.output.messages` (`id`, `name`,
   `arguments`), results are `tool_call_response` parts (paired by `id`) in
   subsequent input messages. Proposal: the action stream is tool spans when
   the trace has any, else tool_call parts extracted from LLM messages — same
   signature/result-hash pipeline either way. Needs a one-line amendment to
   `1_analysis.md` loop detection.
2. **`tool_call_count` counts actions, not just tool spans.** The catalog says
   "per-kind span counts", which makes `tool_call_count` 0 on every Claude
   Code trace — useless as a filter field and guaranteed to fail the hit-rate
   gate for the wrong reason. Proposal: `llm_call_count` = llm-kind span
   count (as specced); `tool_call_count` = count of actions per decision 1
   (tool spans, or message-embedded calls when there are none). Field
   names/types unchanged (the frozen part); the definition change is a spec
   amendment recorded here.
3. **Arg normalization** (a finalized-at-build parameter per `1_analysis.md`):
   parse `arguments` as JSON when possible → compact-dump with sorted keys;
   non-JSON strings → whitespace-stripped. Signature =
   `(tool_name, sha256(normalized_args))`; result hash = sha256 of the
   compacted result. No volatile-key stripping in v1 — no evidence yet of
   which keys are volatile, and dropping keys silently weakens exact-repeat.
4. **Per-field null semantics** (fail open, null = no opinion):
   - `llm_call_count` / `tool_call_count`: always non-null — counts over
     normalized rows are always defined; 0 is an answer, not an abstention.
   - `has_retry_loop` / `loop_kind`: null when the trace yields no actions at
     all (nothing to detect over); otherwise bool, with `loop_kind` null
     unless `has_retry_loop` is true.
   - `truncation_suspected`: null when the final LLM span exposes no finish
     evidence; true on finish reason `length`/`max_tokens` (case-insensitive;
     keys: `gen_ai.response.finish_reasons` array, flattened
     `gen_ai.completion.N.finish_reason`) or `output_tokens ≥
     gen_ai.request.max_tokens`; false when finish evidence exists and is
     benign.
   - `recovered_from_error`: null when the trace has no error spans (nothing
     to recover from); true when an error span is followed by a later
     successful span with the same identity (same signature for actions, same
     name otherwise) and the trace ends normally (final span not an error);
     false otherwise.
5. **`failure_suspected`** = trace ends in unrecovered error (trace `status`
   = `error` and `recovered_from_error` is not true) OR `has_retry_loop` OR
   `truncation_suspected`. False otherwise (no opinion, per spec).
6. **One loop threshold env var.** `ANALYSIS_LOOP_N` (default 3) drives
   exact-repeat and stagnation; cycle parameters stay spec-fixed constants
   (period ≤ 4, ≥ 2 repetitions). One knob matching the spec's "N = 3
   default" rather than three speculative ones.
7. **Hit-rate report is a runner subcommand.** `python -m app.cli.analyze
   signals-report <paths…>`: runs the signals analyzer over every trace,
   prints per-field non-null and truthy rates. `devdata/` is git-ignored, so
   the report output is recorded in this buildlog's Outcome and the promotion
   list locked there (with `2_data-model.md` amended if any field drops).

Ratified 2026-06-11, all seven as proposed (decisions 1–2 include their spec
amendments to `1_analysis.md`).

## Plan

### Module layout

```
services/api/app/analysis/
  signals.py       # NEW: action extraction glue, loop detection, the analyzer
  content.py       # +tool_actions(trace) — message-part extraction lives here
  registry.py      # +"signals" registration (replaces nothing; stub stays)
  config.py        # +loop_n on AnalysisSettings
services/api/app/cli/analyze.py   # +signals-report subcommand
```

`SignalsResult` (frozen in B0's `models.py`) is the output — no contract
change. The stub registration stays (A2 may still want it); "signals" is a
second registry entry with `version="1"`.

### Action extraction (`content.py` + `signals.py`)

An action = `(tool_name, normalized_args, result_text | None)`:

- Tool spans: name from `tool_name`, args/result via the existing
  `input_text`/`output_text` tool key chains.
- Message-embedded (used only when the trace has no tool spans): walk LLM
  spans chronologically; `tool_call` parts in `gen_ai.output.messages` (and
  flattened `gen_ai.completion.N.*` tool_calls if present) yield name + args;
  `tool_call_response` parts anywhere later pair back by `id` for the result
  hash. Unpaired calls get no result hash (stagnation just can't see them —
  fail open).

The part-parsing helpers already live in `content.py`; the new
`tool_actions` extractor joins them. `signals.py` consumes the action list
and never touches raw attributes itself.

### Loop detection (`signals.py`)

Over the chronological action list, signature = decision-3 hash:

1. **Exact repeat** — same signature ≥ N consecutive.
2. **Cycle** — some n-gram of signatures with period 2–4 repeating ≥ 2
   consecutive times (period-1 is exact repeat's job).
3. **Stagnation** — same `(tool_name, result_hash)` ≥ N times (not
   necessarily consecutive args; same tool, identical result).

First match in that order sets `loop_kind` (exact_repeat > cycle >
stagnation when multiple fire — most specific first; deterministic).
N = `settings.loop_n`, default 3.

### The analyzer

`run_signals(trace, settings) -> SignalsResult` — pure, no I/O:
counts → loop detection → `recovered_from_error` → `truncation_suspected` →
`failure_suspected`, each per the decisions above. Registered as
`AnalyzerSpec(name="signals", version="1", result_model=SignalsResult)`;
`confidence`/`model_id` stay None (deterministic analyzer,
`analyzer_results.confidence` is null per `2_data-model.md`).

### Config + env

`AnalysisSettings.loop_n: int = 3`; `.env.example` Analysis section gains
`ANALYSIS_LOOP_N=3`.

### Hit-rate report (`app/cli/analyze.py`)

`signals-report` subcommand (same input args as `run`/`render`): runs the
signals analyzer per trace, prints a fixed-order table — per field: non-null
count/rate and truthy count/rate (counts only, never trace content). The
promotion call: fields whose non-null rate is ~0 on the dev dataset are
candidates to drop from `trace_analysis`; the locked list is recorded in
this file's Outcome. The dev dataset is 5 files (3 real Exgentic sessions +
2 synthetic stress traces) — small, so the report informs rather than
dictates; the lock is a judgment call made on the recorded numbers.

### Tests (offline, no compose)

- **Golden tests** (the done-when bar): signals output for the four committed
  fixtures pinned as `tests/unit/golden/<name>.signals.expected.json`;
  `regenerate.py` extended. Fixtures exercise counts, error paths, and
  fail-open nulls; loop behavior is synthetic-only (fixtures have no loops).
- **Loop detection** (synthetic traces via `analysis_factories`): exact
  repeat at/below/above N; cycle period 2 and 4, with the ≥ 2-repetition
  bound; stagnation with varying args but identical results; signature
  invariance to JSON key order; no actions → null `has_retry_loop`.
- **Message-embedded actions**: a synthetic LLM-span trace shaped like the
  Claude Code data (tool_call/tool_call_response parts) detects the same
  loops; `tool_call_count` counts the embedded calls.
- **`recovered_from_error`**: error→retry-success→normal-end true;
  error→no-retry false; error at trace end false; no errors null.
- **`truncation_suspected`**: finish_reasons `length`/`max_tokens` true;
  `stop`/`tool_calls` false; max-token fallback true; no evidence null.
- **`failure_suspected`**: each trigger independently; recovered error +
  no loop + no truncation → false.
- **Determinism**: same trace → identical serialized result, twice.

### Verification (done-when walkthrough)

1. Unit suite green (goldens included); ruff clean on slice files.
2. `uv run python -m app.cli.analyze run --analyzer signals devdata/*.json`
   → one envelope per trace (5 files, 7 traces incl. fan-out), twice →
   byte-identical.
3. `uv run python -m app.cli.analyze signals-report devdata/*.json` → the
   report; numbers recorded in Outcome; promotion list locked.
4. Spec amendments from ratified decisions 1–2 applied to `1_analysis.md`
   (and `2_data-model.md` only if the lock drops a field).

## Drift

1. **`signals-report` takes no `--out`.** The report is a printed table, not
   per-trace JSON files; offering the flag would imply file output that
   doesn't exist. `run --analyzer signals --out` covers the JSON-dump need.
2. **Test factories gained a `name` parameter** (`make_span`) — retry-identity
   tests need same-name spans; additive, no existing test touched.
3. **Promotion lock kept `truncation_suspected`** despite a 0% dev-dataset
   hit rate (see Outcome) — the plan flagged ~0% fields as drop candidates,
   but the zero is artifactual, so the judgment call went the other way.
   Ratified by the user 2026-06-11.

## Outcome

Done-when met (2026-06-11):

1. **Golden tests pass:** signals goldens pinned for all four committed
   fixtures (`<name>.signals.expected.json`, `regenerate.py` extended);
   91 unit tests green (35 new: loop strategies, action extraction incl.
   the message-embedded path, recovery, truncation, `failure_suspected`,
   determinism, goldens). Importer/renderer goldens byte-identical. Ruff
   check + format clean on slice files.
2. **Runner emits signals for every dev-dataset trace:**
   `run --analyzer signals devdata/*.json` → 5/5 envelopes, run twice →
   byte-identical. The three real Claude Code traces produce real values
   via the message-embedded action path (27/17/20 tool calls each).
3. **Hit-rate report exists:** `signals-report devdata/*.json` →

   | field | non-null | truthy |
   |---|---|---|
   | `has_retry_loop` | 5/5 | 3/5 |
   | `loop_kind` | 3/5 | 3/5 |
   | `recovered_from_error` | 5/5 | 2/5 |
   | `truncation_suspected` | 0/5 | 0/5 |
   | `llm_call_count` | 5/5 | 5/5 |
   | `tool_call_count` | 5/5 | 5/5 |
   | `failure_suspected` | 5/5 | 3/5 |

**Promotion list locked (user-ratified):** all six catalog fields —
`has_retry_loop`, `loop_kind`, `recovered_from_error`,
`truncation_suspected`, `llm_call_count`, `tool_call_count` — keep their
`trace_analysis` columns; `failure_suspected` stays unpromoted per spec.
`truncation_suspected`'s 0% is artifactual, not a verdict on the signal:
all three real traces end in an errored LLM span carrying no response
attributes (the 27 healthy spans before it all have finish reasons), and
the two synthetic stress traces have none anywhere. The mechanism works
where evidence exists; re-measure on real ingested data post-A2.

**Recorded caveat — stagnation false positive on ack-style tools:**
`TodoWrite` returns an identical acknowledgment for every distinct write,
so 8 normal todo updates trip stagnation on one dev trace (the other
stagnation hits — `approve_payment_request` ×5, `search_notes` ×9
identical results — look like genuine stuck loops). Kept spec-true: any
static filter is guesswork, and the cost of the false positive is at most
a review item, which HIL routing absorbs. Learning per-tool suppression
from accumulated human resolutions is filed in
`docs/follow-up/judging-post-v1-candidates.md`.
