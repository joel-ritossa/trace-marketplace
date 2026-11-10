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
    `isCompactSummary`, `isVisibleInTranscriptOnly`) are skipped. User
    records with `origin.kind` other than `human` (task notifications, peer
    messages) remain llm input but never open a turn; `<pasted_content>`
    wrapper tags are stripped from asks (content kept).
  - Token accounting: Anthropic input = `input_tokens` +
    `cache_read_input_tokens` + `cache_creation_input_tokens`. Codex usage
    arrives as `token_count` events (per model request, not per message);
    per-turn sums land on the turn span as `gen_ai.usage.*`; the session root carries no usage (trace totals already sum spans).
  - Reasoning is preserved as `gen_ai.reasoning` on the llm span: Claude
    `thinking` blocks, Codex `reasoning` summary text (the encrypted body
    is dropped).
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
  format; session-converted traces carry the sessions importer version (`2.0.0`: one trace per session; `2.1.0`: harness-injected user records no longer open turns; `2.2.0`: subagents nest under their spawning call).

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
  0-based; `turn.user_message`, the full ask; per-turn `gen_ai.usage.*`, or on the llm spans for formats reporting
  per-message usage) → that turn's llm and tool spans.
- Turn splitting is unchanged: events before any user message (or sessions
  with none) form one leading turn; a trailing unanswered ask is dropped;
  consecutive asks merge into one turn.
- Native OTLP uploads are not grouped: instrumented agents that emit
  per-request traces still land one trace per OTLP `trace_id`. Cross-trace
  stitching stays the future extension (docs/extensions/session-stitching.md).
- Timestamps: real where the log has them (Codex, Claude). Cursor
  transcripts carry none: synthesized at one second per event anchored to
  the upload's `created_at`, marked `converted.synthesized_timestamps`.
  Anchoring to the upload row keeps re-ingest deterministic.
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
