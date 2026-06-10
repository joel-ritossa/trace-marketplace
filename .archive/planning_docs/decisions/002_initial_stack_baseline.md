# Decision: Initial Stack Baseline

## Context

Trace Marketplace needs enough project shape to initialize the repo without committing to premature implementation detail. The first version should remain locally runnable and prioritize the trace data foundation over production-grade platform work.

## Decision

The initial baseline stack is:

- Frontend: TypeScript, Next.js, and pnpm.
- Backend: Python and FastAPI.
- API contract: FastAPI OpenAPI is the source of truth between backend and frontend.
- Database and auth: Supabase, with RLS enabled from the beginning.
- Schema workflow: Supabase CLI migrations committed in the repo.
- Validation: Pydantic models for backend-side trace and request validation.
- Local deployment: Docker Compose for the local app stack.

The frontend owns the browser-facing Supabase auth flow. The Python backend verifies Supabase-issued JWTs for protected API requests.

## Rationale

This stack gives the project a clear local development path while keeping the implementation surface small. FastAPI and OpenAPI provide a simple backend contract, Next.js is a strong default for the web UI, and Supabase covers the database and authentication needs without adding separate services during the trial window.

Starting with RLS avoids a later security retrofit around sensitive trace data.

## Consequences

- Repo initialization can proceed without deciding every data-processing detail upfront.
- Backend and frontend can evolve independently around the OpenAPI contract.
- Auth and data access rules must be designed with Supabase RLS in mind from the first schema migration.
- Trace storage, trace input formats, worker architecture, search strategy, and Python tooling are intentionally deferred until their requirements are clearer.
