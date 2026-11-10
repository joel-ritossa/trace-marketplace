# Evaluation Guide

Everything runs locally from this repo: three commands start the stack, one command populates it, one command runs the stage-1 demo loop end to end. A deployed instance also runs at [trace-mp.com](https://trace-mp.com) (sign-up is allowlist-gated there — ask to have your email added).

## Setup

Prerequisites: Docker and the [Supabase CLI](https://supabase.com/docs/guides/cli). Node 22+/pnpm and uv are only needed for running services outside Docker or using the CLI tools.

```sh
supabase start                 # local Postgres/auth/storage (ports 553xx)
cp .env.example .env
docker compose up --build      # web :3000, api :8000, redis, worker, scheduler
```

Sign-up is restricted to an allowlist (a DB trigger on the `allowed_emails` table), so allowlist yourself before creating an account:

```sh
make allow EMAIL=you@example.com
```

**Keyless vs with-key.** The stack runs fully without an LLM key: deterministic signals still run, and LLM-derived fields stay null with a recorded skip reason — the UI says `analysis skipped — judge not configured`, never a fake pending ([04](04_analysis-pipeline.md)). To see the judge and embeddings live, set `OPENAI_API_KEY` in `.env` (the compose worker reads `.env`; host-run tools like the offline validation runner read `.env.local`). The judge model and all tunables are env vars with defaults documented in `.env.example`.

## Quick Demo Loop

The shortest path to a populated marketplace:

```sh
make seed       # synthetic fixtures uploaded + listed by a demo contributor
make smoke      # full stage-1 loop: upload → ingest → list → search → acquire → byte-identical download
```

Variants: `make seed-dev` seeds with real benchmark traces uploaded through the sync CLI; `make seed-demo EMAIL=you@example.com` builds full live state for your own account — listed and labeled traces, open review items, unread notifications, subscriptions with matches (`WIPE=1` re-seeds clean).

## Click-Through Script

The stage-2 demo script that defined "done" (`docs/spec/stage-2/0_README.md`). Assumes the stack is up with an LLM key; step 5 has a keyless lever.

1. **Settings** — mint an API key: the plaintext is shown exactly once, with a ready-to-run CLI command.
2. **Terminal** — sync a directory (`make dev-dataset` pulls real benchmark traces into `devdata/`, or use `fixtures/`):

```sh
cd apps/cli && uv sync
TRACE_API_KEY=tmk_… uv run trace-sync sync ../../devdata
```

   Each file prints its terminal status as it lands. Re-running syncs nothing (server-side sha256 dedupe: `already synced`). `trace-sync watch` stays alive and uploads files as they appear.
3. **Unattended failure** — upload a malformed file (any non-OTLP JSON): the failure shows on **/uploads** with the reason verbatim, plus an `upload_failed` notification.
4. **Inspect analysis** — open a synced trace: the Analysis section shows the session verdict (goal, outcome, summary, categories, failure modes) and a verdict per turn, each failure mode citing the spans that show it, plus deterministic signals. Turns are judged as the session grows; the last turn and the session verdict arrive once it has been idle (or via Analyze now).
5. **Relabel an uncertain turn** — a session with an uncertain turn lands in **/review** (notifications digest per upload). The machine's take is shown as context, never pre-selected; relabelling makes the turn `human`, and it is never re-judged. Keyless stacks can drive this with a canned-verdict fault — [docs/demos/hil-loop.md](../docs/demos/hil-loop.md).
6. **Bulk list** — multi-select on **My Traces** → "List N traces" → one batched consent confirmation.
7. **Filter + subscribe** (as a second, consumer account — `make allow` another email) — filter the marketplace on label predicates (`outcome = failure`, `failure_mode = invalid_invocation`, `llm_call_count ≥ 50`) → save as a subscription with backfill preview.
8. **Match → bulk acquire** — sync and list a new matching trace as the contributor: the consumer gets a `subscription_match` notification → feed → multi-select → bulk acquire with an itemized result.
9. **Download** — **/library**: select acquired traces → "Download N" → zip of scrubbed payloads + `labels.jsonl` (owners downloading their own traces get raw bytes).

## Guided Demos

Each demo in `docs/demos/` is a runnable walkthrough — steps, what was solved, why it's interesting, with code pointers:

| Demo | Proves |
|---|---|
| [large-trace-handling.md](../docs/demos/large-trace-handling.md) | A 5,000-span trace ingests and inspects smoothly |
| [cli-sync.md](../docs/demos/cli-sync.md) | The machine door on your own Codex/Claude Code/Cursor sessions: key auth, stateless sync, dedupe, honest unattended failures |
| [hil-loop.md](../docs/demos/hil-loop.md) | Uncertain turns open a review item with the agent's reasons; human relabels stick — runs keyless via a canned-verdict fault |
| [subscriptions.md](../docs/demos/subscriptions.md) | Saved searches that watch the marketplace: event-driven matching, notify-once digests, bulk acquire → labeled zip |

## Running the Validation

*Superseded 2026-11-10.* The agreement scripts (`app.cli.analyze agreement` / `metrics-agreement`), the HaluBench converter and their demos were removed with the voted judge and the quality metrics; the headline numbers in [04](04_analysis-pipeline.md) were measured on that judge and are recorded in `docs/buildlog/stage-2/B4/` and `B5/`. The per-turn agent has not been re-measured against expert labels. The AgentRewardBench and AgentRx converters remain (`python3 tools/arb_to_otlp.py`, `python3 tools/agentrx_to_otlp.py`, outputs under git-ignored `devdata/`), and the offline runner judges any OTLP file or fixture turn by turn and dumps JSON (needs `OPENAI_API_KEY` in `.env.local`):

```sh
cd services/api
uv run python -m app.cli.analyze run ../fixtures/agent-session.json
```

## Tests

```sh
cd services/api && uv run pytest tests/unit          # 283 tests, no stack needed
cd services/api && uv run pytest tests/integration   # 85 tests, stack must be running
cd apps/cli && uv run pytest                          # CLI, no stack needed
```

## Where to Look in the Code

| Where | What |
|---|---|
| `services/api/app/routers/` + `queries/` | HTTP surface: one thin router + one queries module per domain |
| `services/api/app/importers/` | OTLP validation/parsing + Codex/Claude Code/Cursor session converters |
| `services/api/app/analysis/` | Signals, the agent judge (`agent/`), the OpenAI client wrapper, embeddings, rendering (offline runner only) |
| `services/api/app/worker/` | taskiq tasks (ingest, analyze, subscription matching) + scheduler |
| `services/api/app/cli/` | Offline analysis runner, dead-letter requeue |
| `apps/web/src/` | Next.js app; API client and types in `lib/api/` |
| `apps/cli/` | `trace-sync` CLI |
| `apps/desktop/` | Tauri tray app |
| `supabase/migrations/` | Schema + RLS, 17 ordered migrations |
| `tools/` | Seed, smoke, benchmark converters, operator scripts |
| `infra/` | Terraform for the production AWS stack |
| `docs/spec/` | The normative spec (stage 1, stage 2) |
| `docs/buildlog/` | Per-slice record: plan, drift, verification, audits |
| `docs/explainers/` | Delivery guarantee, how a session gets judged, redaction boundary |
| `docs/demos/` | The guided demos above |
