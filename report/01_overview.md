# Overview

Trace Marketplace is a marketplace for AI-agent trace data: contributors upload traces, consumers discover, inspect, acquire, and download them. Over the trial it grew from that core loop into a full data platform — passive capture from real agent sessions, server-side analysis into validated labels, human review of uncertain verdicts, redaction at ingestion, and subscriptions over the derived fields — all runnable locally from one repo, and deployed to production at [trace-mp.com](https://trace-mp.com).

## The Product

Two roles, one account type:

- **Contributors** get trace data in with as little friction as possible — drag a file into the web app, point the sync CLI at a directory of trace files or raw Codex/Claude Code/Cursor session logs, or let the desktop tray app watch folders in the background. Everything is private by default; listing on the marketplace is an explicit consent act.
- **Consumers** find data worth having: full-text search plus structured filters over analysis-derived fields (`outcome = failure`, `failure_mode = invalid_invocation`, `llm_call_count ≥ 50`), per-span inspection of every listed trace, saved-query subscriptions that notify on new matches, and bulk acquisition into a library with zip + `labels.jsonl` downloads.

The connecting thesis: trace data is only worth discovering if the platform can say something *trustworthy* about it. So every ingested trace is analyzed — deterministic signals plus an LLM agent judge that returns span-anchored verdicts turn by turn — and the turns the judge was unsure about go to a human review queue rather than being published as fact. (The trial's original judge used voted calls with confidence and quality metrics; see the note in [04](04_analysis-pipeline.md).)

## What Was Built

### Stage 1 — Platform

The foundational loop: upload an OTLP JSON trace file → validation → raw payload preserved verbatim in storage (content-hash keyed) → async ingestion by a worker (Redis queue, retries, dead letters) into a canonical trace/spans shape → full span-tree inspection → list with ownership confirmation → marketplace search → $0 acquisition → byte-identical raw download. Supabase auth and Postgres with every access rule enforced twice (API query + RLS), rate limiting, and a smoke script covering the whole demo path.

### Stage 2 — Passive Capture, Analysis, Subscriptions

Built as two parallel streams against a frozen analyzer contract:

- **Machine door**: upload-only API keys, a stateless sync CLI (`sync` + `watch`, server-side sha256 dedupe), an `/uploads` page surfacing failures that happen while nobody watches, and native session ingestion — raw Codex / Claude Code / Cursor session JSONL converts server-side into one trace per session (turns as spans, subagents nested).
- **Analysis pipeline**: on the existing worker machinery — deterministic signals (always run, per turn) and an OpenAI Agents SDK judge: one agent per turn explores the trace through tools and returns an outcome, multi-select task categories and AgentRx failure modes anchored to cited spans; a roll-up writes the session verdict. (Originally a voted judge plus quality-metric critics; both retired — [04](04_analysis-pipeline.md).) Without an LLM key the system degrades honestly: signals run, LLM fields stay null with a recorded skip reason, never a fake "pending".
- **Human-in-the-loop**: a trace with turns the judge could not judge confidently gets one review item; owners relabel turns, which become `human` and are never re-judged.
- **Redaction**: credential and pattern-PII scrubbing at ingestion (detect-secrets + in-house recognizers, deterministic HMAC placeholders). Owners see raw; every other surface — inspection, downloads, the LLM analyzers — sees scrubbed.
- **Discovery at scale**: one filter language across search and subscriptions, event-driven subscription matching with backfill preview, bulk acquire / list / download.
- **Validation**: benchmark→OTLP converters and offline agreement scripts that measured the original voted judge against expert human labels (numbers below; the scripts were retired with that judge and the per-turn agent has not been re-measured).

### Beyond the Base Scope

- **Production deployment**: Terraform-managed AWS stack (ECS Fargate, ALB + WAF, ElastiCache, Supabase Cloud) serving [trace-mp.com](https://trace-mp.com), deployed from GitHub Actions via OIDC.
- **Desktop app**: a Tauri tray app wrapping the sync loop — watches folders, auto-detects agent session directories, fires native notifications, lists review items in-app; distributed as a `.dmg` via GitHub Releases.
- **Similar-behavior extension**: per-trace embeddings computed at analysis, a similar-traces lookup, and behavior-anchored subscription matching — an embedding predicate that stays inside the deterministic-matching rule.
- **UI redesign pass**: a coherent design system (`DESIGN.md`), light/dark schemes, realtime trace lists.

## Headline Outcomes

- **The original judge's quality was measured, not asserted** (before the 2026-11-10 agent redesign, not re-measured since): 87.9% outcome agreement with expert annotators on decided traces (200-trajectory AgentRewardBench slice), 51% failure-mode category match on judge-flagged failures (73-trajectory AgentRx corpus) — measured through the shipped importer, renderer, and prompts, not a lab harness.
- **The quality metrics too** (retired with the redesign): the hallucination critic agrees with human PASS/FAIL labels on 88.8% of traces (90.4% precision) across a 294-trace HaluBench slice; RAGAS faithfulness separates the classes at AUC 0.77.
- **Provenance is never lost**: raw payloads are preserved verbatim and download byte-identical; ingestion is a pure function of the raw payload (delete-and-rewrite, one transaction), so re-ingestion is idempotent by construction.
- **A real privacy boundary**: detected credentials and PII never leave the owner's view — not in other users' inspection, not in acquirer downloads, not in prompts sent to OpenAI — and private-trace LLM analysis has a per-account opt-out.
- **Honest failure everywhere**: typed permanent/transient error classification, dead letters with one-command requeue, keyless degradation with recorded reasons, and failure notifications for uploads nobody was watching.

## How to Read This Report

[02](02_architecture.md)–[06](06_privacy-and-redaction.md) cover the system itself, roughly in data-flow order: architecture, ingestion, analysis, marketplace, privacy. [07](07_engineering-practices.md)–[09](09_limitations-and-future-work.md) cover the judgment behind it: process, the material decisions and trade-offs, and an honest account of limitations. To verify any of it hands-on, go straight to the [evaluation guide](10_evaluation-guide.md) — the full system runs locally with three commands, and every claim above has a runnable demo behind it.
