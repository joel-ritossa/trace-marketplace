---
name: restart-stack
description: Restart the local Docker Compose services for trace-marketplace — all of them, just the backend (api, worker, scheduler), or just the web app — with or without a rebuild. Use when asked to restart, rebuild, or bounce the docker services, the stack, the backend, or the web container.
---

# Restart Docker Services

The local stack is Docker Compose (`docker-compose.yml` at the repo root). Service groups:

- **backend**: `api worker scheduler` (all built from `services/api`; `redis` rarely needs restarting)
- **web**: `web` (Next.js, built from `apps/web/Dockerfile`)

## Which services?

If the user didn't specify, ask whether to restart **everything**, **backend only**, or **web only**.

## Restart vs rebuild

- Code changed since the last build → rebuild (`up -d --build`). Code is baked into the images, so a plain restart won't pick up changes.
- Just bouncing the process (config/env change in `.env`, stuck service) → `up -d` re-creates with fresh env; `restart` does not re-read `.env`.

## Commands

Run from the repo root.

```bash
# Backend only
docker compose up -d --build api worker scheduler

# Web only
docker compose up -d --build web

# Everything
docker compose up -d --build

# Bounce without rebuild (picks up .env changes)
docker compose up -d api worker scheduler
```

## Verify

```bash
docker compose ps
curl -s http://localhost:8000/v1/health
```

All services should be `running` (api `healthy`). Web serves at `http://localhost:3000` (or `WEB_PORT` from `.env`).
