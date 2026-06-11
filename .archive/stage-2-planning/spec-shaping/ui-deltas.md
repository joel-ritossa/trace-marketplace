# Stage 2 UI Deltas

What stage 2 does to the UI beyond the new surfaces, which have their own doc ([ui-new.md](ui-new.md)) and are mapped in `ux-principles/product-map.yaml`. Two kinds of delta: mutations to existing stage-1 pages, and stage-1 UX gaps that stage 2 turns from minor into broken. Spec-shaping level; promote with `infra.md` + `judging/`.

## 1. Trace detail: Analysis section

The judging output is far more than the three header labels: deterministic signals (`loop_kind`, retries…), ~5–6 `metric_scores` with flags + reasons, the judge's reasoning text (spec'd to appear on trace detail), per-field provenance/confidence, analyzer versions, model id, the N stored votes.

- **Trace detail gains a third section** — Analysis — between the metadata header and the span tree.
- Header keeps a compact label strip (outcome / failure_mode / task_category badges with provenance + confidence) for triage; the Analysis section is the full view.
- Section contents, in disclosure order: labels with per-field provenance + confidence → judge reasoning → deterministic signals → metric scores (flag/score + reason each). Audit details (analyzer versions, model id, stored votes) behind a collapsed "details" disclosure — present for honesty, not in the default eye-line.
- Owner-initiated relabel lives here (entry point to the resolve view, per `ux-principles/review-queue/labeling.md`).
- The section always renders, with explicit non-result states — see §7.

## 2. Labels at list level (cards / rows)

Filtering on label fields is designed; *rendering* them on marketplace cards and the `/traces` table is not.

- List level shows **outcome + provenance only**: one outcome badge whose visual variant encodes provenance (e.g. solid = human/human_confirmed, outline = machine). Confidence as secondary text on the badge (`0.84`), not a separate column.
- `failure_mode`, `task_category`, metric scores: filterable but not rendered at list level — that's what filters and the detail page are for. Keeps cards scannable.
- Unanalyzed traces show a quiet "not analyzed" placeholder in the same slot, visually distinct from a verdict (per the null-semantics principle in `ux-principles/search/filtering.md`).

## 3. Numeric-range filter controls

The shared filter component today is selects/toggles/date-range. Confidence and `metric_scores` need `field >= x`:

- **Threshold control, min-bound only** (a number input with a `≥` affordance), matching the spec'd predicate shape — no dual-handle sliders.
- Chips render the predicate verbatim: `faithfulness ≥ 0.8 ×`, `confidence ≥ 0.7 ×`.
- `metric_scores` keys are a dynamic set: the filter UI enumerates available metrics from observed data (consistent with "facet options derived from data"), not a hardcoded list. Applies to stage-1 numerics (duration, tokens) for free.

## 4. Upload history surface + failed CLI uploads

Stage 1's only ingestion-feedback surface is the `/upload` poll loop — it assumes the user is present. CLI watch mode uploads while nobody is looking; a failed upload never becomes a trace, so it is invisible in the web app. The API already has everything needed (`GET /v1/uploads` returns status + `error_message`, paginated); the page is missing.

- **New `/uploads` page:** upload history table — filename, source (cli/web), status, error message verbatim, created/processed, link to created traces. Not a primary nav item; linked from `/upload` ("history") and `/traces`.
- **New notification type `upload_failed`**, emitted only for `source = cli` uploads (web failures fail in front of the user). Digested per burst like `review_request`. Links to the upload row on `/uploads`. Infra delta: one new notification type, no schema change (infra §3 already supports types additively).

## 5. Bulk listing (consent at scale) — settled: batched consent

Listing is per-trace on the detail page with a consent checkbox — deliberately weighty. CLI sync produces hundreds of private traces; sharing them is currently a per-trace pilgrimage. Consumers got multi-select → bulk acquire; contributors have no bulk-list.

**Settled:** multi-select on `/traces` → "List N traces", one confirmation dialog carrying the same ownership-consent copy, naming the exact count, requiring the same affirmative checkbox once for the batch. The unit of deliberation moves from trace to batch — which matches how the traces arrived (one sync, one sharing decision). Consent stays explicit, informed, and never pre-checked; "listing is the consent act" survives intact, just batched.

Guardrails: the dialog operates only on an explicit selection (no "list all" shortcut), and the per-trace flow on the detail page is unchanged. Bulk-unlist rides along for symmetry (cheap, not consent-sensitive).

## 6. My Traces at sync scale

The stage-1 table was designed for a handful of manual uploads; watch mode means hundreds of rows.

- **Pagination UI** on all three list pages (API already paginates at max 100; the pages spec never specified the UI side). Standard pager, no infinite scroll.
- `/traces` gains an **analysis column**: the outcome badge from §2, or pending/skipped state, plus a needs-review indicator linking to the review item.
- **Trace naming:** CLI-synced traces must get scannable names — derive from root-span name or source filename at ingestion, never a bare id. (Small stage-1 importer check: confirm current name derivation; fix if it produces ids.)

## 7. Analysis status: pending vs skipped, never a lie

Infra §7: with no LLM key configured, LLM analyzers skip and leave fields null. A "pending" placeholder would then be false — it never arrives. Per the cross-cutting honesty rule, the UI distinguishes:

- `pending` — analysis queued/running → "Analysis pending".
- `complete` — results render.
- `skipped` — LLM analyzers not configured → "Judge not configured" (deterministic signals still shown).
- `failed` — analyzer errored terminally → real reason, verbatim.

Infra delta: the API must expose per-trace analysis state (derivable from the results table + job state + config; exact mechanism is build-time). Filter exclusion notes ("N not-yet-analyzed excluded") use the same state.

## 8. Bulk download from library

Bulk acquire of 50 traces lands in a library offering per-card download. The `labels.jsonl` export (judging README) needs a surface.

- `/library` reuses the **bulk-selection pattern** → "Download N": a zip of raw payloads + one `labels.jsonl` covering the selection. Same artifact shape from the bulk-acquire confirmation moment ("Acquired 50 — download now").
- Single-trace download unchanged (original raw payload; `labels.jsonl` alongside per the export spec, same code path).

## 9. Profile display name

`profiles.display_name` is consumer-facing on marketplace cards; no surface sets or edits it (presumably seeded at signup). Settings gains a one-field profile block: display name, inline edit. Trivial; noted so it stops dangling.

## Deltas to other docs

- **infra.md:** `upload_failed` notification type (§3); API exposes per-trace analysis state (§6); batch visibility endpoint for bulk list/unlist (§5); bulk download artifact endpoint (§5/bulk acquire).
- **ux-principles/product-map.yaml:** add `uploads_history` screen; add Analysis section to `trace_detail` intent; `bulk_selection` pattern extends to listing and library download. (Applied.)
- **spec/stage-1 contact:** none beyond the trace-naming check in §6 — everything else is additive pages/columns/notification types.

## Open questions

- Confidence rendering at list level: raw number vs bucketed (high/med/low). Leaning raw (consumers filter on the number; the UI shouldn't invent a granularity the system doesn't store — same argument as the label model).
- Whether `/uploads` deserves a nav slot once CLI usage dominates, or stays a secondary link. Decide from use, not now.
