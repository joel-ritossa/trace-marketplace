# Session as Trace — Implementation

Amends A6 (`docs/spec/stage-2/8_session-ingestion.md`) and the B0 renderer (`1_analysis.md`).

## Decision

2026-11-10, user: sessions are the main unit. A coding-agent session log (Claude Code / Codex / Cursor) is **one trace**, not one trace per turn. Judging a session needs the original goal and the clarifying exchanges; per-turn traces were each judged blind to their siblings.

## Plan

1. **Importer** (`IMPORTER_VERSION` 2.0.0): `trace_id = sha256(agent:session_id)`. Span tree: session root `invoke_agent` span (`<agent>: <first ask>`; `session.id`, `session.turn_count`, `workspace.cwd`; no `gen_ai.usage.*`, since trace totals already sum spans) → one turn `invoke_agent` span per turn (`turn N: <ask>`; `turn.index` 0-based, `turn.user_message` = full ask, per-turn `gen_ai.usage.*`, or on llm spans for formats with per-message usage) → that turn's llm/tool spans. Turn-splitting rules unchanged (leading turn before any ask, dropped trailing unanswered ask, consecutive asks merge).
2. **Re-sync**: same `source_trace_id` → the existing row is adopted and rewritten in place; `traces.id` is stable (acquisitions, labels, review survive); new turns appear as more turn spans; analysis re-runs (every ingest already does).
3. **Renderer** (`RENDERER_VERSION` 3): every turn's ask (`turn.user_message`) is a must-have `user` message in chronological position, never elided, alongside error spans and the final K steps; middle steps fill the budget newest-first as before. Non-session OTLP traces render unchanged.
4. **Docs**: `8_session-ingestion.md`, `1_analysis.md`, `trace-rendering.md`, `cli-sync.md`, README, session-stitching note.

## Contract notes

- Native OTLP uploads (instrumented agents emitting per-request traces with session/conversation ids) are **not** grouped: one trace per OTLP `trace_id`. Cross-trace stitching stays the future extension (`docs/extensions/session-stitching.md`).

## Outcome

TODO (coordinator): fill after verification.
