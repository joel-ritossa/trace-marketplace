# Observability pass — structured logging with correlation ids

## Goal

Make a trace analysis observable end to end: one correlation id follows an
upload from `POST /v1/uploads` through ingest → analyze → match, and
`analyze_trace` logs each pipeline stage with its duration. Output stays
local (JSON lines on stdout + an in-process ring buffer); the logger is the
seam for shipping to CloudWatch et al. later without touching call sites.

## Design

- `app/obs.py` is the one logging module: `correlation_id_var` contextvar,
  `bind()` for context fields (`upload_id`, `trace_id`, `task`), a JSON-lines
  formatter on stdout, a `MemoryLogHandler` ring buffer
  (`LOG_BUFFER_RECORDS`), idempotent `configure_logging()` (called from
  `app/main.py` and `app/worker/broker.py`, so API, worker, and scheduler all
  get it), and a `stage()` context manager that logs stage durations.
- File sink for easy local reading: `LOG_FILE` adds a JSON-lines
  `FileHandler`; docker-compose mounts `./logs` into api/worker/scheduler and
  points each at its own file (`logs/api.log`, `logs/worker.log`,
  `logs/scheduler.log`), so logs are greppable on the host without docker.
  `logs/` is gitignored.
- Stdlib `logging` only — no structlog dependency. CloudWatch later = ship
  stdout (ECS awslogs already does) or add a handler in `configure_logging()`.
- HTTP side: `app/middleware/correlation.py` honors a sanitized
  `X-Correlation-ID` or mints one, and echoes it on the response. Sits inside
  CORS, outside rate limiting, so 429s are correlated.
- Worker side: `app/worker/correlation.py` taskiq middleware. `pre_send`
  stamps the current correlation id onto the message as a label (setdefault —
  the retry re-kick copies labels, so the id survives retries); `pre_execute`
  restores it and binds the task name. Sweep/CLI kicks mint fresh ids.
- `analyze_trace` logs: started (attempt, span count), per-stage durations
  (signals, judge, metrics, listing, rewrite, embedding), judge verdict
  labels, LLM-gate skips, review routing, and a completion line with total
  duration. Labels and counts only — never prompts, span attributes, or
  payload bodies (AGENTS.md no-log rules hold).
- `ingest_upload` / `match_trace` / the upload route bind their domain ids so
  existing log lines pick up the structured fields for free.

## Verification

- `tests/unit/test_obs.py`: formatter includes correlation id + bound context
  + extras; binds don't leak across contexts; ring buffer caps and filters by
  correlation id; taskiq middleware stamps/preserves/restores the label; HTTP
  middleware mints, echoes, and rejects unsafe supplied ids.
- Smoke: importing the app and logging through `obs.stage` emits JSON lines
  carrying `correlation_id`, `trace_id`, `task`, `stage`, `duration_ms`.
- Full unit suite passes except a pre-existing, unrelated failure in the
  in-flight `test_filter_query.py` (subscription empty-query validation).

## Drift

None.
