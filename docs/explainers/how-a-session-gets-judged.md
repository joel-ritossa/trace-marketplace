# How does a session get judged?

**One-line answer:** each turn is judged once by an OpenAI Agents SDK agent
that explores the (redacted) trace through four read-only tools and returns a
verdict whose failure modes cite spans; a tool-less roll-up call turns the
turn verdicts into the session verdict when the session has gone quiet (or the
owner asks). A turn is re-judged only if its spans change.

Normative design: `docs/spec/stage-2/9_session-analysis.md`.

## Mechanism

1. **Split into turns** (`app/analysis/agent/turns.py:split`). A session trace
   has one `turn.index` span per user ask; a turn is that span and all its
   descendants, nested subagent spans included. A trace with no turn spans
   (native OTLP) is one synthetic turn 0 over every span. Each turn carries a
   fingerprint (hash of its span ids, statuses and input/output digests; no
   timestamps).
2. **Decide what to judge** (`worker/tasks/analyze.py:analyze_trace`). A turn
   is judged when it has no `turn_analysis` row or its fingerprint changed,
   and never when the row is `provenance = human`. Non-session traces are
   finalized right after ingest. Session traces are judged turn by turn,
   every ingest, but only *complete* turns (a later turn exists); the last
   turn and the roll-up wait until `traces.ended_at` is older than
   `ANALYSIS_IDLE_SECONDS` (the minute sweep, `queries/analysis.py:due_ids`),
   or `POST /v1/traces/{id}/analyze`, or listing the trace.
3. **One agent per turn** (`analysis/agent/judge.py:judge_turn_with_meta`),
   up to `ANALYSIS_TURN_CONCURRENCY` at a time. The agent gets `list_turns`,
   `read_turn` (25 spans a page, 200-char previews), `read_span` (full
   input/output, capped) and `search` (`analysis/agent/tools.py`), all over
   the in-memory redacted `TraceInput`. It must `read_turn` the judged turn
   before answering.
4. **Validate the answer** (`judge.py:_check`). Categories must be in the
   owner's task scope (plus `other`); each failure mode needs at least one
   `span_id` that is an llm/tool span inside the turn. Violations are fed
   back once, with a few valid span ids of the turn as candidates; if the
   retry still violates, bad ids and labels are dropped and `uncertain` says
   so in plain language (`judge.py:_verdict`). Otherwise `uncertain` is the
   agent's own, meant only for "a human should look", not for caveats.
5. **Roll up** (`judge.py:roll_up_with_meta`): one tool-less call over each
   turn's ask, outcome, failure modes and one-line summary (not spans) gives
   the session `goal`, `outcome`, `summary` and the listing copy. Session
   categories and failure modes are the union over turns, computed in SQL,
   never asked of the model. The embedding input is the roll-up text.
6. **Persist in one transaction** (`queries/analysis.py:rewrite`):
   `turn_analysis`, `trace_labels`, `trace_analysis`, an `analyzer_results`
   audit row, and the review item for any uncertain turns.

## Caveats

- **Token use grows with turn size.** The agent reads spans through tools, so
  a big or deep turn means more tool rounds and more tokens. Per-field
  previews and caps bound each read, not the total
  (`ANALYSIS_RENDER_TOOL_FIELD_CAP_CHARS`, `..._CONVERSATION_CAP_CHARS`);
  per-turn usage is in the audit row.
- **A turn that exhausts the step limit** (`ANALYSIS_AGENT_MAX_STEPS`, default
  100 model turns) **or the model's context window** is forced to answer
  from what it has read; that outcome stands and `uncertain` is set, so it
  lands in the review queue. Every tool result stays in the agent's
  conversation, so a very large turn can overflow the window; the forced
  answer then drops the older half of the tool outputs until it fits
  (`judge.py:_forced_answer`). The judge is told to skim long turns (first
  and last page, then search) rather than page through every span.
- **Judgments are made once.** An unchanged turn is never revisited: changing
  the model, the prompts or the owner's task scope does not re-judge
  history. A turn is re-judged only when its fingerprint changes, and a
  human relabel is permanent.
- **The last turn is provisional until the session is idle.** While a session
  is being written, the newest turn and the session verdict are absent or
  stale (`status: in_progress`); a session that resumes after finalizing gets
  its roll-up re-run at the next idle point.
- **The judge sees redacted content.** Spans are read after scrubbing
  ([redaction-boundary.md](redaction-boundary.md)); placeholders, not
  originals, reach OpenAI. Judgments are only as good as what survives
  scrubbing and the per-field caps.
- **Not deterministic.** The agent samples; two runs can differ. There is no
  voting and no confidence score, only `uncertain` reasons.
- **No key or opt-out = no verdict.** Signals still run per turn; LLM fields
  stay null (`llm_status = skipped`).
- `app/analysis/rendering.py` (`render_trace`) is no longer on the judging
  path; it survives as the offline runner's `render` command, and its
  `middle_out` truncation helper is reused by the tools.
