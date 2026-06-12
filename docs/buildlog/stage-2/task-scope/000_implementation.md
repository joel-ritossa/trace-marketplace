# task-scope — expanded task taxonomy + owner hard scoping

Goal (user-approved, spec'd in this pass): grow `task_category` from 8 to
50 values, and let owners scope the judge's category vocabulary to the
categories they actually work in — a large taxonomy gives precise labels,
hard scoping keeps the vote-split (routing) rate down. Follows B4 pass 4,
which established the cat-eval harness and fixed the evidence bug.

## Decisions

- **Taxonomy**: 50 values in 10 display groups (1_analysis.md table), a
  strict superset of the original 8 — existing labels stay valid, no data
  migration. Canonical values + one-line descriptions in
  `app/analysis/models.py`; web/desktop taxonomy files mirror it.
- **Hard scope**: `profiles.task_categories text[]` (default `{}` =
  unscoped). The category prompt is built per trace from a versioned
  template over (owner scope + `other`); votes outside the scoped
  vocabulary are malformed, like out-of-enum values. Human resolution may
  still pick any global value; marketplace filters use the global enum.
- Not retroactive (no automatic re-judging on scope change); routing
  semantics unchanged.

## Plan

1. Spec: 1_analysis (taxonomy table + scoping), 2_data-model, 3_api,
   4_pages.
2. Migration `00000000000015_task_scope.sql`.
3. Backend: grouped taxonomy in models.py; `category.V2` prompt builder;
   judge threads owner scope (TraceInput field, populated by
   `fetch_trace_input`); per-call vocabulary; `JUDGE_VERSION` 6 → 7.
4. Profile API: `task_categories` read/update with validation.
5. Web: settings "Task scope" section (grouped checkboxes); taxonomy
   mirror with groups; desktop taxonomy mirror (flat list for resolve).
6. Tests: prompt builder, scope vocabulary enforcement, profile API
   validation, scoped-judge integration.
7. Eval: re-run `cat_eval.py` unscoped on the 50-value prompt (does a
   bigger vocabulary regress accuracy/routing?) and scoped (sessions
   corpus with a coding-ish scope) to measure what scoping buys.

## Drift

- `cat_eval.py` ground truth went from single labels to **acceptable-category
  sets** per corpus: under a 50-value taxonomy the old single labels were
  wrong, not just coarse — "now run the tests" *is* `testing_qa`, a tau-bench
  agent legitimately does both `customer_ops` and `customer_support`. The
  set is the honest unit of agreement at this granularity.
- `cat_eval.py` grew per-trace retries: provider flakes under burst (a bogus
  "Request headers are too large" BadRequest on a 160-char input) classify
  as permanent and killed whole runs.
- `_one_vote`/`_collect_votes` gained `system`/`vocabulary` overrides instead
  of a scoped-judge fork — the category call is the only caller that scopes;
  outcome/failure-mode are untouched.

## Outcome

All measured on the same 279-trace corpus as B4 pass 4 (`cat_eval.py`),
same model (gpt-5-mini), 3 votes, threshold 0.7:

| configuration | routing rate | labeled accuracy (set-aware) |
|---|---|---|
| 8-value taxonomy (B4 pass 4 baseline) | 10.4% | 86.8% |
| 50-value, unscoped | 23.3% | 82.9% |
| 50-value, dev scope (7 categories) | **1.8%** | sessions 6/6, 0 routed |

- The headline trade: a fine taxonomy alone **doubles** routing — the new
  confusion mass is near-synonym boundaries (`customer_ops`→
  `customer_support` 5, `web_research`→`data_analysis`/`financial_analysis`
  16, `coding`→`testing_qa`/`ci_cd` 3). Hard scoping removes exactly those
  boundaries and takes routing to ~2% while keeping the finer labels.
- Under the dev scope, all out-of-scope corpora (tau_retail, magentic_one,
  assistantbench) fold to `other` **confidently** — correct behavior by
  construction (their labels are outside the offered vocabulary), reads as
  0% in the table because the acceptable sets don't include `other`.
- Verification: 337 unit tests pass (3 new: scoped prompt+vocabulary,
  unscoped full taxonomy, builder ordering); integration
  `test_profile_roundtrip` extended (dedupe/sort, partial-update, 422 on
  out-of-enum and `other`, reset); web + desktop `tsc` clean; migration
  applies on the local stack. Known-unrelated failures: `test_owner_relabel`
  (keyed stack), one post-restart timing flake that passes in isolation.
- `JUDGE_VERSION` 6 → 7 (category vocabulary + prompt builder change);
  renderer untouched.

### Follow-up probe — 5 votes (`cat_eval.py --votes 5`)

Unscoped 50-value, same corpus, threshold 0.7: routing 23.3% → **13.3%**
(one defector no longer routes: 4/5 = 0.8), accuracy flat (83.7%), 20/279
label flips, cost +69% (~$0.004/trace). Accepting bare 3/5 pluralities
(threshold 0.6) cuts routing to 2.9% but that band is only 5/8 correct —
the share ladder is calibrated (1.0 → 86%, 0.8 → 75%, 0.6 → 63%), so the
0.7 floor stands. `JUDGE_VOTES` env var; no code change to adopt.

Adopted (user-approved): `judge_votes` default 3 → 5 (`config.py`,
`.env.example`, spec Self-consistency section). The knob is shared by all
three composed calls, so total judge spend scales ~5/3 — including the
full-rendering outcome votes, the expensive ones. No `JUDGE_VERSION` bump:
vote count is runtime voting config, not prompt/composition identity, and
each verdict's actual N is auditable from its stored votes. Not
retroactive; verified live (`judge_votes = 5` in the worker container).
