# B2 — Outcome Judge

Spec: `docs/spec/stage-2/6_build-order.md` (B2), `1_analysis.md` (Family 2:
composed calls, self-consistency voting, confidence formula, HIL routing,
runtime/config/degradation, privacy), `2_data-model.md` (`analyzer_results`,
`trace_analysis` label columns).

**Done when:** the runner judges fixtures end to end (votes + reasoning
recorded); disagreement/indeterminate/low-confidence fixtures produce the
right routing reasons; a keyless run skips cleanly.

Decisions proposed in this plan, to ratify before implementation:

1. **Provider-conventional env keys, with the repo's env files made to
   reach them.** Keys stay litellm-standard (`OPENAI_API_KEY`,
   `ANTHROPIC_API_KEY`, …) so switching providers is just changing
   `ANALYSIS_JUDGE_MODEL` (default `openai/gpt-5-mini` — cheap, and what
   the sandbox experiments already use), never re-plumbing a key var. The
   gap today: pydantic-settings reads `.env`/`.env.local` only for declared
   fields, so a provider key in those files never reaches `os.environ`
   where litellm looks. Fix at the source: the LLM client bootstraps
   `os.environ` from the same `env_files()` discovery via python-dotenv
   (already a pydantic-settings dependency — no new dep), `override=False`
   in `.env.local`-then-`.env` order — identical precedence to settings
   loading (real env > `.env.local` > `.env`). "Configured" is decided by
   `litellm.validate_environment(judge_model)` (litellm owns the
   provider→key map; empty values count as unset), exposed as
   `llm_configured(settings)` on the package surface — the same predicate
   A2's worker will use for `llm_skip_reason = 'not_configured'`. A keyless
   judge run returns `None` (the registry's inapplicable path), so the
   runner skips cleanly with no fake output.
2. **The client seam is one module, monkeypatchable.** `llm.py` is the only
   place provider calls happen (litellm `acompletion`; provider SDKs never
   imported). One function: structured output requested via litellm's
   `response_format` json-schema mode from a per-call Pydantic vote schema;
   returns parsed model + call metadata (latency ms, input/output tokens,
   cost from litellm's price map; cost null when the model is missing from
   the map). Error classification per the spec: structurally permanent
   litellm exceptions (authentication, bad request, context window) raise
   `PermanentAnalysisError` (new, mirroring `PermanentIngestError`);
   everything else propagates as transient — no blanket retries inside the
   analyzer, the worker's job-level machinery (A2) owns retry. One
   in-module exception: a response that fails schema validation gets a
   single parse-retry (malformed JSON is model noise, not infra), then
   degrades per decision 4. Tests monkeypatch `llm.complete` with scripted
   fakes; no network in the unit suite.
3. **Additive contract change: per-call metadata rides `JudgeVote`.**
   `latency_ms`, `input_tokens`, `output_tokens`, `cost_usd` (all nullable)
   added to `JudgeVote` — each vote is exactly one LLM call, so the audit
   artifact carries what each verdict cost (AGENTS: cost/latency in result
   metadata). Additive to the frozen contract, recorded here per the B0
   freeze rule. All three vote schemas also include a self-reported
   `confidence` float (decision 4) — stored on the vote, not the prompt's
   trace content.
4. **Voting semantics, fully pinned** (the spec's finalized-at-build
   parameters):
   - Each composed call runs N = `ANALYSIS_JUDGE_VOTES` (default 3) times
     concurrently, temperature fixed at 0.7 in code (spec requires > 0 but
     lists no env var; one fewer speculative knob).
   - **Outcome:** modal vote value wins when its share of N exceeds
     `ANALYSIS_JUDGE_CONSENSUS` (default 0.5, strict) and is not
     `indeterminate`; otherwise outcome = `indeterminate` (split or
     abstention-majority). Confidence = share of votes matching the *final*
     label (so a 1/1/1 split → `indeterminate` at 1/3).
   - **Failure-mode:** plurality wins; a tie or no valid votes →
     `inconclusive` (the taxonomy's built-in abstention).
   - **Category:** plurality wins; ties break to the lexicographically
     smallest tied value — arbitrary but deterministic, and a tie's vote
     share is low enough that the confidence knob routes it anyway.
   - **N=1 degrades to self-report** for all three confidences (uniform
     application of the spec's outcome rule — vote share at N=1 is always
     1.0, which says nothing). At N>1, vote share wins and self-report is
     ignored.
   - **Malformed votes** (schema-invalid after the one parse-retry):
     recorded as value `indeterminate` for outcome (an abstention), dropped
     from the numerator for failure-mode/category; the denominator stays N
     everywhere. Fail open, never a guess.
   - `JudgeVerdict.reasoning` = the reasoning of the first vote matching
     the final outcome label, null when none does.
5. **Disagreement cap applied post-judge, in `routing.py`.** The confidence
   formula's hard cap (≤ 0.5 when `failure_suspected` is true and the judge
   says `success`) needs signals, which the clean-room rule keeps out of
   the judge. `finalize_verdict(signals, verdict) -> JudgeVerdict` lives
   beside the routing function — one home for signals×verdict composition;
   the clean room governs prompts, not post-hoc arithmetic. The envelope
   (`analyzer_results.confidence`) carries the *capped* outcome confidence;
   the uncapped share is recoverable from the stored votes. A2's worker and
   the runner both call finalize-then-route.
6. **Failure-mode evidence comes from an internal signals run.** The
   failure-mode prompt may include deterministic evidence (spec: anchoring
   matters for the verdict, not for diagnosing a declared failure). The
   judge calls `run_signals` itself (pure, cheap) and injects `loop_kind`
   plus error-span skeleton lines (name, status, error_type — never bodies)
   into the failure-mode prompt only. The outcome prompt stays clean-room:
   no signals field ever appears in it (tested).
7. **Routing function + one threshold knob.** `route(signals, verdict) ->
   list[RoutingReason]` in `routing.py`, the four spec triggers in order:
   disagreement (`failure_suspected` + judge `success`), outcome
   `indeterminate`, outcome confidence < threshold, category confidence <
   threshold. `ANALYSIS_CONFIDENCE_THRESHOLD` (default 0.7) is the one knob
   for both confidence triggers (spec: "same default knob"). Plain-language
   messages are written here and frozen with the reason model — they are
   what `review_items.context` records.
8. **Runner gains a `route` subcommand.** Runs signals + judge + finalize +
   route per trace and emits one combined JSON (signals, final verdict,
   routing reasons) — the done-when's "right routing reasons" surface,
   end to end through the real pipeline. `run --analyzer judge` keeps
   emitting the plain envelope.
9. **`task_category` set is locked at verification.** `models.py` flags the
   starting set as "finalized before B2 lock": the verification pass runs
   the category call over the dev dataset and the lock (additions are
   additive text values, no contract break) is recorded in this file's
   Outcome.

Ratified 2026-06-11. Decision 1 was revised during review (from a single
explicit `ANALYSIS_LLM_API_KEY` to provider-conventional keys + the env-file
bootstrap, as recorded above); 2–9 as proposed. Also confirmed during
review: one judge-model knob for all three composed calls (per-call models
have nowhere honest to live in `analyzer_results.model_id`; the per-vote
cost metadata is what would justify a split later), and tunables stay on
env-backed `AnalysisSettings` per the repo rule.

## Plan

### Module layout

```
services/api/app/analysis/
  llm.py           # NEW: the litellm wrapper — the only provider-call site
  judge.py         # NEW: composed calls, voting, the analyzer; JUDGE_VERSION
  prompts/         # NEW: outcome_v1.md, failure_mode_v1.md, category_v1.md
  routing.py       # +finalize_verdict, +route (RoutingReason model unchanged)
  registry.py      # +"judge" registration
  config.py        # +judge fields on AnalysisSettings
  __init__.py      # +llm_configured, finalize_verdict, route re-exports
services/api/app/cli/analyze.py   # +route subcommand
```

### LLM client (`llm.py`)

Module import runs the env bootstrap (decision 1): python-dotenv over
`env_files()` paths, `override=False`, `.env.local` before `.env` — then
litellm's conventional key lookup just works, in the runner and the worker
alike. `llm_configured(settings)` wraps `litellm.validate_environment`.

`async def complete(model, messages, schema: type[BaseModel],
temperature) -> tuple[BaseModel, CallMeta]` — litellm `acompletion` with
json-schema `response_format`, parse + validate, one parse-retry on
validation failure (then raises `MalformedResponse` for the judge to absorb
per decision 4). `CallMeta` = latency_ms / input_tokens / output_tokens /
cost_usd. Permanent litellm exception types map to
`PermanentAnalysisError`; all else propagates. **Privacy:** the module
never logs — prompts and raw outputs exist only in memory; only structured
results and counts leave the call site (1_analysis.md Privacy).

### Prompts (`prompts/`)

Versioned markdown files loaded at import, `{placeholder}`-formatted:

- `outcome_v1.md` — ternary rubric adapted from openevals'
  trajectory-accuracy rubrics; explicit `indeterminate` option; asks for
  outcome + confidence (0–1) + short reasoning. Input: the full
  `render_trace` rendering. **No signals content.**
- `failure_mode_v1.md` — the AgentRx 10-category taxonomy with one-line
  definitions, seeded from AgentRx's classification prompt; asks for
  failure_mode + confidence + reasoning. Input: rendering + deterministic
  evidence block (loop_kind, error-span skeletons).
- `category_v1.md` — Clio-style facet classification over the closed
  `TASK_CATEGORIES` set. Input: goal-focused minimal rendering — first
  user message + tool names only (no full render). When the trace has
  neither, the category call is skipped and the fields stay null (fail
  open).

`JUDGE_VERSION = "1"` covers prompts + composition + voting config;
per `2_data-model.md`, prompt/renderer/config changes bump it.

### The judge (`judge.py`)

`run_judge(trace, settings) -> JudgeVerdict | None` — pure async, no I/O
beyond `llm.complete`:

1. Keyless → `None` (registry's inapplicable path; runner and worker skip).
2. Render once (`render_trace`); `rendering_truncated` → verdict.
3. **Outcome call** × N concurrent votes (`asyncio.gather`) → vote fold per
   decision 4.
4. **Failure-mode call** × N — only when the folded outcome is `failure`.
5. **Category call** × N — always (unless inputs are absent, see prompts).
6. Assemble `JudgeVerdict` with all votes (the audit artifact), per-field
   confidences, reasoning.

Per-vote response schemas are small Pydantic models (value + confidence +
reasoning); values validate against `Outcome` / `FAILURE_MODES` /
`TASK_CATEGORIES` — an out-of-vocabulary value is a malformed vote, not a
new label. A transient provider error on any vote fails the whole run
(typed, propagates); the worker's job-level retry owns recovery — no
partial-vote salvage.

Registration: `AnalyzerSpec(name="judge", version=JUDGE_VERSION,
result_model=JudgeVerdict, run=run_judge,
confidence=verdict.outcome_confidence, model_id=settings.judge_model)`.
Envelope confidence is the capped value, so the registry entry composes
with `finalize_verdict` — the runner/worker finalize before persisting.

### Routing (`routing.py`)

- `finalize_verdict(signals, verdict)` — returns a copy with
  `outcome_confidence = min(0.5, x)` when `signals.failure_suspected` and
  `verdict.outcome == "success"`; identity otherwise.
- `route(signals, verdict) -> list[RoutingReason]` — the four triggers in
  spec order, each with its plain-language message (e.g. "Structural
  signals suggest failure but the judge concluded success."). Pure,
  deterministic, exhaustively unit-tested. Empty list = no review item.

### Config + env (`config.py`, `.env.example`)

`AnalysisSettings` gains: `judge_model: str = "openai/gpt-5-mini"`,
`judge_votes: int = 3`, `judge_consensus: float = 0.5`,
`confidence_threshold: float = 0.7`. `.env.example` Analysis section
documents the four `ANALYSIS_*` vars plus a commented-out provider key
line (`# OPENAI_API_KEY=sk-…` — match the key to the judge model's
provider; keyless is the zero-external-flow default). Real keys belong in
`.env.local` per the existing convention.

### Runner (`app/cli/analyze.py`)

`route` subcommand (same input args as `run`): per trace, run signals +
judge, finalize, route; emit one combined JSON document (signals result,
final verdict, reasons). Keyless → per-trace skip line on stderr, exit 0
(clean skip, the done-when's third leg). `run --analyzer judge` works via
the registry as-is.

### Tests (offline, no compose, no network)

Scripted fake for `llm.complete` (monkeypatched) returning canned vote
sequences and recording the prompts it saw:

- **Voting fold:** 3-0 / 2-1 majorities, 1-1-1 split → `indeterminate`,
  abstention-majority → `indeterminate`, consensus-threshold edge (share
  == threshold fails strict comparison), failure-mode tie →
  `inconclusive`, category tie → lexicographic, N=1 self-report for all
  three fields, malformed-vote degradation (outcome abstention vs
  numerator drop), out-of-vocabulary value treated as malformed.
- **Composition:** outcome `failure` triggers the failure-mode call;
  `success`/`indeterminate` skip it; category always runs; no first user
  message + no tools skips category with null fields.
- **Clean room:** the recorded outcome prompt contains no signals-derived
  content; loop/error evidence appears only in the failure-mode prompt.
- **Cap:** `failure_suspected` + judge `success` → finalized confidence ≤
  0.5; all other combinations untouched.
- **Routing:** each trigger independently, stacked triggers in spec order,
  confident agreement → empty list; threshold boundary (0.7 exactly does
  not route).
- **Keyless:** `llm_configured` false → `run_judge` returns `None`;
  registry path skips. The predicate's branches are tested with
  `litellm.validate_environment` monkeypatched — unit tests must not
  depend on (or be polluted by) a real key in the dev machine's
  `.env.local`, so the analyzer tests patch `llm_configured` directly.
- **Client:** parse-retry on first malformed response; permanent litellm
  exception types → `PermanentAnalysisError`; metadata fields populated
  from the (faked) litellm response.
- **Contract:** `JudgeVerdict` with votes + metadata round-trips through
  the `AnalyzerRun` envelope JSON-safely.

Live-key behavior (real verdicts on fixtures/devdata) is manual
verification, not CI — recorded in Outcome.

### Verification (done-when walkthrough)

1. Unit suite green; ruff check + format clean on slice files.
2. With a key in `.env.local`:
   `uv run python -m app.cli.analyze run --analyzer judge fixtures/*.json`
   → one envelope per trace with N recorded votes, reasoning, per-call
   cost/latency metadata; spot-run over `devdata/*.json`.
3. `uv run python -m app.cli.analyze route fixtures/*.json` +
   `devdata/*.json` → combined documents; confirm the disagreement /
   indeterminate / low-confidence cases produce the right reasons (unit
   tests prove the function exhaustively; the live run shows it end to
   end — results recorded in Outcome).
4. Keyless run (provider key commented out of `.env.local`, not exported
   in the shell) → both commands skip cleanly (stderr notes, exit 0, no
   envelopes).
5. `task_category` lock: category labels over devdata reviewed; final set
   recorded in Outcome (additive-only change if any).

## Drift

1. **The judge applies the cap itself.** The plan had the runner/worker
   call `finalize_verdict` before persisting; implemented with `run_judge`
   calling it as its last step instead (it already runs signals for the
   failure-mode evidence). No caller can forget the cap, and every envelope
   confidence is final by construction. `finalize_verdict` stays exported
   in `routing.py` (it is the cap's one home); callers now only `route()`.
2. **Malformed failure-mode/category votes are recorded, not dropped.** The
   spec stores all N votes as the audit artifact, and a malformed vote
   still cost money — so they record with sentinel value `invalid`
   (`judge.INVALID_VOTE`) and null reasoning/confidence; the folds exclude
   them from numerators with denominator N, exactly as ratified. Outcome
   malformed votes record as `indeterminate` per decision 4.
3. **`route()` takes the threshold as an explicit third argument**
   (`route(signals, verdict, confidence_threshold)`) rather than reading
   settings — keeps the routing function pure over its inputs; callers
   pass `settings.confidence_threshold`.
4. **`llm_configured` takes the model string, not settings** — directly
   reusable for B3's metric models without a settings reshuffle.
5. **litellm `drop_params` enabled in the client.** gpt-5-family models
   reject non-default temperature; litellm drops the param there and the
   model samples at its default temperature (> 0, so self-consistency
   still holds). Models that accept it get the fixed 0.7.

## Outcome

Done-when met (2026-06-11):

1. **Runner judges fixtures end to end:** `run --analyzer judge` and
   `route` over the four committed fixtures and the 21-trace dev dataset —
   every verdict carries the N=3 recorded votes with reasoning and
   per-call latency/tokens/cost. Whole-set totals: 168 LLM calls, $0.38,
   median 6.7s/call (gpt-5-mini). Live verdicts behave: agent-session →
   confident `success`/`web_research`; failure-trace → `failure` +
   `system_failure` (signals agree, so no routing); minimal → `success`
   with the category call correctly skipped (no goal inputs).
2. **Right routing reasons:** unit tests prove all four triggers and the
   cap exhaustively (38 judge/routing tests). Live, every reason code
   fired on real data: 8/21 dev traces routed `signals_judge_disagreement`
   + `low_outcome_confidence` with the 0.5 cap visibly applied (judge said
   `success`, structure suspected failure — mostly swebench/appworld
   sessions, the known B1 stagnation overlap); `over-cap` routed
   `outcome_indeterminate`; `low_task_category_confidence` fired on three
   tau2 traces. Confident agreements routed nothing.
3. **Keyless run skips cleanly:** with `.env.local` moved aside and
   provider vars scrubbed, `route` and `run --analyzer judge` print a
   per-trace "judge skipped (LLM not configured)" note to stderr and exit
   0 with no envelopes.

47 new unit tests (voting folds, composition, clean room, cap, routing
triggers, client parse-retry/error classification, keyless, envelope
round-trip); full unit suite green at close (169 tests — the count grew
during the slice from concurrent A-stream work). Ruff check + format clean
on slice files.

**`task_category` lock:** observed labels across the 25 judged traces —
`coding`, `content_generation`, `customer_ops`, `other`, `retrieval_qa`,
`web_research` — all within the starting set, with `other` absorbing the
genuinely ambiguous synthetics. The starting eight values are locked
unchanged; `models.py` notes the lock.

**Recorded caveat — the judge is generous on partial completions:** the
three swebench and three appworld dev traces end in errored final LLM
spans (the session cut off), yet the judge votes `success` 3-0 from the
work completed before the cut. The disagreement trigger catches exactly
this (all six routed with capped 0.5 confidence), which is the designed
behavior — but it means outcome agreement on cut-off traces leans on HIL
rather than the prompt. Worth re-measuring in B4's agreement report before
any prompt tuning.
