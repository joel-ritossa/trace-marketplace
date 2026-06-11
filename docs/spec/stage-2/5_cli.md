# Sync CLI

A terminal tool, separate from the webapp, that uploads local trace files through the existing upload API. Lives in `apps/cli`, Python + uv (same toolchain as `services/api`), installed/run as `trace-sync`.

## Commands

| Command | Behavior |
|---|---|
| `trace-sync sync <paths...>` | Walk the paths, upload every new trace file, print per-file results, exit. |
| `trace-sync watch <paths...>` | Same loop, then stays alive and uploads files as they appear or change. Runs until interrupted. |

One code path; watch only changes the exit condition. Watch debounces filesystem events and waits for a file to stop growing before uploading.

## Behavior Rules

- **Stateless.** No local manifest, no config file. The server's per-user sha256 dedupe is the source of truth: `409 duplicate_upload` → skip, print "already synced". Re-syncing a directory is always safe and idempotent.
- **File detection:** `*.json` files under the given paths (recursive).
- **Raw bytes only.** The CLI sends the file verbatim via `POST /v1/uploads` — no tags, no metadata, no client-side parsing or analysis. Everything derived happens server-side. It does not set `uploads.source`; the API infers `cli` from the API-key auth.
- **Status feedback.** After each upload, poll `GET /v1/uploads/{id}` until terminal (bounded timeout) and print the result: `complete, 3 traces` / `failed: <error_message verbatim>`.
- **Rate-limit aware.** The first sync of a big directory will hit the tight upload bucket; the CLI honors `Retry-After` and backs off rather than erroring. Provider-side backpressure is normal operation, not failure.
- **Readable errors.** Auth failures, unreachable API, oversized files, and per-file rejections print as one human-readable line each; one bad file never stops the run.

## Configuration

Env vars, overridable by flags:

| Env var | Flag | Meaning |
|---|---|---|
| `TRACE_API_URL` | `--api-url` | API base URL (local-demo default). |
| `TRACE_API_KEY` | `--api-key` | API key minted in `/settings`. Upload-only scope. |

## Output And Exit Codes

One line per file: path → `uploaded (complete, N traces)` / `already synced` / `failed: <reason>`. A summary line on exit (`synced 12 · skipped 40 · failed 1`).

| Code | Meaning |
|---|---|
| 0 | All files uploaded or already synced. |
| 1 | At least one file failed (upload rejected or ingestion failed). |
| 2 | Could not run at all (bad key, unreachable API, no files found). |

`watch` exits only on interrupt (code reflects failures seen so far).
