# Privacy & Redaction

Agent traces are sensitive by nature — prompts, tool arguments, and environment dumps routinely carry API keys, emails, and other PII — so the system draws one explicit boundary: the owner sees their original content; every other surface (listed-trace inspection, acquirer downloads, search, the LLM analyzers) sees scrubbed content with deterministic placeholders. Raw payloads in storage are never mutated ([spec](../docs/spec/stage-2/7_redaction.md), [explainer](../docs/explainers/redaction-boundary.md)).

## Threat Model

Three audiences can see trace-derived content, and each gets a different answer:

| Audience | Sees |
|---|---|
| Owner | Original span content (raw download, raw `attributes`/`events`/`status_message` on span detail) |
| Other users (listed / acquired traces) | Scrubbed content everywhere — inspection, search, downloads |
| LLM provider (judge, metrics, embeddings) | Scrubbed content only, and only with consent (below) |

The asset being protected is leaked credentials and pattern-detectable PII inside span content. Free-text PII without a pattern (names, addresses) is explicitly out of scope — see Honest Caveats.

## Redaction at Ingestion

Scrubbing runs inside the importer, as a pure function of `(payload, redaction_salt, ruleset_version)` — which preserves the stage-1 invariant that ingestion is a pure function of the raw stored payload, and makes a ruleset upgrade just a re-ingest (`services/api/app/redaction.py`).

- **Detection is two rule families over every string value**: the `detect-secrets` plugin set (named provider keys — AWS, GitHub, Stripe, OpenAI, … — keyword secrets, high-entropy strings) plus in-house pattern recognizers defined as data (email; phone validated via `phonenumbers`; Luhn-checked credit cards; SSN; public IPs; full JWTs; private-key blocks). No NER — model-based entity detection misfires on structured trace JSON and was deliberately excluded. String values that parse as JSON (stringified message blobs like `gen_ai.input.messages`) are recursed so key context like `"api_key": "…"` inside them still fires; replacement applies to the original string, preserving formatting.
- **False-positive guards are load-bearing.** Agent traces are dense with high-entropy non-secrets, so entropy detections that are id-shaped (pure hex at span-id/trace-id/sha256 lengths, UUIDs) are dropped; 13/19-digit pure numbers are treated as unix timestamps, not card numbers; private/loopback IPs are never masked (localhost URLs are everywhere in traces — public IPs are the PII case).
- **Replacement is `<KIND_xxxxxxxx>`** (e.g. `<EMAIL_3f9a2c1d>`, `<API_KEY_91c30d55>`), suffix = HMAC-SHA256(per-upload salt, value). The same value reads coherently within an upload — for human readers and analyzers alike — but is unlinkable across uploads, unrecoverable from the placeholder, and re-ingests byte-identically (the salt is minted once per upload and reused).
- **The ruleset is versioned code, not env vars.** Entropy thresholds and patterns live in the module under `REDACTION_VERSION` (currently 1.1.0); env-tunable detection would break determinism and make the recorded version meaningless — a deliberate exception to the everything-is-an-env-var rule. A version bump never auto-backfills; re-scrubbing existing uploads is an explicit `make requeue`.
- **Tested with goldens**: fixtures seeded with synthetic secrets/PII assert exact placeholder output, an id/hash-heavy negative fixture asserts zero replacements, and re-ingest byte-identity is checked at unit and integration level (`tests/integration/test_redaction.py`, [buildlog](../docs/buildlog/stage-2/A5/000_implementation.md)).

Per-type replacement counts (`{"EMAIL": 4, "API_KEY": 1}`) are stored on the upload and shown on `/uploads`, so contributors see what was masked.

## The Boundary

The boundary is structural, not per-endpoint: the `spans` table itself holds the scrubbed form, so any code path that reads spans — analysis, search indexing, the API — is clean automatically, with no opt-in scrub calls to forget. Raw content survives in exactly two places:

- the immutable raw storage object (content-hash keyed, never mutated — provenance and byte-identical owner downloads depend on it), and
- the owner-only `span_raw` side table, whose RLS deliberately has no listed-visibility policy — listing a trace never exposes its raw content.

