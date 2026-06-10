# User Types And Flows

## Purpose

Trace Marketplace v1 has two product user types. This keeps the first user-flow definition focused on the upload, ingestion, search, inspection, and download foundation without modeling marketplace operations that are not needed yet.

## Trace Contributor

A trace contributor is a person or team that has AI-agent trace data and wants to upload, validate, inspect, manage, and eventually share or list it.

Primary goals:

- Contribute trace data with clear ownership and provenance.
- Understand upload and ingestion progress, including whether follow-up is needed.
- Inspect parsed traces and derived metadata before exposing them to others.
- Control whether traces remain private, are shared, or become discoverable.

V1 implications:

- Contributor flows should prioritize upload, validation feedback, ingestion status, trace inspection, and visibility controls.
- Contributor-facing language should avoid assuming that every uploaded trace is immediately public or for sale.
- The contributor owns uploaded traces unless a later access model says otherwise.

## Trace Consumer

A trace consumer is a person or team looking for useful trace data to discover, inspect, evaluate, learn from, benchmark against, and download when access allows it.

Primary goals:

- Discover traces by search, filters, tags, metadata, tools, models, errors, or value signals.
- Understand what a trace contains without reading raw private data by default.
- Inspect enough normalized detail to judge quality, usefulness, provenance, and limitations.
- Download only traces that are visible, shared, or listed according to the current access rules.

V1 implications:

- Consumer flows should prioritize browsing, search, filtering, result comparison, trace inspection, and trace download.
- Consumer-facing trace pages should expose provenance, format, redaction status, summaries, labels, and other quality signals when available.
- Paid purchase, licensing, and access-request workflows are not required to treat someone as a trace consumer.

## Non-User Types For V1

The following concepts may exist in the product or implementation, but they are not separate v1 user types:

- Paid purchaser: a future specialization of trace consumer once pricing, payment, licensing, or access requests are in scope.
- Admin or moderator: an operational role that may be needed later for review, abuse handling, or manual moderation, but should not drive the first user-flow model.

## V1 Flow Principles

The v1 flows should be simple enough for one person to exercise both contributor and consumer paths locally:

- Uploads are private by default.
- Contribution and consumption are connected by explicit visibility and listing controls.
- Search and discovery use safe metadata, summaries, labels, and redaction state before raw trace bodies.
- A trace can be useful to consumers before pricing, payments, licensing, or access requests exist.
- The UI should make ingestion progress and data quality issues visible instead of hiding them behind a generic success state.

## Trace Contributor Flow

Goal: upload trace data, understand upload and ingestion status, inspect what the system derived, and decide whether to share or list it.

Happy path:

1. The contributor enters the app through lightweight onboarding or an existing contributor identity.
2. The contributor opens the upload flow and provides a trace file, archive, folder export, or pasted payload.
3. The system validates file type, size, structure, duplicate hash, and supported format before preserving the raw upload.
4. The contributor sees upload progress from received through processing to either complete or requiring follow-up.
5. The ingestion pipeline parses the upload into normalized trace records, extracts safe metadata, records provenance, and creates searchable documents.
6. The contributor opens the trace inspection page from the upload result or trace library.
7. The contributor reviews parsed spans, events, artifacts, errors, source format, provenance, summaries, labels, privacy findings, and redaction state.
8. The contributor leaves the trace private, shares it through the local app, or lists it in the marketplace.

Required feedback paths:

- If validation fails, show the specific reason and do not create a public or searchable trace.
- If parsing partially succeeds, preserve the raw upload, expose parser errors, and show whatever normalized records are reliable.
- If sensitive values are detected, show the privacy state before the contributor can list the trace.
- If a duplicate is detected, connect the contributor to the existing upload or trace rather than silently ingesting another copy.

V1 success state:

- The contributor can upload synthetic or scrubbed trace data, verify ingestion, inspect the normalized trace, and intentionally make it discoverable.

## Trace Consumer Flow

Goal: discover traces, evaluate whether they are useful, inspect visible details, and download allowed trace data.

Happy path:

1. The consumer enters the app through the trace library, marketplace view, or lightweight consumer identity.
2. The consumer searches or browses traces by keyword, source format, model, tool, error type, tag, label, failure signal, owner, visibility, listing state, or upload date.
3. The system returns only traces the consumer is allowed to see, with result cards that expose safe summaries and quality signals.
4. The consumer filters or sorts results to compare traces by usefulness, provenance, redaction state, and derived metadata.
5. The consumer opens a trace detail page.
6. The consumer inspects overview metadata, timeline, spans, events, tool calls, errors, artifacts, annotations, and listing details that are visible under the current access rules.
7. The consumer downloads the allowed trace export when the trace is useful and access rules permit it.
8. The consumer returns to search with enough context to refine the query or compare another trace.

Required feedback paths:

- If no results match, show which query and filters were applied and keep the user in the search workflow.
- If a trace is private or not listed, exclude it from marketplace discovery unless the current identity owns it.
- If raw or sensitive content is redacted, show that redaction happened and prefer safe previews or summaries.
- If search metadata is incomplete because ingestion or enrichment failed, surface that state in the result and detail views.
- If download is unavailable, explain the current visibility or access reason.

V1 success state:

- The consumer can find listed or otherwise visible traces, understand why a trace may be valuable, inspect enough normalized detail to evaluate quality and limitations, and download allowed trace data.

## Shared Handoff Points

These visibility states connect the contributor and consumer flows:

| State | Contributor Meaning | Consumer Meaning |
|---|---|---|
| `private` | Uploaded trace is only visible to its owner. | Not discoverable or downloadable unless the consumer is also the owner. |
| `shared` | Trace can be inspected through allowed local access but is not marketplace-listed. | Visible only where the current access model permits it. |
| `listed` | Trace is intentionally discoverable with marketplace metadata. | Appears in marketplace and search results with safe summary, provenance, labels, quality signals, and an allowed download path. |

The practical v1 handoff is:

1. Contributor uploads and validates trace data.
2. System preserves raw provenance and derives safe searchable metadata.
3. Contributor inspects the parsed trace and privacy state.
4. Contributor changes visibility from private to shared or listed.
5. Consumer discovers the trace through search or marketplace browsing.
6. Consumer evaluates the trace through normalized inspection views.
7. Consumer downloads the allowed trace export.

## Out Of Scope For V1 Flows

- Pricing, payments, purchase checkout, and licensing.
- Paid purchaser-specific accounts beyond the trace consumer role.
- Admin review queues and manual moderation workflows.
- Organization membership and team permission management.
- Full anonymization guarantees beyond visible detection, redaction state, and safe previews.
