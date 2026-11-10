# Agent Judge — Implementation

Supersedes the B2 outcome judge, B3 quality metrics, the B5 metrics validation and the routing/confidence parts of A3/A4 (`docs/spec/stage-2/1_analysis.md` now points at the new spec). Normative design: `docs/spec/stage-2/9_session-analysis.md`. Follows [session-as-trace](../session-as-trace/000_implementation.md).

## Decision

Owner decisions, 2026-11-10:

- **Sessions are the unit of upload.** One trace per session, subagents nested, upload limit 50 MB (`8_session-ingestion.md`; CLI: quiet-period watch, `.jsonl.zst`, client-side pruning, subagent bundling — `5_cli.md`).
- **The turn is the unit of judgment.** The session verdict is a roll-up of turn verdicts. Native OTLP traces are one synthetic turn.
- **A Luna-tier agent explores the trace via tools** (`list_turns`, `read_turn`, `read_span`, `search`) instead of judging a budgeted rendering.
- **No voting, no confidence scores.** The agent flags what it could not judge (`uncertain`); review follows that flag.
- **Multi-select labels** (`task_category`, `failure_mode`), per turn and as the union per session; `outcome` stays single-valued and gains `partial`.
- **Labels are anchored to spans:** every failure mode cites span ids inside its turn and a reason.
- **Judge complete turns on ingest, finalize when idle.** A turn is judged once a later turn exists; the last turn and the roll-up run after `ANALYSIS_IDLE_SECONDS` (2 h), on `POST /v1/traces/{id}/analyze`, or when the trace is listed.
- **OpenAI Agents SDK, no litellm.** OpenAI only, behind `app/analysis/llm.py`; SDK tracing export disabled.
- **Quality metrics retired** (critics, RAGAS, `metric_scores`, the `ragas` dependency, `metric` filter), together with the standalone summary and listing calls (both now come from the roll-up).

## Plan (as built)

1. **Agent** (`app/analysis/agent/`): `turns.py` splits a trace into turns with a fingerprint (span ids + end time); `tools.py` the four tools over the in-memory redacted `TraceInput`, reusing the renderer's field caps and `middle_out`; `judge.py` `judge_turn` (agent + one validation retry; step limit → forced answer → `indeterminate` + `uncertain`; invalid span ids dropped) and `roll_up` (tool-less, one call); `models.py` `TurnVerdict` / `SessionVerdict`; prompts in `app/analysis/prompts/agent/`.
2. **LLM client** (`app/analysis/llm.py`): Agents SDK runner, `StepLimitExceeded`, embeddings, per-call usage metadata. litellm removed.
3. **Signals per turn** (`analysis/signals.py`): computed over a turn's spans; `combine` aggregates to the session. `failure_suspected` removed.
4. **Migration 17** (`supabase/migrations/00000000000017_session_analysis.sql`): new `turn_analysis` and `trace_labels` (RLS mirrors `trace_analysis`, realtime on `turn_analysis`); `trace_analysis` reshaped (arrays, goal/summary, no confidence/provenance/metric columns, `analyzed_at` nullable until finalized); `analyzer_results.confidence` dropped; embeddings input renamed; removed filter keys stripped from stored subscriptions. Existing analysis rows are cleared and re-derived by the sweep.
5. **Worker** (`worker/tasks/analyze.py`, `queries/analysis.py`, `queries/review_items.py`): incremental `analyze_trace(finalize)`; judges only stale turns with bounded concurrency; partial progress is persisted before a failure is re-raised; one transaction writes turns, labels, session arrays, audit row and syncs the review item. The minute sweep finalizes idle sessions (`due_ids`). Listing finalizes non-final traces.
6. **API**: analysis block on `GET /v1/traces/{id}` (`session` + `turns[]`); `POST /v1/traces/{id}/analyze` finalizes; `PUT /v1/traces/{id}/turns/{turn_index}/labels` relabels; review items reduced to list/get. Removed: `GET …/analysis`, `POST /review-items/{id}/resolve`, `POST /traces/{id}/review-items`, `GET /traces/metric-keys`, the provenance/confidence/metric filters. `labels.jsonl` carries the session block and per-turn verdicts.
7. **Dev surface**: canned-verdict fault now `analyze:verdict:<outcome>[:uncertain]`; `python -m app.cli.analyze run` judges fixtures turn by turn; the agreement runner and its demos were removed.
8. **Docs**: spec 0–4, 6; explainer `how-a-session-gets-judged.md` replaces `trace-rendering.md`; demos `hil-loop`, `subscriptions`, `cli-sync` updated, `judge-agreement` and `metric-agreement` deleted; README, ARCHITECTURE, `report/` corrected or marked superseded.

## Drift and notes

- The renderer (`rendering.py`, `ANALYSIS_RENDER_*`) stayed, but only its field caps and `middle_out` serve the judge; `render_trace` is now the offline runner's `render` command. `ANALYSIS_RENDER_BUDGET_TOKENS` / `..._FINAL_STEPS` no longer affect judging.
- `review_items.question_type` and `answer` columns are unchanged but unused (`answer` always null).
- Validation (B4 agreement numbers) was not re-run for the agent; the converters remain.

## Outcome

Verified 2026-11-10 on the deployed stack, model `gpt-6-luna`:

- **Tests:** unit tests pass — API 219, CLI 26.
- **Migration 17** applied; `traces`, `spans` and `uploads` counts unchanged.
- **Multi-turn session:** a 16-turn Claude Code session judged in 95 s — 554,712 input / 20,856 output tokens, 165 tool calls; 13 success, 2 partial, 1 failure; no uncertain turns.
- **Single-turn session:** a 1-turn Codex session judged in 40 s.
- **Anchoring:** every cited span id resolved inside its turn (3/3).
- **Incremental:** a turn marked stale was re-judged alone; a human-relabelled turn survived a re-run untouched.
- **Finalize gate:** a non-finalizing run judged the stale middle turn, left the last turn, and reported `in_progress`.
- **Cost:** observed average ≈ 35k input / 1.3k output tokens per turn.

Known limits:

- Very large turns can exhaust the 20-step budget and come back `indeterminate` + uncertain; judging per subagent is the planned next step.
- "Analyze now" has no explicit running signal from the server.
- `apps/desktop` still calls the removed review endpoints.
- One weak verdict observed, on a 1-turn Codex session whose goal was vague.
