# A5 pass 001 — Keyword Detection Inside Stringified JSON

An accuracy probe after the slice shipped (30-case battery of realistic
agent-trace content) found one recall gap worth closing immediately: secrets
with keyword context *inside* JSON-stringified blobs — `gen_ai.input.messages`
containing `"api_key": "q7Rt…"` — were missed, because the synthetic
`"key": "value"` line the detect-secrets plugins scan hides the inner key
behind JSON escaping. Message blobs are where trace content lives, so this
was the highest-value miss.

## Change

`app/redaction.py`, `REDACTION_VERSION` 1.0.0 → 1.1.0:

- String values that parse as JSON (`{`/`[` prefix, bounded depth 4) are
  recursed: the detect-secrets pass runs per string leaf with its real key.
- The detect-secrets pass scans two line shapes per value: the synthetic
  `"key": "value"` form (plugins keying off the attribute name) and the raw
  text itself — inline keyword patterns in prose (`api_key: "…"` inside a
  message) need the unescaped quotes the synthetic form hides.
- Replacement still applies to the **original outer string** — formatting is
  preserved, nothing is re-serialized, and a clean blob passes through
  byte-identical. Leaf values whose JSON escaping differs from the raw text
  fail the `value in text` guard and are skipped, never corrupted.
- Pattern recognizers (email, phone, etc.) are context-free and already ran
  on the full text; only the key-context-sensitive plugin pass recurses.

Spec amended in the same pass (7_redaction.md Detection); explainer caveat
updated.

## Verification

- 4 new unit tests: keyword hit inside a blob, formatting preservation,
  nested blob-in-blob, clean/non-JSON blobs untouched. 33 redaction unit
  tests green; full unit suite green in this slice's scope.
- Importer goldens regenerated: no diff (existing fixtures carry no
  blob-embedded secrets — also asserted by the clean-blob unit test).
- Live-stack rebuild deferred: concurrent A2/B2 work-in-progress in the
  repo doesn't import cleanly yet, so baking an image now would break the
  running stack. No integration test depends on the new behavior; the next
  rebuild picks up 1.1.0. Pre-existing uploads keep `redaction_version`
  1.0.0 until re-ingested, per the no-auto-backfill rule.

## Known remaining gaps (accepted, documented in the explainer)

- Free-text PII (names, addresses) — no NER, by design.
- Short mixed-charset secrets with no key context.
- Non-US national phone formats; unseparated SSNs.
- Compressed-form IPv6 (`2001:db8::1`) — regex matches uncompressed only;
  candidate fix queued behind a real need.
- FP classes: high-entropy base64 content blobs → `SECRET`; ~10% of
  16-digit numeric ids → `CREDIT_CARD`; 40-hex (commit SHAs) → `SECRET`
  (kept deliberately for the legacy GitHub token shape).
