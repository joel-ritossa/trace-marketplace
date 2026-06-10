# Trace Source Schemas For Search

Pulled on 2026-06-10 from primary project docs and repositories.

This is a schema inventory for ingestion and search. It does not assume uploaded
traces need to become portable between downstream consumers. The product need is
smaller: preserve each uploaded payload, then derive a common searchable layer
for marketplace browsing, quality analysis, and trace inspection.

## Bottom Line

The trace ecosystems in `llm-trace-interoperability.md` are not one shared
provider schema. They share enough concepts to normalize:

- OTLP gives the common transport/object envelope.
- OpenTelemetry GenAI gives current `gen_ai.*` vocabulary for model, agent,
  tool, retrieval, memory, and evaluation spans.
- OpenInference gives a mature AI span-kind taxonomy and rich `llm.*`,
  `tool.*`, `retrieval.*`, `document.*`, `embedding.*`, and `metadata` fields.
- OpenLLMetry emits OpenTelemetry-shaped spans, but still includes project
  attributes and legacy aliases.
- Langfuse has both an OTLP ingestion path and a product data model around
  traces, observations, scores, prompts, sessions, and tags.
- Phoenix standardizes display and analysis around OpenInference/OpenTelemetry,
  with its own GraphQL model for spans, traces, costs, and annotations.

The import design should be adapter-based. The search design should be unified.

## Unified Search Layer

Index these fields first. Keep raw prompts, outputs, documents, tool arguments,
terminal logs, screenshots, and other long or sensitive content as artifacts or
redacted text, not as default full-text search.

### Trace

| Field | Purpose |
|---|---|
| `trace_id` | Internal stable ID. |
| `source_trace_id` | Original trace/session/request ID. |
| `source_format` | `otlp`, `otel_genai`, `openinference`, `openllmetry`, `langfuse`, `phoenix`, `generic_json`. |
| `source_schema_version` | External schema or convention version when known. |
| `importer_version` | Version of our adapter. |
| `root_span_id` | Root span when known. |
| `started_at`, `ended_at`, `duration_ms` | Time range and latency. |
| `name` | User-visible trace/request name. |
| `status` | `ok`, `error`, `unset`, or source-specific fallback. |
| `environment`, `release`, `version` | Deployment/version filters. |
| `session_id`, `conversation_id`, `user_id` | Correlation filters. |
| `tags` | Curated tags from source plus marketplace tags. |
| `service_name`, `framework`, `agent_name`, `workflow_name` | Runtime context. |
| `provider`, `model` | Dominant provider/model, plus per-span values. |
| `span_count`, `span_kind_counts` | Trace shape summary. |
| `error_count`, `error_types` | Failure search. |
| `input_tokens`, `output_tokens`, `total_tokens` | Usage summary. |
| `input_cost_usd`, `output_cost_usd`, `total_cost_usd` | Cost summary when source provides it or we derive it. |
| `score_summary` | Numeric/categorical score aggregates. |
| `privacy_state`, `redaction_state` | Marketplace safety filters. |
| `raw_payload_hash` | Provenance and de-duping. |

### Span

| Field | Purpose |
|---|---|
| `span_id`, `parent_span_id`, `trace_id` | Tree reconstruction. |
| `source_span_id`, `source_parent_span_id` | Original IDs. |
| `name` | Operation label. |
| `kind` | Normalized AI kind: `llm`, `agent`, `chain`, `tool`, `retriever`, `reranker`, `embedding`, `guardrail`, `evaluator`, `prompt`, `workflow`, `memory`, `http`, `db`, `unknown`. |
| `otel_kind` | Raw OTel span kind when present. |
| `operation` | `chat`, `text_completion`, `embeddings`, `retrieval`, `execute_tool`, etc. |
| `started_at`, `ended_at`, `duration_ms` | Timing. |
| `status_code`, `status_message`, `error_type` | Failure filters. |
| `provider`, `model`, `response_model` | Model/provider search. |
| `request_parameters` | Safe scalar request params such as temperature, top_p, max tokens, stream. |
| `prompt_template_name`, `prompt_template_version` | Prompt search. |
| `tool_name`, `tool_call_id`, `tool_type` | Tool search. |
| `retrieval_query_ref`, `retrieved_document_count`, `retrieval_top_k` | RAG search without indexing private document text by default. |
| `input_ref`, `output_ref` | Artifact references for prompt/output bodies. |
| `input_summary`, `output_summary` | Short derived summaries after privacy checks. |
| `input_tokens`, `output_tokens`, `reasoning_tokens`, `cache_read_tokens`, `cache_write_tokens`, `total_tokens` | Usage search. |
| `input_cost_usd`, `output_cost_usd`, `total_cost_usd` | Cost search. |
| `attributes` | Raw source attributes as JSON for inspection. |
| `source_field_paths` | Mapping from normalized values back to original fields. |

