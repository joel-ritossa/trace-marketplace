# Stage 2 Ideation — Session 1

Notes from the first stage-2 ideation session (held while stage 1 was in development). One session's thinking, not an exhaustive idea inventory; later sessions may add, revise, or overturn this. Non-normative — like the rest of `.archive/`, this is raw thinking, not spec. Stage 2 gets a real `spec/stage-2/` before any code.

## Framing

Stage 1 proves the loop works: upload → validate → preserve raw → normalize → inspect → list → search → acquire → download. Stage 2 should answer the question stage 1 deliberately leaves open: **why is this marketplace worth anything?**

What "impressive" means in the trial context:

1. **Exploit the asset stage 1 builds** — raw payloads preserved verbatim + fully normalized spans. Anything that derives value from that data proves the foundation was worth building.
2. **Demo as a story, not a feature** — a click-through where the system does something the user couldn't do manually.
3. **Reuse stage-1 architecture** — the worker/queue/retry/DLQ machinery already exists; a new async pipeline slots in almost for free and proves the architecture was right.

Practical filter applied to everything below: **prefer ideas whose demo works with ~20 traces on a laptop.** Analytics and clustering get dramatically better with volume; diffing, similarity, replay, and lint are compelling at small scale — which is what the trial evaluator will actually see.

## Chosen Core Direction

Working decision from this session: implement **#1 (enrichment + intelligent discovery)** and **#2 (trace sets / dataset building)** as the stage-2 core. Everything else is candidate stretch/satellite work.

### 1. Enrichment + intelligent discovery

The highest-leverage option; `spec/stage-1/0_README.md` already names "failure-mode analysis, enrichment" as stage-2 candidates.

- **Enrichment as a second pipeline stage.** After ingestion completes, enqueue an `enrich_trace` job. Same reliability rules as ingestion: pure function of normalized data, delete-and-rewrite, versioned (`enricher_version`), re-runnable. The taskiq/DLQ/retry machinery from slice 1 absorbs a whole new workload without modification — that's the architectural flex.
- **Two enricher tiers:**
  - *Deterministic/heuristic* (no API key, demo-safe): failure-mode classification from span structure — retry loops (repeated identical tool calls), tool-error cascades, timeout patterns, context-window blowups (token counts), dead-end agents (error root with no recovery), latency outliers per span kind. Genuinely useful labels computable from spans already normalized in stage 1.
  - *LLM-based* (optional, env-gated): one-paragraph trace summary, auto-tags, "what went wrong" narrative for error traces. Documented as the one third-party dependency.
- **Semantic search via pgvector.** Supabase ships pgvector. Embed the *derived* summary/labels — never raw prompt text. This preserves the stage-1 privacy invariant: enrichment reads raw content, but only safe derived signal enters indexes. Search becomes "agent stuck in a retry loop calling a flaky API" instead of keyword matching on `error_types`.
- **UI payoff:** enrichment panel on trace detail, failure-mode filter chips in the marketplace, semantic search box.
- **Demo story:** upload a pile of messy traces → system auto-labels three of them "tool retry loop" → search the marketplace in natural language → find exactly the failure traces you'd want for evals. The marketplace becomes *smart*.

### 2. Trace sets / dataset building

Stage 1 explicitly defers "curated/derived bundles that cut across uploads." Once search is smart, the natural consumer act is: search → select results → bundle into a named dataset → acquire/download the set as one artifact (e.g. JSONL of normalized traces, or a zip of raw payloads).

- Converts the marketplace from "browse single traces" to "build an eval dataset" — the actual real-world use case for buying agent traces.
- Mechanically cheap: a `trace_sets` table, a membership table, a bundle-download endpoint reusing existing access checks.
- Best complement to #1: smart search is what makes set-building possible.

## Other Candidate Directions (ranked-ish)

### Builds on the embeddings/enrichment from #1 (cheapest wins)

- **Similar traces / "more like this".** pgvector already in place; nearest-neighbor on the trace detail page is nearly free. Powers discovery ("show me other retry-loop failures") and gives consumers a natural path from one good trace to a dataset. Best effort-to-impressiveness ratio after #1 ships.
- **Corpus map / cluster view.** Project embeddings (UMAP/t-SNE) into a 2D scatter of the marketplace, colored by failure mode or model. A visual "map of agent behavior" is a striking demo artifact and surfaces near-duplicate uploads as a side effect. Risk: needs enough traces to look good — depends on dev dataset size. The wildcard: spectacular if the dataset is big enough, flat if it isn't.
- **Aggregate analytics — "state of the corpus".** Cross-trace dashboards from enrichment output: failure-mode rates per model/provider, tool reliability rankings, latency/token distributions. The network-effect argument made visible: individual traces are data, the aggregate is *insight*, and only the marketplace can compute it. Pure SQL over existing tables; the work is mostly a good dashboard page.