At the read boundaries (`app/routers/traces.py`): span detail joins `span_raw` for the owner and serves the scrubbed columns to everyone else; downloads serve the raw object to the owner and a scrubbed payload artifact (`scrubbed/{owner}/{sha256}.json`, materialized at ingestion) to acquirers. Because analyzers read `spans`, detected credentials never reach the LLM provider — including for the owner's own traces.

## LLM Data Flow & Consent

Analysis sends trace content (the scrubbed representation) to the configured LLM provider — for judging, quality metrics, and behavior embeddings. Three controls govern this flow:

- **Operator-level**: no provider key configured means zero external data flow; analysis degrades honestly with recorded skip reasons ([04](04_analysis-pipeline.md)).
- **Per-account**: a `/settings` toggle (`profiles.allow_private_llm_analysis`, default on) excludes an account's *private* traces from LLM analysis; opted-out traces skip with `owner_opt_out` recorded and get deterministic signals only.
- **Listing overrides the opt-out**: listed traces are always analyzed — listing is the consent act, and flipping a private opted-out trace to listed re-enqueues its analysis so the marketplace never carries an unanalyzed listing ([05](05_marketplace.md)).

Embeddings ride exactly the same gates as the judge — an embedding call sends trace content to the provider just like a judge call — and the stored vectors are treated as derived sensitive data, with RLS mirroring trace visibility.

## Access Control

- **Every access rule exists twice** — enforced in the API query and mirrored as an RLS policy. The duplication is not belt-and-braces theater: the browser holds a real Supabase session for realtime invalidation, so RLS is load-bearing on that path ([02](02_architecture.md)).
- **Email allowlist**: sign-up is blocked by a DB trigger against the `allowed_emails` table, and every authenticated API request re-checks the allowlist (`app/auth.py`) — removing an email locks out existing sessions, not just new sign-ups. The check fails closed on a missing email claim.
- **API keys are minimal-scope by construction**: `tmk_` keys are sha256-stored (plaintext shown once), authenticate exactly the upload pair (`POST /v1/uploads`, `GET /v1/uploads/{id}`), and are soft-revoked from `/settings`. Keys skip the per-request allowlist re-check deliberately — minting required an allowlisted session, and key offboarding is revocation (recorded in the A1 audit).

## Honest Caveats

What redaction does not do, stated plainly (full list in the [explainer](../docs/explainers/redaction-boundary.md)):

- **Pattern-based detection only.** Free-text PII without a pattern — names, addresses, locations — is not caught. NER was excluded deliberately for its false-positive rate on structured trace JSON; listing remains the consent act for anything detection misses. Other known misses: short mixed-charset secrets with no key context, non-US national phone formats, unseparated SSNs, compressed-form IPv6, and a real secret that happens to be exactly 64 hex chars with no key context (it matches the sha256 id-guard).
- **Known over-masking, kept deliberately.** High-entropy base64 content (embeddings, encoded attachments) flags as `SECRET`; roughly 10% of random 16-digit ids pass Luhn and flag as `CREDIT_CARD`; 40-hex strings (commit SHAs) flag as `SECRET` because that is the legacy GitHub token shape. All detection errors fail toward masking, never leaking.
- **Names are scrubbed for everyone, owner included** — trace and span names have a single stored representation. The span *list* also serves the scrubbed `status_message` to owners; raw appears on span detail.
- **Contributor-authored fields are not scrubbed.** `description` and `tags` are marketplace copy the contributor wrote deliberately; upload filenames likewise.
- **Logging discipline**: span `attributes`, `events`, and raw payload bodies are never logged (a standing repo rule); judge/critic prompts and raw LLM outputs exist only in memory — only parsed labels and call metadata (latency/tokens/cost) leave the call site (`app/analysis/llm.py`).
- **Pre-redaction uploads** (ingested before the ruleset shipped) have no scrubbed artifact; an acquirer download 404s with a readable reason until the upload is re-ingested. A fresh compose — the evaluation path — never hits this.
