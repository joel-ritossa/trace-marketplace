# Redaction

Ingestion scrubs credentials and pattern-detectable PII out of everything derived from an upload. The owner still sees their original span content; everyone and everything else — listed-trace inspection, acquirer downloads, LLM analyzers — sees deterministic placeholders. Raw payloads in storage are never mutated.

## In One Sentence

A pure, versioned scrub step inside the importer replaces detected secrets and PII with deterministic placeholders before rows are written; raw values survive only in the immutable storage object and an owner-only side table.

## Pipeline Placement

The scrub runs inside `import_payload`, between decode and normalization, as a pure function of `(payload, redaction_salt, ruleset_version)`. This preserves the stage-1 invariant — ingestion stays a pure function of the raw stored payload — and inherits delete-and-rewrite: a ruleset upgrade is just a re-ingest.

Scrubbed in place (single representation, all viewers):

- trace `name`, span `name`

Scrubbed with the raw value preserved owner-only (see Data Model):

- span `attributes`, `events`, `status_message`

Not scrubbed (out of scope, stated in Non-Goals): contributor-authored `description` and `tags`, upload `filename`, `parse_warnings` samples (already content-free per stage 1).

## Detection

Two rule families run over every string value in the scrubbed fields (recursing through jsonb objects/arrays; keys are never rewritten, only values):

| Family | Mechanism |
|---|---|
| Credentials | `detect-secrets` (Yelp) plugin set: keyword/prefix patterns (`sk-`, `AKIA`, `ghp_`, `xoxb-`, …), JWTs, private-key blocks, high-entropy strings. |
| PII | In-house recognizers, defined as data (`name`, `pattern`, optional `validator`): email; phone (validated via `phonenumbers`); credit card (Luhn-validated); SSN; IPv4/IPv6. |

Both families share one walker and one replacement mechanism. No NER — model-based entity detection misfires on structured JSON and is explicitly out.

String values that parse as JSON (stringified message blobs like `gen_ai.input.messages`) are recursed to a bounded depth: key-context detection runs per string leaf with its real key, so `"api_key": "…"` inside a blob still fires; replacement applies to the original string, preserving formatting.

**False-positive guard.** Agent traces are dense with high-entropy non-secrets (trace/span ids, sha256 hashes, UUIDs). The entropy detectors run behind a validator that skips pure-hex strings and UUID-shaped values. The full ruleset is golden-tested against the dev dataset; a ruleset change that alters dev-dataset output requires reviewing the diff before the version bumps.

**Tunables are not env vars.** Entropy thresholds and pattern sets live in code as part of the versioned ruleset — env-tunable detection would break determinism and make `redaction_version` meaningless. This is a deliberate exception to the everything-tunable-is-an-env-var rule.

## Replacement

Detected values are replaced with deterministic placeholders:

```
<EMAIL_3f9a2c1d>   <PHONE_b04e77a2>   <API_KEY_91c30d55>   <JWT_5dd0a1f4>
```

- Suffix = first 8 hex chars of `HMAC-SHA256(redaction_salt, original_value)`.
- `redaction_salt` is random per upload, generated when the upload row is created, stored on `uploads`. Re-ingest reuses it, so scrubbing stays deterministic per upload.
- Properties: the same value maps to the same placeholder *within* an upload (trace coherence survives for readers and analyzers); placeholders are not linkable *across* uploads; the original value is not recoverable from the placeholder.

## Data Model

### span_raw (new table)

Owner-only raw copies of the scrubbed span fields. `spans` itself becomes default-safe: any code path reading `spans` gets scrubbed content; raw requires an explicit join gated by RLS.

| Column | Type | Notes |
|---|---|---|
| `span_id` | uuid PK | References `spans.id`, cascade delete. |
| `attributes` | jsonb | Original OTLP attributes. |
| `events` | jsonb | Original OTLP events. |
| `status_message` | text | Original status message. |

Written in the same ingestion transaction as `spans`; delete-and-rewrite covers both.

### uploads (stage-1 delta)

| Column | Type | Notes |
|---|---|---|
| `redaction_salt` | text | Random hex, set at upload creation, immutable. |
| `redaction_version` | text | Ruleset version applied at last ingestion; rewritten on re-ingest. |
| `redaction_counts` | jsonb | Per-type replacement counts (e.g. `{"EMAIL": 4, "API_KEY": 1}`); rewritten on re-ingest. |

### Storage

Alongside the immutable raw object, ingestion materializes a scrubbed payload artifact at `scrubbed/{owner_id}/{sha256}.json` in the same bucket — the raw payload with every detected value replaced, same placeholder scheme. Overwritten idempotently on every ingest, written before the upload is marked `complete`. This is what non-owner downloads serve.

## Access Rules

Enforced in API queries; mirrored as RLS (stage-1 rule).

| Surface | Owner | Non-owner (listed/acquired) |
|---|---|---|
| Span detail (`attributes`, `events`, `status_message`) | Raw, via `span_raw` join | Scrubbed columns on `spans` |
| Trace/span `name` | Scrubbed | Scrubbed |
| Download | Raw storage object | Scrubbed artifact |
| `span_raw` rows | Owner only (RLS) | No access |

LLM analyzers, deterministic signals, and search all read the scrubbed representation — no per-path scrub calls, no opt-in. Credentials never reach the LLM provider, including for the owner's own traces.

## Versioning and Re-ingest

- `redaction_version` is a constant in the redaction module; any pattern, validator, or threshold change bumps it.
- A version bump does not auto-backfill. Backfill = re-enqueue ingestion for affected uploads (the existing requeue mechanism); delete-and-rewrite makes this safe and complete, including the scrubbed artifact.
- `redaction_counts` surface on the upload detail so contributors can see what was masked.

## Testing

- Golden tests: fixtures seeded with known secrets/PII (synthetic — committed examples follow the standing fixture rule) assert exact placeholder output.
- Negative goldens: id/hash/UUID-heavy fixtures assert zero replacements.
- Determinism test: scrubbing the same payload twice with the same salt is byte-identical (unit) and across full re-ingests (integration).
- Ruleset-change review artifact: the regenerated importer goldens — any detection change shows up as a reviewable golden diff before `REDACTION_VERSION` bumps.

## Non-Goals

- NER / model-based entity detection (names, addresses, locations).
- Scrubbing contributor-authored fields (`description`, `tags`) — marketplace copy the contributor wrote deliberately.
- Mutating or deleting raw storage objects (provenance is preserved; visibility remains the kill switch).
- Cross-upload pseudonym consistency.
- Retroactive automatic backfill on ruleset change.
