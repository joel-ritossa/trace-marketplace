# Stage 1 Build Log

Status index for the slices in `spec/stage-1/5_build-order.md`. Each slice
directory holds numbered pass records: `000_implementation.md` (plan, drift,
outcome), `001_audit.md`, then `00N_<slug>.md` for subsequent passes.

## Slice process

Every slice follows the same sequence, each pass re-verified end to end:

1. **Plan** — write the plan up front in `000_implementation.md`.
2. **Implement** — build it, logging every deviation in the Drift section.
3. **Verify** — run the done-when criteria; record the result in Outcome.
4. **Audit** — code-review pass (bugs, modularity, future-proofing) in
   `001_audit.md`, following the `code-audit` skill
   (`.cursor/skills/code-audit/SKILL.md`).
5. **Follow-up passes** — polish or other targeted work, one numbered file
   each.
6. **Close out** — mark the slice done here and in `000_implementation.md`,
   then commit.

## Slices

| Slice | Scope | Status |
|---|---|---|
| [slice-0](slice-0/000_implementation.md) | Walking skeleton (auth, API, worker, compose) | Done (2026-06-10) |
| [slice-1](slice-1/000_implementation.md) | Raw upload loop + reliability skeleton | Done (2026-06-10): implemented + [audited](slice-1/001_audit.md) + [modularity pass](slice-1/002_modularity.md) |
| slice-2 | Ingestion and inspection | Not started |
| slice-3 | Discovery, listing, and acquisition | Not started |
