# Family 1: Deterministic Signals

Pure functions over normalized rows — `traces`/`spans` columns plus `span.attributes`/`events` jsonb; never the raw storage object. No model calls. Runs on every trace.

## Principles

- **New fields only.** The catalog never duplicates stage-1 trace columns (`status`, `error_count`, `error_types`, `duration_ms`, `tool_names` stay on `traces` and are already filterable). One source of truth per concept.
- **Fail open.** Every signal is nullable. When attributes don't match expected schema/conventions (instrumentation varies by SDK), emit null — never a guess. Null never matches predicates (README null semantics).
- **Reproducible.** A signal is a pure function of the trace's own rows: re-running the analyzer reproduces its output. Corpus-relative signals (token/latency outliers) are **cut** for exactly this reason — their value would change as the corpus grows. Consumers can express absolute thresholds (`duration_ms > x`) themselves.
- **Hit-rate earns promotion.** A promoted field must actually fire on real traces; low-hit-rate fields get dropped, not kept as schema noise. **TODO (build time):** measure per-field hit rates on the dev dataset before locking the promotion list.

## Role

1. **Independent disagreement counterpart for the outcome judge.** Signals are **never fed into the judge prompt** — anchoring/prior leakage is a documented judge bias, and our confidence mechanism depends on the two layers being independent (see family 2). They compose only afterward, in routing.
2. **Tier-1 filterable fields.** Promoted to `trace_analysis` columns (infra §6) for rule-based search/subscriptions/bounties.

## Signal catalog (settled list; definitions finalized at build)

| Signal | Type | Definition sketch |
|---|---|---|
| `has_retry_loop` | bool | Loop detection below |
| `loop_kind` | enum, nullable | `exact_repeat \| cycle \| stagnation` — falls out of detection for free |
| `recovered_from_error` | bool | Error span followed by successful retry then normal completion |
| `truncation_suspected` | bool | Final LLM span finish_reason `length` / output cut at max tokens |
| `llm_call_count` / `tool_call_count` | int | Per-kind span counts |

Dropped from earlier drafts: `has_errors`, `error_span_count`, `exception_events` (duplicate stage-1 `status`/`error_count`/`error_types`), `distinct_tool_count` (redundant with `tool_names`), `token_outlier`/`latency_outlier` (corpus-relative, see principles), `final_span_shape` (most instrumentation-dependent field in the catalog — likely low hit rate; its useful part, error-shaped endings, feeds `failure_suspected` internally; revisit post-v1 against real hit rates).

**Stage-1 delta:** trace-level `total_tokens` does not exist (tokens are per-span). It is ingestion-derived (like `duration_ms`), so it belongs on `traces` via a small importer addition + migration — not in this family. Deliberate, minimal stage-1 contact.

## Loop detection (standard strategies)

Industry-standard signature-based detection (converged across agent-loop-guard, Hermes-agent's detector, and the unsupervised cycle-detection literature). Per tool span compute an **action signature** `(tool_name, hash(normalized_args))` and a result hash, then run three deterministic strategies over the sequence:

1. **Exact repeat** — same signature ≥ N consecutive times.
2. **Cycle** — repeating n-gram of signatures (A→B→C→A→B→C), period ≤ 4, ≥ 2 repetitions. Catches ping-pong loops.
3. **Stagnation** — same tool returning an identical result hash ≥ N times (no progress even if args drift).

Thresholds env-var tunable, N = 3 default. The literature's fourth layer — semantic output similarity for "hidden" cycles — requires embeddings (non-deterministic); excluded from base, consistent with the rule-based principle.

## Heuristic verdict: `failure_suspected`

A single boolean, true on strong negatives (unrecovered error ending, loop detected, truncation), false otherwise. Internal only — **stored on the signals results row** (disagreement routing must be auditable: "why was this sent to review?") but never promoted, never user-facing, never in the judge prompt.

The asymmetry is structural: structure can prove failure but cannot prove success (a structurally immaculate trace can still be flat wrong — structure can't see content). So the heuristic only ever speaks up about failure; `false` means "no opinion", not "success". Disagreement = `failure_suspected AND llm_outcome == success`. There is no `likely_success` to define and no "fully clean trace" problem.

## Output

- One typed signals object (Pydantic model) per trace → one row in the analyzer results table (`analyzer = "signals"`, versioned), `failure_suspected` included.
- Promoted to `trace_analysis`: `has_retry_loop`, `loop_kind`, `recovered_from_error`, `truncation_suspected`, `llm_call_count`, `tool_call_count`.

## Libraries (resolved: build, don't adopt)

No mature library exists for offline deterministic signal extraction over OTel agent traces. The space is young — `agent-loop-guard` (sliding-window loop detection), `llm-failure-atlas` (17 deterministic failure patterns / 34 signals), `TraceGuard` (retry storms, silent failures), `Agent-Xray` (22-category classifier, experimental OTel adapter) — all small, early-stage, single-maintainer, and built as *runtime guards* rather than offline analyzers. Adapting one to our span model costs more than the small pure-function module this family is. We implement the standard strategies ourselves and crib their detection patterns and failure vocabularies. (Contrast family 3, where RAGAS-class libraries are mature.)

## Open questions

- Arg normalization for action signatures: key sorting, stripping volatile fields (timestamps, request ids) — build-time detail.
- Post-v1 signal candidates (`final_span_shape`, silent-failure continuation, `context_pressure`, etc.) are tracked in [`follow-up/judging-post-v1-candidates.md`](../../../../follow-up/judging-post-v1-candidates.md), each gated on the hit-rate principle.
