# Session Analysis (agent judge)

Normative. Supersedes the outcome judge, voting, confidence, quality metrics,
and HIL routing sections of `1_analysis.md` (decision: owner, 2026-11-10).
Where the two disagree, this file wins.

## Why

A trace is now a whole session (8_session-ingestion.md): many turns, nested
subagents, sometimes days long. The voted judge gave one verdict, one
category (from turn 1) and one failure mode for all of it, from a truncated
rendering, and re-ran ~20 calls on every upload.

## Model

- **The turn is the unit of judgment.** A session's labels are the roll-up
  of its turns. A trace with no turn spans (native OTLP) is treated as one
  turn (`turn_index` 0) covering every span, so there is one code path.
- **One agent pass per turn, no voting.** An LLM agent explores the trace
  through tools and returns a verdict for one turn. A second, tool-less call
  rolls turn verdicts up into the session verdict.
- **Multi-select.** `task_category` and `failure_mode` are sets, per turn
  and (as the union) per session. `outcome` stays single-valued.
- **Anchored.** Every failure-mode label cites the spans that show it. Every
  label belongs to a turn.

### Vocabularies

- `outcome` (turn and session): `success | partial | failure | indeterminate`.
- `task_category`: the existing taxonomy in `app/analysis/models.py`; owner
  task scope (`profiles.task_categories` + `other`) still constrains it.
- `failure_mode`: the existing AgentRx taxonomy minus `inconclusive` (an
  empty set already says "none identified"). Allowed on any outcome: a turn
  can succeed after an `invalid_invocation`.

### Verdict shapes (Pydantic, `app/analysis/agent/models.py`)

```python
class FailureLabel(BaseModel):
    value: FailureMode
    span_ids: list[str]      # source_span_id of llm/tool spans in this turn, >= 1
    reason: str              # one sentence

class TurnVerdict(BaseModel):
    turn_index: int
    outcome: Outcome
    summary: str             # one line: what was asked, what happened
    task_categories: list[TaskCategory]   # >= 1
    failure_modes: list[FailureLabel]     # may be empty
    uncertain: str | None    # null, or why a human should look: the agent
                             # could not judge confidently (not caveats)

class SessionVerdict(BaseModel):
    goal: str                # what the user was trying to get done overall
    outcome: Outcome
    summary: str             # short paragraph
    tags: list[str]          # listing copy
    description: str         # listing copy
```

Session `task_categories` / `failure_modes` are computed (union over turns),
never asked of the model.

## Agent

Entry points (pure; no DB, no HTTP — same contract as other analyzers):

```python
async def judge_turn(trace: TraceInput, turn_index: int, settings) -> TurnVerdict
async def roll_up(trace: TraceInput, verdicts: list[TurnVerdict], settings) -> SessionVerdict
```

Tools given to `judge_turn` (all read the in-memory `TraceInput`, already
redacted):

| Tool | Returns |
|---|---|
| `list_turns()` | every turn: index, the user's ask, duration, span count, error count |
| `read_turn(turn_index, offset?)` | that turn's spans in order as compact rows: `span_id`, depth, kind, name/tool, status, duration, input/output previews. A subagent call's children are included, indented by depth. Paged. |
| `read_span(span_id)` | one span's full input and output |
| `search(query, turn_index?)` | spans whose input/output/name contain the text |

- Previews and full-field caps reuse the renderer's existing caps
  (`ANALYSIS_RENDER_TOOL_FIELD_CAP_CHARS`, `..._CONVERSATION_CAP_CHARS`).
- The agent is told which turn it is judging and that other turns are
  context. It must read the turn before answering.
- **Validation.** Output must parse; `span_ids` must be llm/tool spans inside
  the judged turn (nested subagent spans count). On a violation the errors
  are fed back once; if the retry still violates, invalid ids are dropped, a
  label left with no ids is dropped, and `uncertain` is set in plain
  language (no span ids or internal error text).
- A turn the agent never read (no `read_turn` call for it) is a violation.
- Loop bound: `ANALYSIS_AGENT_MAX_STEPS` model turns. Hitting it, or a
  model call overflowing the context window, forces a tool-less answer from
  what was read (older tool outputs dropped until it fits); the forced
  answer's outcome stands and `uncertain` is set. The turn never fails the run.
- LLM access stays behind `app/analysis/llm.py` (OpenAI Agents SDK,
  Responses API; OpenAI only). Model: `ANALYSIS_JUDGE_MODEL` (a plain
  OpenAI model id). Record latency/tokens and call counts per turn.

## Subagent verdicts

