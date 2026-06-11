---
name: seed-demo
description: Seed a full live demo for one account — listed + labeled traces, open review-queue items, unread notifications, subscriptions with matches — or wipe/re-seed an account's data, on the local stack or the deployed trace-mp.com production stack. Use when asked to seed demo data for an email, prep a demo account, reset or wipe an account's data, or populate the app for a walkthrough.
---

# Seed a demo account

`tools/seed_demo.py` takes an email and seeds everything needed to show the
app live, driven by the object manifest `tools/seed_demo.json`:

- fixture uploads through the real HTTP API → listed traces with tags and
  descriptions;
- deterministic analysis labels (machine provenance) on `trace_analysis`,
  so traces look analyzed even without LLM keys — human-resolved labels are
  never overwritten;
- open review items with verdict snapshots + routing reasons, and an unread
  `review_request` digest notification;
- subscriptions, first-match records, and an unread `subscription_match`
  digest notification;
- a demo contributor account (`demo-contributor@example.com`) listing its
  own fixtures, which the target user acquires — so the Library page has
  content and the marketplace looks multi-user.

Sign-in uses the admin magic-link flow: the account is created pre-confirmed
if missing, and an existing account's password is never touched — safe to
run against someone's real production account. The email is allowlisted
automatically. Idempotent: re-runs reuse duplicate uploads and skip existing
open items, unread digests, and matches.

## Local stack

```sh
make seed-demo EMAIL=user@example.com
```

Targets whatever `.env` / `.env.local` point at (the Compose stack by
default). Stack must be up: `supabase start` + `docker compose up`.

## Production (trace-mp.com)

```sh
make seed-demo EMAIL=user@example.com STACK=production
```

Reads git-ignored `.env.production` directly (and defaults the API to
`https://trace-mp.com`) — no sourcing needed, but only with the explicit
`STACK=production`. `tools/_stack.py:load_env()` still never reads
`.env.production`, so nothing can target production by accident; do not
"fix" that.

If `.env.production` is missing, regenerate it per
`.cursor/skills/allow-email/SKILL.md` (SUPABASE_URL from
`infra/terraform.tfvars`, the service-role key from SSM). Never print or
commit the key.

## Wipe / re-seed

```sh
make seed-demo EMAIL=user@example.com WIPE=1   # wipe, then seed fresh
make wipe-demo EMAIL=user@example.com          # wipe only, no re-seed
```

Both accept `STACK=production`. Wipe deletes the account's owned traces
through the real API (upload rows and storage objects ride along), leftover
trace-less upload rows, subscriptions (matches cascade), acquisitions, and
notifications. It does NOT delete the account, its allowlist entry, or its
API keys, and never touches other accounts' data — the demo contributor's
listings survive a wipe of the target user. Destructive and instant: on
production, confirm the email with the user before running.

## Verify

The script prints per-object lines (`seeded <fixture>: …`,
`seeded subscription '…'`) and exits non-zero on any failure. Then sign in
as the email: the marketplace shows the listed traces with labels, the bell
shows unread notifications, `/review` has open items, the subscriptions
feed has matches, and `/library` holds the acquired contributor traces.

## Changing what gets seeded

Edit `tools/seed_demo.json`. Constraints worth knowing:

- `analysis` values must satisfy the taxonomies in
  `services/api/app/analysis/models.py` (`FAILURE_MODES`,
  `TASK_CATEGORIES`) and the `trace_analysis` check constraints.
- `review.reasons[].code` must be a `RoutingReasonCode`
  (`services/api/app/analysis/routing.py`); keep messages in the same
  format the router produces.
- `subscriptions[].query` uses the `TraceFilterQuery` vocabulary
  (`services/api/app/schemas/trace.py`); it is validated by the API at
  create time.
- `matches` lists fixture filenames whose traces get first-match records.
- New fixtures need repo-unique OTLP `traceId`s: traces upsert on
  `(owner_id, source_trace_id)`, so two fixtures sharing a traceId steal
  one trace row from each other on every ingest. Ids 1111–6666 are taken.
