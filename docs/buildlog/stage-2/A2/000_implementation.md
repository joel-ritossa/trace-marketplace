# A2 — Analysis Plumbing: Tables, analyze_trace Job, States, Analysis UI

Spec: `docs/spec/stage-2/6_build-order.md` (A2), `1_analysis.md` (analyzer
contract, runtime/config/degradation, privacy), `2_data-model.md`
(`analyzer_results`, `trace_analysis`, derived analysis state, stage-1
deltas), `3_api.md` (`GET /v1/traces/{id}/analysis`, result-card fields),
`4_pages.md` (Analysis section, the four honest states, labels at list
level).

**Done when:** upload → `trace_analysis` row with real signals; keyless and
opted-out runs show `skipped` with the right reason, never fake `pending`;
re-runs reproduce rows; an injected failure dead-letters and surfaces as
`failed`.

Consumes B1 (real signals — promotion list locked: all six catalog fields)
and wires the judge as B2 registered it (the registry already carries
`signals` and `judge`; swapping analyzers stays a registration change).
Metrics (B3) are not registered yet — the promotion path for `metric:*`
rows is built and exercised by nothing until B3 lands; `metric_scores`
stays null. Routing reasons → review items + notifications is A3; A2
persists analysis only.

Decisions proposed in this plan, to ratify before implementation:

1. **Stable trace identity** (resolves the stage-1 `TODO(trace-analysis)` in
   `ingest.py`). Ingestion switches from delete-and-reinsert of an upload's
   traces to a per-trace upsert keyed on a new unique
   `(upload_id, source_trace_id)`; spans still delete-and-rewrite *under
   each trace* in the same transaction, and traces absent from the
   re-imported payload are deleted. Re-ingest therefore preserves
   `traces.id` — and everything cascade-hung off it: `trace_analysis`
   (incl. human-provenance labels), `analyzer_results`, acquisitions, and
   A3's review items. Without this, any re-ingest silently destroys human
   labels via cascade, violating "human fields never machine-overwritten".
   The ingestion invariant (pure function of the raw payload,
   delete-and-rewrite semantics, one transaction) is unchanged in effect:
   the normalized *content* is still fully rewritten from the payload.
2. **Re-ingest re-enqueues analysis.** After a successful ingest
   transaction, the worker kicks `analyze_trace` for every trace in the
   upload (first ingest and re-ingest alike). Analysis is idempotent
   (delete-and-rewrite per run), so re-analysis after re-ingest keeps
   derived rows consistent with re-imported content — the same
   re-ingest + re-analysis backfill A5's sequencing note relies on.
   Re-ingestion and re-analysis stay independent in ownership (ingestion
   never writes analysis tables); the kick is just the trigger.
