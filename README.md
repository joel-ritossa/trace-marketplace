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

Open http://localhost:3000, sign up, and upload a trace file (OTLP JSON) from the Upload page; it is validated, preserved raw, parsed into traces and spans by the worker, and downloadable byte-identical. My Traces lists what was parsed; each trace opens an inspector with the span tree and per-span attributes/events. From there, list a trace on the Marketplace (with the ownership confirmation), where any signed-in user can search, inspect, acquire it ($0), and download the raw payload from their Library.

```sh
make seed     # populate the marketplace: fixtures uploaded + listed by a demo contributor
make smoke    # run the full demo loop end to end (upload → list → search → acquire → download)
```

No trace file handy? Use the committed synthetic fixtures in `fixtures/`, or pull real agent-benchmark sessions: `make dev-dataset` converts [Exgentic/agent-llm-traces](https://huggingface.co/datasets/Exgentic/agent-llm-traces) (CDLA-Permissive-2.0) into uploadable OTLP JSON under git-ignored `devdata/`. See `docs/demos/` for guided walkthroughs.

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

- **Requeue a dead-lettered upload**: `make requeue UPLOAD=<upload_id>` — resets the upload and enqueues a fresh ingest job (see `dead_letters` table).
- **Tests**: `cd services/api && uv run pytest tests/unit` (importer golden + edge cases, no stack needed); `uv run pytest tests/integration` (stack must be running).
- **Fault injection** (local only, requires `DEV_ROUTES=true`): send `X-Fault: transient:2 | exhaust | permanent` with `POST /v1/uploads` to demo retries and dead-lettering.

## Database

Schema changes are Supabase CLI migrations in `supabase/migrations/`. Apply locally with `supabase db reset`.
