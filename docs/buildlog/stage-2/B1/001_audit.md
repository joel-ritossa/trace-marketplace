# B1 Audit — Deterministic Signals

Post-implementation review per `.cursor/skills/code-audit/SKILL.md`
(2026-06-11). Scope: `signals.py`, `content.py` (tool-action extraction),
`registry.py`, `config.py`, `cli/analyze.py`, `models.py`/`trace_input.py`
(read for contract), `sample.py` (cross-check), both signals test files,
`analysis_factories.py`, `golden/regenerate.py`, `.env.example`, and the
B1 spec amendments in `1_analysis.md`.

## Findings

### Correctness

- **C1 (bug, low)** — `_embedded_tool_actions`: a `tool_call_response` part
  with an `id` but no `response`/`result` key produced the string `"null"`
  as the result (via `_compact(None)`) instead of no result. N vacuous
  responses from one tool then satisfied stagnation's identical-result-hash
  test — a loop verdict manufactured from absent data, against fail-open.
- **C2 (nit)** — a span carrying tool calls in both `gen_ai.output.messages`
  and flattened `gen_ai.completion.N.tool_calls.*` double-counted every
  call (both branches ran unconditionally). No known emitter does both.
- **C3 (nit)** — `_truncation_suspected`'s max-tokens fallback accepted
  `max_tokens=True` (bool is an int subclass) as a token limit.
- **C4 (nit)** — `_finish_reasons`' flattened scan broke at the first index
  lacking a `finish_reason`, hiding a reason on `gen_ai.completion.1` when
  `completion.0` had none.

### Spec conformance — clean

Catalog definitions, loop strategies and most-specific-first order,
`failure_suspected` formula and non-promotion, fail-open null semantics
(ratified decision 4), and the single `ANALYSIS_LOOP_N` knob (ratified
decision 6) all match the amended `1_analysis.md`.

### Modularity

- **M1** — `signals.py` imported the private `_MAX_INDEXED_ATTRS` from
  `content.py` (cross-module private import).
- **M2** — two sources of truth for "the trace's tool calls": B1's
  `content.tool_actions` vs `sample.trace_to_sample`'s own inline tool-span
  loop (B0). The sample adapter also never saw message-embedded calls, so
  family 3's `tool_calls` was empty on every Claude Code-shaped trace —
  the entire real dev dataset.

### Future-proofing / security & privacy / reliability — clean

One env-documented tunable; spec-fixed constants commented as such. No
trace content in any signals output or in the report (counts only); nothing
logged. Pure, deterministic, fail-open throughout.

### Consistency

- **N1 (nit)** — `assert isinstance(output, SignalsResult)` in
  `_cmd_signals_report` strips under `python -O`.

## Fixes (all findings approved and implemented)

- **C1** — record a result only when the payload key is present; absent
  payload → no result hash (stagnation can't see it), matching the
  unpaired-call path.
- **C2** — the flattened-completion scan runs only when the span yielded no
  structured `tool_call` parts: alternative encoding, never additional calls.
- **C3** — bool explicitly excluded from the max-tokens check.
- **C4** — the flattened scan now walks completions by index-existence
  (`gen_ai.completion.N.*` prefix) and collects reasons wherever they appear.
- **M1** — `_MAX_INDEXED_ATTRS` → public `MAX_INDEXED_ATTRS`; `_compact` →
  public `compact_text` (needed by M2).
- **M2** — `trace_to_sample` now consumes `content.tool_actions`: one
  extraction path, and family 3 sees message-embedded calls. Behavior
  change to the B3 input shape, deliberate — tool-span traces are
  unaffected (same name/args/result extraction either way).
- **N1** — `_cmd_signals_report` calls `run_signals` directly (it needs the
  typed result, not the persistence envelope); assert gone.

`SIGNALS_VERSION` stays `"1"`: C1–C4 change outputs for some synthetic
inputs, but no fixture golden changed and no `analyzer_results` row exists
anywhere yet (A2 unlanded) — version 1 has never been persisted, so the
fixes fold into it.

## Re-verification

- 96 unit tests green (5 new: payloadless responses → no result/no
  stagnation, dual-encoding dedup, bool max_tokens, later-completion finish
  reason, embedded calls reaching the sample).
- `ruff check` + `ruff format --check` clean.
- Goldens byte-stable: golden tests passed against pre-fix files;
  `regenerate.py` reproduces them.
- `signals-report devdata/*.json` reproduces the 000 Outcome table exactly
  (5 traces; same non-null/truthy rates per field). Promotion lock
  unchanged.
