# Codex Project Instructions

## Project Context

- This repository is for a two-day work trial project, not a full production deployment.
- Build for a person to run, inspect, and evaluate locally with minimal setup.
- Prefer pragmatic, defensible choices that demonstrate product and engineering judgment within the trial window.
- Avoid production-only work unless it directly supports the trial evaluation.

## Core Principles

- Prefer simple, elegant solutions and avoid over-engineering.
- Choose the smallest coherent design that solves the real problem.
- Avoid abstractions, services, frameworks, and configuration layers until they remove current complexity or clearly reduce risk.
- Confirm material product, UX, architecture, and data-model decisions with the user before implementing them.
- Keep comments minimal. Add comments only when they explain non-obvious intent, tradeoffs, or constraints that the code cannot express clearly.
- Keep documentation concise, direct, and easy to scan.

## Spec Authority

- `spec/stage-1/` is the normative spec. Implement what it says; if it and anything else disagree, the spec wins.
- If implementation needs a decision the spec does not answer, stop and resolve it with the user in the spec first. Do not improvise in code.
- `.archive/planning_docs/` is historical first-pass planning. Non-normative; do not consult it unless explicitly asked.

## Engineering Rules

### Stack

- Python (`services/api`, one codebase with API and worker entrypoints): uv for packaging, ruff for lint + format, pytest. Type hints everywhere; Pydantic models at every boundary (requests, responses, task payloads).
- TypeScript (`apps/web`): pnpm, strict `tsconfig`, Next.js App Router. API types derive from the FastAPI OpenAPI schema — never hand-write duplicates.
- UI follows `DESIGN.md` (Vercel-derived system + the Trace Marketplace Adaptation section, which wins on conflict). Use its tokens; do not invent colors, radii, or type scales.
- All tunables (size limits, rate limits, retry counts) are env vars with local-demo defaults, documented in a single `.env.example`.

### Code Organization

- Before writing new code, look for an existing function, component, model, or pattern to reuse or extend. Duplicated logic is a bug: one source of truth per concept (status enums, error shapes, formatting, access checks).
- One canonical home per concern. Backend: routes stay thin; domain logic lives in one module per domain (uploads, traces, ingestion, acquisitions), shared helpers in a common module. Frontend: shared UI primitives (badges, buttons, cards, status displays) live in a shared components directory and are reused everywhere — never re-styled inline per page; API client and types live in one place.
- File structure should be parseable at a glance: predictable names, consistent module layout across domains, no grab-bag `utils` dumping grounds, no deep nesting. If a file needs explanation to navigate, restructure it.
- Consistency beats local cleverness: same patterns for the same problems everywhere (route handler shape, error raising, component props, data fetching). New patterns must replace the old one repo-wide, not coexist with it.
- Extract shared code when the second usage appears, not speculatively before — this sharpens, not contradicts, the anti-abstraction principle above.

### Database

- Schema changes only via new files in `supabase/migrations/`; never edit an applied migration.
- Every access rule exists twice: enforced in the API query and mirrored as an RLS policy.

### Reliability Invariants

- Ingestion is a pure function of the raw stored payload: delete-and-rewrite per upload, in one transaction. Every importer change preserves this.
- Errors classify as permanent vs transient via typed exceptions; no blanket retries.
- Never log span `attributes`, `events`, or raw payload bodies.

### Testing

- Prioritize e2e/integration tests that exercise the real system (real Postgres, real Redis, real worker via Compose). The smoke script and each slice's "done when" are the bar.
- Mock-based unit tests are fine where they earn their keep (importer edge cases, error classification); do not spam them or mock things Compose can run for real.

### Process

- Implement in `spec/stage-1/5_build-order.md` slice order. A slice is done when its "done when" passes on a fresh `docker compose up`; do not start the next slice on top of a broken one.

## Product Direction

- Build Trace Marketplace: a website for contributing, discovering, downloading, and evaluating AI-agent trace data.
- Favor strong, defensible architecture decisions over placeholder implementation.
- Prioritize the data processing foundation: upload, validation, storage, search, and analysis.
- Marketplace features can be thin at first if the trace foundation is solid.

## Data Handling

- Treat agent traces as sensitive user data.
- Use synthetic fixtures for committed examples unless the user explicitly provides scrubbed samples.
- Preserve raw trace provenance while deriving searchable metadata, summaries, labels, and failure-mode signals.
- Avoid logging secrets, credentials, raw private trace bodies, or long user content by default.
- Do not store secrets, credentials, real private trace payloads, or customer data in `.codex/`.

## Delivery

- Keep the full system runnable from this single repo.
- Document any third-party or cloud service required to run the app.
- Ensure a contributor can onboard and upload trace data, and a consumer can discover and download allowed traces without manual operator work.
- Build visible trace inspection and search paths early so data quality problems are obvious.

## Agent Guidance Assets

- Keep durable project rules in this file because Codex auto-reads `AGENTS.md`.
- Use `.codex/skills/` only for specialized reusable workflows that are narrower than the whole project.
- Keep new agent guidance concise and reusable. Update `AGENTS.md` or `.codex/skills/` instead of scattering long prompts across notes.
