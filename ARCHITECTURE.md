# Architecture Diagram

System-level view of Trace Marketplace. The full narrative lives in [report/02_architecture.md](report/02_architecture.md); this file is just the picture.

## System Diagram

```mermaid
flowchart LR
  subgraph clients["Clients"]
    direction TB
    web["Web app<br/>(Next.js)"]
    desktop["Desktop tray app<br/>(Tauri)"]
    cli["Sync CLI"]
  end

  api["API<br/>FastAPI /v1/*"]

  subgraph pipeline["Async pipeline"]
    direction TB
    sched["Scheduler<br/>(60s sweep)"]
    redis[("Redis queue")]
    worker["Worker (taskiq)<br/>ingest → analyze → match"]
    sched --> redis --> worker
  end

  llm["LLM provider<br/>(litellm)"]

  subgraph supabase["Supabase"]
    direction TB
    auth["Auth + Realtime"]
    pg[("Postgres<br/>+ pgvector")]
    store[("Storage")]
  end

  web -->|JWT| api
  desktop -->|JWT| api
  cli -->|API key| api

  api -->|enqueue| redis
  worker -->|judge, metrics,<br/>embeddings| llm

  api --> supabase
  worker --> supabase
  web -.->|sign-in, realtime| auth
```

- **Clients**: web app (`apps/web`), sync CLI (`apps/cli`), desktop tray app (`apps/desktop`) — all speak the same upload API. The CLI authenticates with an upload-only `tmk_` API key; web and desktop hold Supabase JWTs (the desktop app also uses sign-in + realtime, omitted above for clarity).
- **Backend** (`services/api`): one Python image, three entrypoints — API, worker, scheduler. The API and worker both read/write Postgres and Storage.

## Upload Data Flow

```mermaid
flowchart LR
  up["POST /v1/uploads"]
  raw["Raw payload stored<br/>verbatim + job enqueued"]
  ing["Ingest<br/>parse + redact<br/>→ traces/spans"]
  an["Analyze<br/>signals, LLM judge,<br/>metrics, embeddings"]
  rev["Review queue<br/>(uncertain verdicts)"]
  match["Match subscriptions<br/>→ notifications"]

  up --> raw --> ing --> an
  an --> rev
  an --> match
```

## Notes

- **Postgres is the source of truth**; Redis holds only in-flight queue messages and rate-limit counters. At-least-once delivery comes from the 60s scheduler sweep, not the broker.
- **Failures are typed** permanent vs transient: transient retries with backoff (5 attempts) then dead-letters to Postgres; permanent fails immediately with a readable reason.
- **Redaction is structural**: the `spans` tables hold the scrubbed form; raw content exists only in the owner-only `span_raw` table and the immutable raw object.
- **Local**: four containers under Docker Compose against a host-run Supabase CLI stack. **Production** ([trace-mp.com](https://trace-mp.com)): the same four containers on ECS Fargate behind ALB + WAF (path routing: `/v1/*` → api, rest → web), ElastiCache Redis, Supabase Cloud — Terraform in `infra/`.
