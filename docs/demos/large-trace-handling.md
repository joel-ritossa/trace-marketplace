# Large Trace Handling

A trace with thousands of spans uploads, ingests, and inspects without
falling over — payload cost scales with what the user looks at, not with
trace size.

## Steps

With the stack running (`supabase start` + `docker compose up`):

```sh
# 1. Generate a synthetic 5,000-span trace (~3 MB OTLP JSON, git-ignored).
python3 tools/make_large_trace.py --spans 5000

# 2. Sign up / sign in at http://localhost:3000, then upload
#    devdata/large-trace.json from the Uploads page.
```

3. Watch the upload reach **complete** in under a second, then follow the
   "View the trace" link.
4. The tree renders immediately with the first ~300 spans visible; expand
   nodes to walk deeper into all 5,000.
5. Click any span — the detail panel fetches and renders its full
   attributes (including the multi-KB `gen_ai.input.messages`) on demand.

To see the same thing on real data, `make dev-dataset ARGS="--min-spans 100"`
pulls big agent-benchmark sessions from HuggingFace into `devdata/`.

## What was solved

A single agent session can produce tens of thousands of spans, and span
attributes (LLM message payloads) routinely run to megabytes. Naively
returning "all spans with attributes" for the detail page would mean
tens-of-MB responses, multi-second parses, and a frozen tab — trace size
would set the cost of *opening* a trace, not inspecting it.

## Why it's interesting

The load is split across three boundaries, each bounded independently:

- **Light span list** — `GET /v1/traces/{id}/spans` returns only
  tree-building fields (ids, name, kind, timing, status, tokens), paginated
  at 500/page; the 5,000-span first page returns in ~10 ms. Attributes and
  events never ride along (`services/api/app/queries/spans.py`,
  `LIGHT_FIELDS`).
- **Per-span detail fetch** — full `attributes`/`events` come from
  `GET /v1/traces/{id}/spans/{span_id}` only when a span is selected, then
  cached client-side (`apps/web/src/components/traces/trace-inspector.tsx`).
  Inspecting one span costs one span's payload.
- **Capped default expansion** — the tree expands breadth-first to ~300
  visible spans by default (`apps/web/src/components/traces/span-tree.ts`,
  `defaultExpandedIds`), keeping the initial DOM small while every span
  stays reachable by expanding.

Honest limits, measured on the 5,000-span trace (production build): the
span tree is not virtualized, so a span-selection re-render with ~300 cards
in the DOM takes ~1 s; expanding everything would make it worse. Acceptable
for the trial; virtualization is the noted fix in
`docs/follow-up/trace-viewer-alternatives.md`.
