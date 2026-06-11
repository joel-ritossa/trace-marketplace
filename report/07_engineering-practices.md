# Engineering Practices

How the project was run, not just what it produced: a normative spec drove a sliced build order, every slice left a buildlog trail (plan, drift, verification, audit), and testing ran integration-first against the real stack. The process artifacts are all in the repo — nothing below is reconstructed after the fact.

## Spec-First Process

The discipline: `docs/spec/` is normative, and decisions get resolved there before code. When implementation hit a question the spec didn't answer, the answer went into the spec first — the stage-2 buildlog index records two pre-build spec amendments (the private-trace LLM opt-out, the realtime-invalidation rule) made exactly this way (`docs/buildlog/stage-2/README.md`).

The build ran in slices, each with an explicit "done when":

- **Stage 1** (`docs/spec/stage-1/5_build-order.md`) — four sequential slices from walking skeleton to discovery/acquisition, each verified on a fresh `docker compose up`.
- **Stage 2** (`docs/spec/stage-2/6_build-order.md`) — two parallel streams: A (platform: machine door, analysis plumbing, HIL, discovery at scale, redaction) and B (analysis core: signals, judge, metrics, validation). B0 froze the analyzer contract before anything else; A-slices wired stub analyzers behind that contract until the matching B-slice merged. B-slices verified offline (runner + pytest, no Compose), A-slices on the live stack.

The freeze is what made the two-day window workable: platform and analysis work proceeded simultaneously without either blocking the other, and the merge points were mechanical because the contract never moved.

Every slice has a directory in `docs/buildlog/` — 21 slice directories, 53 numbered pass records. `000_implementation.md` holds the plan written *before* coding, a Drift section logging every deviation during implementation, and an Outcome verifying the done-when. Twelve slices carry an audit pass (`001_audit.md`): a read-everything code review across fixed axes (`.cursor/skills/code-audit/SKILL.md`) that reports findings without editing, implements only after approval, and re-verifies.

## Testing Strategy

The bar is the real system, not mocks. The integration suite (85 test functions, `services/api/tests/integration/`) runs against a live `supabase start` + `docker compose up` stack — real Postgres, real Redis, real worker — with a fresh user per test so rate-limit buckets and dedupe state never leak between tests. It covers ingestion, reliability (retries, dead letters, the sweep), redaction boundaries, the machine door, HIL, discovery at scale, and similar-behavior.

Unit tests (283 test functions) are kept to where mocks earn their keep: importer edge cases, error classification, filter-query parsing, judge voting and routing math. Golden-file tests pin the deterministic surfaces — importer output, the judge's trace rendering, signal extraction — against expected JSON (`tests/unit/golden/`), so an unintended change to what the LLM sees fails a diff, not a vibe check.

Two more layers sit outside pytest:

- **The smoke script** (`tools/smoke.py`, `make smoke`) is the stage-1 demo script made executable: two throwaway accounts run upload → ingest → inspect → list → search → acquire → download against the live stack, asserting a byte-identical raw download, exiting non-zero on the first failed step.
- **Analyzer quality** is measured separately, against expert-labeled benchmarks through the shipped pipeline — converters, offline runner, one-command agreement reports ([04](04_analysis-pipeline.md)).

Two deliberate scoping calls. No browser automation: UI work is verified by the test suite, the smoke script, and curl; click-through verification is left to a human (rule in `AGENTS.md`). And CI is thin: the deploy workflow builds and ships images, the CLI release workflow runs the CLI's pytest suite before publishing to PyPI — but the API suite runs locally against Compose, not in CI. For a two-day trial the local suite was the gate; a CI test job is straightforward future work.

## Code Organization

One canonical home per concern, repo-wide. Backend: one router plus one queries module per domain, routes thin, SQL in the queries layer, Pydantic models at every boundary (requests, responses, task payloads), typed permanent/transient exceptions in one place. The payoff shows where reuse matters: one `filter_clauses` builder serves search, subscriptions, and the feed ([05](05_marketplace.md)); one litellm wrapper (`app/analysis/llm.py`) is the only LLM call site.

Frontend: a single API client layer (`apps/web/src/lib/api/`) with request/response types hand-mirrored from the Pydantic schemas under keep-in-sync markers — a recorded deviation from the original generate-from-OpenAPI intent ([02](02_architecture.md)). UI primitives are shadcn/ui components themed by `DESIGN.md` tokens; no per-page restyling, light and dark schemes from one token ladder.

Database: schema changes only as new ordered migrations (15 in `supabase/migrations/`; applied migrations are never edited), and every access rule exists twice — API query and RLS policy ([02](02_architecture.md)).

Toolchain: Python 3.12 with uv, ruff (lint + format), pytest; TypeScript with pnpm and a strict `tsconfig`.

## Documentation as a Deliverable

Three documentation types ship with the code, each with a maintenance rule that keeps it from rotting:

- **Explainers** (`docs/explainers/`, 3) — canonical answers to recurring "how does X behave?" questions: the upload delivery guarantee, what the judge sees when a trace renders, the redaction boundary. Descriptive, not normative — if an explainer and the spec disagree, code or spec gets fixed first. Updated in the same pass as any behavior change.
- **Demos** (`docs/demos/`, 6) — runnable walkthroughs of behavior worth showing but non-obvious to exercise: large-trace handling, CLI sync, the HIL loop, judge agreement, metric agreement, subscriptions. Each is steps / what was solved / why it's interesting, with code pointers. The rule: a demo that doesn't run is worse than none, so demos update in the same pass as anything that breaks them.
- **The buildlog** (`docs/buildlog/`) — the record of how each slice actually went: plan, drift, verification, audit findings. It is a record, not a spec; the spec stays in `docs/spec/`.

## Tooling & Operations

Operator actions are one Makefile command each:

| Command | Does |
|---|---|
| `make smoke` | Full stage-1 demo loop against the live stack |
| `make seed` / `make seed-dev` | Populate the marketplace with fixtures / real benchmark traces |
| `make seed-demo EMAIL=…` | Full live demo state for one account (traces, review queue, notifications, subscriptions); `WIPE=1` re-seeds clean |
| `make requeue UPLOAD=… \| TRACE=…` | Recover dead-lettered ingestion / re-run analysis |
| `make allow EMAIL=…` | Allowlist an email or domain for sign-up |
| `make dev-dataset` / `make link-sessions` | Pull benchmark traces / symlink local agent session logs for the sync CLI |
| `make web-dev` | Swap the containerized web build for a hot-reload dev server |

Failure paths are demoable, not just claimed: an opt-in `X-Fault` header on uploads (`dev_routes`, off by default so a deployment that forgets it gets the safe outcome) injects `transient:N`, `exhaust`, or `permanent` faults into ingestion or analysis — driving the retry, dead-letter, and immediate-fail paths on demand. An `analyze:verdict:…` spec substitutes a canned judge verdict, so the entire HIL routing → digest → queue → resolve loop runs on a stack with no LLM key (`app/dev/faults.py`; used by [docs/demos/hil-loop.md](../docs/demos/hil-loop.md)).

Deployment is push-driven: merging to main builds and deploys to production via GitHub Actions with OIDC (no long-lived AWS keys); tag-driven workflows publish the CLI to PyPI (tag must match the package version, tests run first) and the desktop `.dmg` to GitHub Releases. The production architecture itself is in [02](02_architecture.md).
