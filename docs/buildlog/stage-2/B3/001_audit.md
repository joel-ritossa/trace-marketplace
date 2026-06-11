# B3 audit — quality metrics

Post-implementation review per `.cursor/skills/code-audit/SKILL.md`. Scope:
everything B3 touched — `metrics.py`, the `prompts/` package (critics +
migrated judge prompts), `models.py` (`MetricCall`, `MetricResult.calls`,
`METRICS`), `config.py` (metrics/critic_votes knobs), `registry.py`
(`metric:*` registrations, `enabled_metric_specs`), `llm.py`
(`SAMPLING_TEMPERATURE`), `judge.py` (prompt-package migration),
`rendering.py` (`rendering_text`), `sample.py`/`content.py` (consumed
surfaces), `worker/tasks/analyze.py`, `cli/analyze.py`, tests, the
`retrieval-qa` fixture + golden, `.env.example`, `pyproject.toml`.

## Findings

By audit axis; severity per the skill's categories.

1. **Correctness — clean.** Verified: gather-then-reraise preserves typed
   permanent/transient classification; RAGAS NaN fails open; scores clamp
   to [0, 1]; the adapter is constructed per run (no shared mutable
   state); critic tie / all-malformed folds to no row. One recorded
   asymmetry (nit, accepted): when a critic fold fails open, the dropped
   votes' call costs leave no audit row — recording them would require a
   row for a no-result metric, which the contract forbids.
2. **Spec conformance — one finding (spec violation, mild).** The offline
   runner's `--analyzer all` took the registry wholesale
   (`list(ANALYZERS.values())`), bypassing `ANALYSIS_METRICS` and running
   the stub — contradicting ratified decision 1 ("used by the worker's
   `_metric_specs()` and the runner alike"). Everything else conforms:
   reference-free pin, applicability predicates (extensions recorded in
   000 Outcome), `metric:<name>` storage, critic N=1 default at
   temperature > 0, litellm as the only provider-call site.
   Nit (accepted): the dev canned-verdict fault path skips metrics, so
   `metric_scores` can't be demoed keyless — intentional; the lever
   exists for routing.
3. **Modularity & file structure — clean.** Prompt package convention
   applied repo-wide, shared constants in their right homes. Two nits:
   `enabled_metric_specs` lives in `registry.py` rather than the planned
   `metrics.py` (right call — avoids an import cycle — but unrecorded;
   now drift item 5 in 000); `test_metrics.py` imports `FakeLLM`/`META`
   from `test_judge.py` (accepted at two consumers; a third moves it to
   `analysis_factories.py`).
4. **Future-proofing — one finding.** The `metrics` validator rejected
   unknown names but not duplicates: a repeated name would run (and pay
   for) the metric twice, writing duplicate `analyzer_results` rows
   (migration 8 has no per-analyzer unique key).
5. **Security & auth — clean.** No logging anywhere in `metrics.py`;
   prompts and renderings exist only in memory; every critic prompt
   instructs reasons to cite structure, never verbatim content. No
   schema or RLS surface touched.
6. **Reliability invariants — clean.** Typed exception classification
   propagates intact through the critic gather and the RAGAS adapter;
   `MalformedResponse` fails open at the right granularity (one dropped
   vote for critics, whole-metric `None` for RAGAS). Worker idempotency
   untouched.
7. **Consistency — clean.** Critic call shape, keyless predicate,
   fail-open vocabulary, and version constants mirror the judge; one
   pattern repo-wide. Out-of-scope note: `ruff check` failures in
   `app/analysis/validation.py` and its `__init__.py` re-exports belong
   to B4's surface and are left for B4's pass.

## Fixes (approved 2026-06-11)

1. **Runner honors the metric knob:** `cli/analyze.py` `--analyzer all`
   now runs the production set in run order — signals, judge,
   `enabled_metric_specs(settings)` — matching the worker; the stub runs
   only by name.
2. **Duplicate metric names dedupe:** `config.py` `_known_metrics` is
   order-preserving-unique (`dict.fromkeys`); new unit test
   `test_duplicate_metric_names_dedupe_order_preserving`.
3. **Drift recorded:** `enabled_metric_specs` location noted as drift
   item 5 in `000_implementation.md`.

## Re-verification

- `ruff check` + `ruff format --check` clean on B3 scope (B4's
  `validation.py` failures excluded, left for B4).
- Full unit suite green after fixes (261 tests — includes B4's in-flight
  additions; B3 closed at 245, this pass adds 1).
