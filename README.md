# Trace Marketplace

A marketplace for AI-agent trace data: contributors upload traces, consumers discover, inspect, acquire, and download them.

- Spec: `docs/spec/stage-1/` (normative)
- Build log: `docs/buildlog/stage-1/`
- Engineering rules: `AGENTS.md` · Design system: `DESIGN.md`

## Stack

Next.js (`apps/web`) · FastAPI + taskiq worker/scheduler (`services/api`) · Supabase (Postgres, auth, storage) · Redis (queue + rate limiting).

## Prerequisites

- Docker
- [Supabase CLI](https://supabase.com/docs/guides/cli)
- Node 22+ / pnpm and [uv](https://docs.astral.sh/uv/) (only for running outside Docker)

## Run

```sh
supabase start                 # local Postgres/auth/storage (ports 553xx)
cp .env.example .env
docker compose up --build      # web :3000, api :8000, redis, worker, scheduler
```

Open http://localhost:3000, sign up, and upload trace files (OTLP JSON) from the Uploads page; each is validated, preserved raw, parsed into traces and spans by the worker, and downloadable byte-identical. Traces lists what was parsed; each trace opens an inspector with the span tree and per-span attributes/events. From there, list a trace on the marketplace (with the ownership confirmation), where any signed-in user can browse, inspect, acquire it ($0), and download the raw payload from their Library.

Every ingested trace is also analyzed by the worker: deterministic signals (retry loops, error recovery, call counts) always run, and an LLM judge labels outcome / failure mode / task category when a provider key is configured (`OPENAI_API_KEY` etc. in `.env` — see `.env.example`). Keyless mode is honest, not broken: traces show `analysis skipped — judge not configured`, never a fake pending. The trace detail page carries the full Analysis section (labels, judge reasoning, signals, audit trail); list surfaces show the outcome badge.

```sh
make seed      # populate the marketplace: fixtures uploaded + listed by a demo contributor
make seed-dev  # same with real benchmark traces, uploaded through the trace-sync CLI
make smoke     # run the full demo loop end to end (upload → list → search → acquire → download)
```

No trace file handy? Use the committed synthetic fixtures in `fixtures/`, or pull real agent-benchmark sessions: `make dev-dataset` converts [Exgentic/agent-llm-traces](https://huggingface.co/datasets/Exgentic/agent-llm-traces) (CDLA-Permissive-2.0) into uploadable OTLP JSON under git-ignored `devdata/`. See `docs/demos/` for guided walkthroughs.

## Sync CLI

`trace-sync` (`apps/cli`) uploads local trace files through the same upload API, authenticated with an upload-only API key minted on **Settings** (the plaintext is shown exactly once, with a ready-to-run command):

```sh
cd apps/cli && uv sync
TRACE_API_KEY=tmk_… uv run trace-sync sync ../../devdata   # one-shot: upload everything new
TRACE_API_KEY=tmk_… uv run trace-sync watch ~/agent-logs   # stay alive, upload as files appear
```

The CLI is stateless — the server's per-user content hash dedupe makes re-syncing a directory a no-op (`already synced`). Per-file ingestion results print as they land (`uploaded (complete, 3 traces)` / `failed: <reason>`); failures that happen while nobody watches are visible on **/uploads**. Exit codes: 0 all synced/skipped, 1 some file failed, 2 couldn't run (bad key, unreachable API, no files).

Want real data of your own? Raw Codex / Claude Code / Cursor session logs upload directly — the server detects the schema and converts each session into per-turn traces. `make link-sessions` symlinks your local session directories into git-ignored `devdata/sessions-src/`; see `docs/demos/cli-sync.md` for the full walkthrough.

## Desktop app

`apps/desktop` is a lightweight Tauri tray app wrapping the same loop for people who'd rather not keep a terminal open: it watches folders (auto-detecting Codex/Claude Code/Cursor session dirs), uploads through the same API, fires native notifications for review requests, and resolves review items in-app. Users install the `.dmg` from the latest `desktop-v*` GitHub Release (pointed at production, no local stack needed); building from source requires a Rust toolchain. Install and release docs: `apps/desktop/README.md`.

## Develop (outside Docker)

```sh
supabase start
docker compose up redis -d
cd services/api && uv run uvicorn app.main:app --reload                  # API :8000
cd services/api && uv run taskiq worker app.worker:broker                # worker
cd services/api && uv run taskiq scheduler app.worker.scheduler:scheduler  # stuck-upload sweep
pnpm install && pnpm --filter web dev                                    # web :3000 (needs .env.local, see .env.example)
```

## Operations

- **Allowlist an email or domain**: `make allow EMAIL=<email>` or `make allow EMAIL=@<domain>` — sign-up and sign-in are restricted to the `allowed_emails` table (enforced by a DB trigger on signup and an API check per request). The seed/smoke tools allowlist their own demo users automatically.
- **Email confirmation**: production sign-up requires clicking a confirmation link before the first sign-in (Supabase dashboard: "Confirm email" + Mailgun SMTP, see `infra/README.md`). Locally it's off — sign-up signs you straight in. To demo the flow locally, set `enable_confirmations = true` in `supabase/config.toml` and watch Mailpit (`http://127.0.0.1:55324`); the web app handles both modes, and seed/smoke/test users are admin-created pre-confirmed either way.
- **Requeue dead-lettered work**: `make requeue UPLOAD=<upload_id>` re-ingests an upload (also works on `complete` uploads — re-ingest preserves trace ids); `make requeue TRACE=<trace_id>` re-runs a trace's analysis (see `dead_letters` table).
- **Tests**: `cd services/api && uv run pytest tests/unit` (importer golden + edge cases, no stack needed); `uv run pytest tests/integration` (stack must be running); `cd apps/cli && uv run pytest` (CLI, no stack needed).
- **Fault injection** (local only, requires `DEV_ROUTES=true`): send `X-Fault: transient:2 | exhaust | permanent` with `POST /v1/uploads` to demo retries and dead-lettering; prefix with `analyze:` (e.g. `X-Fault: analyze:permanent`) to fault the analysis job instead.

## Database

Schema changes are Supabase CLI migrations in `supabase/migrations/`. Apply locally with `supabase db reset`.
