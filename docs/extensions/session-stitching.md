# Extension: Session Stitching

Stage 1 defines one marketplace trace = one OTLP `trace_id`. There is no session/conversation concept: a multi-turn agent session instrumented as per-turn traces lands as N independent traces, each judged with no visibility into its siblings. This extension adds the session as a first-class grouping.

## Why

- **Judging accuracy:** a turn that looks like `gave_up` may be a clarifying question answered in the next trace; a goal stated in turn 1 is invisible when judging turn 3. Session context is the single biggest input the outcome judge is missing on per-turn instrumentation.
- **Consumer value:** training data for multi-turn agents wants whole sessions, not shuffled turns. Session-level search/acquire ("sessions containing a failure turn") is a richer product surface than trace-level alone.

## Mechanism sketch

- **Grouping key:** session id attributes already present in real instrumentation — OTel GenAI semconv `gen_ai.conversation.id`, OpenInference/Langfuse `session.id`, LangSmith thread ids. Extracted at ingestion (fail open: no attribute, no session) into a nullable `session_key` scoped per owner — ids are only meaningful within one contributor's uploads.
- **Storage:** a derived grouping (`session_key` column or a `sessions` side table), never a change to trace identity — traces stay the atomic unit; sessions are a lens over them. Ordering within a session by `started_at`.
- **Judging:** a session-level outcome pass becomes possible (render = concatenated per-turn renderings under the same budget rules; the per-trace judge stays as-is). Session outcome is a new derived field, not a rewrite of trace outcomes.
- **Surfaces:** session view in the web app (turn list → trace detail); session-scoped filters; bulk-acquire a session.

## Why extension, not base

- Organic uploads may not carry session attributes at all — hit-rate principle applies before any of this earns schema.
- Every surface it touches (judging unit, search, exports, UI) multiplies scope; base ships the per-trace story first.

## Open questions (settled if/when picked up)

- Hit rate of session attributes on real/candidate data — gates everything.
- Whether session outcome is judged from turn renderings or turn *verdicts* (cheaper, but compounds judge errors).
- Listing/acquisition semantics: is a session listable as a unit, or only its traces individually?
- Cross-upload sessions (turns synced in different uploads) — should fall out of the grouping key, but ingestion ordering needs checking.
