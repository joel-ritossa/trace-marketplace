# Family 1: Deterministic Signals

Pure functions over normalized spans. No model calls, no nondeterminism — cheap, fast, unit-testable. Runs on every trace, always.

## Role

1. **Prior for the outcome judge.** The signals object is an input to family 2's prompt, and the heuristic verdict it implies is one side of the disagreement-based confidence signal.
2. **Tier-1 filterable fields.** Several signals promote directly to `traces` columns for rule-based search/subscriptions/bounties.

## Proposed signal catalog

Structure-only — computed from the normalized `traces`/`spans` rows, never from raw payload re-parsing.

| Signal | Type | Definition sketch |
|---|---|---|
| `has_errors` | bool | Any span with error status (exists in stage 1 shape) |
| `error_span_count` | int | Count of error-status spans |
| `exception_events` | int | Spans carrying exception events |
| `has_retry_loop` | bool | N+ near-identical consecutive tool calls (same tool, similar args) |
| `recovered_from_error` | bool | Error span followed by successful sibling/retry then normal completion |
| `truncation_suspected` | bool | Final LLM span output cut at max tokens / finish_reason `length` |
| `final_span_shape` | enum | How the trace ends: `normal_completion \| error \| tool_call_unanswered \| empty_output` |
| `llm_call_count` / `tool_call_count` | int | Per-kind span counts |
| `distinct_tool_count` | int | Unique tools invoked |
| `total_tokens` / `duration_ms` | int | Aggregates (largely exist in stage 1) |
| `token_outlier` / `latency_outlier` | bool | Trace is an outlier vs corpus baseline (definition open) |

## Output

- One typed signals object (Pydantic model) per trace → one row in the analyzer results table (`analyzer = "signals"`, versioned).
- Promoted to `traces`: the boolean flags and counts that matter for filtering (`has_retry_loop`, `recovered_from_error`, `final_span_shape`, counts). Exact promotion list decided with the filter vocabulary.

## Heuristic verdict

A small rule layer maps signals → a coarse prior: `likely_success | likely_failure | unclear` (e.g. clean completion + no errors → likely_success; unrecovered error ending → likely_failure). This is **not** a user-facing label — it exists only as the outcome judge's disagreement counterpart.

## Open questions

- Exact catalog: which of the proposed signals make the cut; anything missing (per-model breakdowns?). `estimated_cost` is settled as an extension, not base (see README Extensions).
- Loop detection definition: what counts as "near-identical" tool calls (exact args? normalized args? threshold N).
- Outlier baselines: corpus-global vs per-task-category; cold-start behavior on a small corpus.
- Heuristic verdict rules: keep minimal (3–4 rules) — at what point do they belong in the judge prompt instead.