### Event, Artifact, Annotation

| Entity | Minimal fields |
|---|---|
| `event` | `span_id`, `name`, `timestamp`, `attributes`, `error_type`, `message_ref`. |
| `artifact` | `artifact_id`, `trace_id`, `span_id`, `kind`, `mime_type`, `storage_ref`, `hash`, `size_bytes`, `redaction_state`. |
| `annotation` | `target_type`, `target_id`, `name`, `score`, `label`, `explanation_ref`, `source`, `annotator_kind`, `metadata`. |

## Source Schemas

### 1. OpenTelemetry OTLP + GenAI

Primary sources:

- [OTLP trace service proto](https://github.com/open-telemetry/opentelemetry-proto/blob/main/opentelemetry/proto/collector/trace/v1/trace_service.proto)
- [OTLP trace data proto](https://github.com/open-telemetry/opentelemetry-proto/blob/main/opentelemetry/proto/trace/v1/trace.proto)
- [OpenTelemetry GenAI spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md)
- [OpenTelemetry GenAI events](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-events.md)
- [OpenTelemetry GenAI attribute registry](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/registry/attributes/gen-ai.md)

OTLP structural envelope:

```text
ExportTraceServiceRequest
  resource_spans[]
    resource.attributes[]
    schema_url
    scope_spans[]
      scope.name/version/attributes
      schema_url
      spans[]
        trace_id
        span_id
        parent_span_id
        trace_state
        flags
        name
        kind
        start_time_unix_nano
        end_time_unix_nano
        attributes[]
        events[]
          time_unix_nano
          name
          attributes[]
        links[]
        status
```

Current GenAI fields worth mapping:

| Area | Source fields |
|---|---|
| Operation identity | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.conversation.id`, `gen_ai.output.type`, `server.address`, `server.port`. |
| Request model/params | `gen_ai.request.model`, `gen_ai.request.choice.count`, `gen_ai.request.seed`, `gen_ai.request.stream`, `gen_ai.request.max_tokens`, `gen_ai.request.temperature`, `gen_ai.request.top_p`, `gen_ai.request.top_k`, `gen_ai.request.frequency_penalty`, `gen_ai.request.presence_penalty`, `gen_ai.request.stop_sequences`, `gen_ai.request.encoding_formats`. |
| Response | `gen_ai.response.id`, `gen_ai.response.model`, `gen_ai.response.finish_reasons`, `gen_ai.response.time_to_first_chunk`. |
| Usage | `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.reasoning.output_tokens`, `gen_ai.usage.cache_read.input_tokens`, `gen_ai.usage.cache_creation.input_tokens`. |
| Content, opt-in | `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.tool.definitions`. Store as artifacts or redacted values by default. |
| Agent/workflow | `gen_ai.agent.id`, `gen_ai.agent.name`, `gen_ai.agent.description`, `gen_ai.agent.version`, `gen_ai.workflow.name`. |
| Tool execution | `gen_ai.tool.name`, `gen_ai.tool.type`, `gen_ai.tool.description`, `gen_ai.tool.call.id`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result`. |
| Retrieval/memory | `gen_ai.retrieval.query.text`, `gen_ai.retrieval.top_k`, `gen_ai.retrieval.documents`, `gen_ai.data_source.id`, `gen_ai.memory.*`. |
| Evaluation | `gen_ai.evaluation.name`, `gen_ai.evaluation.score.value`, `gen_ai.evaluation.score.label`, `gen_ai.evaluation.explanation`. |
| Errors | OTel span status, `error.type`, exception events/attributes. |

Well-known `gen_ai.operation.name` values currently include `chat`,
`text_completion`, `generate_content`, `embeddings`, `retrieval`,
`execute_tool`, `create_agent`, `invoke_agent`, `invoke_workflow`, `plan`, and
memory operations such as `search_memory`, `create_memory`, `update_memory`,
`upsert_memory`, and `delete_memory`.

Import note: OpenTelemetry GenAI is still marked development. Store the schema
URL/convention version where available and preserve raw attributes.

### 2. OpenInference

Primary sources:

- [OpenInference specification](https://arize-ai.github.io/openinference/spec/)
- [OpenInference semantic conventions](https://arize-ai.github.io/openinference/spec/semantic_conventions.html)
- [OpenInference Python semantic convention constants](https://github.com/Arize-ai/openinference/blob/main/python/openinference-semantic-conventions/src/openinference/semconv/trace/__init__.py)

OpenInference is a semantic convention layer on top of OpenTelemetry. Every
OpenInference trace should still be importable as an OTLP trace, but the AI
meaning lives in span attributes.

Required discriminator:

| Field | Values |
|---|---|
| `openinference.span.kind` | `LLM`, `AGENT`, `CHAIN`, `TOOL`, `RETRIEVER`, `RERANKER`, `EMBEDDING`, `GUARDRAIL`, `EVALUATOR`, `PROMPT`, `UNKNOWN`. |

High-value attributes:

| Area | Source fields |
|---|---|
| Generic IO | `input.value`, `input.mime_type`, `output.value`, `output.mime_type`. |
| Identity/context | `metadata`, `tag.tags`, `session.id`, `user.id`, `agent.name`, `graph.node.id`, `graph.node.name`, `graph.node.parent_id`. |
| LLM identity | `llm.system`, `llm.provider`, `llm.model_name`. |
| LLM request/response | `llm.invocation_parameters`, `llm.input_messages`, `llm.output_messages`, `llm.prompts`, `llm.choices`, `llm.function_call`, `llm.finish_reason`, `llm.tools`. |
| Prompt template | `llm.prompt_template.template`, `llm.prompt_template.variables`, `llm.prompt_template.version`. |
| Usage | `llm.token_count.prompt`, `llm.token_count.completion`, `llm.token_count.total`, `llm.token_count.prompt_details.*`, `llm.token_count.completion_details.*`. |
| Cost | `llm.cost.prompt`, `llm.cost.completion`, `llm.cost.total`, `llm.cost.prompt_details.*`, `llm.cost.completion_details.*`. |
| Message internals | `message.role`, `message.content`, `message.contents`, `message.name`, `message.tool_calls`, `message.tool_call_id`, `message.function_call_name`, `message.function_call_arguments_json`. |
| Multimodal/reasoning content | `message_content.type`, `message_content.text`, `message_content.image`, `message_content.id`, `message_content.signature`, `message_content.data`, `message_content.encrypted_content`, `image.url`, `audio.url`, `audio.mime_type`, `audio.transcript`. |
| Tools | `tool.name`, `tool.id`, `tool.description`, `tool.parameters`, `tool.json_schema`, `tool_call.id`, `tool_call.function.name`, `tool_call.function.arguments`, `tool_call.reasoning_signature`. |
| Retrieval | `retrieval.documents`, plus document fields `document.id`, `document.score`, `document.content`, `document.metadata`. |
| Reranking | `reranker.input_documents`, `reranker.output_documents`, `reranker.query`, `reranker.model_name`, `reranker.top_k`. |
| Embeddings | `embedding.model_name`, `embedding.embeddings`, `embedding.text`, `embedding.vector`, `embedding.invocation_parameters`. |
| Prompt registry | `prompt.vendor`, `prompt.id`, `prompt.url`. |
| Exceptions | `exception.type`, `exception.message`, `exception.stacktrace`, `exception.escaped`. |

Import note: OpenInference has the best current coverage for RAG/tool/agent
search. It is a strong candidate for the internal vocabulary, but the product
should still keep project-owned normalized field names.

### 3. OpenLLMetry

Primary sources:

- [OpenLLMetry README](https://github.com/traceloop/openllmetry)
- [OpenLLMetry AI semantic convention constants](https://github.com/traceloop/openllmetry/blob/main/packages/opentelemetry-semantic-conventions-ai/opentelemetry/semconv_ai/__init__.py)
- [OpenLLMetry semantic convention docs](https://www.traceloop.com/docs/openllmetry/contributing/semantic-conventions)

OpenLLMetry is instrumentation, not a standalone product schema. It outputs
OpenTelemetry data and has historically carried its own AI semantic convention
attributes. Current traces may contain a mix of upstream `gen_ai.*`,
OpenLLMetry-specific `traceloop.*`, vector database attributes, and legacy
aliases.

Provider/system enum values observed in constants:

```text
openai, anthropic, cohere, mistral_ai, ollama, groq, aleph_alpha,
replicate, together_ai, ibm.watsonx.ai, hugging_face, fireworks,
az.ai.openai, aws.bedrock, gcp.gen_ai, openrouter, langchain, crewai
```

High-value attributes:

| Area | Source fields |
|---|---|
| Upstream-compatible GenAI | `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.request.max_tokens`, `gen_ai.request.temperature`, `gen_ai.request.top_p`, `gen_ai.usage.cache_creation.input_tokens`, `gen_ai.usage.cache_read.input_tokens`. |
| Project GenAI extensions | `gen_ai.usage.total_tokens`, `gen_ai.usage.token_type`, `gen_ai.user`, `gen_ai.headers`, `gen_ai.is_streaming`, `gen_ai.request.repetition_penalty`, `gen_ai.response.finish_reason`, `gen_ai.response.stop_reason`, `gen_ai.content.completion.chunk`, `gen_ai.request.reasoning_effort`, `gen_ai.usage.reasoning_tokens`, `gen_ai.request.n`, `gen_ai.request.max_completion_tokens`, `gen_ai.request.structured_output_schema`, `gen_ai.request.reasoning_summary`, `gen_ai.response.reasoning_effort`. |
| Legacy aliases | `gen_ai.system`, `gen_ai.prompt`, `gen_ai.completion`, `gen_ai.usage.prompt_tokens`, `gen_ai.usage.completion_tokens`, `gen_ai.openai.system_fingerprint`, old `llm.*` aliases such as `llm.usage.total_tokens`, `llm.user`, `llm.headers`, `llm.request.functions`, `llm.request.type`. |
| Workflow/framework | `traceloop.span.kind`, `traceloop.workflow.name`, `traceloop.entity.name`, `traceloop.entity.path`, `traceloop.entity.version`, `traceloop.entity.input`, `traceloop.entity.output`, `traceloop.association.properties`. |
| Prompt management | `traceloop.prompt.managed`, `traceloop.prompt.key`, `traceloop.prompt.version`, `traceloop.prompt.version_name`, `traceloop.prompt.version_hash`, `traceloop.prompt.template`, `traceloop.prompt.template_variables`. |
| Vector databases | Generic `db.system`, `db.operation`, `db.vector.query.top_k`, `db.vector.query.result_count`, `db.vector.query.top_score`, `db.vector.query.top_distance`; plus Pinecone, Chroma, Milvus, Qdrant, and Marqo-specific keys. |
| Metrics | `gen_ai.client.generation.choices`, `gen_ai.client.token.usage`, `gen_ai.client.operation.duration`, plus provider/vector DB metric names. |

Import note: accept OpenLLMetry through the OTLP importer. Add compatibility
aliases for legacy keys, especially `gen_ai.prompt`, `gen_ai.completion`,
`gen_ai.usage.prompt_tokens`, and `gen_ai.usage.completion_tokens`.

### 4. Langfuse

Primary sources:

- [Langfuse data model docs](https://langfuse.com/docs/observability/data-model)
- [Langfuse generated OpenAPI](https://github.com/langfuse/langfuse/blob/main/web/public/generated/api/openapi.yml)
- [Langfuse observations API definition](https://github.com/langfuse/langfuse/blob/main/fern/apis/server/definition/observations.yml)
- [Langfuse trace domain schema](https://github.com/langfuse/langfuse/blob/main/packages/shared/src/domain/traces.ts)
- [Langfuse observation domain schema](https://github.com/langfuse/langfuse/blob/main/packages/shared/src/domain/observations.ts)
- [Langfuse score domain schema](https://github.com/langfuse/langfuse/blob/main/packages/shared/src/domain/scores.ts)
- [Langfuse traces ClickHouse table](https://github.com/langfuse/langfuse/blob/main/packages/shared/clickhouse/migrations/unclustered/0001_traces.up.sql)
- [Langfuse observations ClickHouse table](https://github.com/langfuse/langfuse/blob/main/packages/shared/clickhouse/migrations/unclustered/0002_observations.up.sql)

Langfuse has two relevant shapes:

1. OTLP ingestion at `/api/public/otel/v1/traces`, implementing OTLP/HTTP
   `ExportTraceServiceRequest` with JSON/protobuf payloads.
2. Langfuse product objects: traces, observations, scores, sessions, prompts,
   datasets, comments, and tags.

Trace fields:

| Area | Source fields |
|---|---|
| Core | `id`, `name`, `timestamp`, `environment`, `projectId`, `createdAt`, `updatedAt`. |
| Correlation | `sessionId`, `userId`. |
| Release/search | `tags`, `release`, `version`, `bookmarked`, `public`. |
| IO/metadata | `input`, `output`, `metadata`. |
| Aggregates from observations | `latency`, `inputTokens`, `outputTokens`, `totalTokens`, `inputCost`, `outputCost`, `totalCost`, `warningCount`, `errorCount`, `defaultCount`, `debugCount`. |
| Scores | `scores_avg`, `score_categories`, and score records associated to trace/session/observation. |

Observation fields:

| Area | Source fields |
|---|---|
| Core | `id`, `traceId`, `projectId`, `type`, `startTime`, `endTime`, `parentObservationId`, `name`. |
| Observation types | `SPAN`, `EVENT`, `GENERATION`, `AGENT`, `TOOL`, `CHAIN`, `RETRIEVER`, `EVALUATOR`, `EMBEDDING`, `GUARDRAIL`. |
| Status/filtering | `level`, `statusMessage`, `environment`, `version`, `createdAt`, `updatedAt`. |
| Model | `providedModelName`/`model`, `internalModelId`, `modelParameters`. |
| IO/metadata | `input`, `output`, `metadata`. Langfuse v2 exposes indexed literal search on `input`, `output`, and metadata values. |
| Prompt | `promptId`, `promptName`, `promptVersion`. |
| Usage/cost | `providedUsageDetails`, `usageDetails`, `providedCostDetails`, `costDetails`, `totalCost`, `inputUsage`, `outputUsage`, `totalUsage`, `inputCost`, `outputCost`, `usagePricingTierId`, `usagePricingTierName`. |
| Timing metrics | `completionStartTime`, `latency`, `timeToFirstToken`. |
| Tool data | `toolDefinitions`, `toolCalls`, `toolCallNames`. |
| Trace context on v2 observations | `tags`, `release`, `traceName`. |

Score fields:

| Area | Source fields |
|---|---|
| Core | `id`, `projectId`, `environment`, `name`, `value`, `source`, `authorUserId`, `comment`, `metadata`. |
| Type | `dataType`: `NUMERIC`, `CATEGORICAL`, `BOOLEAN`, `CORRECTION`, `TEXT`. |
| Associations | `traceId`, `observationId`, `sessionId`, `datasetRunId`, `configId`, `queueId`, `executionTraceId`. |
| Timestamps | `timestamp`, `createdAt`, `updatedAt`. |

Import note: for contributed Langfuse exports/API payloads, map traces and
observations directly. For Langfuse OTLP, use the OTLP path and recognize
Langfuse-specific attributes such as `langfuse.observation.type` when present.

### 5. Phoenix

Primary sources:

- [Phoenix README](https://github.com/Arize-ai/phoenix)
- [Phoenix translating conventions docs](https://arize.com/docs/phoenix/tracing/concepts-tracing/translating-conventions)
- [Phoenix GraphQL schema](https://github.com/Arize-ai/phoenix/blob/main/app/schema.graphql)
- [OpenInference semantic conventions](https://arize-ai.github.io/openinference/spec/semantic_conventions.html)

Phoenix ingest/display standard:

- Phoenix is built on OpenTelemetry and OpenInference.
- Phoenix docs state that traces from other libraries should be translated into
  OpenInference semantic conventions for consistent display.
- Treat Phoenix trace payloads as OpenInference/OTLP unless consuming Phoenix's
  own GraphQL/API exports.

Phoenix GraphQL trace fields useful for analysis:

| Area | Source fields |
|---|---|
| Core | `id`, `traceId`, `startTime`, `endTime`, `latencyMs`, `projectId`, `projectSessionId`. |
| Tree | `rootSpan`, `numSpans`, `spanCountsByKind`, `spans`. |
| Errors | `errorCount`, `errorsByType`. |
| Cost | `costSummary`, `costDetailSummaryEntries`. |
| Annotations | `traceAnnotations`, `traceAnnotationSummaries`. |

Phoenix GraphQL span fields:

| Area | Source fields |
|---|---|
| Core | `id`, `name`, `spanId`, `parentId`, `trace`, `context`, `spanKind`, `startTime`, `endTime`, `latencyMs`. |
| Status | `statusCode`, `statusMessage`, `propagatedStatusCode`. |
| Raw data | `attributes` as JSON string, `metadata` as JSON string, `events`. |
| IO | `input`, `output` with `mimeType`, `truncatedValue`, `value`. |
| RAG | `numDocuments`, `documentEvaluations`, `documentRetrievalMetrics`. |
| Usage | `tokenCountPrompt`, `tokenCountCompletion`, `tokenCountTotal`, `tokenPromptDetails`, cumulative token counts. |
| Cost | `costSummary`, `costDetailSummaryEntries`. |
| Annotations | `spanAnnotations`, `spanNotes`, `spanAnnotationSummaries`. |
| Dataset | `asExampleRevision`, `containedInDataset`. |

Phoenix span kinds:

```text
chain, tool, llm, prompt, retriever, embedding, agent, reranker,
evaluator, guardrail, unknown
```

Import note: Phoenix is mostly not a separate raw-trace schema for us. It is a
reference implementation and optional export/API target. The importer should
accept Phoenix/OpenInference traces via the OpenInference adapter and only add a
Phoenix adapter if we ingest Phoenix GraphQL/API exports with annotations,
document evals, or cost summaries.

## Crosswalk Into Unified Fields

| Unified field | OTel/GenAI | OpenInference | OpenLLMetry | Langfuse | Phoenix |
|---|---|---|---|---|---|
| `trace_id` | `span.trace_id` | `span.trace_id` | `span.trace_id` | `trace.id` | `trace.traceId` |
| `span_id` | `span.span_id` | `span.span_id` | `span.span_id` | `observation.id` | `span.spanId` |
| `parent_span_id` | `span.parent_span_id` | `span.parent_span_id` | `span.parent_span_id` | `observation.parentObservationId` | `span.parentId` |
| `kind` | `gen_ai.operation.name`, OTel span kind, resource/scope hints | `openinference.span.kind` | `traceloop.span.kind`, `gen_ai.operation.name` | `observation.type` | `span.spanKind` |
| `operation` | `gen_ai.operation.name` | `openinference.span.kind` plus span name | `gen_ai.operation.name`, `llm.request.type` | `observation.type`, `observation.name` | `span.spanKind`, `span.name` |
| `provider` | `gen_ai.provider.name` | `llm.provider`, `llm.system` | `gen_ai.provider.name`, `gen_ai.system`, `GenAISystem` enum | Usually metadata/model params unless OTLP attrs preserved | Usually `span.attributes` (`llm.provider`/`llm.system`) |
| `model` | `gen_ai.request.model`, `gen_ai.response.model` | `llm.model_name`, `embedding.model_name`, `reranker.model_name` | `gen_ai.request.model`, `gen_ai.response.model` | `providedModelName`/`model` | `span.attributes`, sometimes model-derived UI fields |
| `session_id` | `gen_ai.conversation.id` when session-like | `session.id` | `traceloop.association.properties`, `gen_ai.conversation.id` if present | `trace.sessionId` | `trace.projectSessionId`, source attrs |
| `user_id` | custom/resource attrs | `user.id` | `gen_ai.user`, `llm.user`, association props | `trace.userId` | source attrs |
| `input_ref` | `gen_ai.input.messages`, event details | `input.value`, `llm.input_messages`, `llm.prompts` | `gen_ai.prompt`, `traceloop.entity.input` | `trace.input`, `observation.input` | `span.input`, `span.attributes` |
| `output_ref` | `gen_ai.output.messages`, event details | `output.value`, `llm.output_messages`, `llm.choices` | `gen_ai.completion`, `traceloop.entity.output` | `trace.output`, `observation.output` | `span.output`, `span.attributes` |
| `tool_name` | `gen_ai.tool.name`, tool definitions/calls | `tool.name`, `tool_call.function.name` | tool/function aliases, framework attrs | `toolCallNames`, `toolCalls`, `toolDefinitions` | `span.attributes`, `spanKind=tool` |
| `retrieved_document_count` | `gen_ai.retrieval.documents` length | `retrieval.documents` length | vector DB result count keys | `type=RETRIEVER`, metadata/input/output conventions | `numDocuments` |
| `input_tokens` | `gen_ai.usage.input_tokens` | `llm.token_count.prompt` | `gen_ai.usage.prompt_tokens`, `gen_ai.usage.input_tokens` | `inputUsage`, `usageDetails.input`, aggregate `inputTokens` | `tokenCountPrompt` |
| `output_tokens` | `gen_ai.usage.output_tokens` | `llm.token_count.completion` | `gen_ai.usage.completion_tokens`, `gen_ai.usage.output_tokens` | `outputUsage`, `usageDetails.output`, aggregate `outputTokens` | `tokenCountCompletion` |
| `total_tokens` | derived | `llm.token_count.total` | `gen_ai.usage.total_tokens`, `llm.usage.total_tokens` | `totalUsage`, aggregate `totalTokens` | `tokenCountTotal` |
| `reasoning_tokens` | `gen_ai.usage.reasoning.output_tokens` | `llm.token_count.completion_details.reasoning` | `gen_ai.usage.reasoning_tokens`, `llm.usage.reasoning_tokens` | `usageDetails` if present | `tokenPromptDetails`/attributes if present |
| `total_cost_usd` | derived, not core GenAI today | `llm.cost.total` | derived or custom attrs | `totalCost`, `costDetails` | `costSummary.total` |
| `error_type` | `error.type`, exception event attrs | `exception.type` | `error.type`, exception attrs, provider exception metrics | `level=ERROR`, `statusMessage` | `statusCode`, `errorsByType`, events |
| `score_summary` | `gen_ai.evaluation.*` | evaluator spans/metadata | custom/eval attrs | scores API/domain | annotations, document evals |

## Importer Implications

1. Build one normalized span-tree model with source provenance and raw payload
   preservation.
2. Start with OTLP JSON/protobuf import because it covers OTel GenAI,
   OpenInference, OpenLLMetry, Langfuse OTLP, and Phoenix/OpenInference.
3. Add an OpenInference mapper for its richer AI taxonomy.
4. Add a Langfuse mapper for API/export-shaped traces, observations, and
   scores.
5. Treat OpenLLMetry as OTLP plus compatibility aliases, not as a separate
   product schema.
6. Treat Phoenix as OpenInference unless importing Phoenix GraphQL/API exports.
7. Store raw text and large structured blobs as artifacts first; index metadata,
   short summaries, and safe scalar fields before indexing raw content.
