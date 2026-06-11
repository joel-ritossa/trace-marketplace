# Decisions & Trade-offs

The calls that shaped the system: what was decided, why, and what each call cost. The raw material is the locked-decision tables in the stage specs (`docs/spec/stage-1/0_README.md`, `docs/spec/stage-2/0_README.md`) — this doc adds the reasoning. Mechanisms live in [02](02_architecture.md)–[06](06_privacy-and-redaction.md); each entry links rather than repeats.

## Architecture

**One Python codebase, three entrypoints.** API, worker, and scheduler run from one image (`services/api`) with different entrypoints. Models, queries, and typed exceptions are shared without packaging; an analyzer change and its task wiring are one diff. Cost: the services can't diverge dependencies — irrelevant at this size.

**A queue and a dedicated worker from day one.** Inline ingestion would have been less work for a demo. Rejected because async reliability — retries, dead letters, horizontal scaling, the stuck-upload sweep — *is* the data-platform substance the trial is meant to demonstrate, not hardening to defer. Cost: four app containers instead of two, accepted as the point.

**Redis broker, Postgres state of record.** Redis over a Postgres-native queue (queue churn stays off the primary database) and over RabbitMQ (one container serves both queueing and rate limiting); taskiq over Celery for an asyncio-native queue with little operational surface on a codebase that is async end-to-end. The real trade: the Redis list broker has no acks, so a crash can drop an in-flight message. Instead of buying broker durability, the design makes Postgres the source of truth and a 60-second sweep re-enqueues stuck uploads — a lost message costs at most ~11 minutes of latency, never the upload ([explainer](../docs/explainers/trace-upload-delivery-guarantee.md)). Same logic rejects exactly-once machinery: at-least-once delivery plus an idempotent consumer is sufficient once re-runs are free.

**Supabase for Postgres, auth, storage, and realtime.** One dependency covers four concerns and runs both as a local CLI stack and a managed cloud project — fitting the run-it-locally constraint without a separate production architecture. Cost: vendor coupling, plus the discipline of mirroring every access rule as an RLS policy. The mirror earned its keep when the browser later got a real Supabase session for realtime invalidation — RLS is load-bearing on that path ([02](02_architecture.md)).

**Ingestion is a pure function of the raw stored payload.** Raw bytes are preserved verbatim; everything else is derived by delete-and-rewrite in one transaction. Why: retries, requeues, duplicate deliveries, and redaction-ruleset upgrades all reduce to "run it again". Cost: every importer change must preserve the invariant, and rewrite identity took two spec amendments to get right — stable trace identity at A2, owner-scoped adoption at A6 — so that acquisitions, human labels, and review items never cascade away under a rewrite (`docs/spec/stage-1/6_architecture.md`).

## Data & Matching

**Deterministic matching everywhere; non-determinism only in derivation.** LLMs derive fields; rules match on the stored values like any column — never an LLM at query time. Why: a stored subscription must mean the same thing on every trace and every evaluation, and a match must be explainable after the fact. Cost: no fuzzy queries in the base build. The similar-behavior extension added behavior search without breaking the rule — embedding (derivation) is non-deterministic, matching is a SQL distance comparison against a stored vector ([05](05_marketplace.md)).

**Rarity is filterability.** Rare data needed no dedicated mechanism: sparse label combinations (`task_category` × `failure_mode`, signal flags, metric bounds) are discoverable and subscribable like any other query. Behavioral novelty scoring — ranking by how unusual a trace's behavior is — was designed as an extension that orders results but never changes what matches (`docs/extensions/behavioral-novelty.md`).

**Stateless CLI, server-side dedupe.** No local manifest; the server's per-user sha256 check at POST is the only truth. Why: nothing to corrupt, migrate, or explain — re-syncing any directory from any machine is safe by construction. Cost: already-synced files re-upload their bytes each run to be told `409 duplicate`. The desktop app layers a local synced-file memo on top as an optimization, without making it state of record ([03](03_ingestion-and-data.md)).

**One filter language.** Search, subscriptions, and the feed share one Pydantic model and one SQL clause builder; stored queries are validated at write time so they can never fail to execute later. Why: a filter added once works everywhere, and a saved subscription is exactly a marketplace search. Cost: the vocabulary is a contract — every new field has to make sense in both contexts, which is why stage 2 admits only equality filters, booleans, and min-bounds ([05](05_marketplace.md)).

## Analysis

**Ternary outcome.** `indeterminate` is a designed answer, valid from machine and human alike. Some traces genuinely can't be judged; a forced binary would publish false consensus as fact on a marketplace whose value is label trustworthiness.

**Vote-share confidence, capped on disagreement.** Confidence is the vote share of N judge runs, hard-capped at 0.5 when the deterministic signals contradict the verdict, 1.0 on human resolution. Why: defined, explainable semantics a consumer can filter on — not a pseudo-probability. Cost: it is not a calibrated probability, and the system never pretends otherwise — nothing gates on confidence; consumers set their own bar in queries.

**The outcome judge is clean-room; signals route, never anchor.** Deterministic signals are deliberately excluded from the outcome call, because an anchored judge can't disagree with the signals — and signals/judge disagreement is the trigger that routes to human review. The failure-mode call *does* get the evidence: anchoring matters for the verdict, not for diagnosing a declared failure ([04](04_analysis-pipeline.md)).