### Deepens the inspection surface (plays to the strongest stage-1 asset)

- **Trace diff / comparison.** Pick two traces (same agent task, different model/version), align span trees, highlight divergence — extra tool calls, different errors, latency deltas. Exactly what someone evaluating models does manually today, and no tooling does it well. Harder than it looks (tree alignment is fuzzy), but even side-by-side with divergence highlighting demos extremely well. Pairs naturally with trace sets ("compare across the set"). Deepest "wow", most differentiated.
- **Replay / timeline player.** Step through a trace chronologically like a debugger — play/pause/scrub through spans as the agent "thinks". Same data, different lens; turns inspection from reading into watching. Mostly frontend work, no new backend, very demoable.

### Closes the loop with the consumer's real workflow

- **Eval-ready export formats.** Dataset bundles that download as ready-to-use shapes: eval-harness JSONL, prompt/response pairs, failure-case suites — not just raw JSON. Answers "what do I *do* with acquired traces?" (the stage-1 consumer story ends at a file download). Small, pragmatic; the sleeper pick for demonstrating product judgment over technical flash.
- **API keys + programmatic access.** On the stage-1 deferred list. Much more interesting *after* bundles exist: `GET /v1/sets/{id}/download` with an API key plugs datasets into CI eval pipelines. Also a prerequisite for `tracepush`. Plumbing-heavy — only worth it if it enables one of the above.

### Improves the supply side

- **`tracepush` — local auto-upload agent.** A file-watcher is fine, but the impressive version is a tiny **local OTLP receiver**: listens on `localhost:4318`, point any OTel-instrumented agent at it via `OTEL_EXPORTER_OTLP_ENDPOINT`, traces stream into your marketplace account live. One env var to publish your agent's traces. Demo: run an agent in one terminal, watch the trace appear in My Traces. Not a core pick because it forces the deferred API-key auth work (plumbing, not insight), shows breadth rather than depth, and the demo depends on having a live OTLP-emitting agent on hand. Good cherry on top of #1/#2 (frictionless in → intelligent out).
- **Trace lint / instrumentation quality score.** At ingestion, score how well-instrumented a trace is: missing token counts, unnamed spans, absent tool attributes, no status codes. Show contributors a quality report with fixes; surface the score as a marketplace filter. Cheap (pure heuristics over normalized spans), genuinely useful, and gives a quality signal future pricing can hang off.
- **Annotations.** Let users mark spans ("this is where it went wrong") on traces they can see. Human labels stack on machine enrichment and make datasets materially more valuable; stage 1 already reserved the concept (deferred `annotations` table). Catch: community features demo poorly with one user — would need framing as "label your own data" first.

### Considered and deprioritized

- **Privacy/redaction pipeline.** Product-important, but demos poorly ("it found a fake API key" is underwhelming), precision-sensitive, high risk of visible false positives in a trial window.
- **Payments/pricing.** Explicitly the boring part; Stripe-in-a-demo proves nothing about the data foundation.
- **More importers.** Incremental; the OTLP envelope already covers the interesting sources.

## Stretch Priority After #1 + #2

If the core lands and there's appetite for more, the reach order:

1. **Similar traces** — nearly free given pgvector.
2. **Trace diff** — deepest wow, most differentiated.
3. **Aggregate analytics** — best strategic story.
4. **Eval-ready exports** — pragmatic product-judgment pick.
5. **`tracepush`** — satellite, only if API-key auth is justified by something else too.

## Approach / Process Notes

1. **Spec-first, same discipline as stage 1.** Draft `spec/stage-2/` (README + enrichment model + failure-mode taxonomy + API/page deltas + build order) while stage 1 is in flight. The stage-1 spec format works; reuse it.
2. **Design against stage-1's contracts only** — tables, job queue, API shapes — never its internals. Keeps the workstreams from colliding while stage-1 code churns.
3. **Decisions to settle early** (they shape the spec):
   - **LLM dependency policy.** Lean: heuristic tier always works offline; LLM tier env-gated and optional.
   - **Where enrichment lives.** Lean: new `enrichments` table keyed by trace + enricher version — not columns bolted onto `traces` — keeping ingestion pure and enrichment independently re-runnable.
   - **Failure-mode taxonomy v1.** Define concretely against the real dev dataset once available; "do these labels fire on real traces" makes or breaks the demo.
