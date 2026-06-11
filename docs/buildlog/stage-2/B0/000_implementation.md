# B0 — Analyzer Contract, Trace Renderer, Offline Runner

Spec: `docs/spec/stage-2/6_build-order.md` (B0), `1_analysis.md` (analyzer
contract, rendering, routing reasons), `2_data-model.md` (`analyzer_results`,
`trace_analysis` columns).

**Done when:** any dev-dataset trace renders deterministically within budget;
the runner round-trips a stub analyzer; the contract is frozen.

Decisions proposed in this plan, to ratify before implementation:

1. **Separate `AnalysisSettings`** (`ANALYSIS_*` env prefix, its own
   pydantic-settings class) rather than extending the platform `Settings` —
   platform `Settings` hard-requires `DATABASE_URL`/`REDIS_URL`/Supabase vars,
   and the fixture-mode runner must work with zero infrastructure env. All
   defaults are local-demo values documented in `.env.example`.
2. **Token budget approximated as chars/4.** No tokenizer dependency; the env
   var is in tokens (spec language), converted to a char budget internally.
   Exact token counts buy nothing here — the budget is a cost/size guard, not
   a hard model limit.
3. **`AnalyzerRun` envelope mirrors `analyzer_results` columns** (analyzer,
   analyzer_version, model_id, confidence, output). The runner dumps
   envelopes; A2's worker persists them verbatim — one shape from analyzer to
   row.
4. **Config models ship per-slice.** B0 ships `RendererConfig` + the
   `AnalysisSettings` scaffold; signals/judge/metrics config models land with
   B1/B2/B3 (their fields would be guesses today). The *frozen* contract per
   the build order is result models + `trace_analysis` columns + routing
   reasons — config models are internal to each analyzer and additive.
5. **Default tunables** (env-overridable, finalized-at-build parameters per
   `1_analysis.md`): render budget 15,000 tokens (~60k chars), final-K steps
   8, tool input/output per-field cap 2,000 chars, conversation/LLM content
   cap 8,000 chars.

Ratified 2026-06-11 with one user note: the flat layout below is a starting
point, not a constraint — split modules into subpackages where they grow
(modularity preferred in general).

## Plan

### Module layout

New analysis package, flat and shallow; plus one CLI entrypoint:

```
services/api/app/analysis/
  __init__.py      # public surface re-exports (the contract import point)
  config.py        # AnalysisSettings + RendererConfig
  models.py        # FROZEN: result models + AnalyzerRun envelope
  routing.py       # FROZEN: RoutingReason model (routing *function* is B2)
  trace_input.py   # TraceInput/SpanInput + loaders (DB rows, fixture files)
  registry.py      # AnalyzerSpec, ANALYZERS registry, stub analyzer
  content.py       # per-convention span content extraction (shared)
  rendering.py     # render_trace(trace, config) -> RenderedTrace
  sample.py        # trace→sample adapter (RAGAS shape, consumed by B3)
services/api/app/cli/analyze.py   # offline runner
```

A-stream imports only from `app.analysis` (`__init__` re-exports); nothing in
the package touches the DB, queue, or HTTP — the only I/O lives in
`trace_input.py` loaders and the CLI.

### Contract — input model (`trace_input.py`)

Pydantic `TraceInput` + `SpanInput` mirroring the normalized `traces`/`spans`
columns (span includes `attributes`/`events` jsonb), per the contract: input
is normalized rows, never the raw storage object. Two constructors:

- `from_db_rows(trace_row, span_rows)` — asyncpg records (worker + runner DB
  mode).
- `from_import(normalized_trace)` — the stage-1 importer's `NormalizedTrace`
  (runner fixture mode runs `import_payload` first, so fixtures take the
  exact ingestion path).

One input shape; analyzers depend on neither asyncpg nor the importer.

### Contract — result models (`models.py`, frozen)

- `SignalsResult` — full `1_analysis.md` catalog, all nullable (fail open):
  `has_retry_loop`, `loop_kind`, `recovered_from_error`,
  `truncation_suspected`, `llm_call_count`, `tool_call_count`; plus
  `failure_suspected: bool` (stored, never promoted). Promotion list is
  B1's hit-rate call — that gates `trace_analysis` columns at A2, not this
  model.