**HIL routing only on the outcome judge, and low confidence blocks nothing.** Human attention is the scarce resource, so only label-bearing verdicts route, on four recorded reasons, at most one open item per trace. Machine labels are stored and filterable immediately; the review item exists alongside them. Cost: an uncertain label is live until a human resolves it — mitigated by confidence and provenance being filterable, so consumers can exclude machine-only or low-confidence labels themselves.

**No feedback fine-tuning, no retroactive re-judging.** Human resolutions correct the trace's own labels and are never machine-overwritten; that is the whole base loop. Each step further (exemplar pools, retroactive re-judging on version bumps) trades auditability for accuracy that hadn't been demonstrated — a label whose history can't be explained is worse for a marketplace than a slightly staler one. Both next steps are written up as extensions the schema already supports ([04](04_analysis-pipeline.md)).

**Degrade honestly without an LLM key.** Signals run, LLM analyzers skip with a recorded reason, fields stay null — never a fake "pending". An evaluator without a key still sees a truthful system, and `null` never matches a filter predicate, so degradation can't pollute subscriptions.

## Privacy

**Scrub at ingestion, not at read.** The `spans` table itself holds the scrubbed form, so every reader — search, inspection, the LLM analyzers — is clean automatically, with no per-endpoint scrub call to forget. Cost: a ruleset upgrade requires an explicit re-ingest (no auto-backfill), and single-representation fields (trace and span names) are scrubbed for the owner too ([06](06_privacy-and-redaction.md)).

**Placeholders over removal.** Detected values become deterministic HMAC placeholders (`<EMAIL_3f9a2c1d>`), salted per upload. The same value reads coherently within an upload — for human readers and analyzers alike — while staying unlinkable across uploads and unrecoverable. Plain deletion would have destroyed exactly the structure a judge or reviewer needs to follow the trace.

**Patterns, not NER.** Model-based entity detection misfires on structured trace JSON, so detection is `detect-secrets` plus in-house pattern recognizers, with the misses stated plainly (free-text names and addresses are not caught) and every detection error failing toward masking, never leaking ([06](06_privacy-and-redaction.md)). The ruleset is versioned code, not env vars — a deliberate exception to the everything-is-an-env-var rule, because tunable detection would break determinism and make the recorded version meaningless.

**Per-account LLM opt-out, scoped to private traces.** `allow_private_llm_analysis` (default on) excludes an account's private traces from the provider data flow; deterministic signals still run. Listed traces are always analyzed — the marketplace can't say anything trustworthy about an unanalyzed listing, and listing is the consent act that covers it.

## Product

**Listing is the consent act.** One explicit, server-enforced act (`confirm_ownership: true`, 422 without it) covers everything that follows: discoverability, LLM analysis, subscription matching, scrubbed acquirer downloads. Bulk listing keeps the same shape — one confirmation naming the exact count, never implied consent. Everything is private by default on every upload path.

**No auto-acquire anywhere.** Subscriptions watch; humans take. A match produces a notification and a feed entry; acquiring is always a deliberate multi-select and confirm. Why: an entitlement is a real object — a robot creating them on a consumer's behalf removes exactly the judgment the marketplace exists to support. Cost: one extra click per match, accepted.

**In-app-only notifications, one routed page.** Notifications are server-generated rows only (no client ever creates one), digested per upload and per subscription with flood control enforced by Postgres constraints, surfaced on a single `/notifications` page — no popover panel, no email/push in trial scope. The desktop tray app later added native notifications on top without changing the server model ([05](05_marketplace.md)).

**$0 pricing, real entitlements.** Acquisition is its own object (`acquisitions` row, `price_usd` defaulting to 0, unique consumer/trace pair) so pricing can attach later without remodeling — but checkout, licensing, and payouts add no signal to a two-day trial. What the trial demonstrates is the entitlement mechanics: library, idempotent acquire, download rights.

## Roads Not Taken

Options considered and rejected, with what would change the call:

- **Embedding search in the base build.** Rejected to keep matching deterministic and the base scope small. Revisited only after a research pass showed the judge-rendering representation actually retrieves behavior (`sandbox/behavior-similarity/_FINDINGS.md`), and then shaped as an explicit anchor-trace predicate that preserves deterministic matching — not free-text vector search, which would change matching semantics and remains unbuilt.
- **NER for PII.** Rejected for its false-positive rate on structured trace JSON. A detector validated on trace-shaped data — or a corpus showing heavy free-text PII traffic — would reopen this; until then the misses are documented rather than papered over.
- **Browser-automation testing.** Rejected as too slow for the trial loop (rule in `AGENTS.md`); UI work is verified by the integration suite, the smoke script, and curl, with click-through left to a human. A longer window with a CI budget would change this call.
- **Per-trace job fan-out.** One ingestion job per upload, deliberately; the split (a parse job fanning out per-trace normalize jobs) is designed in the spec but unbuilt — waiting for evidence of uploads big enough to care (`docs/spec/stage-1/6_architecture.md`).
- **Generated TS client from the OpenAPI schema.** The stage-1 scope deferred the generated-client CI check; the shipped web app hand-mirrors request/response types from the Pydantic schemas under keep-in-sync markers — a recorded deviation from the original derive-from-OpenAPI intent ([07](07_engineering-practices.md)). Wiring up generation is mechanical future work.
- **Trace sets, payments, orgs, moderation.** Deferred whole stages, not partially built: acquisitions are per-trace and $0, accounts are flat. `upload_id` already preserves arrival grouping, so sets can become marketplace objects later without re-ingesting anything.

The longer list of designed-for extensions — bounties, behavioral novelty, session stitching, exemplar feedback — lives in [09](09_limitations-and-future-work.md) and `docs/extensions/`.