A linked subagent (a spawn tool span with `subagent.id` and at least one
child span) is judged on its own, before the turn that contains it.

```python
class SubagentVerdict(BaseModel):
    span_id: str             # source_span_id of the spawn span
    outcome: Outcome
    summary: str             # one line: what it was briefed to do, what it did
    failure_modes: list[FailureLabel]   # span_ids inside this subagent
```

- **Judged against its brief** (the spawn span's input), not the user's ask:
  did it do what it was told, and does its final report match what it
  actually did. No task categories, no `uncertain`.
- **Same agent, same tools.** The subagent judge is the turn judge scoped
  to the spawn span: it starts with `read_turn(turn, under=<spawn span>)`,
  and may cite only llm/tool spans below that span. Validation, the one
  retry, the step bound and the context-limit fallback are the turn's.
- **Nested subagents** are judged deepest first. A judged spawn span shows
  in its parent's `read_turn` rows as one row carrying the verdict
  (outcome, summary, failure-mode values) with its children hidden;
  `read_turn(turn, under=<spawn span>)` still opens them. This holds for
  the turn judge and for a parent subagent's judge.
- **The turn judge decides what a subagent failure means for the turn.**
  Subagent labels do not enter the turn's or the session's label arrays; a
  failure the parent caught and corrected need not be a turn failure. The
  turn judge may cite the spawn span.
- **Persistence**: `subagent_analysis`, PK `(trace_id, span_id)`:
  `turn_index`, `fingerprint` (same recipe as a turn, over the spawn span
  and its descendants), `outcome`, `summary`, `failure_modes jsonb`
  (`[{value, span_ids, reason}]`), `model`, `usage jsonb`, `analyzed_at`.
  RLS mirrors `turn_analysis`. Rows for spawn spans no longer in the trace
  are deleted by the run.
- **When**: in the same run as its turn. A subagent is judged when its turn
  is being judged and it has no row or its fingerprint changed. Subagent
  and turn judging share `ANALYSIS_TURN_CONCURRENCY`. A subagent gets no
  row, and the turn judge reads it inline as before, when the judge
  permanently cannot process it, returns malformed output, never read it
  (still, after the retry), or was cut short by the step bound or the
  context window (a verdict has no `uncertain` to carry that). A transient
  failure (rate limit, network) fails the run like a turn's. Duplicate
  failure-mode values are merged as for a turn.
- **API**: each item of `GET /v1/traces/{id}/agents` gains
  `verdict: {outcome, summary, failure_modes[{value, span_ids, reason}]} | null`.
- Unlinked spawns (no transcript) are not judged.

## Persistence

- `turn_analysis` — PK `(trace_id, turn_index)`: `fingerprint`, `outcome`,
  `summary`, `uncertain`, `signals jsonb`, `provenance`
  (`machine | human`), `model`, `usage jsonb`, `analyzed_at`.
- `trace_labels` — one row per label: `trace_id`, `turn_index`, `field`
  (`task_category | failure_mode`), `value`, `span_ids text[]`, `reason`.
- `trace_analysis` (session roll-up, 1:1 with trace): `outcome`, `goal`,
  `summary`, `task_categories text[]`, `failure_modes text[]`, the
  session-level signal columns, `analyzed_at`. The scalar `failure_mode`,
  `task_category`, every `*_confidence` / `*_provenance` column, and
  `metric_scores` are removed.
- `analyzer_results` keeps one row per run for audit (model, usage, tool-call
  counts); votes are gone.
- RLS mirrors `trace_analysis` for the new tables.

**Fingerprint** = hash of the turn's span ids with each span's status and a
digest of its input/output text (no timestamps: clockless logs get
synthesized ones). A turn is judged when it has no row or its fingerprint
changed. A turn with
`provenance=human` is never re-judged or overwritten.

## When analysis runs

Ingest no longer enqueues analysis unconditionally.

- **Non-session formats** (`otlp_json`): analyzed right after ingest, as now.
- **Session formats, turn by turn**: a turn is *complete* once a later turn
  exists (the next ask is the user's reaction to it, and its spans no longer
  change). Every ingest enqueues analysis when a complete turn needs
  judging; that run judges complete turns only and refreshes the computed
  session arrays, but does not roll up.
- **Session formats, at the end**: the last turn and the roll-up
  (`goal`, `outcome`, `summary`, listing copy, embedding) run when the trace
  has gone quiet — `traces.ended_at` older than `ANALYSIS_IDLE_SECONDS`
  (default 7200). The existing minute sweep finds these. If the session
  later grows, the old last turn is re-judged only if its fingerprint
  changed, and the roll-up re-runs at the next idle point.
- **On demand**: `POST /v1/traces/{id}/analyze` (owner) finalizes now — last
  turn and roll-up included — whatever the idle state. It is idempotent: a
  final trace queues nothing, and a run in flight gets the request noted.
- Listing a trace on the marketplace finalizes it first if it is not final.

**One run per trace.** A run holds a per-trace lease
(`ANALYSIS_LEASE_SECONDS`, heartbeat-extended while it lives, so a crashed
worker frees the trace within one period). A run that finds the lease held
exits at once and records its mode; the holder enqueues one rerun in that
mode on release, so a finalize asked for mid-run still happens. The sweep
skips leased traces and enqueues at most `SWEEP_ANALYSIS_BATCH` per tick.
Writes are still guarded: a turn is written only if its row is as the run
read it, and only turns in the current spans are deleted.

A turn the judge permanently cannot process is stored `indeterminate`,
`uncertain` ("The judge could not process this turn."), and the run goes on
to the roll-up; a transient failure persists the judged turns and retries.

A run judges only the turns that need it (bounded concurrency,
`ANALYSIS_TURN_CONCURRENCY`), then re-runs the roll-up, then writes
everything in one transaction. Deterministic signals are computed per turn
(a turn's spans only, so repeats across turns no longer count as a loop);
session-level signal columns are the aggregate (any turn / sums).

Listing copy (`tags`, `description`) and the behavior summary come from the
roll-up (fill-if-empty for owner-editable copy). The embedding input is the
roll-up text (goal, summary, one line per turn).

## Review

- No confidence scores and no disagreement routing.
- A trace with any `uncertain` machine turn has one open review item listing
  those turns. When the set changes the item is updated in place (no new
  item, no new notification); it closes when the set is empty.
- `uncertain` is review content: owner-only, like review items.
- Owners relabel a turn at any time:
  `PUT /v1/traces/{id}/turns/{turn_index}/labels` with `outcome`,
  `task_categories`, `failure_modes`. That turn becomes `provenance=human`,
  `uncertain` clears, the roll-up arrays are recomputed, and the review item
  closes when no uncertain turn is left. The session verdict is then stale:
  a finalizing run re-rolls it up (no turn is re-judged).

## API

- `GET /v1/traces/{id}` analysis block: `session` (`goal`, `outcome`,
  `summary`, `task_categories`, `failure_modes`, `analyzed_at`,
  `turn_count` (every turn as the judge splits them, judged or not), `status`:
  `pending` (nothing judged) | `in_progress` (some turns judged, not
  finalized) | `final` (every turn judged and the roll-up is current) |
  `skipped` (no provider key / opt-out)) and `turns[]`
  (`turn_index`, `outcome`, `summary`, `uncertain`, `provenance`, `signals`,
  `labels[]` with `field`, `value`, `span_ids`, `reason`).
- List/filter/subscription/bulk surfaces: `outcome` is the session outcome;
  `task_category` and `failure_mode` filters match when the session array
  contains any requested value (CSV-OR, as before). Metric-score filters and
  confidence/provenance filters are removed.

## Removed

Voting and vote storage, confidence formula, `failure_suspected`
disagreement cap, quality-metric critics and RAGAS evals (and the `ragas`
dependency), `metric_scores`, the standalone summary and listing calls.

## Tunables (env, documented in `.env.example`)

`ANALYSIS_JUDGE_MODEL=gpt-5-mini`, `ANALYSIS_IDLE_SECONDS=7200`,
`ANALYSIS_AGENT_MAX_STEPS=100`, `ANALYSIS_TURN_CONCURRENCY`,
`ANALYSIS_LEASE_SECONDS=120`, `SWEEP_ANALYSIS_BATCH=50`. Removed:
`ANALYSIS_JUDGE_VOTES`, `ANALYSIS_JUDGE_CONSENSUS`,
`ANALYSIS_CONFIDENCE_THRESHOLD`, `ANALYSIS_METRICS`, `ANALYSIS_CRITIC_VOTES`.

## Done when

- A multi-turn session gets a verdict per turn with multi-valued categories
  and span-anchored failure modes, visible on the trace page; clicking a
  label's evidence opens that span.
- Re-syncing a session that grew by one turn judges exactly one turn (plus
  the roll-up).
- While a session is still being written, each turn is judged once the next
  turn starts; the last turn and the session verdict wait until it is idle
  or the owner asks.
- Every cited span id resolves to a span inside the cited turn.
