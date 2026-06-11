# HIL Loop — Uncertainty → Review → Human Labels

When the judge isn't sure about a trace, the verdict doesn't ship silently:
it routes to a review queue with plain-language reasons, digests into one
notification per upload, and a human answer lands back on the trace with
human provenance the machine can never overwrite. Runs end to end on a
keyless stack via a canned-verdict fault.

## Steps

With the stack running (`supabase start` + `docker compose up`) and a user
signed in at http://localhost:3000 (or your `WEB_PORT`):

```sh
# 1. Upload a batch with an uncertain verdict injected (keyless lever:
#    the worker adopts this verdict instead of calling the LLM, then runs
#    the real cap + routing math over it).
TOKEN=…   # browser session token, or use the web upload with devtools off
curl -s -X POST http://localhost:8000/v1/uploads \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Fault: analyze:verdict:success:0.4" \
  -F "file=@fixtures/agent-session.json"
```

   Easier without curl: upload any fixture from `/upload` twice (the dev
   fault header is also settable via the integration helpers), or run

```sh
cd services/api && uv run pytest tests/integration/test_hil.py -q
```

   which exercises the whole loop against the live stack and leaves the
   data visible in the UI.

2. Watch the **bell badge increment without a refresh** (Supabase Realtime
   on `notifications`, invalidation-only). `/notifications` shows one
   digest — "N review requests from upload X" — not one ping per trace;
   more uncertain traces from the same upload bump the same unread row.

3. Follow the digest → `/review` filtered to that upload. Each row carries
   the machine verdict with its confidence and the routing reasons
   verbatim ("Outcome confidence 0.40 is below the 0.70 threshold.").
   Bulk syncs group per upload, expandable.

4. Open an item: the **same span-tree + details inspection components as
   the trace page** sit beside the verdict form. The machine's take is
   context, never pre-selected. Answer any subset — outcome ternary,
   failure mode (only when failure is chosen, with one-line category
   descriptions), task category — and resolve:

   - match the machine value → `human_confirmed`, confidence 1.00
   - differ → `human`, confidence 1.00
   - a non-failure human outcome clears a machine failure_mode

   "Resolve & next" walks the rest of the batch oldest-first.

5. Back on `/traces`: the resolved trace shows the **solid** outcome badge
   (human provenance) at 1.00; unresolved ones keep the outline machine
   badge and stay fully listable/filterable — review gates nothing. The
   needs-review indicator links straight to the open item.

6. Re-run analysis on a trace with an open item
   (`make requeue UPLOAD=<id>` with the fault still armed): the old item
   flips `superseded`, exactly one fresh item is open — never two. Resolve
   the outcome and requeue again: the same uncertainty reasons are now
   filtered (that question was answered by a human) and nothing routes.

7. Owner relabel: on any analyzed trace's detail page, Analysis →
   "Relabel" self-creates an item (empty reasons) and lands on the same
   resolve view. Works on keyless-skipped traces too.

8. Unattended failures: sync a bad file through the CLI
   (`echo '{"resourceSpans": []}' > bad.json`, then `trace-sync sync`) —
   an `upload_failed` notification appears with the filename, linking to
   `/uploads`. The same failure through the web door stays silent: it
   already failed in front of you.

## What was solved

B2's analysis ships verdicts with calibrated confidence, but a label the
judge wasn't sure about is a data-quality liability for the marketplace,
and asking a human costs attention. The loop closes the gap with strict
budget discipline: only genuinely uncertain verdicts ask, each question is
asked once, bulk uploads collapse into one notification, and a human
answer permanently outranks the machine on exactly the fields it touched.

## Why it's interesting

- **Routing rides the rewrite transaction.** The worker passes routing
  context into the same delete-and-rewrite that persists analysis
  (`services/api/app/queries/analysis.py:rewrite`): labels never commit
  without the review item that routed them, and a crash re-run converges
  both together. Supersede-then-insert under a partial unique index
  (`review_items (trace_id) where status = 'open'`) makes duplicate open
  items impossible, not just unlikely.
- **Humans are never re-asked.** The reason filter
  (`queries/analysis.py:filter_reasons`) drops any routing reason whose
  target field already carries human provenance on the row being written —
  composed on top of B2's frozen `route()`, which stays pure.
- **Flood control is one unique index.** The digest is an
  `insert … on conflict … do update` against a partial unique index on
  `(user_id, payload->>'upload_id') where unread`
  (`queries/notifications.py`): per-upload notification dedupe with a
  live item counter and zero scheduling machinery. Reading the digest
  frees the slot; the next routed item starts a fresh one.
- **Provenance arithmetic is a pure function.**
  `queries/review_items.py:label_updates` decides
  `human` vs `human_confirmed` (comparator: the field's current
  machine-provenance value), stamps confidence 1.0, and applies the
  failure-mode coherence rule — unit-tested as a matrix, executed inside
  one transaction with the analysis row locked against concurrent
  rewrites.
- **Keyless CI exercises the whole loop.** The canned-verdict fault
  (`X-Fault: analyze:verdict:<outcome>:<conf>[:<category>:<conf>]`,
  `app/dev/faults.py`) substitutes the judge while keeping the real cap,
  routing, filter, digest, and resolve paths live —
  `tests/integration/test_hil.py` runs the full done-when on a stack with
  no provider key, audit rows honestly marked `fault:canned`.
- **One evidence pane, two surfaces.** The resolve view composes the same
  `TraceEvidence` component as the trace page
  (`apps/web/src/components/traces/trace-evidence.tsx`) — the reviewer
  judges with full span-level evidence on one screen, by construction
  rather than by copy.