- `JudgeVerdict` — `outcome` / `failure_mode` / `task_category`, per-field
  confidence, `reasoning`, `votes` (the N stored votes, the audit artifact),
  `rendering_truncated`. Taxonomy literals from `1_analysis.md`.
- `MetricResult` — `metric`, `value` (float 0–1 | bool), `reason`.
  Inapplicable = no result at all, never a row.
- `RenderedTrace` — `messages` (role/content list), `rendering_truncated`,
  `renderer_version`, step/elision counts.
- `AnalyzerRun` envelope — `analyzer`, `analyzer_version`, `model_id | None`,
  `confidence | None`, `output` (one of the above), matching
  `analyzer_results` columns 1:1.

### Contract — routing reasons (`routing.py`, frozen)

`RoutingReason` model: machine code + plain-language message (the message is
what `review_items.context` records). Codes fixed by `1_analysis.md` HIL
routing: `signals_judge_disagreement`, `outcome_indeterminate`,
`low_outcome_confidence`, `low_task_category_confidence`. The pure routing
*function* over these lands in B2.

### Registry + stub (`registry.py`)

`AnalyzerSpec`: name, version, result-model type, pure async fn
`(TraceInput, config) -> output | None` (None = inapplicable/skip).
`ANALYZERS` dict with one entry: the `stub` analyzer — deterministic counts
off the input (span/llm/tool counts), exercising the full path registry →
run → envelope → JSON. B1–B3 replace/extend registrations; A2 wires stubs
behind this same interface until then.

### Renderer (`rendering.py` + `content.py`)

Pure function of (trace, renderer version, config); `RENDERER_VERSION`
constant, bumped on behavior change.

