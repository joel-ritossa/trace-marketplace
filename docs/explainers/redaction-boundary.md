# Who Sees Raw Trace Content vs Placeholders?

**One-line answer:** the trace owner sees their original content; every other
surface — listed-trace inspection, acquirer downloads, LLM analyzers, search
— sees deterministic placeholders like `<EMAIL_3f9a2c1d>`; raw payloads in
storage are never mutated.

## Mechanism

Ingestion scrubs detected credentials and pattern-PII inside the importer
(`app/importers/otlp/normalize.py` calling `app/redaction.py`), as a pure
function of `(payload, upload.redaction_salt, ruleset)`:

- **Detection** is two passes over every string value: `detect-secrets`
  (provider keys, keyword secrets, high-entropy strings) plus in-house
  pattern recognizers (email, phone via `phonenumbers`, Luhn-checked cards,
  SSN, public IPs, JWTs, private-key blocks). No NER. String values that
  parse as JSON (stringified message blobs) are recursed so key context
  like `"api_key": "…"` inside them still fires; replacement applies to the
  original string, preserving formatting.
- **Replacement** is `<KIND_xxxxxxxx>` where the suffix is
  HMAC-SHA256(per-upload salt, value): the same value reads coherently
  within an upload, is unlinkable across uploads, and re-ingests
  byte-identically.
- **Storage is default-safe:** `spans.attributes/events/status_message` and
  trace/span names hold the scrubbed form — any code path reading `spans`
  (analysis, search, API) is clean automatically. Raw copies live only in
  the owner-only `span_raw` table (RLS has no listed-visibility policy) and
  the immutable raw storage object.
- **Boundaries** (`app/routers/traces.py`): span detail joins `span_raw` for
  the owner; downloads serve the raw object to the owner and the
  `scrubbed/{owner}/{sha256}.json` artifact (materialized at ingestion) to
  acquirers.

Because analyzers read `spans`, detected credentials never reach the LLM
provider — including for the owner's own traces.

## Caveats

- Detection is pattern-based. Free-text PII without a pattern (names,
  addresses) is **not** caught — NER was deliberately excluded for its
  false-positive rate on structured trace JSON. Listing remains the consent
  act. Other known misses: short mixed-charset secrets with no key context,
  non-US national phone formats, unseparated SSNs, compressed-form IPv6.
- Known over-masking: high-entropy base64 content (embeddings, encoded
  attachments) flags as `SECRET`; ~10% of random 16-digit ids pass Luhn and
  flag as `CREDIT_CARD`; 40-hex strings (commit SHAs) flag as `SECRET` —
  kept deliberately, it's the legacy GitHub token shape. All errors fail
  toward masking, never leaking.
- Trace/span **names** are scrubbed in place for everyone, owner included
  (single representation). The span *list* endpoint also serves the scrubbed
  `status_message` to owners; raw appears on span detail.
- Uploads ingested before redaction shipped have no scrubbed artifact;
  acquirer downloads 404 with a readable reason until the upload is
  re-ingested. Ruleset upgrades likewise apply via re-ingest only
  (`uploads.redaction_version` records what ran).
- Entropy detectors skip id-shaped values (pure hex of length 16/32/64,
  UUIDs), so a real secret that happens to be exactly 64 hex chars with no
  context would be missed; 13/19-digit unseparated numbers are treated as
  timestamps, not card numbers.
