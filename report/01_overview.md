# Overview

Trace Marketplace is a marketplace for AI-agent trace data: contributors upload traces, consumers discover, inspect, acquire, and download them. Over the trial it grew from that core loop into a full data platform — passive capture from real agent sessions, server-side analysis into validated labels, human review of uncertain verdicts, redaction at ingestion, and subscriptions over the derived fields — all runnable locally from one repo, and deployed to production at [trace-mp.com](https://trace-mp.com).

## The Product

Two roles, one account type:

- **Contributors** get trace data in with as little friction as possible — drag a file into the web app, point the sync CLI at a directory of trace files or raw Codex/Claude Code/Cursor session logs, or let the desktop tray app watch folders in the background. Everything is private by default; listing on the marketplace is an explicit consent act.
- **Consumers** find data worth having: full-text search plus structured filters over analysis-derived fields (`outcome = failure`, `confidence ≥ 0.8`, `faithfulness ≥ 0.8`), per-span inspection of every listed trace, saved-query subscriptions that notify on new matches, and bulk acquisition into a library with zip + `labels.jsonl` downloads.

The connecting thesis: trace data is only worth discovering if the platform can say something *trustworthy* about it. So every ingested trace is analyzed — deterministic signals, an LLM outcome judge, quality metrics — and the labels carry per-field confidence and provenance, with uncertain verdicts routed to a human review queue rather than published as fact.

## What Was Built

### Stage 1 — Platform

The foundational loop: upload an OTLP JSON trace file → validation → raw payload preserved verbatim in storage (content-hash keyed) → async ingestion by a worker (Redis queue, retries, dead letters) into a canonical trace/spans shape → full span-tree inspection → list with ownership confirmation → marketplace search → $0 acquisition → byte-identical raw download. Supabase auth and Postgres with every access rule enforced twice (API query + RLS), rate limiting, and a smoke script covering the whole demo path.

### Stage 2 — Passive Capture, Analysis, Subscriptions

Built as two parallel streams against a frozen analyzer contract:

- **Machine door**: upload-only API keys, a stateless sync CLI (`sync` + `watch`, server-side sha256 dedupe), an `/uploads` page surfacing failures that happen while nobody watches, and native session ingestion — raw Codex / Claude Code / Cursor session JSONL converts server-side into per-turn traces.
- **Analysis pipeline**: three analyzer families on the existing worker machinery — deterministic signals (always run), a composed LLM outcome judge with self-consistency voting (ternary outcome, AgentRx failure taxonomy, task category), and quality-metric critics + RAGAS collections. Without an LLM key the system degrades honestly: signals run, LLM fields stay null with a recorded skip reason, never a fake "pending".
- **Human-in-the-loop**: disagreement, indeterminate, and low-confidence verdicts create review items; resolving writes labels with `human` provenance and confidence 1.0; machine re-runs never overwrite human fields.
- **Redaction**: credential and pattern-PII scrubbing at ingestion (detect-secrets + in-house recognizers, deterministic HMAC placeholders). Owners see raw; every other surface — inspection, downloads, the LLM analyzers — sees scrubbed.
- **Discovery at scale**: one filter language across search and subscriptions, event-driven subscription matching with backfill preview, bulk acquire / list / download.
- **Validation**: benchmark→OTLP converters and offline agreement scripts that measure the *shipped* pipeline against expert human labels (numbers below).

### Beyond the Base Scope

- **Production deployment**: Terraform-managed AWS stack (ECS Fargate, ALB + WAF, ElastiCache, Supabase Cloud) serving [trace-mp.com](https://trace-mp.com), deployed from GitHub Actions via OIDC.
- **Desktop app**: a Tauri tray app wrapping the sync loop — watches folders, auto-detects agent session directories, fires native notifications, resolves review items in-app; distributed as a `.dmg` via GitHub Releases.
- **Similar-behavior extension**: per-trace embeddings computed at analysis, a similar-traces lookup, and behavior-anchored subscription matching — an embedding predicate that stays inside the deterministic-matching rule.
- **UI redesign pass**: a coherent design system (`DESIGN.md`), light/dark schemes, realtime trace lists.

## Headline Outcomes

- **The judge's quality is measured, not asserted**: 87.9% outcome agreement with expert annotators on decided traces (200-trajectory AgentRewardBench slice), 51% failure-mode category match on judge-flagged failures (73-trajectory AgentRx corpus) — measured through the shipped importer, renderer, and prompts, not a lab harness.
- **The quality metrics too**: the hallucination critic agrees with human PASS/FAIL labels on 88.8% of traces (90.4% precision) across a 294-trace HaluBench slice; RAGAS faithfulness separates the classes at AUC 0.77.
- **Provenance is never lost**: raw payloads are preserved verbatim and download byte-identical; ingestion is a pure function of the raw payload (delete-and-rewrite, one transaction), so re-ingestion is idempotent by construction.
- **A real privacy boundary**: detected credentials and PII never leave the owner's view — not in other users' inspection, not in acquirer downloads, not in prompts sent to the LLM provider — and private-trace LLM analysis has a per-account opt-out.
- **Honest failure everywhere**: typed permanent/transient error classification, dead letters with one-command requeue, keyless degradation with recorded reasons, and failure notifications for uploads nobody was watching.

## How to Read This Report

[02](02_architecture.md)–[06](06_privacy-and-redaction.md) cover the system itself, roughly in data-flow order: architecture, ingestion, analysis, marketplace, privacy. [07](07_engineering-practices.md)–[09](09_limitations-and-future-work.md) cover the judgment behind it: process, the material decisions and trade-offs, and an honest account of limitations. To verify any of it hands-on, go straight to the [evaluation guide](10_evaluation-guide.md) — the full system runs locally with three commands, and every claim above has a runnable demo behind it.
