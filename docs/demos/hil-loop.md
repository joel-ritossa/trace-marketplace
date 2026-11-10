# HIL Loop — Uncertain Turns → Review → Human Labels

When the judge can't confidently judge a turn, the verdict doesn't ship
silently: the trace gets one open review item listing its uncertain turns
with the agent's reasons, digested into one notification per upload, and the
owner's relabel lands on the turn with human provenance the machine can never
overwrite. Runs end to end on a keyless stack via a canned-verdict fault.

## Steps

With the stack running (`supabase start` + `docker compose up`) and a user
signed in at http://localhost:3000 (or your `WEB_PORT`):

```sh
# 1. Upload a batch with an uncertain verdict injected (keyless lever:
#    the worker adopts this canned verdict for every turn it judges and the
#    roll-up, instead of calling the LLM; outcome is one of
#    success|partial|failure|indeterminate).
TOKEN=…   # browser session token
curl -s -X POST http://localhost:8000/v1/uploads \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Fault: analyze:verdict:success:uncertain" \
  -F "file=@fixtures/agent-session.json"
```

   Or run the integration test, which exercises the whole loop against the
   live stack and leaves the data visible in the UI:

```sh
cd services/api && uv run pytest tests/integration/test_hil.py -q
```

2. Watch the **bell badge increment without a refresh** (Supabase Realtime
   on `notifications`, invalidation-only). `/notifications` shows one
   digest — "N review requests from upload X" — not one ping per trace;
   more uncertain traces from the same upload bump the same unread row.

3. Follow the digest → `/review` filtered to that upload. Each row lists the
   trace's uncertain turns with the agent's `uncertain` reason verbatim
   (the canned one reads "Fault injection: canned uncertain turn.").
   Bulk syncs group per upload, expandable.

4. Open an item: the same evidence components as the trace page sit beside
   the relabel form. The machine's take is context, never pre-selected.
   Set the turn's outcome, task categories and failure modes (each failure
   mode must cite at least one span of that turn) and save. This is
   `PUT /v1/traces/{id}/turns/{turn_index}/labels`: the turn becomes
   `provenance = human`, its `uncertain` clears, the session's category and
   failure-mode arrays are recomputed, and when no uncertain turn is left
   the item resolves.

5. Back on `/traces`: the trace keeps its (machine) session outcome and
   stays fully listable/filterable — review gates nothing. The needs-review
   indicator links straight to the open item until it resolves.

6. Re-run analysis on a trace with an open item
   (`make requeue UPLOAD=<id>` with the fault still armed): an unchanged
   uncertain set keeps the same item; a different set supersedes it with one
   fresh item — never two. Re-arm a confident verdict
   (`analyze:verdict:success`) and requeue: the open item flips
   `superseded` with no fresh one — a re-run that resolves the uncertainty
   closes the question instead of leaving a stale ask. A relabelled turn is
   never re-judged, whatever a re-run says.

7. Owner relabel without an item: on any analyzed trace's detail page,
   Analysis → relabel a turn. Same endpoint, no review item involved.

8. Unattended failures: sync a bad file through the CLI
   (`echo '{"resourceSpans": []}' > bad.json`, then `trace-sync sync`) —
   an `upload_failed` notification appears with the filename, linking to
   `/uploads`. The same failure through the web door stays silent: it
   already failed in front of you.

## What was solved

A turn the agent couldn't judge (it ran out of steps, or its citations didn't
check out) is a data-quality liability for the marketplace, and asking a
human costs attention. The loop closes the gap with strict budget discipline:
only genuinely uncertain turns ask, each trace has one open question, bulk
uploads collapse into one notification, and a human answer permanently
outranks the machine on exactly the turn it touched.

## Why it's interesting

- **The item rides the analysis transaction.** The worker syncs the review
  item inside the same write that persists the turns
  (`services/api/app/queries/analysis.py:rewrite` →
  `queries/review_items.py:sync`): labels never commit without the item
  that flags them, and a crash re-run converges both together.
  Supersede-then-insert under a partial unique index
  (`review_items (trace_id) where status = 'open'`) makes duplicate open
  items impossible, not just unlikely.
- **Humans are never re-asked.** `sync` only counts `provenance = 'machine'`
  uncertain turns, and `rewrite` skips any turn that is human by the time
  it writes — so a relabel can't be overwritten even by a run that was
  already in flight.
- **Flood control is one unique index.** The digest is an
  `insert … on conflict … do update` against a partial unique index on
  `(user_id, payload->>'upload_id') where unread`
  (`queries/notifications.py`): per-upload notification dedupe with a
  live item counter and zero scheduling machinery. Reading the digest
  frees the slot; the next item starts a fresh one.
- **Relabels are anchored.** A failure mode on the relabel request must cite
  spans inside the turn (`routers/review_items.py:relabel_turn`, 422
  otherwise) — the same rule the agent's own output is held to.
- **Keyless CI exercises the whole loop.** The canned-verdict fault
  (`X-Fault: analyze:verdict:<outcome>[:uncertain]`, `app/dev/faults.py`)
  substitutes the judge while keeping the real turn persistence, review,
  digest, and relabel paths live — `tests/integration/test_hil.py` runs it
  on a stack with no provider key, audit rows honestly marked
  `fault:canned`.
- **One evidence pane, two surfaces.** The relabel view composes the same
  `TraceEvidence` component as the trace page
  (`apps/web/src/components/traces/trace-evidence.tsx`), so the reviewer
  judges with full span-level evidence on one screen, by construction
  rather than by copy.
