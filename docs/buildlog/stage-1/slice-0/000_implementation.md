# Slice 0 — Walking Skeleton

Spec: `docs/spec/stage-1/5_build-order.md` (Slice 0). Stack glue, zero product logic.

**Done when:** a fresh clone can sign up, sign in, and see an authenticated page that round-trips through FastAPI; a test task enqueued by the API is executed by the worker.

## Plan

### Layout (per decision 003)

```
apps/web/          Next.js (App Router, TS strict, pnpm workspace member)
services/api/      Python: FastAPI app + taskiq worker, one uv project
supabase/          Supabase CLI project + migrations
docs/buildlog/          Per-slice plan/drift/outcome records
docker-compose.yml redis, api, worker, web
```

### Supabase

- `supabase init`; local stack via `supabase start` (runs outside Compose — it manages its own containers).
- Migration `0001_profiles.sql`: `profiles` table (`id` FK to `auth.users`, `display_name`, `created_at`), RLS enabled (select/update own row), `on_auth_user_created` trigger inserting a profile row on signup.

### API (`services/api`)

- uv project, Python 3.12. Deps: `fastapi`, `uvicorn`, `pydantic-settings`, `pyjwt`, `asyncpg`, `taskiq`, `taskiq-redis`. Dev: `ruff`, `pytest`.
- Auth: verify Supabase HS256 JWT (`SUPABASE_JWT_SECRET`) in a FastAPI dependency; expose claims as `AuthUser(id, email)`.
- Endpoints: `GET /v1/health` (unauthenticated); `GET /v1/me` (authenticated round-trip — reads the caller's `profiles` row via asyncpg).
- Taskiq: Redis broker + result backend in `app/tasks.py`; `ping` task does `SELECT 1` against Postgres and returns a payload. `POST /v1/dev/ping` enqueues and returns the task id; `GET /v1/dev/ping/{task_id}` polls the result. Dev-only surface, removed when real jobs exist in Slice 1.
- Worker: `taskiq worker app.tasks:broker` as a separate entrypoint, same codebase.

### Web (`apps/web`)

- `create-next-app` (TS, App Router, Tailwind v4 for DESIGN.md token wiring later; minimal styling this slice).
- `@supabase/supabase-js` + `@supabase/ssr`: sign up, sign in, sign out; session-gated `(app)` layout group redirecting to `/auth/sign-in` when unauthenticated.
- Authenticated home page calls `GET /v1/me` with the session access token (via a small `lib/api.ts` client) and renders the result — the round-trip proof.

### Compose

- Services: `redis` (redis:7-alpine), `api` (uvicorn), `worker` (taskiq), `web` (next start). All env via `.env` (template committed as `.env.example`).
- Supabase is reached from containers at `host.docker.internal` (its stack runs on the host via the CLI); web reaches the API on a published port.

### Verification

1. `supabase start`, `supabase db reset` (applies migration).
2. `docker compose up --build`.
3. Browser: sign up → land on gated page → `/v1/me` renders profile id/email.
4. `POST /v1/dev/ping` → poll result → worker log shows execution, result contains the DB check.

## Drift

1. **Supabase ports moved to 553xx** (`config.toml`). Another local Supabase project (`duckie-app`) holds the default 543xx ports. API/web/compose reference 55321 (API) and 55322 (DB).
2. **JWT verification is JWKS/ES256, not HS256.** Supabase CLI ≥2.75 signs access tokens with an asymmetric key (ES256, `kid` in header) published at `/auth/v1/.well-known/jwks.json`. The planned shared-secret HS256 verification was replaced with `jwt.PyJWKClient` + `pyjwt[crypto]`; `SUPABASE_JWT_SECRET` config became `SUPABASE_URL`.
3. **Redis published on host 56379** (in-network still `redis:6379`) — host port 6379 was taken by another local Redis.
4. **Web host port is `WEB_PORT`** (default 3000; 53000 in this machine's `.env`) — 3000 was taken by another dev server.
5. **`middleware.ts` → `proxy.ts`.** Next 16 deprecates the middleware file convention; same session-refresh logic, renamed export.
6. **Pinned auth cookie name (`tm-auth`).** Real bug found in verification: `@supabase/ssr` derives the cookie name from the Supabase URL host, so the browser client (`127.0.0.1`) and the in-container server client (`host.docker.internal`) disagreed and the server never saw the session. Fixed with a shared `cookieOptions.name` in `lib/supabase/cookie.ts`, used by the browser client, server client, and proxy.
7. **Nested `pnpm-workspace.yaml` removed.** `create-next-app` generated one inside `apps/web`; its `ignoredBuiltDependencies` moved to the root workspace file.
8. **Settings load from env files, no localhost fallbacks.** `app/config.py` reads `.env` then `.env.local` (found by walking up from cwd; real env vars beat both) and the infra URLs (`DATABASE_URL`, `REDIS_URL`, `SUPABASE_URL`) are required fields — a misconfigured cloud deployment fails at startup instead of silently targeting a local stack. Local values live in `.env` (from `.env.example`); `.env.local` is for gitignored machine-local secrets.

## Outcome

> Verified as written below on 2026-06-10. Two follow-up passes landed after
> this and changed some of the surfaces described here — see
> [Follow-ups](#follow-ups).

Done-when verified in-browser against the Compose stack on 2026-06-10:

- Fresh sign-up (`fresh-signup@example.com`) → lands on the gated page; signup trigger created the profile (`display_name: fresh-signup`).
- Sign-in with an existing account works; signed-out users are redirected to `/auth/sign-in`.
- Gated page renders `GET /v1/me` through FastAPI (JWKS-verified JWT, profile read via asyncpg).
- "Ping worker" → task enqueued by API, executed by worker, `db_ok=true` returned through the Redis result backend (API → Redis → worker → Postgres).
- `ruff check`, `eslint`, and `next build` all pass; stack runs via `supabase start` + `docker compose up --build`.

## Follow-ups

Slice complete, including two post-slice passes (each re-verified end to end):

1. **[001_audit.md](001_audit.md)** — code review fixes and restructure: spec
   error envelope, worker DB pool, routers/schemas/queries/worker layout, typed
   FE API client, `DEV_ROUTES` flag (off by default), compose env interpolation.
2. **[002_design-system.md](002_design-system.md)** — shadcn/ui themed via
   DESIGN.md tokens, plus the UI polish pass. The ping demo *page* described above was
   removed (the `/v1/dev/*` endpoints and worker task remain, flag-gated);
   the home page is now the Traces empty state that Slice 1 fills in.

**Status: done.** Final state — sign-up/sign-in/sign-out, gated app shell,
`GET /v1/me` round-trip, worker pipeline provable via `/v1/dev/ping` (curl),
design system wired. Next: Slice 1 — Raw Upload Loop.
