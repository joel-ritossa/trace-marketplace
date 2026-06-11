# Listing copy generation — implementation

## Ask

Auto-generate the marketplace listing's tags + description ("What is this trace? What makes it worth acquiring?") on ingestion, and document the tag caveats (non-determinism) in the docs.

## Plan

- Not literally in ingestion (the determinism invariant): a new `listing` analyzer inside `analyze_trace`, so it still runs automatically post-upload.
- One sampled call on the judge model, no voting; output normalized to the PATCH endpoint's owner-input bounds (tag ≤ 80 chars, ≤ 6 tags, description ≤ 2000).
- Fill-if-empty into `traces.tags` / `traces.description`, atomic in SQL — owner values never overwritten, no regeneration once set.
- Gated like the judge (keyless skip, private-trace owner opt-out); malformed response fails open.
- Spec section in `1_analysis.md` ("Listing Copy") carrying the caveats: non-deterministic, never filter vocabulary, search-visible.

## Decisions

1. Writes target the owner-editable `traces` columns directly (no separate suggested-fields) — the fields already exist, the editor already shows them, and fill-if-empty gives the no-clobber guarantee provenance columns would otherwise provide.
2. The already-set check happens in the worker (gate row), so re-analysis of a trace with copy skips the LLM call entirely.
3. No new env knobs: the analyzer rides the judge model and the existing LLM gates.

## Drift

- The `fetch_llm_gate` query grew `tags`/`description`; the worker's three duplicated opt-out predicates collapsed into one local.

## Outcome

- `services/api/app/analysis/listing.py` + `prompts/listing.py` (V1), registered as `listing`; `ListingResult` added to the contract models (additive).
- Worker runs it after judge/metrics when copy is missing; fills via `traces_q.fill_listing_meta` after the rewrite, before the match kick (subscription search sees the tags).
- `tests/unit/test_listing.py` (10 tests: normalization bounds, fail-open paths, registry envelope) — passing alongside the existing analysis unit suite; keyless integration runs are unaffected (the analyzer skips itself).