3. **Analysis retry budget lives on `traces`**, mirroring ingestion's
   durable counter: `analysis_attempts int not null default 0` +
   `analysis_attempted_at timestamptz`, claim-incremented by the task. The
   retry/DLQ middleware generalizes to trace-scoped tasks (label
   `retry_dlq_scope: trace`); backoff/budget reuse the existing
   `INGEST_RETRY_*` / `INGEST_MAX_ATTEMPTS` settings — the spec says "same
   retry/backoff/DLQ rules as ingestion", so no new knobs. Exhaustion
   writes `dead_letters` with the new `trace_id` set (and `upload_id` too —
   the trace knows its upload; ingestion rows leave `trace_id` null per
   spec). Permanent analysis errors (B2's `PermanentAnalysisError`)
   dead-letter immediately with attempts as-is — unlike ingestion there is
   no status column to mark, and the derived state needs a row to call the
   trace `failed`.
4. **`failed` derives from non-requeued analyze dead letters.**
   `analysis_state = failed` ⇔ a `dead_letters` row for `analyze_trace`
   with this `trace_id` and `requeued_at is null` exists. The requeue CLI
   gains a trace mode (`requeue trace <id>`): marks the dead letter
   requeued, resets `analysis_attempts`, re-kicks — the trace honestly
   returns to `pending`. This is also the "re-runs reproduce rows" lever
   for verification.
5. **Lost-analysis sweep.** `pending` is defined as "it will arrive"
   (4_pages.md), so the existing per-minute sweep also re-enqueues traces
   with no `trace_analysis` row, no open analyze dead letter, attempts
   below budget, and a stale `analysis_attempted_at` (same
   `SWEEP_STUCK_AFTER_MINUTES` timeout). Safe to double-fire — the job is
   idempotent.
6. **Skip-gate order: `owner_opt_out` before `not_configured`.** The worker
   evaluates the LLM gate itself (the judge's internal keyless check stays
   as defense-in-depth): trace private + owner's
   `allow_private_llm_analysis = false` → skip `owner_opt_out`; else
   `llm_configured()` false → skip `not_configured`; else run the judge.
   When both hold, consent dominates configuration — the owner said no, so
   that is the reason shown (and it makes the opt-out path testable in the
   keyless CI environment).
7. **The worker runs an explicit production set** — `signals`, `judge`, and
   any registered `metric:*` specs — never the registry wholesale (the
   `stub` analyzer stays a harness fixture, not a production row).
8. **The worker applies `finalize_verdict` before persisting.** The
   disagreement cap composes signals × verdict, which only the worker (and
   the offline `route` command) can see. The stored `trace_analysis` and
   judge `analyzer_results` rows carry the capped confidence; the uncapped
   share stays recoverable from the stored votes.
9. **Importer deltas:** `traces.total_tokens` = sum of span `total_tokens`
   (null when no span carries tokens — fail open, like `duration_ms` would);
   trace-name check adds a fallback — when root-span derivation yields an
   empty or bare-id-looking name (hex/uuid-shaped), use the upload's
   filename (sans extension). `import_payload` gains an optional
   `fallback_name`; the offline runner passes the fixture filename, the
   ingest task passes `uploads.filename`. Both are importer-version bumps.
10. **Outcome badge lands on all list surfaces, not just `/traces`.** The
    build order names the `/traces` analysis column, but list rows share
    one query and one card/row component family, and 4_pages' "labels at
    list level" law covers marketplace cards too. One shared
    `OutcomeBadge` (solid = human/human_confirmed, outline = machine,
    confidence as the raw number) + a quiet "not analyzed" placeholder,
    rendered on `/traces` rows (full analysis column with pending/skipped/
    failed states) and marketplace/library cards (badge only). Cheaper to
    do now than to special-case.
11. **A3 placeholders stay additive:** the analysis endpoint ships
    `open_review_item_id` always null (the schema field exists; A3
    populates); list rows do *not* ship `has_open_review_item` until A3.

Ratified 2026-06-11, all eleven as proposed (the discussion pass grouped
them into eight points; all confirmed). Notes from ratification: decision 1
gets a one-line stable-identity note in the stage-1 architecture spec;
decision 3 reuses the ingest retry knobs verbatim (no new env vars);
B2 is done (audit in flight), so the live-key verification step is
expected to pass.

## Plan

### Migration (`supabase/migrations/00000000000008_analysis.sql`)

- `analyzer_results` per `2_data-model.md`: id, `trace_id` → traces
  (cascade), `analyzer`, `analyzer_version`, `model_id` nullable, `output`
  jsonb, `confidence` numeric nullable, `created_at`. Index on `trace_id`.
  RLS select: owner of the referenced trace, or anyone authenticated when
  it is listed (mirrors traces).
- `trace_analysis` per `2_data-model.md`: `trace_id` PK → traces (cascade);
  label triplets (`outcome` check-constrained to the ternary,
  `*_confidence`, `*_provenance` check-constrained; `failure_mode` /
  `task_category` app-validated text, no check); the six promoted signal
  columns (all nullable); `metric_scores` jsonb nullable; `llm_status`
  check `complete | skipped`, `llm_skip_reason` check
  `not_configured | owner_opt_out` (null when complete); `analyzed_at`.
  No secondary indexes (PK-joined only). RLS select mirrors traces exactly.
  No insert/update policies for clients — only the worker (service role)
  and the API write here.
- `traces`: add `total_tokens integer`, `analysis_attempts integer not null
  default 0`, `analysis_attempted_at timestamptz`, and the unique
  constraint on `(upload_id, source_trace_id)` (decision 1).
- `dead_letters`: add `trace_id uuid references traces (id) on delete
  cascade` nullable; partial index on `(trace_id) where requeued_at is
  null` (backs the failed-state probe).

### Backend — stable identity (`worker/tasks/ingest.py`, `queries/traces.py`)

- `traces_q.insert` becomes `upsert` on `(upload_id, source_trace_id)`:
  update all normalized columns + `total_tokens`, reset
  `analysis_attempts = 0`, return the (stable) id and whether it existed.
  Discovery columns (`visibility`, `tags`, `description`, `listed_at`) are
  owner state, untouched by the rewrite.
- The ingest transaction: upsert each trace, `delete from spans where
  trace_id = …` + re-insert per trace, then delete traces of this upload
  whose `source_trace_id` is not in the new payload. The
  `delete_for_upload` pre-pass goes away. Remove the TODO.
- After commit: `analyze_trace.kiq(trace_id)` per trace (decision 2).

### Backend — `analyze_trace` (`worker/tasks/analyze.py`, `queries/analysis.py`)

The job, mirroring `ingest_upload`'s shape:

1. Claim: increment `analysis_attempts`, stamp `analysis_attempted_at`
   (one SQL update returning the attempt; trace gone → log + drop).
2. Dev fault check (see below).
3. Load `TraceInput` via the existing `fetch_trace_input`, plus the gate
   facts (trace visibility, owner's `allow_private_llm_analysis`).
4. Run `signals` via `run_analyzer`.
5. LLM gate (decision 6): skip with reason, or run `judge` (+ registered
   `metric:*`) via `run_analyzer`; apply `finalize_verdict` (decision 8)
   and patch the judge envelope's output/confidence with the capped
   verdict.
6. Persist in one transaction: delete this trace's `analyzer_results` +
   `trace_analysis`, insert the new envelopes verbatim, insert the
   promoted `trace_analysis` row — labels from the verdict (provenance
   `machine` where the value is non-null, null provenance where null),
   the six signal fields, `metric_scores` from any metric envelopes,
   `llm_status` / `llm_skip_reason`, `analyzed_at = now()`. **Human-field
   preservation:** read the prior row first; any label triplet with
   provenance `human` / `human_confirmed` is carried over the machine
   values (value + confidence + provenance) — never machine-overwritten.
7. Error classification: `PermanentAnalysisError` → immediate dead letter
   (decision 3); anything else propagates to the retry middleware.

Retry/DLQ middleware: generalized to read scope from the task label —
upload-scoped tasks keep today's behavior verbatim; trace-scoped tasks use
the `traces.analysis_attempts` budget and write `trace_id`-bearing dead
letters. No upload status side effects on the analysis path.

Sweep: add the stale-pending-analysis re-enqueue (decision 5) to the
existing minute task.

Dev faults: `X-Fault: analyze:<spec>` armed at upload time alongside the
ingest faults (`analyze:permanent | analyze:exhaust | analyze:transient:N`);
`analyze_trace` trips on the armed spec via its upload id. This is the
done-when's injected failure.

Requeue CLI (`cli/requeue.py`): `trace` mode per decision 4.

### Backend — API (`routers/traces.py`, `schemas/analysis.py`, `queries/analysis.py`)

- **Derived state** (one SQL shape, used by list + detail + analysis
  endpoints): `failed` if a non-requeued analyze dead letter exists, else
  `complete`/`skipped` from the row's `llm_status`, else `pending`.
- `GET /v1/traces/{trace_id}/analysis` — owner or listed (`get_visible`
  guard, 404-not-403). Response per 3_api.md: `analysis_state` (+
  `skip_reason`, + the dead-letter `last_error` verbatim on `failed`),
  `labels` (triplet objects), `reasoning`, `signals`, `metric_scores`,
  `open_review_item_id` (null, decision 11), `audit.analyzers` (analyzer,
  version, model_id, votes, rendering_truncated from the judge envelope).
  Built from the `analyzer_results` + `trace_analysis` rows; one new
  schema module mirrored to the frontend.
- `TraceListItem` gains `outcome`, `outcome_confidence`,
  `outcome_provenance`, `analysis_state`; `list_visible` left-joins
  `trace_analysis` (1:1 PK join) + the dead-letter exists probe.
- `TraceDetailResponse` gains the same four (the header label strip
  renders from detail; the section fetches the analysis endpoint) plus
  `total_tokens`.

### Frontend

- `lib/api/traces.ts`: list/detail type additions + `TraceAnalysis` type +
  `getTraceAnalysis`.
- `components/traces/badges.tsx`: `OutcomeBadge` (variant by provenance,
  raw confidence number) + `AnalysisStateBadge` (pending / skipped /
  failed / not-analyzed placeholder).
- `components/traces/analysis-section.tsx`, rendered by `TraceInspector`
  between the metadata header and the span tree; header gains the compact
  label strip. Disclosure order per 4_pages: labels (per-field provenance +
  confidence) → judge reasoning → signals → metric scores; audit details
  (versions, model id, stored votes) behind a collapsed disclosure. The
  four honest states verbatim: `pending` → "Analysis pending"; `skipped` →
  reason-specific copy (`not_configured` → "Judge not configured";
  `owner_opt_out` → "LLM analysis is off for your private traces", linking
  `/settings` for the owner) with signals still shown; `failed` → the real
  reason verbatim. Never a false pending.
- `traces-table.tsx`: analysis column (outcome badge or state); marketplace/
  library cards: outcome badge / placeholder (decision 10).

### Env + docs

No new env vars (decision 3 reuses ingest retry settings; analysis knobs
shipped with B0–B2). `.env.example` comment pointing `ANALYSIS_*` at the
worker too. README: analysis section note (keyless mode honest-skips).

### Tests

Integration (`tests/integration/test_analysis.py`; the suite env is
keyless, so `skipped/not_configured` is the CI-reachable complete-path):

- Upload a loop fixture → poll the analysis endpoint → `trace_analysis`
  row with real signal values (`has_retry_loop` true, counts); list rows
  carry `analysis_state`; keyless → `skipped` + `not_configured`, signals
  present, labels null.
- Opt-out: flip the profile toggle off, upload private → `owner_opt_out`
  (decision 6 precedence makes this reachable keyless).
- Injected failure: `X-Fault: analyze:exhaust` → dead letter with
  `trace_id`, `analysis_state = failed` with the reason verbatim;
  `analyze:permanent` → immediate fail; requeue CLI flips it back to
  pending and a clean re-run completes.
- Re-run reproduces rows: re-kick → same promoted values, fresh
  `analyzed_at`, exactly one `trace_analysis` row, envelope count stable.
- Human preservation: seed a `human`-provenance outcome via SQL, re-run →
  value/confidence/provenance intact, machine fields rewritten.
- Stable identity: requeue the upload (re-ingest) → same `trace_id`s,
  `trace_analysis` survives, spans rewritten.
- Access: non-owner on a private trace's analysis endpoint → 404; listed →
  readable.

Unit:

- Importer: `total_tokens` summing (incl. all-null → null), name fallback
  (bare-id root span → filename), golden updates for the version bump.
- Middleware scope split + permanent-analysis immediate dead-letter
  (mirrors the existing retry_dlq unit coverage).
- Derived-state function over the four condition combinations.

### Verification (done-when walkthrough)

1. Fresh `supabase db reset` + `docker compose up --build` (keyless);
   upload the dev dataset via CLI sync.
2. `/traces`: analysis column populates as the worker drains — `skipped`
   states, never fake pending; detail page Analysis section shows signals
   + "Judge not configured".
3. Add a provider key to the worker env, requeue one trace → `complete`
   with labels, reasoning, votes in the audit disclosure; confidence cap
   visible on a disagreement fixture (route fixtures from B2).
4. Toggle `/settings` LLM analysis off, upload a private fixture →
   `skipped / owner_opt_out` with the settings-linking copy.
5. `X-Fault: analyze:exhaust` upload → `/traces` shows `failed`, reason
   verbatim on detail; `requeue trace` → pending → complete.
6. Re-kick analysis on an analyzed trace → identical promoted row,
   re-ingest the upload → same trace ids, analysis intact.
7. Integration + unit suites green; ruff + format clean; `next build` +
   eslint clean.

## Drift

- **`reset_for_requeue` now accepts `complete` uploads** (was failed-only).
  The restriction existed because a re-ingest used to mint new trace ids
  (slice-3 audit observation); stable identity removes that hazard, and
  A5's redaction backfill ("re-enqueue ingestion … the existing requeue
  mechanism") plus this slice's stable-identity verification both need
  operator re-ingest of complete uploads. `make requeue` gained the
  `TRACE=<id>` form alongside `UPLOAD=<id>`.
- **Middleware label is `retry_dlq: upload | trace`** (plan said
  `retry_dlq_scope`); one label carrying the scope value reads cleaner than
  a flag plus a second label.
- **Post-commit analyze kick is best-effort** (log + continue on enqueue
  failure): the ingest transaction is already committed, so a failed kick
  must not error the task into the retry path — a complete upload can't be
  re-claimed, so the "retry" would burn budget into a misleading dead
  letter. The stale-pending-analysis sweep recovers lost kicks. (Found via
  the redaction re-ingest test, which runs `ingest_upload` in-process
  without a started broker.)
- **Compose env pass-through for `ANALYSIS_*` + provider keys** (null-value
  map entries): the worker container could otherwise never see a key, and
  an empty-string default (`${VAR:-}`) would poison the keyless skip —
  litellm treats an empty-string key as configured.
- **State derivation is one Python function** (`queries.analysis.
  derive_state`) fed by `llm_status` + a dead-letter exists probe selected
  in SQL, rather than a SQL `case` duplicated per query — one source of
  truth for all surfaces, unit-testable.
- The `not analyzed` placeholder also covers the complete-but-no-verdict
  edge (judge failed open on every field) at list level; the detail
  section still shows the full honest picture.

## Outcome

Done-when, verified 2026-06-11 against the running compose stack
(migration 8 applied; api/worker/scheduler rebuilt):

1. **Upload → `trace_analysis` row with real signals** —
   `test_real_signals_persisted_keyless_skip`: a payload with a genuine
   3× identical tool-call loop yields `has_retry_loop=true`,
   `loop_kind=exact_repeat`, `tool_call_count=3`, `llm_call_count=1`;
   `total_tokens=45` summed onto the trace; `failure_suspected` stored on
   the result row but absent from the API response.
2. **Keyless and opted-out runs show `skipped` with the right reason** —
   same test (`not_configured`, labels all null, audit = signals only) and
   `test_owner_opt_out_beats_not_configured` (private + opt-out skips as
   `owner_opt_out` even keyless, signals still present).
3. **Re-runs reproduce rows / stable identity** —
   `test_reingest_keeps_identity_and_reanalyzes`: requeue of a complete
   upload preserves `trace_ids`, re-analysis reproduces the signal row,
   and a seeded `human`-provenance outcome survives the machine rewrite.
4. **Injected failure dead-letters and surfaces as `failed`** —
   `test_injected_failure_dead_letters_and_requeues`
   (`analyze:permanent` → immediate dead letter with `trace_id`, state
   `failed` with the reason verbatim; `requeue trace` recovers) and
   `test_transient_failure_retries_to_success` (`analyze:transient:1` →
   budget burns to 2 attempts, no dead letter).
5. **Access** — `test_analysis_access_mirrors_trace_visibility`: private
   analysis 404s for non-owners; listing opens it.

Live-judge verification (key exported into the worker, then reverted):
`failure-trace.json` → `complete` with
outcome=failure / failure_mode=system_failure / task_category=web_research,
capped confidence 1.0, reasoning present, 9 stored votes on the judge
audit row, `model_id=openai/gpt-5-mini`.

Suites: unit 193 passed (one pre-existing flake in B2's
`test_llm.py::test_malformed_after_retry_raises_with_meta` — meta token
counts accumulate across the parse retry; B2-audit territory, observed
once and passing on re-run); integration 52 passed on the live stack;
ruff + format clean; `tsc --noEmit`, eslint, and `next build` clean.
