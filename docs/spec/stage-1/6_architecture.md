# Architecture

Runtime topology, the ingestion job pipeline, and the reliability/concurrency rules. The stance: invest in reliability where async work actually happens (ingestion), keep everything else synchronous, and prefer designs whose state is inspectable in Postgres.

## Runtime Topology

Docker Compose services:

| Service | Role |
|---|---|
| `web` | Next.js frontend. Talks only to `api`. |
| `api` | FastAPI. Synchronous request/response; enqueues ingestion jobs; never parses traces in-request. |
| `worker` | taskiq worker, same Python codebase as `api`, separate entrypoint. Consumes jobs from Redis. Scale with `docker compose up --scale worker=N`. |
| `scheduler` | taskiq scheduler, same image as `worker`, separate entrypoint. Fires scheduled tasks (the stuck-upload sweep; future periodic work). Single instance; scheduled tasks must be idempotent so an accidental double-fire is harmless. |
| `redis` | Job broker (taskiq) and rate-limit state. Holds no state of record. |
| Supabase stack | Postgres, auth, storage (local Supabase CLI stack). |

Broker choice: a real broker rather than a Postgres-native queue, keeping queue churn off the primary database and making worker distribution a first-class concern from day one. Redis over RabbitMQ because one container serves both queueing and rate limiting, and durable job state deliberately lives in Postgres (below), so stronger broker durability guarantees buy little here.

## Ingestion Pipeline

One task, `ingest_upload(upload_id)`, enqueued by `POST /v1/uploads` after the raw payload is stored and the `uploads` row is created. The committed row is the acceptance of record: a failed enqueue (broker blip) logs and still returns 201 — the stuck-upload sweep re-enqueues it. *(Amended during the slice-2 reliability sweep.)*

```
API: validate → store raw → uploads row (received) → enqueue
Worker: claim job → status processing → parse → normalize → batch-insert traces+spans (one tx) → status complete
```

- `uploads.status` is the state of record for ingestion progress; Redis holds only in-flight messages. The upload page polls `GET /v1/uploads/{id}`, never Redis.
- One job per upload. Span inserts are batched (`executemany`/COPY), never row-by-row — this is the main latency lever for large traces.
- Worker concurrency: 4 jobs per worker process (asyncio). Back-pressure is queue depth; the concurrency cap bounds Postgres load.

## Error Classification

Classification matters more than retry count:

| Class | Examples | Behavior |
|---|---|---|
| Permanent | JSON invalid, unrecognized envelope, all spans malformed, checksum mismatch, storage 4xx (missing object — the fetch is immutable, a retry can't succeed) | No retry. Upload → `failed` with readable `error_message` immediately. |
| Transient | Storage 5xx/429/network error, DB timeout, Redis blip, worker crash mid-job | Retry with backoff. |

Importer code raises typed exceptions (`PermanentIngestError` / anything else) so the task wrapper can route them without guessing.

## Retries And Dead-Lettering

- Transient failures retry up to **5 attempts**, exponential backoff with jitter (~2s → 60s cap), implemented via taskiq retry middleware. `uploads.attempts` increments each claim and is the counter the cap is enforced on — durable, so a sweep re-enqueue can't reset the budget, and `dead_letters.attempts` records the true count. *(Amended during the slice-2 reliability sweep; previously the count rode on a message label.)*
- On exhaustion: write a `dead_letters` row (see [2_data-model.md](2_data-model.md)) with full error context, set the upload to `failed`. The DLQ is Postgres, so it is durable and queryable; Redis is never the DLQ.
- Requeue: `make requeue UPLOAD=<id>` resets the upload and enqueues a fresh job. No admin UI in Stage 1.

## Idempotency Invariant

Ingestion is a pure function of the raw stored payload. A (re)run of `ingest_upload`:

1. Deletes any existing traces/spans for that `upload_id`.
2. Re-inserts from scratch.
3. Both inside one transaction, with the status flip to `complete`.

This makes retries, requeues, and duplicate deliveries safe by construction. It is the invariant every importer change must preserve.

`complete` is terminal for ingestion: the claim (`mark_processing`) and the failure write (`mark_failed`) are guarded in SQL (`where status <> 'complete'`), so a stale duplicate delivery can neither redo completed work nor overwrite `complete` with `failed` after a concurrent run succeeded. Only an explicit operator requeue or upload deletion moves a terminal upload. *(Amended during the slice-2 reliability sweep.)*

## Lost-Job Recovery

If Redis drops a message (restart, eviction), the job is gone but the upload row is not. A periodic sweep (taskiq scheduled task fired by the `scheduler` service, every 60s) re-enqueues uploads stuck in `received` or `processing` for more than 10 minutes since the last claim (`uploads.last_attempt_at`, falling back to `created_at`), so a legitimately long-running attempt is re-enqueued at most once per timeout window. Combined with idempotency, at-least-once delivery is sufficient — no exactly-once machinery.

## Rate Limiting

Token buckets in Redis, enforced as FastAPI middleware, so limits hold across multiple API instances without code change:

| Bucket | Limit |
|---|---|
| Global (all traffic) | 50 req/s, burst 100 |
| Per user | 10 req/s, burst 20 |
| Per user, `POST /v1/uploads` | 10/min |

Exceeding any bucket returns `429 rate_limited` with `Retry-After`. Limits are env-configurable; defaults above are tuned for a local demo, not production traffic.

The limiter fails open: rate-limit state is not state of record, so Redis loss degrades to "no limiting" (with a warning log) rather than 500s on Postgres-only reads. *(Amended during the slice-2 reliability sweep.)*

## Scaling Knobs (Designed For, Not Built)

- **More workers**: `--scale worker=N` already distributes correctly; nothing else needed.
- **Per-trace fan-out**: if single uploads carry many traces, split `ingest_upload` into a parse job that fans out per-trace normalize jobs. The idempotency invariant moves to per-trace scope. Build only if the dev dataset shows uploads big enough to care.
- **Multiple API instances**: rate limiting and enqueueing are already Redis-backed; only Compose wiring changes.

## Deliberate Non-Goals

No RabbitMQ/Kafka, no Celery, no circuit breakers, no autoscaling, no exactly-once delivery, no priority queues, no distributed tracing of our own infrastructure. Each would add operational surface without a Stage 1 problem to solve.
