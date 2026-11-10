# Native Session Ingestion (A6)

Raw coding-agent session logs (Codex, Claude Code, Cursor JSONL) upload
directly; the server detects the schema, converts each session to one trace, and
rejects what it cannot convert. The client-side converter
(`tools/agent_sessions_to_otlp.py`) is retired: capture is `trace-sync`
pointed at the directories the tools already write.

## Format Model

- **OTLP JSON stays canonical.** Session schemas are *source formats* that
  ingestion converts into the OTLP in-memory shape, then runs through the
  one existing normalize path (`importers/otlp`). One normalization
  pipeline; the ingestion purity invariant (6_architecture.md) is untouched
  — the raw JSONL is the stored payload, conversion is deterministic, and
  delete-and-rewrite re-ingest reproduces identical rows.
- **Supported source formats** (`app/importers/sessions/`):

| `source_format` | Detection (first parseable JSONL lines) |
|---|---|
| `otlp_json` | JSON object with `resourceSpans` (existing) |
| `codex_jsonl` | objects with `type` ∈ {`session_meta`, `turn_context`, `response_item`, `event_msg`} |
| `anthropic_jsonl` | objects with `type` ∈ {`user`, `assistant`} carrying `message` (Claude Code and Cursor share this shape; agent name is `claude` when records carry timestamps, else `cursor`) |