- `content.py` — input/output text extraction per span with fallback chains
  across conventions (mirroring the importer's `mapping.py` approach):
  `gen_ai.*` prompt/completion attributes and `gen_ai.content.*` events →
  OpenInference `input.value`/`output.value` → Traceloop aliases → compact
  attribute summary. Fail open: no extractable content still yields the
  skeleton line.
- Steps: one chronological step per span — role mapped from kind (llm →
  assistant, tool → tool, else log line), content = extracted input/output;
  first user message extracted from the earliest LLM span's input and
  emitted as a leading user message; a deterministic system header (name,
  status, span/error counts, tools) opens the list.
- Budget mechanics, per spec order: (1) per-step content caps first —
  middle-out truncation per field at the tool cap, looser conversation cap;
  (2) tiering — must-haves are the first user message, all error spans, the
  final K steps; (3) remaining middle steps fill newest-first until the
  budget; elided ranges become explicit marker messages. The step skeleton
  is never dropped. `rendering_truncated` set whenever any cap or elision
  fired.

### Trace→sample adapter (`sample.py`)

`TraceSample` — `user_input`, `response`, `retrieved_contexts`,
`tool_calls`, extracted from `gen_ai.*` span attributes via `content.py`.
Consumed by B3 (RAGAS collections); B0 ships it with unit tests so the
renderer/adapter pair is one reviewed surface ("one adapter serves the judge
and family 3").

### Offline runner (`app/cli/analyze.py`)

Follows the `app.cli.requeue` pattern (module main, no CLI framework):

- `python -m app.cli.analyze run --analyzer <name|all> [paths… | --trace-id <uuid>] [--out DIR]`
  — fixture mode runs `import_payload` per file (multi-trace files fan out
  per trace); DB mode loads normalized rows by trace id. Dumps one
  `AnalyzerRun` envelope JSON per (trace, analyzer) to stdout or `--out`.
- `python -m app.cli.analyze render [paths… | --trace-id <uuid>] [--out DIR]`
  — dumps `RenderedTrace` JSON; the done-when's verification surface.

DB clients are imported lazily inside the DB branch so fixture mode needs no
platform env.

### Config + env (`config.py`, `.env.example`)

`AnalysisSettings(BaseSettings)`, `ANALYSIS_` prefix, all defaulted:
`render_budget_tokens=15000`, `render_final_steps=8`,
`render_tool_field_cap_chars=2000`, `render_conversation_cap_chars=8000`.
Documented in `.env.example` under a new Analysis section. Later slices add
their vars here (loop N, judge model, vote N, thresholds, metric set).

### Tests (offline, no compose)

- Renderer golden tests: the three committed fixtures → expected
  `RenderedTrace` JSON (existing `tests/unit/golden` + `regenerate.py`
  pattern).
- Determinism: render twice → identical serialized output.
- Budget: synthetic many-span trace (built in-test) with a tiny configured
  budget → output within budget, `rendering_truncated`, first user message +
  error spans + final K present, elision markers correct.
- Content extraction: per-convention fallback cases; span with no
  extractable content keeps its skeleton.
- Adapter: `gen_ai.*` fixtures → expected `TraceSample`; absent fields null.
- Round-trip: run stub via the runner's code path on a fixture → dump JSON →
  parse back into `AnalyzerRun` → equal models.
- Contract sanity: every result model serializes to JSON-safe dicts
  (jsonb-compatible — what A2 will persist).

Dev-dataset verification (`devdata/` is git-ignored real data, so manual, not
CI): render all converted Exgentic files + `large-trace.json` twice — byte
identical, within budget; the 5,000-span trace truncates correctly.

### Contract freeze

Closing this slice freezes `models.py` + `routing.py` field names/types and
the `trace_analysis` column promotion targets (already in `2_data-model.md`).
Subsequent change is additive or goes through a spec amendment recorded in
the buildlog — noted in module docstrings.

### Verification (done-when walkthrough)

1. `uv run python -m app.cli.analyze render devdata/*.json` twice →
   byte-identical output for every trace, sizes within budget;
   `large-trace.json` renders truncated, still within budget.
2. `uv run python -m app.cli.analyze run --analyzer stub fixtures/agent-session.json`
   → envelope JSON; the round-trip test parses it back losslessly.
3. With compose up and a seeded trace: `run --analyzer stub --trace-id <id>`
   works against the DB (spot check; offline done-when holds without it).
4. Unit suite green; ruff clean; contract-freeze note in place.

## Drift

1. **`_env_files` extracted to `app/env.py`.** The plan assumed analysis
   settings could reuse the platform env-file discovery, but importing
   `app.config` instantiates the platform `Settings` at module import —
   which requires DB/Redis env. The helper moved to a dependency-free
   module; `app.config` now imports it (behavior unchanged).
2. **Budget enforcement gained an exact trim pass.** The plan's
   reserve-headroom approach for elision markers undercounted when error
   spans scatter (many elided runs → many markers): the first large-trace
   render came out ~1.2k chars over budget. The renderer now assembles the
   real message list (markers included) and trims lowest-priority rendered
   steps — optional middles before pre-final-K error spans, oldest first —
   until the total fits. Final K steps and the fixed messages always stay;
   as a consequence, when even the skeleton-only must-haves exceed the
   budget, oldest error steps can be elided (marked, never silent).
3. **Attribute-summary exclusions widened** beyond content keys to fields
   already promoted to span columns (provider, model, token counts, tool
   name) — they were duplicating the step skeleton in the first smoke test.
4. **Stub result field names** are `*_span_count` (span-shape counts), not
   the signals catalog's `llm_call_count`/`tool_call_count` — the stub must
   not look like a half-real signals analyzer.

## Outcome

Done-when met (2026-06-11):

1. **Renders deterministically within budget:** all five `devdata/` files
   (three Exgentic sessions, the 5,000-span `large-trace.json`, the
   42k-span `over-cap.json`) rendered twice via the runner → byte-identical
   outputs, every trace ≤ 60,000 chars (15k-token budget), truncation and
   elision marked. Fixture renderings are pinned as golden files.
2. **Runner round-trips the stub:** `run --analyzer stub` over fixtures
   emits `AnalyzerRun` envelopes; the round-trip test parses the dump back
   and re-validates the output through the registry's result model. DB mode
   spot-checked against the live compose stack (`--trace-id` on a seeded
   trace: stub run + render both work).
3. **Contract frozen:** `app/analysis/models.py` + `routing.py` carry the
   freeze note; result models verified jsonb-safe; `__init__` re-exports
   are the import surface for the A-stream.

56 unit tests green (32 new: renderer golden/behavior, content extraction,
sample adapter, contract round-trip); importer goldens byte-identical;
ruff check + format clean on slice files. (`tests/integration/
test_discovery.py` has a pre-existing lint error from in-progress slice-3
work — not touched here.)
