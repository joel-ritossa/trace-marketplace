# Phase 04: DB And API Design

## Purpose

Design the persistence and API surface needed to support the confirmed data lifecycle and user flows.

## Focus Questions

- Which tables are needed for upload, ingestion, traces, spans, events, artifacts, annotations, search, and listings?
- Which API endpoints are needed by the first pages, including trace download?
- What job states and error states must be visible to users?
- What access and visibility rules must the API enforce?
- What can stay JSONB or derived for v1 instead of becoming a first-class table?

## Outputs

- Initial database model.
- API route list.
- Request and response shapes.
- Job state model.
- Error response contract.
- Search and filter semantics.

## Existing Docs

- [Architecture proposal](../../architecture-proposal.md)

## Decision Gate

Before moving on, each page should have a clear API path for loading, mutating, and displaying its required states.
