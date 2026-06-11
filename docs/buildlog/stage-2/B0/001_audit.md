# B0 Audit

Post-implementation review of the analyzer contract, renderer, and offline
runner, per the `code-audit` skill. Scope: `app/analysis/` (all eight
modules), `app/cli/analyze.py`, `app/env.py`, the `app/config.py` extraction,
all six new test files + golden files + `regenerate.py`, `.env.example`,
checked against `docs/spec/stage-2/1_analysis.md` and `2_data-model.md`.

All axes walked. **Correctness had no bugs** (trim-pass convergence, marker
arithmetic, CLI exit codes, `from_db_rows` extra-column handling, and the
importer/DB span-ordering agreement all verified clean). **Security/privacy
clean** (no attribute/event/payload logging anywhere; the CLI printing
renderings to stdout is the tool's purpose, and its access-check-free DB mode
matches the `requeue` operator-tool precedent). **Reliability clean** (pure
package; the runner's only I/O closes its pool in `finally`; `run_analyzer`
deliberately propagates exceptions — classification is A2's worker concern).
Findings below were all approved and fixed in this pass.

## Findings + fixes

1. **(Correctness, nit) Silent truncation below cap 48** —
   `rendering._middle_out` hard-cut text with no in-text cue when the
   per-field cap was too small for the counted marker (reachable after 2–3
   cap halvings). The flag was set, but the judge would see text that looks
   complete. Fix: bare `…` terminal cue (fits any cap); comment records the
   trade-off. Goldens unchanged (fixture renders never hit sub-48 caps).
2. **(Correctness, nit) Undocumented budget floor** — if the final-K
   skeletons plus fixed messages alone exceed the budget, the output runs
   over rather than dropping must-haves. Unreachable with sane configs;
   now documented at the trim pass in `render_trace`.
3. **(Spec, low) Must-have overflow behavior was code-only** — the trim pass
   elides pre-final-K error spans oldest-first under extreme budgets
   (implementation drift note 2), but `1_analysis.md` listed error spans as
   unconditional must-haves and was silent on the overflow case. Fix: one
   sentence added to the spec's rendering section; spec and code now agree.
4. **(Modularity, low) Inline SQL in the CLI** — `analyze.py` DB mode had
   raw `select *` queries inline; repo convention is one query home per
   domain, and A2's worker needs the same loader. Fix: new
   `app/queries/analysis.py` with `fetch_trace_input(pool, trace_id)`;
   the CLI now calls it (still lazily imported, fixture mode stays
   platform-env-free).
5. **(Future-proofing, nit) Magic 64** — the indexed-attribute scan ceiling
   appeared as a bare literal three times in `content.py`. Fix: named
   `_MAX_INDEXED_ATTRS` constant with a comment.
6. **(Consistency, nit) `Provenance` looked like dead code** — defined in
   `models.py`, used by no field (A2's worker stamps it at persistence).
   Fix: comment marking it as frozen contract vocabulary.
7. **(Consistency, nit) Formatter residue** — redundant parens in
   `rendering._field_cap`. Fixed.

## Re-verification

- 56 unit tests green; renderer goldens byte-identical (no regeneration
  needed — fix 1 doesn't fire at the golden config).
- ruff check + format clean on all B0 files (the pre-existing slice-3 lint
  error in `tests/integration/test_discovery.py` remains out of scope).
- Done-when re-run: all five `devdata/` files rendered twice via the runner
  → byte-identical, every trace ≤ 60,000 chars, truncation marked;
  `run --analyzer stub` emits the envelope as before.
