# A5 — Redaction at Ingestion

Spec: `docs/spec/stage-2/7_redaction.md`, `6_build-order.md` (A5), `2_data-model.md`
(`span_raw`, uploads deltas, access rules), `3_api.md` + `4_pages.md` (download
boundary, `/uploads` counts).

**Done when:** a fixture seeded with secrets/PII ingests with placeholders in
`spans` and raw values in owner-only `span_raw`; a non-owner span view and
acquirer download show placeholders while the owner sees originals; the
negative-golden (id/hash-heavy) fixture shows zero replacements; re-ingest is
byte-identical; redaction counts appear on the upload.

Decisions proposed in this plan, to ratify (or veto) before/at review:

1. **Scrub at the normalized-field level, artifact via a targeted OTLP walk.**
   `import_payload` scrubs span `name`/`status_message`/`attributes`/`events`
   and the trace name inside normalization; `NormalizedSpan` carries
   `raw_attributes`/`raw_events`/`raw_status_message` for `span_raw`. The
   scrubbed payload artifact comes from a separate walk that rewrites the same
   regions of the OTLP JSON (span fields plus resource/scope attributes —
   which can carry env dumps), leaving structural fields (ids, timestamps)
   untouched. Same pure scrub function + salt ⇒ identical placeholders in
   both representations. Artifact-walk counts are the stored
   `redaction_counts` (they cover resource attributes; span-level counts
   would not).
2. **`redaction_salt` is a required keyword arg on `import_payload`.** No call
   path can silently skip scrubbing. Offline callers (analysis CLI fixtures,
   unit tests, golden regenerate) pass a fixed constant salt so outputs stay
   deterministic. `IMPORTER_VERSION` bumps to 1.1.0; importer goldens are
   regenerated with the fixed salt.
3. **detect-secrets runs against synthetic `key: value` lines.** Plugins like
   KeywordDetector need key context (`"password": "hunter2"`); the walker
   scans `f"{key}: {value}"` and replaces detected secret substrings inside
   the value only. Plugin set: the named detectors (AWS, GitHub, GitLab,
   Stripe, Slack, OpenAI, SendGrid, Twilio, NPM, PyPI, JWT, private key,
   basic-auth, keyword) plus base64/hex high-entropy.
