# A6 pass 2 — harness parsing audit + golden corpus

Full review of session parsing against *real* harness logs on a live machine
(`~/.claude/projects`, `~/.codex/sessions`, `~/.cursor/projects`; structure
inspected, never content). The committed fixtures were idealized; real logs
exposed six defects.

## Findings (all fixed)

| # | Harness | Defect | Evidence (10 recent real files) |
|---|---|---|---|
| 1 | Claude Code | Sidechain (sub-agent) records not filtered → spurious turns, misattributed spans, leaked sub-agent model | 119 user + 184 assistant `isSidechain` records |
| 2 | Claude Code | `isMeta`/`isCompactSummary`/`isVisibleInTranscriptOnly` user records became turn titles | 18 + 4 + 4 records |
| 3 | Claude Code | Responses split across same-`message.id` records (one block each, identical usage): per-record llm spans double-counted multi-text responses and dropped tool-only responses' usage entirely | 405 ids, 100 tool-only, 0 with differing usage |
| 4 | Claude Code | Cache tokens ignored — input undercounted (real `input_tokens` is often single digits next to ~2k cached) | cache keys on 945/945 records |
| 5 | Codex | No token counts at all — usage lives in `event_msg`/`token_count`, never on messages | 416 events ignored |
| 6 | Codex | `tool_search_call`/`tool_search_output` dropped; unpaired calls dropped; reasoning summaries dropped; `input.value` polluted by preamble-laden `response_item` user echo | 6 + 1 + 347 items |

Plus: mixed-clock timestamp synthesis could order leading clockless events
*after* the first real clock (latent; no current harness emits that shape).

## Fixes

- `anthropic_jsonl.py`: skip flagged records; group assistant records by
  `message.id` into one llm span per API response (tool-only responses kept
  — their usage is real spend); input = `input_tokens + cache_read +
  cache_creation`; `thinking` → `gen_ai.reasoning`.
- `codex.py`: `token_count.last_token_usage` sums per turn onto the root
  span (`SessionBuilder.add_turn_usage`); generic `*_call`/`*_output`
  pairing by `call_id`; unpaired calls flush at parse end; `reasoning`
  summaries attach to the next assistant message as `gen_ai.reasoning`;
  typed ask wins over the `response_item` user echo for `input.value`.
- `turns.py`: turn-level usage rendered on the root span; leading clockless
  events now walk backward from the first real clock.
- `IMPORTER_VERSION` 1.1.0 → 1.2.0.

## Golden corpus

`fixtures/golden/{claude-code,codex,cursor}.jsonl` — one synthetic session
per harness whose structure mirrors the real logs (sidechains, meta records,
split responses, cache-heavy usage, `token_count` events, `tool_search_*`,
reasoning/thinking, an output-less trailing call, id-less multi-block Cursor
tool_use). They run the full sniff → convert → normalize pipeline in
`tests/unit/test_session_golden.py` against exact snapshots in
`tests/unit/golden/*.expected.json`, wired into the existing
`tests.unit.golden.regenerate` flow. Targeted semantic tests (hand-computed
token sums, turn lists, event ordering) live in
`test_importer_sessions.py` so regressions read as intent, not snapshot
noise.

Baseline vs fixed on the corpus: Claude went from 3 traces/124 tokens to
2 traces/5610+4177 tokens with no sidechain leakage; Codex gained turn
token totals (2520/550), the `tool_search` span, the unpaired call, and
clean prompts; Cursor was already correct (id-less fix from pass 1).

## Verification

- `pytest tests/unit` — importer suites pass (332 passed; one pre-existing
  unrelated failure in `test_filter_query.py::test_empty_query_rejected`,
  subscription validation, untouched by this pass).
- `ruff check` / `ruff format` clean.
- Existing OTLP golden files byte-identical after regenerate (normalize
  path untouched).

Out of scope, noted: Codex `thread_rolled_back` (1 occurrence in sample)
still leaves rolled-back turns in place; conversation view does not yet
render `gen_ai.reasoning`.
