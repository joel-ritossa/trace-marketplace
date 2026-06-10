# LLM Trace Interoperability

## Why This Matters

Trace Marketplace should not invent its own trace worldview too early. The product needs to ingest real agent traces from many tools, preserve provenance, normalize enough metadata for search, and avoid locking future contributors or consumers into one vendor format.

The important research target is not which tracing UI is best. It is which schemas, conventions, and export formats are becoming common enough that Trace Marketplace can import them without custom work for every source.

## Short Recommendation

Use OpenTelemetry concepts as the neutral base:

- Store raw uploaded trace payloads unchanged.
- Normalize each trace into an internal span tree with stable IDs, parent-child relationships, timestamps, duration, status, attributes, events, and links.
- Map known GenAI fields into first-class searchable columns: provider, model, operation, prompt/input references, output references, tool calls, retrieval events, token counts, cost, errors, eval scores, and feedback.
- Store the source format, schema version, importer version, and original field paths used for every derived value.
- Treat trace text as sensitive. Index metadata and short derived summaries first; keep raw prompts, outputs, files, and long user content behind explicit privacy and access controls.

OpenTelemetry GenAI conventions should influence the canonical vocabulary, but they should not be the only accepted input. The importer should be adapter-based: OTel/OTLP, OpenInference, OpenLLMetry, Langfuse exports/API payloads, Phoenix/OpenInference traces, and later app-specific trace logs.

## Projects To Track

| Project | What matters for Trace Marketplace | Risk or caveat |
|---|---|---|
| [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) | Closest neutral schema layer for model spans, agent spans, events, metrics, exceptions, provider-specific attributes, and MCP-related telemetry. This is the right vocabulary to borrow for the internal normalized model. | The GenAI conventions are still marked development, so store convention version and be prepared to remap fields. |
| [OpenInference](https://github.com/Arize-ai/openinference) | AI-specific conventions and instrumentations on top of OpenTelemetry. Strong fit for importing traces from agent, RAG, vector store, and tool-use workflows. Its spec is intentionally transport/file-format agnostic. | Closely tied to the Arize/Phoenix ecosystem, even though it can target any OTel-compatible backend. Avoid making Phoenix-specific assumptions part of the core model. |
| [OpenLLMetry](https://github.com/traceloop/openllmetry) | Practical OpenTelemetry instrumentation for LLM providers, vector DBs, and frameworks. Useful as a source of real OTel-shaped traces and as a reference for auto-instrumented metadata. | Primarily instrumentation, not a marketplace schema or durable storage model. Use it to accept traces, not to define the whole product. |
| [Langfuse](https://github.com/langfuse/langfuse) | Strong production reference for trace inspection, sessions, observations, scores, prompts, datasets, and user feedback. Its imports, APIs, and OTel integration are relevant because many teams may already have Langfuse data. | Product model is broader than raw tracing. Do not copy its full application model unless it directly supports upload, search, viewing, or analysis. Core is MIT except `ee` folders, so license boundaries matter. |
| [Phoenix](https://github.com/Arize-ai/phoenix) | Strong reference for AI trace visualization, OpenInference integration, RAG evals, experiments, datasets, and replay/debug workflows. Useful to understand what high-quality trace inspection should expose. | Licensed under Elastic License 2.0. Treat it as source-available for dependency and vendoring decisions, not as a permissive component to embed casually. |

## Canonical Trace Shape

The internal representation should be boring and inspectable:

- `trace`: one user-visible session or request graph.
- `span`: one model call, tool call, retrieval step, agent step, framework step, or system operation.
- `event`: timestamped detail inside a span, such as streamed tokens, prompt/message events, tool call arguments, warnings, and exceptions.
- `artifact`: large or sensitive payload attached by reference, such as prompts, completions, files, terminal output, retrieved documents, and screenshots.
- `annotation`: derived labels, eval scores, human feedback, failure-mode tags, privacy review state, and marketplace value signals.
- `provenance`: upload source, original format, importer, parser version, source field paths, hashes, redaction status, and uploader identity.

This keeps the product independent of any single external project while still making imports predictable.

## Import Priorities

Start with importers that maximize interoperability:

1. OTel/OTLP JSON traces using GenAI semantic convention attributes where present.
2. OpenInference traces because they cover LLM calls plus surrounding RAG, tools, and framework context.
3. Langfuse exports or API-shaped traces because Langfuse is a common production LLM observability tool.
4. Phoenix/OpenInference traces because Phoenix is a common inspection/evaluation reference implementation.
5. Raw generic JSON span trees as a fallback for agent logs that are not standard yet.

OpenLLMetry matters mostly because it generates OTel-compatible traces from common SDKs. It should be validated through the OTel/OpenInference import path rather than treated as a separate product-shaped format unless its emitted attributes require special handling.

## Search And Analysis Implications

Normalize fields that consumers will actually search:

- model provider and model name
- framework or agent runtime
- tool names and tool error states
- retrieval sources and document counts
- token counts, latency, and approximate cost
- exception type, status, retry count, and interrupted spans
- human intervention, correction, or feedback
- eval scores and failure-mode labels
- privacy/redaction status

Keep raw text searchable only after deliberate privacy design. Search should work well on metadata and derived summaries before exposing full prompt and output bodies.

## Design Decisions To Confirm Before Implementation

- Which import format is first-class for the demo: OTLP JSON, OpenInference, Langfuse export, or a generic JSON trace format?
- Whether the normalized database model should use OTel names directly or project-owned names with OTel field mappings.
- Whether raw prompt/output text is indexed immediately, redacted before indexing, or stored but excluded from search by default.
- Whether Phoenix and Langfuse are research references only, optional import targets, or runtime dependencies.

## Source Notes

- OpenTelemetry GenAI semantic conventions are marked development and define GenAI signals for events, exceptions, metrics, model spans, and agent spans.
- OpenInference describes itself as conventions and plugins complementary to OpenTelemetry, with a transport/file-format agnostic spec.
- OpenLLMetry is an OpenTelemetry extension/instrumentation set that emits standard OTel data.
- Langfuse is an open-source LLM engineering platform with observability, evals, prompts, datasets, and OTel integrations; its repository is MIT except `ee` folders.
- Phoenix is an AI observability and evaluation platform built on OpenTelemetry/OpenInference concepts, but its repository is licensed under Elastic License 2.0.