4. **False-positive guards** (the spec's hex/UUID guard, made concrete):
   detected entropy values are dropped when they are pure hex of length 16,
   32, or 64 (span/trace ids, sha256) or UUID-shaped. Credit-card candidates
   must pass Luhn *and* pure-digit candidates of length 13 or 19 are skipped
   (unix-millis / unix-nanos timestamp shapes). Phone candidates must
   validate via `phonenumbers`. SSN requires separators. Private/loopback/
   link-local IPs are not masked (localhost URLs everywhere in traces;
   public IPs are the PII case).
5. **Placeholder types** map detector → `EMAIL`, `PHONE`, `CREDIT_CARD`,
   `SSN`, `IP`, `JWT`, `PRIVATE_KEY`, `API_KEY` (named credential detectors),
   `SECRET` (keyword/entropy). Format `<TYPE_xxxxxxxx>`, suffix = first 8 hex
   of HMAC-SHA256(salt, value).
6. **Span ids are generated in Python** (uuid4) so `spans` and `span_raw`
   insert as parallel executemany batches without `returning id` plumbing.
7. **Span list (`LIGHT_FIELDS`) serves the scrubbed `status_message` to
   everyone, including the owner.** Raw status_message appears only on the
   span-detail join, matching the spec's access table; joining `span_raw`
   into list pages for owners isn't worth the query weight.
8. **Uploads ingested before A5 have no scrubbed artifact.** An acquirer
   download of such a trace 404s with a readable message until the upload is
   re-ingested (`make requeue`) — the spec's no-auto-backfill rule. Fresh
   compose (the evaluation path) never hits this.
9. **Migration backfills `redaction_salt`** for existing uploads with a
   random value, then sets not null; new salts are minted in Python at upload
   creation (`secrets.token_hex(16)`).
10. **Trace deletion also removes the scrubbed artifact** when it deletes the
    orphaned raw object (same best-effort post-commit path).

## Plan

### Migration (`supabase/migrations/00000000000007_redaction.sql`)

- `span_raw`: `span_id` uuid PK references `spans(id)` on delete cascade;
  `attributes` jsonb, `events` jsonb, `status_message` text. RLS enabled;
  owner-only select via the traces join — deliberately no listed-visibility
  policy, ever.
- `uploads`: add `redaction_salt` text (backfill + not null),
  `redaction_version` text, `redaction_counts` jsonb.

### Redaction module (`services/api/app/redaction.py`)

- `REDACTION_VERSION` constant.
- PII recognizers as data: `(type, pattern, validator)` tuples — email,
  phone, credit card, SSN, IP — one detection/replacement loop shared with
  the detect-secrets pass.
- `scrub_text(text, salt, key=None) -> (text, Counter)`;
  `scrub_tree(value, salt) -> (value, Counter)` recursing dicts/lists,
  values only, never keys.
- `scrub_otlp_payload(payload, salt) -> (payload, Counter)` — the targeted
  artifact walk (span name/status/attributes/events + resource/scope
  attributes).

### Importer

- `NormalizedSpan` gains `raw_attributes`, `raw_events`,
  `raw_status_message`; `_normalize_span`/`_build_trace` scrub via the
  module; `import_payload(payload, *, redaction_salt)`.

### Ingestion (`worker/tasks/ingest.py`)

- After parse: `scrub_otlp_payload` → put artifact at
  `scrubbed/{owner_id}/{sha256}.json` (idempotent upsert, before the DB
  transaction so a failure retries transiently).
- `import_payload(payload, redaction_salt=upload["redaction_salt"])`.
- `spans_q.insert_many` writes `spans` + `span_raw` with Python-minted ids.
- `mark_complete` records `redaction_version` + `redaction_counts`.

### API

- `uploads.create` mints the salt; upload schemas + list/detail responses
  expose `redaction_counts`.
- Span detail: owner gets raw via `span_raw` left join; non-owner gets
  scrubbed columns. Access check unchanged (`_visible_or_404` provides
  `is_owner`).
- Trace download: owner → raw object; acquirer → scrubbed artifact
  (`storage.scrubbed_path` derived from the raw path); missing artifact →
  readable 404 (decision 8). Upload download is owner-only → raw, unchanged.
- Trace delete: also best-effort-deletes the scrubbed artifact.

### Web

- `/uploads`: per-row masked summary from `redaction_counts` (e.g. "4 emails,
  1 API key masked"); nothing rendered at zero.

### Tests

- `unit/test_redaction.py`: per-recognizer positives/negatives, the guards
  (ids, sha256, UUIDs, timestamps vs cards, private IPs), placeholder
  determinism, counts.
- Golden: `redaction.json` fixture (synthetic seeded secrets/PII) and a
  negative fixture (id/hash-heavy, zero replacements) through the importer
  with the fixed test salt; regenerate importer goldens.
- Integration (`test_ingestion.py` + a new `test_redaction.py`): seeded
  fixture end to end — owner raw vs non-owner placeholders on span detail,
  acquirer download serves the artifact, counts on the upload, re-ingest
  byte-identical content.

## Drift

- **detect-secrets needs quoted lines.** The keyword and entropy plugins only
  fire on `"key": "value"`-shaped input, so the walker scans
  `f'"{key}": {json.dumps(value)}'` (decision 3 said `key: value`). Detected
  substrings are still validated against and replaced in the original text,
  so values whose JSON escaping changes them (embedded quotes/newlines) fail
  the `value in text` guard and are skipped rather than corrupted — except
  private-key blocks, which our own whole-block recognizer handles.
- **JWT plugin excluded.** detect-secrets matches partial tokens
  (`header.payload.` without the signature); an own full-token recognizer
  replaces it. Its IPv4 plugin is excluded for the same reason (ours covers
  v6 + `ipaddress.is_global` validation).
- **Own PRIVATE_KEY block recognizer added** — the plugin's secret_value is
  just the `BEGIN …` marker line, which would leave the key body behind.
- **Derivations read raw attributes.** `kind`, `provider`, `error_type`,
  tokens are mapped from unscrubbed attributes: scrubbing must never change
  what a span *is*, only what its content shows.
- **Spec testing line amended** (7_redaction.md): the "offline-runner
  dev-dataset sweep" became "regenerated importer goldens as the
  ruleset-change review artifact" — same purpose, artifact that actually
  exists; the seeded + negative fixtures run through the importer goldens.
- Decisions 1–10 otherwise implemented as proposed.

## Outcome

Done-when, verified 2026-06-11 against the live compose stack (migration 7
applied, api/worker rebuilt):

- Seeded fixture (`fixtures/redaction-seeded.json`) ingests with placeholders
  in `spans` and raw values in owner-only `span_raw` —
  `tests/integration/test_redaction.py::test_owner_raw_others_placeholders`.
- Non-owner span view and acquirer download show placeholders; owner sees
  originals and downloads exact original bytes — same test; missing-artifact
  (pre-A5) acquirer download 404s honestly —
  `test_missing_artifact_download_is_honest`.
- Negative golden (`redaction-negative.json`: UUIDs, sha256, trace ids, nano/
  milli timestamps, private IPs, URLs, ISO dates) shows zero replacements —
  unit goldens + `test_negative_fixture_masks_nothing`.
- Re-ingest byte-identical: spans rows and scrubbed artifact compared before/
  after an in-process re-run — `test_reingest_is_byte_identical`.
- Redaction counts appear on the upload (API + `/uploads` row summary).

Suites: 169 unit + 47 integration passing; importer goldens regenerated
(diff reviewed: additive `raw_*` fields only, no placeholder churn in
pre-existing fixtures — they contain no detectable values); web `tsc` clean.
Explainer added: `docs/explainers/redaction-boundary.md`.
