# A6 — Native Session Ingestion: Implementation

Spec: [8_session-ingestion.md](../../../spec/stage-2/8_session-ingestion.md)
(written in this pass, confirmed with the user before code).

## Plan

The user's direction: traces should be **per turn**, and raw agent session
logs should ingest **without a client-side conversion step** — the server
detects the format and rejects unsupported schemas. That replaces the
`tools/agent_sessions_to_otlp.py` converter (which emitted one trace per
*session*) with importers inside the ingestion boundary.

Design pinned in the spec:

1. OTLP JSON stays canonical; session schemas (Codex rollouts, Claude
   Code / Cursor Anthropic-block JSONL) are source formats converted
   server-side into per-turn OTLP, then run through the one existing
   normalize path. Ingestion-purity invariant untouched.
2. Shared detection (`importers.sniff_format`) between POST (`422
   unsupported_format`, readable reason) and the worker (route to
   converter); detected-but-unconvertible payloads are
   `PermanentIngestError`s, verbatim on `/uploads`.
3. Turn = user message → all assistant activity until the next user
   message. Deterministic trace identity sha256(agent:session:turn);
   `session.id` on every synthetic root (feeds the session-stitching
   extension). Clockless logs (Cursor) synthesize timestamps anchored to
   the upload's `created_at` — deterministic on re-ingest.
4. CLI widens discovery to `*.jsonl` and gains `--since-hours N` (file
   selection only). Converter retires; `make link-sessions` keeps only the
   symlink maintenance.

## Changes

- `services/api/app/importers/sessions/` — new package: `turns.py` (shared
  turn model, timestamp fill, OTLP emission), `codex.py`,
  `anthropic_jsonl.py` (parsers ported from the converter, minus content
  caps — full fidelity, redaction still applies), `__init__.py` (detect /
  parse_records / convert).
- `importers/__init__.py` — `sniff_format`.
- `routers/uploads.py` — sniff at POST replaces the JSON+envelope check;
  `invalid_json` retired into `unsupported_format`; detected format stored
  on the upload row.
- `worker/tasks/ingest.py` — format routing; session payloads convert then
  share the normalize + scrub-artifact + rewrite path; trace provenance
  (`source_format`, `importer_version`) now per-format. The scrubbed
  non-owner artifact for session uploads is the converted OTLP.
- CLI `files.py` / `run.py` / `main.py` — `*.jsonl`, `--since-hours`.
- `upload-dropzone.tsx` — accepts `.jsonl`, copy updated.
- Retired: `tools/agent_sessions_to_otlp.py`, `tools/my_sessions.sh`,
  `make my-sessions` → `tools/link_sessions.sh`, `make link-sessions`.
- Spec amendments: stage-1 `1_trace-format.md` + `3_api.md` (A6 notes),
  stage-2 `5_cli.md`, `6_build-order.md` (A6 entry), new
  `8_session-ingestion.md`; demo `cli-sync.md` rewritten around the
  no-conversion flow; CLI README.
- Fixtures (synthetic): `codex-session.jsonl`, `claude-session.jsonl`,
  `cursor-session.jsonl`, `unsupported-log.jsonl`.

## Drift

- The anthropic parser distinguishes Claude vs Cursor by timestamp
  presence (spec'd as such; a timestamped Cursor transcript would label as
  `claude` — display-only stakes).
- Synthesized-clock walk ends exactly *on* the anchor (first cut overshot
  by the last event's synthetic duration; caught by the unit test).

## Outcome — done-when

- Unit: 273 passed (12 new in `test_importer_sessions.py`: detection,
  per-turn splits, tokens/model carry, determinism, rejection).
- Integration (real stack): `test_session_ingestion.py` — codex JSONL →
  2 per-turn traces with scannable names; cursor JSONL clockless ingest;
  unsupported schema → 422 at POST; meta-only session → `failed` with
  "no convertible turns" verbatim. `test_cli_sync.py` — raw `.jsonl`
  syncs via the real CLI to `complete, 2 traces`; dedupe and verbatim
  failure cases still pass.
- Known caveat (spec'd): a session file that grows between syncs re-uploads
  as a new upload whose turns duplicate the previous upload's traces —
  cross-upload dedupe is future work enabled by deterministic turn ids.
- Out of scope noise: 9 integration failures in `test_ingestion/discovery/
  hil/analysis` come from the parallel in-flight `TraceListParams` rework
  of `GET /v1/traces` (422 on bare list), unrelated to this slice.
