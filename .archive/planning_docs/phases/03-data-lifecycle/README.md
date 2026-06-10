# Phase 03: Data Lifecycle

## Purpose

Define how trace data moves from user input to stored, searchable, inspectable, and shareable records.

## Focus Questions

- What raw inputs are accepted first?
- What validation happens before raw preservation?
- What does the canonical trace shape look like?
- Which fields are safe to search, summarize, or expose in listings?
- How are privacy findings, redaction state, parser errors, and provenance represented?

## Outputs

- Trace lifecycle diagram or numbered flow.
- Accepted input format for the first demo.
- Canonical trace shape.
- Validation and ingestion states.
- Privacy, redaction, and provenance rules.
- Searchable metadata inventory.

## Existing Docs

- [Architecture proposal](../../architecture-proposal.md)
- [Open-source tracing research](../../research/llm-trace-interoperability.md)
- [Open question: open-source tracing](../../questions/001_open_source_tracing_open.md)

## Decision Gate

Before moving on, the project should define the canonical trace shape and the difference between raw private trace content, safe previews, searchable metadata, and marketplace listing fields.
