---
name: code-audit
description: Run a post-implementation code audit of a build slice in the trace-marketplace repo. Use when the user asks to audit, review, or code-review a slice or a body of recently implemented code. Produces a read-only findings report across fixed audit axes, implements fixes only after explicit approval, and records the pass in the slice buildlog.
---

# Code Audit

Post-implementation review pass for a slice (see `docs/buildlog/stage-1/README.md`
for where this fits in the slice process). Findings first, fixes only after
approval, everything recorded in the buildlog.

## Process

1. **Read everything in scope.** All code the slice touched, across every
   surface: backend (`services/api/`), frontend (`apps/web/`), infra
   (compose, migrations, env files, Dockerfiles).
2. **Report findings — no edits.** Walk the audit axes below. Present a
   categorized findings list to the user. Do not change code yet.
3. **Discuss.** Resolve disagreements or open design questions before
   implementing anything.
4. **Implement on approval.** Fix approved findings in one pass.
5. **Re-verify end to end.** Lint (`ruff check`, eslint), builds
   (`next build`), compose rebuild, and the slice's done-when criteria.
6. **Document.** Write findings + fixes to the slice's next numbered buildlog
   file (`docs/buildlog/stage-1/slice-N/00N_audit.md`).

## Audit axes

Walk each axis explicitly; say so if an axis is clean.

1. **Correctness** — real bugs: failures reported as success, unhandled error
   paths, missing-claim/null crashes, race conditions, wrong status codes.
2. **Spec conformance** — API shapes, error envelope, and behavior match
   `docs/spec/stage-1/` exactly. The spec is normative.
3. **Modularity & file structure** — files growing into grab-bags (e.g.
   response models in `main.py`); enforce the routers/schemas/queries/worker
   layout on the backend and `lib/` separation (env, api client, types) on the
   frontend. Shared code over duplication, FE and BE.
4. **Future-proofing** — hardcoded values that should be config, defaults that
   are wrong for cloud deployment, dev-only surfaces not flag-gated, missing
   required-at-startup validation.
5. **Security & auth** — token verification (algorithms, required claims), RLS
   coverage, secrets or raw trace bodies in logs, CORS scope.
6. **Reliability invariants** — per AGENTS.md: idempotent ingestion, worker
   resource lifecycles (DB pools), retry/DLQ behavior, no silently dropped
   jobs.
7. **Consistency** — naming, error handling style, and patterns match the rest
   of the codebase; one way of doing each thing.

## Findings format

Group by category with severity per finding:

- **Bug** — incorrect behavior; must fix.
- **Spec violation** — diverges from `docs/spec/stage-1/`; must fix or amend spec.
- **Modularity** — structural debt worth paying down now.
- **Future-proofing** — fine locally, breaks or bites in deployment.
- **Nit** — optional polish.

For each finding: file/location, what's wrong, why it matters, proposed fix.
