# Sync CLI

A terminal tool, separate from the webapp, that uploads local trace files through the existing upload API. Lives in `apps/cli`, Python + uv (same toolchain as `services/api`), installed/run as `trace-sync`.

## Commands

| Command | Behavior |
|---|---|
| `trace-sync sync <paths...>` | Walk the paths, upload every new trace file, print per-file results, exit. |
| `trace-sync watch <paths...>` | Same loop, then stays alive and uploads files as they appear or change. Runs until interrupted. |

One code path; watch only changes the exit condition. Watch rescans every 2 s and uploads a new or changed file only once it has been unchanged for a quiet period (default 300 s; `--quiet-seconds` flag or `TRACE_SYNC_QUIET_SECONDS` env, flag wins), so an active session uploads once it pauses rather than on every few-second lull. `sync` is unaffected.

## Behavior Rules

- **Stateless.** No local manifest, no config file. The server's per-user sha256 dedupe is the source of truth: `409 duplicate_upload` → skip, print "already synced". Re-syncing a directory is always safe and idempotent.
- **File detection:** `*.json`, `*.jsonl` and `*.jsonl.zst` files under the given paths (recursive). Zstd-compressed logs (Codex archives rollouts this way) are decompressed client-side and sent under the name without `.zst`, so a session keeps one name live and archived; an unreadable archive fails that file permanently. The optional `--since-hours N` flag restricts to files modified in the last N hours — file selection only, never content interpretation (8_session-ingestion.md). Files under a `subagents/` directory are never selected on their own.
- **Raw bytes, pruned sessions.** The CLI sends the file verbatim, with two deviations for agent-session JSONL: a Claude Code session `X.jsonl` is sent together with its `X/subagents/*.jsonl` (concatenated JSONL, sorted by filename), so subagent transcripts nest in the parent session trace (watch mode treats a subagent change as a change to the session); transcripts of agents the session references (recursively) that live under a sibling session's `subagents/` in the same project directory are appended too, each once — a resumed or forked session copies earlier history into a new file but leaves those transcripts with the original. When the server rejects that bundle as too large (`413`), the CLI retries once with the session's own transcripts only and says in the file's outcome line how many it left out; and session logs are pruned to the records and fields the session importers read (`apps/cli/src/trace_sync/prune.py`, kept in step with `services/api/app/importers/sessions/`), which typically drops 75–95% of the bytes while converting to identical traces. A `.jsonl` with no recognized session record is sent verbatim. Uploads go via `POST /v1/uploads` — no tags, no metadata, no analysis. Everything derived happens server-side. It does not set `uploads.source`; the API infers `cli` from the API-key auth.
- **Pipelined status feedback.** Uploads are enqueued without waiting: the CLI POSTs every file first (ingestion runs server-side off its queue), then polls `GET /v1/uploads/{id}` across the in-flight set until each is terminal (bounded per-file timeout), printing each result as it lands: `complete, 3 traces` / `failed: <error_message verbatim>`. A batch of N files costs N quick uploads plus concurrent ingestion, not N sequential ingest waits.
- **Rate-limit aware.** The first sync of a big directory will hit the tight upload bucket; the CLI honors `Retry-After` and backs off rather than erroring. Provider-side backpressure is normal operation, not failure.
- **Readable errors.** Auth failures, unreachable API, oversized files, and per-file rejections print as one human-readable line each; one bad file never stops the run.

## Configuration

Env vars, overridable by flags:

| Env var | Flag | Meaning |
|---|---|---|
| `TRACE_API_URL` | `--api-url` | API base URL (local-demo default). |
| `TRACE_API_KEY` | `--api-key` | API key minted in `/settings`. Upload-only scope. |

## Output And Exit Codes

One line per file: path → `uploaded (complete, N traces)` / `already synced` / `failed: <reason>`. Lines print as outcomes land, so they may not follow upload order; skips and rejections print immediately, completions as ingestion finishes. A summary line on exit (`synced 12 · skipped 40 · failed 1`).

| Code | Meaning |
|---|---|
| 0 | All files uploaded or already synced. |
| 1 | At least one file failed (upload rejected or ingestion failed). |
| 2 | Could not run at all (bad key, unreachable API, no files found). |

`watch` exits only on interrupt (code reflects failures seen so far).
