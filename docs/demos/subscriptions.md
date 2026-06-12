# Subscriptions — Saved Searches That Watch the Marketplace

A consumer saves a filtered marketplace search; from then on, every trace
that becomes listed (or finishes analysis or gets human-relabeled while
listed) is evaluated against
it — a first match notifies once, ever, and floods digest into one unread
notification per subscription. The feed runs the stored query live, marks
what's new since the last look, and bulk-acquires into a labeled download.

## Steps

With the stack running (`supabase start` + `docker compose up`) and two
users signed in at http://localhost:3000 (contributor + consumer):

1. **Contributor:** upload a few fixtures from `/upload` (or CLI-sync a
   session), then on `/traces` check several rows and **List N** — one
   batched-consent dialog covers the whole selection.

2. **Consumer:** on `/marketplace`, stack filters — e.g. `Outcome =
   failure`, `confidence ≥ 0.8`, a metric like `faithfulness ≥ 0.8` (the
   metric dropdown enumerates only keys observed in visible data). The URL
   carries every predicate; chips render them verbatim. Click **Save as
   subscription** — the dialog previews today's match count as backfill.

3. **Contributor:** list one more matching trace. Watch the consumer's
   **bell increment without a refresh**; `/notifications` shows "1 new
   trace matches …" deep-linking the trace. List a second match before
   reading it: the same unread row becomes "2 new traces match …" and
   links to the feed instead — one digest per subscription, never a ping
   per trace (`subscription_matches` unique pair + the partial-unique
   digest upsert).

4. **Feed (`/subscriptions/[id]`):** matches appear under a
   "new since you last looked" divider that clears on the next visit.
   Check rows → **Acquire N** → itemized result ("2 acquired · 1 already
   in library"), then **Download N now**.

5. The zip holds one payload per upload (scrubbed for acquirers, raw for
   owners) plus `labels.jsonl` — one line per trace with the label
   triplets, metric scores, promoted signals, and analyzer versions;
   unanalyzed traces get honest nulls.

Keyless shortcut: `cd services/api && uv run pytest
tests/integration/test_discovery_scale.py -q` exercises the whole loop
(seeded labels stand in for the LLM) and leaves the data visible in the UI.

## What was solved

Discovery at scale is a polling problem by default: a consumer hunting for
"high-faithfulness failures" would re-run the same search daily. A4 inverts
it — the query becomes a stored object (`subscriptions.query`, validated at
write time against the same Pydantic model the API parses, so it can never
fail to execute later), and matching becomes event-driven: a trace is
evaluated exactly when it becomes listed, when its analysis completes, or
when a review resolve relabels it while listed
(`app/worker/tasks/match.py`). No cron sweep, no re-polling, no missed
window between "listed" and "analyzed" — an `owner_opt_out` trace that gets
listed re-enqueues analysis first and matches when its labels land.

## Why it's interesting

- **One filter language, three call sites.** `TraceFilterQuery`
  (`app/schemas/trace.py`) is parsed from `GET /v1/traces` params, stored
  by subscriptions, and re-parsed on execution; the SQL comes from one
  clause builder (`app/queries/traces.py::filter_clauses`) shared by the
  list endpoint, match evaluation, and the feed. A filter added next slice
  is subscribable for free.
- **Notify-once is a uniqueness constraint, not bookkeeping code.** The
  `subscription_matches` unique pair dedupes re-listing storms; the digest
  is a partial-unique-index upsert (mirroring the A3 review digest), so
  flood control is enforced by Postgres, not remembered by callers.
- **Honest nulls all the way down.** Not-yet-analyzed traces never match an
  analysis predicate; the UI says "N not-yet-analyzed traces excluded"
  instead of silently shrinking results, and `labels.jsonl` writes nulls
  rather than inventing labels.
