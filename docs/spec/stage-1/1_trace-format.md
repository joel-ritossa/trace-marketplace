# Trace Format

## Accepted Input: OTLP JSON

Stage 1 accepts one upload format: an OpenTelemetry OTLP/JSON trace export — the JSON encoding of `ExportTraceServiceRequest`. One uploaded file contains one or more traces; each distinct `trace_id` in the payload becomes one marketplace trace record.

> **Amended at stage-2 A6** (`docs/spec/stage-2/8_session-ingestion.md`): OTLP JSON stays the canonical format, but raw coding-agent session JSONL (Codex, Claude Code / Cursor) is also accepted and converted server-side into per-turn OTLP before the normalize path below. Undetectable bytes reject at POST with `422 unsupported_format`.

Why OTLP JSON first: OTel GenAI, OpenInference, OpenLLMetry, Langfuse's OTLP path, and Phoenix all emit or pass through this envelope, so one importer accepts traces from the widest set of real agent tooling. See `.archive/planning_docs/research/trace-source-schemas.md` for the inventory.

Expected envelope:

```text
resourceSpans[]
  resource.attributes[]
  scopeSpans[]
    scope { name, version }
    spans[]
      traceId, spanId, parentSpanId
      name, kind
      startTimeUnixNano, endTimeUnixNano
      attributes[]            <- where GenAI / OpenInference meaning lives
      events[] { timeUnixNano, name, attributes[] }
      status { code, message }
```

## Validation Rules

An upload is rejected (status `failed`, no trace records created) when:

- File exceeds 25 MB.
- Body is not parseable JSON (A6: nor JSONL matching a supported session schema).
- JSON does not contain a `resourceSpans` array with at least one span.
- SHA-256 of the body matches an existing upload by the same user (duplicate; the response links to the existing upload).

An upload partially succeeds when some spans are malformed: valid spans are normalized, malformed ones are counted and reported in `parse_warnings` on the upload. The raw payload is preserved either way.

## Canonical Normalized Shape

Two entities. Events are folded into spans as JSONB; artifacts and annotations are Stage 2.

### Trace

| Field | Source |
|---|---|
| `source_trace_id` | OTLP `traceId`. |
| `name` | Root span name, else first span name. |
| `started_at`, `ended_at`, `duration_ms` | Min/max span times. |
| `status` | `error` if any span has error status, else `ok`. |
| `span_count`, `error_count` | Derived. |
| `provider`, `model` | Dominant `gen_ai.provider.name` / `gen_ai.request.model` (with OpenInference `llm.provider` / `llm.model_name` and legacy aliases as fallback). |
| `tool_names` | Distinct tool names across spans. |
| `error_types` | Distinct `error.type` / `exception.type` values. |
| `service_name` | Resource attribute `service.name`. |
| `source_format` | `otlp_json` (constant for Stage 1). |
| `importer_version` | Version string of our importer. |

### Span

| Field | Source |
|---|---|
| `source_span_id`, `source_parent_span_id` | OTLP IDs; tree reconstruction. |
| `name` | Span name. |
| `kind` | Normalized: `llm`, `agent`, `tool`, `chain`, `retriever`, `embedding`, `other` — derived from `gen_ai.operation.name`, `openinference.span.kind`, or `traceloop.span.kind`, in that order. |
| `started_at`, `ended_at`, `duration_ms` | OTLP times. |
| `status`, `status_message`, `error_type` | OTLP status + `error.type`/`exception.type`. |
| `provider`, `model` | Per-span GenAI attributes. |
| `tool_name` | `gen_ai.tool.name` or OpenInference `tool.name`. |
| `input_tokens`, `output_tokens`, `total_tokens` | `gen_ai.usage.*` with legacy aliases. |
| `attributes` | Full raw OTLP attributes as JSONB — nothing is dropped. |
| `events` | Raw OTLP events as JSONB. |

Mapping invariants:

- Every normalized value is derived from the preserved raw payload; re-running the importer on the raw payload reproduces the normalized records.
- Unknown attributes are never dropped — they ride along in `attributes` JSONB.
- Raw message/prompt/output content (e.g. `gen_ai.input.messages`, `input.value`) stays inside span `attributes` JSONB. It is shown on the trace detail page to users with access, but it is never written into search indexes.

## Fixtures

`fixtures/` ships at least three synthetic OTLP JSON files:

1. A multi-span agent session: agent root span, LLM calls, tool calls, one retrieval step.
2. A failure trace: tool error and an exception event.
3. A minimal single-span trace.

Fixtures use OTel GenAI attribute names and contain no real data.

A real development dataset will be provided by the project owner. The importer and the span inspection UI are developed against that dataset; synthetic fixtures remain the committed examples. If the provided dataset is not OTLP JSON, the accepted-input decision above is revisited before implementation of the importer.
