# Slice 0 Audit Fixes

Post-slice-0 code review pass, applied before Slice 1. Goal: fix correctness
issues found in audit and restructure for the surface area Slice 1 adds
(uploads, traces, acquisitions, real worker jobs).

## Correctness fixes

1. **Worker DB pool.** Tasks previously opened a raw asyncpg connection each
   run. The broker now opens/closes `db.pool()` via taskiq
   `WORKER_STARTUP`/`WORKER_SHUTDOWN` events (worker process only; the API
   keeps its own pool in the FastAPI lifespan). Tasks use `db.pool()` like
   routes do.
2. **Task failure visibility.** `GET /v1/dev/ping/{task_id}` checks
   `result.is_err` and returns `{ready, ok, result, error}` instead of
   reporting failed tasks as `ready` with a null result.
3. **Spec error envelope.** New `app/errors.py`: `ApiError(code, message,
   status, details)` plus handlers that force domain errors, framework
   `HTTPException`s, and validation errors into the
   `{"error": {code, message, details}}` shape from `3_api.md`. Auth now
   raises `ApiError("unauthorized", ...)`.
4. **CORS host variants.** `settings.web_origins` accepts both `localhost`
   and `127.0.0.1` spellings of `WEB_ORIGIN` (browsers treat them as distinct
   origins).
5. **Auth hardening.** `jwt.decode(..., options={"require": ["sub", "exp"]})`
   so a missing claim is a 401 not a 500; `PyJWKClient(cache_keys=True)`.
6. **`db.pool()` guard** raises `RuntimeError` instead of `assert` (asserts
   vanish under `python -O`).
7. **RLS `with check`** added to `profiles_update_own` (was implicit via
   `using`; now explicit). Reapplied with `supabase db reset` — wiped local
   test users.

## Backend restructure

`app/main.py` is assembly only (lifespan, middleware, error handlers, router
mounting). Version prefix lives in one place: `APIRouter(prefix="/v1")` at
mount time; router files are version-agnostic (no `routers/v1/` directory —
revisit only if a real v2 ever exists).

```
app/
  main.py        assembly
  config.py      settings (+ dev_routes flag, web_origins)
  auth.py        JWT dependency
  db.py          pool lifecycle
  errors.py      ApiError + envelope handlers
  schemas/       pydantic models per resource (health, profile, dev)
  routers/       APIRouter per resource (health, me, dev)
  queries/       plain async SQL functions per table (profiles)
  worker/        broker.py (config + worker lifecycle), tasks.py (ping)
```

`/v1/dev/*` mounts only when `settings.dev_routes` is true. Defaults to
false so a deployment that forgets the var gets the safe outcome; local
`.env` and compose opt in with `DEV_ROUTES=true`.
Worker entrypoint changed: `taskiq worker app.worker:broker` (compose +
README updated); `app/worker/__init__.py` imports tasks so they register.

## Frontend restructure

- `lib/env.ts` — single place that reads `NEXT_PUBLIC_*` and the
  `SUPABASE_INTERNAL_URL` Docker fallback (was duplicated across three files).
- `lib/api/types.ts` — API response types mirroring `app/schemas` (were
  defined ad hoc inside components); `lib/api/client.ts` — browser `apiFetch`
  (replaces `lib/api.ts`), throws typed `ApiError` parsed from the spec
  envelope, sets `Content-Type: application/json` when a body is present.
- `components/ui/` — `Button` (primary/secondary) and `Input` primitives;
  auth form, sign-out, and roundtrip components use them (Tailwind strings
  were triplicated).
- `app/auth/layout.tsx` — redirects signed-in users away from auth pages.

## Infra

- `docker-compose.yml`: Supabase host ports interpolated from `.env`
  (`SUPABASE_API_PORT`/`SUPABASE_DB_PORT`, new in `.env.example`) instead of
  hardcoded in three services; shared api/worker env via a
  `x-backend-env` YAML anchor.

## Outcome

Verified against the rebuilt Compose stack on 2026-06-10:

- `ruff check`/`format`, `eslint`, `next build` pass.
- `GET /v1/health` ok; unauthenticated `/v1/me` and unknown routes return the
  spec error envelope (`unauthorized` 401 / `not_found` 404).
- Fresh signup via Supabase REST → `/v1/me` returns the trigger-created
  profile; `POST /v1/dev/ping` → worker executes via the shared pool →
  `{ready: true, ok: true, result: {db_ok: true}}`.
- Web container serves; auth pages render.

Deferred from the audit: server-side `apiFetch` variant (built when RSC data
fetching lands in Slice 2's trace pages).
