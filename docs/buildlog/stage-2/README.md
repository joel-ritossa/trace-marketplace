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
| B0 | Analyzer contract, trace rendering, offline runner | Not started |
| B1 | Deterministic signals + hit-rate report | Not started |
| B2 | Outcome judge (composed calls, voting, routing function) | Not started |
| B3 | Quality metrics (critics + RAGAS) | Not started |
| B4 | Validation (benchmark converter + agreement script) | Not started |

### Stream A — Platform

| Slice | Scope | Status |
|---|---|---|
| A1 | Machine door: API keys, sync CLI, /uploads, /settings | Not started |
| A2 | Analysis plumbing: tables, analyze_trace job, states, Analysis section | Not started |
| A3 | HIL loop: notifications, review queue, resolve, label badges | Not started |
| A4 | Discovery at scale: filter extension, subscriptions, bulk actions | Not started (blocked on stage-1 slice 3) |

### Integration

| Slice | Scope | Status |
|---|---|---|
| integration | Full demo script on fresh compose + smoke script + validation number + third-party data-flow docs | Not started |

## Spec amendments (pre-build)

Amendments made after promotion but before any slice started — recorded here since there is no slice log to carry them yet:

- **2026-06-11 — per-account private-trace LLM-analysis opt-out.** `profiles.allow_private_llm_analysis` (default on); LLM analyzers skip private traces of opted-out accounts (`llm_skip_reason = 'owner_opt_out'`); listing always analyzes (re-run hook in A4); `/settings` toggle in A1, skip enforcement in A2. Touches `docs/spec/stage-2/` 0–4 and 6.
