# Native Session Ingestion (A6)

Raw coding-agent session logs (Codex, Claude Code, Cursor JSONL) upload
directly; the server detects the schema, converts to per-turn traces, and
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
    including tool-only responses, whose usage is real spend. Sidechain
    (sub-agent) and meta records (`isSidechain`, `isMeta`,
    `isCompactSummary`, `isVisibleInTranscriptOnly`) are skipped.
  - Token accounting: Anthropic input = `input_tokens` +
    `cache_read_input_tokens` + `cache_creation_input_tokens`. Codex usage
    arrives as `token_count` events (per model request, not per message);
    per-turn sums land on the turn root span as `gen_ai.usage.*`.
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
  format; session-converted traces carry the sessions importer version.

## Per-Turn Granularity

One marketplace trace = one *turn*: a user message and all assistant
activity (LLM responses, tool calls) until the next user message.

- Deterministic identity: `trace_id = sha256(source:session_id:turn_index)`
  — re-ingest and re-upload of the same session produce the same source
  trace ids.
- Each turn gets a synthetic `invoke_agent` root span named
  `<agent>: <user ask>`, with `session.id`, `turn.index`, and
  `workspace.cwd` attributes. `session.id` is the grouping key the
  session-stitching extension consumes (docs/extensions/session-stitching.md).
- Events before any user message (or sessions with none) form one leading
  turn named after the agent.
- Timestamps: real where the log has them (Codex, Claude). Cursor
  transcripts carry none: synthesized at one second per event anchored to
  the upload's `created_at`, marked `converted.synthesized_timestamps`.
  Anchoring to the upload row keeps re-ingest deterministic.
- No content caps: span attributes carry full prompt/tool text (the 25 MB
  upload limit bounds size; redaction (7_redaction.md) applies unchanged).

## Boundaries

- The scrubbed non-owner download artifact is the scrub of the *converted
  OTLP* payload — consumers of a session upload download canonical OTLP.
  The owner's raw download remains the original JSONL bytes.
- **Re-syncing a grown session is idempotent.** Trace identity is
  owner-scoped — unique `(owner_id, source_trace_id)`, 6_architecture.md A6
  amendment — and per-turn ids are deterministic, so a later upload of the
  same session adopts its existing turn traces (latest upload owns them,
  content rewritten under its salt), appends new turns, and never
  duplicates. `traces.id` is stable across re-syncs: acquisitions, labels,
  and review items survive. The superseded upload remains `complete` with
  zero traces.

## CLI (amends 5_cli.md)

- File detection widens to `*.json` and `*.jsonl`.
- New optional flag `--since-hours N` (env-free, both commands): only
  consider files modified in the last N hours. Absent = all files. This is
  file *selection*, not content interpretation — the raw-bytes rule holds.

## Done When

- `trace-sync sync devdata/sessions-src/cursor --since-hours 24` (raw
  transcripts, no conversion step) lands per-turn traces on `/traces` with
  scannable names, models, token counts, and tool spans.
- An unsupported-schema `.jsonl` fails at POST with `unsupported_format`;
  a detected-but-empty session fails ingestion with a verbatim reason on
  `/uploads`.
- Re-uploading the same session file dedupes (`409 duplicate_upload`);
  re-ingesting an existing session upload converges to identical rows.
- Re-syncing a session that grew by one turn yields exactly one new trace;
  the existing turns keep their `traces.id` and move to the new upload.
