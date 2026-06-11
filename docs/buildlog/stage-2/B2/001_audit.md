# B2 — Audit

Post-implementation review per `.cursor/skills/code-audit/SKILL.md`. Scope:
`llm.py`, `judge.py`, `routing.py`, `models.py`, `config.py`, `registry.py`,
`__init__.py`, `prompts/*.md`, `cli/analyze.py`, the three B2 test files,
`.env.example`, against `1_analysis.md` / `2_data-model.md`. All findings
approved and fixed in this pass.

## Findings and fixes

### Bug (minor)

1. **A transient vote error orphaned sibling vote tasks** —
   `judge._collect_votes` used bare `asyncio.gather`: the first transient
   provider error propagated immediately while the other in-flight votes
   kept running detached (wasted spend, "exception never retrieved" noise).
   Fixed with `gather(return_exceptions=True)` + re-raise of the first
   exception after all votes settle — the original exception type (not an
   ExceptionGroup) is preserved, which the worker's permanent/transient
   classification keys on.
2. **Parse-retry dropped the first attempt's cost from the audit
   artifact** — `llm.complete` returned only the last attempt's `CallMeta`;
   a parse-retried vote actually cost two calls. Fixed: metadata
   accumulates across attempts (`_fold_meta` — latency sums, tokens/cost
   sum when present), on both the success and the `MalformedResponse`
   path.

### Future-proofing

3. **No bounds on voting config** — `ANALYSIS_JUDGE_VOTES=0` divided by
   zero in every fold; `ANALYSIS_JUDGE_CONSENSUS < 0.5` let *both*
   `success` and `failure` clear the threshold, with `fold_outcome`'s loop
   silently letting `failure` win. Fixed: `judge_votes ≥ 1`,
   `0.5 ≤ judge_consensus < 1` — misconfiguration now fails at settings
   load, never mid-analysis.

### Nit

4. **`route` ran signals twice per trace** — the CLI computed
   `run_signals` and `run_judge` recomputed it internally. `run_judge` now
   accepts an optional `signals` argument (registry signature unchanged —
   it defaults); the route CLI and A2's worker can pass their result
   through. Determinism made the duplicate harmless; now it's also gone.
5. **Prompt filenames were coupled to `JUDGE_VERSION`** — bumping the
   ensemble version would have force-renamed all three prompt files.
   Loading now goes through an explicit `_PROMPT_FILES` map; prompt files
   carry their own per-prompt versions, `JUDGE_VERSION` still covers the
   ensemble.
6. **Env bootstrap exported every env-file value** — `_load_env_files`
   pushed all of `.env`/`.env.local` into `os.environ` (and child
   processes). Now filtered to provider-credential keys (`*_API_KEY`,
   `*_API_BASE`); platform settings stay out of the process environment.
   Exotic provider vars (e.g. Bedrock's AWS credentials) must be real env.

### Clean axes

- **Spec conformance** — composed calls, clean-room outcome prompt,
  evidence only in the failure-mode prompt, votes stored, N=1 self-report
  degrade, strict thresholds, four triggers in spec order, cap semantics,
  keyless skip, `rendering_truncated`, model id in the envelope.
- **Modularity** — one provider-call site, pure routing, registry seam,
  versioned prompt files.
- **Security & privacy** — nothing logs prompts/outputs; evidence block is
  span skeletons only; keys live in `.env.local`.
- **Reliability invariants** — typed permanent/transient classification
  mirroring ingestion; the single parse-retry is scoped; no blanket
  retries (finding 1 was the one gap).
- **Consistency** — error naming, test style, CLI shape all match the
  codebase.

## Verification

- Unit suite green after fixes: 178 passed (5 new tests: sibling-settling
  on transient error, caller-supplied signals drive the cap, settings
  bounds rejection, meta folding, env-bootstrap key filtering; 2 updated
  for accumulated retry cost). Ruff check + format clean on slice files.
- Live spot check (real key): `route` over `fixtures/minimal.json` —
  the filtered bootstrap still delivers the provider key, verdict +
  3 votes with cost metadata recorded, category correctly skipped.

Note: at audit start the working tree had 6 failing importer-golden tests
from concurrent A-stream changes (`total_tokens` mid-sync between importer
and goldens); they resolved upstream during this pass and are not B2's.
