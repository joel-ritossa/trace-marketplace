# Stage 2 Build Log

Status index for the slices in `docs/spec/stage-2/6_build-order.md`. Same pass
records as stage 1: each slice directory holds `000_implementation.md` (plan,
drift, outcome), `001_audit.md`, then `00N_<slug>.md` for subsequent passes.

## Slice process

Identical to stage 1 (`docs/buildlog/stage-1/README.md`), with two stage-2 notes:

- **Two parallel streams.** Slice order is enforced *within* a stream
  (B0 → B1 → … and A1 → A2 → …), not across them — except B0, which freezes
  the analyzer contract and precedes everything. A-slices wire stub analyzers
  behind the contract until the matching B-slice lands (merge map in the
  build order).
- **Verification surface.** A-slices verify their done-when on a fresh
  `docker compose up`, like stage 1. B-slices are offline: their done-when
  runs through the offline runner / pytest / the validation script — no
  compose required until the merge into their A-slice.

## Slices

### Stream B — Analysis Core

| Slice | Scope | Status |
|---|---|---|
| [B0](B0/000_implementation.md) | Analyzer contract, trace rendering, offline runner | Done (2026-06-11): implemented, verified, audited |
| [B1](B1/000_implementation.md) | Deterministic signals + hit-rate report | Done (2026-06-11): implemented, verified, audited |
| [B2](B2/000_implementation.md) | Outcome judge (composed calls, voting, routing function) | Done (2026-06-11): implemented, verified, audited |
| B3 | Quality metrics (critics + RAGAS) | Not started |
| B4 | Validation (benchmark converter + agreement script) | Not started |

### Stream A — Platform

| Slice | Scope | Status |
|---|---|---|
| [A1](A1/000_implementation.md) | Machine door: API keys, sync CLI, /uploads, /settings | Done (2026-06-11): implemented, verified, CLI e2e test + demo, audited |
| [A2](A2/000_implementation.md) | Analysis plumbing: tables, analyze_trace job, states, Analysis section | Done (2026-06-11): implemented, verified (incl. live-judge run), audited |
| A3 | HIL loop: notifications, review queue, resolve, label badges | Not started |
| A4 | Discovery at scale: filter extension, subscriptions, bulk actions | Not started (blocked on stage-1 slice 3) |
| [A5](A5/000_implementation.md) | Redaction: importer scrub, span_raw, read/download boundaries | Done (2026-06-11): implemented, verified |

### Integration

| Slice | Scope | Status |
|---|---|---|
| integration | Full demo script on fresh compose + smoke script + validation number + third-party data-flow docs | Not started |

## Spec amendments (pre-build)

Amendments made after promotion but before any slice started — recorded here since there is no slice log to carry them yet:

- **2026-06-11 — per-account private-trace LLM-analysis opt-out.** `profiles.allow_private_llm_analysis` (default on); LLM analyzers skip private traces of opted-out accounts (`llm_skip_reason = 'owner_opt_out'`); listing always analyzes (re-run hook in A4); `/settings` toggle in A1, skip enforcement in A2. Touches `docs/spec/stage-2/` 0–4 and 6.
- **2026-06-11 — Supabase Realtime for live web surfaces (invalidation only).** The web app may subscribe to `postgres_changes` on its own rows purely as a refetch trigger; the API remains the single read path; CLI polling unchanged. Plumbing + first consumer (`/uploads`) land in A1; bell/notifications in A3. Recorded in `4_pages.md` Cross-Cutting.
