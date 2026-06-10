# Decision: Initial Repo Layout

## Context

The project needs a minimal monorepo structure before app code is introduced. The layout should reflect the accepted stack without forcing decisions about trace storage, workers, search, or detailed package tooling.

## Decision

Use these top-level boundaries:

- `apps/`: user-facing applications.
- `apps/web/`: Next.js TypeScript frontend.
- `services/`: backend services.
- `services/api/`: Python FastAPI backend.
- `packages/`: shared TypeScript workspace packages only when justified.
- `supabase/`: Supabase CLI project files and committed migrations.
- `docs/`: product, architecture, research, and decision docs.

Use pnpm workspaces for `apps/*` and `packages/*`. Python service tooling remains service-local and is deferred until the first backend implementation pass.

## Rationale

This layout keeps frontend, backend, database, and shared-package concerns separate while staying small enough for local evaluation. It leaves room for a worker service later without creating a placeholder implementation before the ingestion flow is settled.

## Consequences

- The repo has clear ownership boundaries before code generation or scaffolding begins.
- Shared packages are opt-in rather than a default abstraction.
- Supabase migrations have a committed home from the beginning.
- Docker Compose, worker structure, trace storage, search, and generated API clients can be added when their concrete requirements are known.
