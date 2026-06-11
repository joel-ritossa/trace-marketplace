# trace-sync

Upload local trace files (OTLP JSON) to a [Trace Marketplace](https://github.com/worktrial-joel-ritossa-dot/trace-marketplace) instance from the terminal.

```sh
pipx install trace-sync          # or: uvx trace-sync …
```

## Usage

Mint an upload-only API key on the marketplace's Settings page, then:

```sh
# upload every new trace file under the paths, then exit
TRACE_API_URL=https://your-marketplace.example TRACE_API_KEY=tmk_… \
  trace-sync sync ./traces

# same, then stay alive and upload files as they appear or change
trace-sync watch ./traces
```

Config is two env vars (`TRACE_API_URL`, `TRACE_API_KEY`), overridable with
`--api-url` / `--api-key`. Uploads are private by default.

## Behavior

- **Stateless and idempotent.** The CLI keeps no manifest; the server's
  per-user content hash is the source of truth, so re-syncing a directory
  from any machine is always safe (`already synced`, exit 0).
- **One bad file never stops the run.** Per-file outcomes are printed as
  they land (`uploaded` / `already synced` / `failed: <reason>`); the exit
  code reflects failures seen.
- **Backpressure is normal.** Rate-limit responses are honored via
  `Retry-After` and retried, not errored.
- **Upload-only keys.** A `tmk_` key can upload traces and poll upload
  status — nothing else — and can be revoked from Settings at any time.