- **Parsing fidelity** (shapes verified against real harness logs; the
  golden corpus in `fixtures/golden/` pins them):
  - Claude Code splits one assistant API response across records sharing
    `message.id`; responses group by id into exactly one llm span each —
    including tool-only responses, whose usage is real spend. Sub-agent
    records (`isSidechain` with an `agentId`, bundled by the CLI from
    `<session>/subagents/`) parse as their own stream and nest under the
    tool span whose result carries `toolUseResult.agentId` (recursively for
    nested subagents); unlinked sidechains and meta records (`isMeta`,
    `isCompactSummary`, `isVisibleInTranscriptOnly`) are skipped, except
    meta peer messages and scheduled triggers (`turnOrigin`), which prompt
    the model. Who asks is read from `origin.kind`: `human` opens a human
    turn; in a log that carries `origin`, an untagged record is
    harness-produced — CI monitor events, cross-session messages from other
    sessions, scheduled triggers and a prompt from the starting session open
    an automated turn (titled by the event's own text, e.g. `CI event: …`),
    while the agent's own delegated work reporting back (task notifications,
    subagent hand-backs, side-session reports), `[Request interrupted
    by user]` markers and local slash commands (`/model`, their
    `<local-command-*>` output) stay llm input and never open or title a
    turn. A skill slash command reads as `/name args`; `<pasted_content>`
    tags are unwrapped and `<system-reminder>`/`<artifact-view-context>`
    blocks dropped from asks (both stay llm input).
  - Token accounting: Anthropic input = `input_tokens` +
    `cache_read_input_tokens` + `cache_creation_input_tokens`. Codex usage
    arrives as `token_count` events (per model request, not per message);
    per-turn sums land on the turn span as `gen_ai.usage.*`; the session root carries no usage (trace totals already sum spans).
  - Reasoning is preserved as `gen_ai.reasoning` on the llm span: Claude
    `thinking` blocks, Codex `reasoning` summary text (the encrypted body
    is dropped).
  - Skills: a span records a skill use with `skill.name` (no leading
    slash, plugin prefix kept) and `skill.source`. Claude Code `Skill` tool
    calls carry them with `agent` (span named `Skill: <name>`); a human
    slash command that expands a skill or command prompt (leads with
    `<command-message>`; local commands like `/model` do not) puts them on
    its turn span with `user`, and a `Skill` call for the same skill later
    in that turn is the same use (named, but no `skill.*`). Codex rollouts
    record no skill use (the model reads `SKILL.md` through its shell), so
    none is derived. Traces list the distinct names as `skill_names`,
    derived from any span's `skill.name` (native OTLP too).
  - Subagents: a Claude Code `Agent`/`Task` call is named
    `Agent: <description>` and carries `subagent.description` (else the
    prompt's first line), `subagent.type`, `subagent.model` (seen on the
    subagent's llm records, else requested) and `subagent.background`
    (`toolUseResult.isAsync`); `subagent.id` only when its transcript was
    linked and nested. Nested work may outlive the spawning call and its
    turn; nothing is clamped.
  - A Codex rollout's first `session_meta` is its own (a forked sub-agent
    replays its parent's after it); its `parent_thread_id`, `agent_path`
    and `agent_nickname` land on the session root as `session.parent_id`,
    `session.agent_path` and `session.agent_nickname`.
  - Codex asks are `user_message` events or, in rollouts without them,
    `item_completed` `UserMessage` items; an `agent_message` from a parent
    agent opens an automated turn, one from a child is llm input only.
  - Codex tool calls parse generically: any `*_call` payload with a
    `call_id` pairs with its `*_output`; `web_search_call` (no call_id, no
    output record) emits in place; calls whose outputs never arrive emit
    unpaired.
- **Detection is shared** between the upload endpoint and the ingest task
  (`importers.detect_format`). POST rejects undetectable bytes with `422
  unsupported_format` and a readable reason; conversion failures discovered
  at ingest (e.g. a detected schema yielding zero turns) are
  `PermanentIngestError`s — verbatim on `/uploads`, never retried.
- `uploads.source_format` and `traces.source_format` record the detected
  format; session-converted traces carry the sessions importer version (`2.0.0`: one trace per session; `2.1.0`: harness-injected user records no longer open turns; `2.2.0`: subagents nest under their spawning call; `2.3.0`: synthesized span ends never cross a turn; `2.4.0`: automated turns marked `turn.origin`, non-asks never open turns, slash-command/reminder wrappers cleaned, a resumed log's leading activity takes the first prompt, Codex `UserMessage` items and parent `agent_message` tasks open turns; `2.5.0`: skill uses and subagent spawn attributes; a forked Codex sub-agent rollout keeps its own session id and records its parent link).

## Per-Session Granularity

One marketplace trace = one *session*. A *turn* is a user message and all
assistant activity (LLM responses, tool calls) until the next user message;
turns are spans inside the session trace, not traces.

- Deterministic identity: `trace_id = sha256(agent:session_id)` — re-ingest
  and re-upload of the same session produce the same source trace id, even
  as the session grows.
- Span tree: a session root `invoke_agent` span named
  `<agent>: <first ask>` (attrs `session.id`, `session.turn_count`,
  `workspace.cwd`; no `gen_ai.usage.*`, which would double-count in trace totals) → one turn
  `invoke_agent` span per turn named `turn N: <ask>` (attrs `turn.index`,
  0-based; `turn.user_message`, the full ask; `turn.origin`, `human` or
  `automated`; per-turn `gen_ai.usage.*`, or on the llm spans for formats reporting
  per-message usage) → that turn's llm and tool spans.
- A turn starts when something new asks the agent to act: a human ask
  (`turn.origin = human`) or an outside event (`automated`). The agent's own
  background work reporting back and non-asks never start one. Events
  before any prompt form one leading turn that takes the first prompt that
  follows (a log resumed after compaction; the summary is never the ask)
  and has no title or origin when none follows; a trailing unanswered ask
  is dropped; consecutive prompts merge into one turn, titled by the first.
- Native OTLP uploads are not grouped: instrumented agents that emit
  per-request traces still land one trace per OTLP `trace_id`. Cross-trace
  stitching stays the future extension (docs/extensions/session-stitching.md).
- Timestamps: real where the log has them (Codex, Claude). Cursor
  transcripts carry none: synthesized at one second per event anchored to
  the upload's `created_at`, marked `converted.synthesized_timestamps`.
  Anchoring to the upload row keeps re-ingest deterministic. Logs record
  when a response arrived, not how long it took: a span without an end runs
  to the next event of the same turn (the turn's last event gets 1s), so
  idle time between asks never reads as latency.
- No content caps: span attributes carry full prompt/tool text (the 50 MB
  upload limit bounds size; redaction (7_redaction.md) applies unchanged).

## Boundaries

- The scrubbed non-owner download artifact is the scrub of the *converted
  OTLP* payload — consumers of a session upload download canonical OTLP.
  The owner's raw download remains the original JSONL bytes.
- **Re-syncing a grown session is idempotent.** Trace identity is
  owner-scoped — unique `(owner_id, source_trace_id)`, 6_architecture.md A6
  amendment — and the session id is deterministic, so a later upload of the
  same session adopts its existing trace (latest upload owns it, content
  rewritten in place under its salt), shows the new turns as more turn
  spans, and never duplicates. Analysis re-runs on every ingest. `traces.id` is stable across re-syncs: acquisitions, labels,
  and review items survive. The superseded upload remains `complete` with
  zero traces.

## CLI (amends 5_cli.md)

- File detection widens to `*.json` and `*.jsonl`.
- New optional flag `--since-hours N` (env-free, both commands): only
  consider files modified in the last N hours. Absent = all files. This is
  file *selection*, not content interpretation — the raw-bytes rule holds.
- A Claude Code session uploads with its `X/subagents/*.jsonl` concatenated
  after it; `subagents/` files are never uploaded alone (5_cli.md).

## Done When

- `trace-sync sync devdata/sessions-src/cursor --since-hours 24` (raw
  transcripts, no conversion step) lands one trace per session on `/traces` with
  scannable names, models, token counts, and tool spans.
- An unsupported-schema `.jsonl` fails at POST with `unsupported_format`;
  a detected-but-empty session fails ingestion with a verbatim reason on
  `/uploads`.
- Re-uploading the same session file dedupes (`409 duplicate_upload`);
  re-ingesting an existing session upload converges to identical rows.
- Re-syncing a session that grew by one turn updates the same trace with
  one more turn span; `traces.id` is stable and moves to the new upload.
