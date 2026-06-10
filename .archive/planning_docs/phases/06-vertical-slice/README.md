# Phase 06: Vertical Slice

## Purpose

Build the smallest complete implementation that proves the trace foundation works end to end.

## Target Slice

The first slice should let one person exercise both contributor and consumer paths:

1. Start the app.
2. Upload a synthetic or scrubbed trace.
3. See validation and ingestion status.
4. Open the parsed trace.
5. Inspect normalized timeline or event details.
6. Search for the trace by safe metadata.
7. Mark the trace shared or listed.
8. Find the listed trace from the marketplace or library view.
9. Download the allowed trace export.

## Outputs

- Working upload path.
- Raw trace preservation.
- Parser for the first supported format.
- Normalized storage.
- Searchable metadata.
- Trace detail view.
- Listing or visibility control.
- Download path for allowed traces.
- Smoke test for the demo path.

## Existing Docs

- [Architecture proposal](../../architecture-proposal.md)
- [Expectations synthesis](../../expectations-synthesis.md)

## Decision Gate

Before broadening features, the vertical slice should work repeatedly from clean local setup with synthetic fixtures.
