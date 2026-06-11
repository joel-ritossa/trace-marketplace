# CLI Sync — the Machine Door

Trace data flows in passively from a terminal: an upload-only API key, a
stateless sync CLI, server-side dedupe, and an `/uploads` surface that
updates live and keeps unattended failures honest. Best demoed on your own
real agent sessions.

## Steps

With the stack running (`supabase start` + `docker compose up`) and a user
signed in at http://localhost:3000 (or your `WEB_PORT`):

```sh
# 1. Convert your own local coding-agent sessions (Codex, Claude Code,
#    Cursor) from the past 24 h into OTLP files under git-ignored
#    devdata/agent-sessions/. Sources are read through symlinks the script
#    keeps in git-ignored devdata/sessions-src/ → ~/.codex, ~/.claude,
#    ~/.cursor, so re-running always converts your latest sessions.
tools/my_sessions.sh                            # = make my-sessions; --hours 0 for all history

# 2. Mint a key: Settings → API keys → Create key. The plaintext is shown
#    exactly once, with a copyable CLI command. (make seed-dev also prints
#    a reusable key for the demo contributor account.)

# 3. Open /uploads in the browser, then sync from the terminal:
cd apps/cli
TRACE_API_KEY=tmk_…  uv run trace-sync sync ../../devdata/agent-sessions
```

4. Watch both sides at once: the terminal prints one line per file
   (`uploaded (complete, 1 trace)`), and `/uploads` rows appear and flip
   `processing → complete` **without a refresh** (Supabase Realtime as an
   invalidation signal). Your sessions land on My Traces with scannable
   names ("cursor: run an implementation plan for A1"), models, token
   counts, and tool spans.

5. Re-run the same sync — every line prints `already synced`, exit 0. The
   CLI keeps no state; the server's per-user sha256 dedupe is the source of
   truth, so re-syncing a directory is always safe.

6. Leave a watcher running and drop files into the directory:

```sh
TRACE_API_KEY=tmk_…  uv run trace-sync watch /tmp/drop
cp ../../fixtures/agent-session.json /tmp/drop/        # → uploads within ~2 s
echo '{"resourceSpans": []}' > /tmp/drop/bad.json       # → failed: Payload contains no valid spans
```

   The bad file fails *while nobody is watching the web UI* — and stays
   visible on `/uploads` with the ingestion error verbatim and a `cli`
   source badge. Ctrl-C prints a `synced N · skipped N · failed N` summary;
   the exit code reflects failures seen.

7. Revoke the key on Settings — the next CLI run dies immediately with
   `API key rejected` (exit 2).

Converted personal sessions contain real prompt/tool content: they stay
git-ignored on disk and **private** in the app (CLI uploads are private by
default; nothing here lists them). The LLM-analysis opt-out for private
traces lives on the same Settings page.

## What was solved

Stage 1 only had a browser door: one file at a time, hand-picked, with a
human watching the result. Real trace data accumulates in directories as a
byproduct of running agents — getting it in needs passive, repeatable bulk
capture, auth that isn't a browser session, and a place where ingestion
failures surface when no one is looking at a progress bar.

## Why it's interesting

- **Stateless capture, server-side truth.** The CLI keeps no manifest or
  config (`apps/cli/src/trace_sync/`); dedupe is the server's per-user
  content hash, so syncs are idempotent from any machine, and `watch` is
  just `sync` without the exit condition (a 2 s size/mtime stability scan,
  no fs-events dependency).
- **One auth header, two principals.** `Authorization: Bearer` accepts a
  Supabase JWT or a `tmk_` key (`services/api/app/auth.py`) — the only
  stage-1 code change. Keys are sha256-stored, upload-scoped (exactly two
  endpoints), soft-revoked, and `uploads.source = 'cli'` is inferred from
  the auth type — clients never claim it.
- **Backpressure is normal operation.** A big first sync hits the tight
  per-user upload bucket; the CLI honors `Retry-After` and keeps going
  instead of erroring (`client.py`). One bad file never stops the run.
- **Failures stay honest.** A failed CLI upload never becomes a trace and
  would otherwise be invisible; `/uploads` shows status + error verbatim,
  updating live via an invalidation-only Realtime hook
  (`apps/web/src/lib/realtime.ts`) — events trigger an API refetch, the
  socket never becomes a second data path.
- **The converter dogfoods the format pipeline.** `make my-sessions`
  (`tools/agent_sessions_to_otlp.py`) emits plain GenAI-semconv OTLP —
  the same fallback chains the importer and renderer use on foreign data
  (kinds, models, tokens, tool calls, error status) — so your own sessions
  exercise ingestion, inspection, and (stage 2) analysis end to end.
