# DATA ACCESS LAYER (DAL) v1.0

> **Deployment note:** This spec is shared infrastructure. Agents reference it via the
> Core Operating Block (§2–3); it is not itself prepended to prompts, except the short
> "Agent-facing rules" section at the end, which the Core Block incorporates by
> reference. It also serves as the build spec for the API tool layer (e.g., an MCP
> server wrapping BLPAPI) when that gets wired.

## 1. The problem it solves

Bloomberg data reaches the agents over three transports with different strengths:

| Transport | What it is | Best for | Weakness |
|---|---|---|---|
| **API** (`[API]`) | BLPAPI / BQL via a wired tool layer | Anything automatable: reference data, history, screens, calendars. Zero PM effort. | No terminal screens/documents; entitlement + metering constraints; needs the tool layer built |
| **Excel** (`[XLS]`) | Bloomberg Excel add-in, PM-operated | **Bulk grids**: 10y quarterly financials (BDH), holders/members lists (BDS), screen imports. Semi-automated Mode B — agent emits formulas, PM pastes the grid back | Manual round-trip; add-in session required |
| **Terminal** (`[TRM]`) | PM runs functions, pastes/exports output | Screens & documents that exist nowhere else: `MODL`, `BI`, `WIRP` (verify), transcripts, `FLDS` lookups; one-off visual checks | Slowest; output is unstructured |

**Core principle: agents never think in transports.** Every data need is expressed once
in canonical form; the DAL (or the PM, pre-wiring) picks the rendering. Prompts stay
transport-agnostic and survive every stage of wiring — terminal-only today, Excel
workbook tomorrow, full API later — without edits.

## 2. Canonical request form

```
{securities: [<ticker + suffix>...],
 fields:     [<field mnemonics>...],        # the lingua franca — see §3
 period:     point | history(start, end, freq) | bulk,
 as_of:      required on every response}
```

Field mnemonics are shared between the API and the Excel add-in (the same `PX_LAST`
works in a ReferenceDataRequest and in `=BDP()`), which is what makes one canonical form
possible. Terminal screens don't take mnemonics — for screen/document content the
canonical form degrades to `{function, security, what-to-extract}`.

## 3. Field mnemonics — discipline

- Mnemonics are looked up authoritatively on the terminal via `FLDS <GO>` (verified
  function) on any security. When an agent is not certain of a mnemonic it writes the
  metric in words + **(verify)** and the PM resolves it in FLDS once; the verified name
  then goes into the field map (§6) and the flag is deleted.
- The API rejects unknown fields with an explicit error — a feature. **Never** work
  around a field error by estimating the value; report the error and request the
  correct mnemonic.
- Entitlement note: some field families (e.g., BEst consensus estimates) carry separate
  entitlements and may work on the terminal/Excel but not via Data License, or vice
  versa. A permission error is a transport-routing signal (fall back to `[XLS]`/`[TRM]`),
  not a data-availability verdict.

## 4. Renderings — one request, three forms

Worked example — 10 years of quarterly revenue and EBITDA for a ticker:

**Canonical:** `{[<tkr> US Equity], [SALES_REV_TURN (verify), EBITDA (verify)], history(-10y, now, quarterly)}`

- **[API]** — HistoricalDataRequest (or BQL equivalent) with those fields, `periodicitySelection=QUARTERLY`.
- **[XLS]** — a ready-to-paste block the agent emits verbatim:
  ```
  =BDH("<tkr> US Equity","SALES_REV_TURN;EBITDA","-10CY","","Per=Q")
  ```
  (BDP/BDH/BDS are verified add-in functions; the exact separator and option tokens
  such as `Per=Q` / relative-date syntax — **(verify once)**, then freeze in this file.)
- **[TRM]** — `FA <GO>` on the security → Excel export of the IS/CF tabs, or screen paste.

Excel function map (agent-emittable):
| Need | Formula | Status |
|---|---|---|
| Point value | `=BDP(security, field)` | verified |
| History grid | `=BDH(security, fields, start, end, options)` | verified (option tokens verify) |
| Bulk set (holders, index members, curve members) | `=BDS(security, field)` | verified |
| Saved EQS screen import | `=BEQS(screen name)` | **(verify)** |
| BQL in Excel | `=BQL(...)` | exists (verified); syntax per use **(verify)** |

## 5. Transport routing rules (defaults)

1. Wired API available and the need is field-shaped → `[API]`.
2. Bulk grid (≥ ~20 rows × several fields: financial history, holders, screen output,
   futures curve) and no API → `[XLS]` formula block. This is the workhorse pre-wiring:
   one paste each way instead of screen-scraping.
3. Screen or document content (MODL, BI, WIRP (verify), transcripts, filings) → `[TRM]`
  , always — no other transport carries it.
4. Public canonical sources stay `[URL]` regardless of Bloomberg transports: cftc.gov
   COT, eia.gov, usda.gov, ismworld.org, central-bank sites. Don't route through
   Bloomberg what is authoritative and free on the web.
5. Anything already supplied this session is `[SUPPLIED]` — never re-request.

## 6. Field-map registry

Verified mnemonics accumulate here per domain; agents cite the map instead of guessing.
Starter map — **every entry below is (verify once) unless marked verified**:

| Domain | Metric | Mnemonic | Status |
|---|---|---|---|
| Price | Last price | `PX_LAST` | verified |
| Price | Volume | `PX_VOLUME` | verified |
| Size | Market cap | `CUR_MKT_CAP` | verify |
| Fundamentals | Revenue | `SALES_REV_TURN` | verify |
| Fundamentals | EBITDA | `EBITDA` | verify |
| Estimates (BEst) | Consensus EPS FY1 | `BEST_EPS` + fiscal-period override | verify + entitlement |
| Estimates | Consensus target price | `BEST_TARGET_PRICE` | verify |
| Positioning | Short interest ratio | `SHORT_INT_RATIO` | verify |
| Ownership | Top holders (bulk) | via `BDS` holders field | verify |
| Eco releases | Survey median / actual / prior | `BN_SURVEY_MEDIAN` / `ACTUAL_RELEASE` / `PREV_RELEASE` (on ECO tickers) | verify |

Maintenance rule: when the PM verifies a mnemonic, it moves to "verified" here and the
inline (verify) flags in agent prompts referencing that metric are deleted. One place,
verified once, used everywhere.

## 7. Guardrails (bind on the API transport; good hygiene elsewhere)

- **Metering:** depending on license (Desktop API / Data License / B-PIPE), hits may be
  billed and redistribution restricted. Default per-task budget: **≤ 50 securities ×
  ≤ 40 fields** and **≤ 10 history requests** without explicit PM approval; an agent
  that needs more says so and waits.
- **Minimal-first:** pull the decision-critical set, read it, then follow up narrowly.
  Never speculatively bulk-pull a universe "in case."
- **No polling.** Agents never loop on a quote. Event-driven or single-snapshot only.
- **Resolution before request:** ambiguous names resolve via `//blp/instruments`
  (API) or `SECF <GO>` (verify) before any data pull — never guess a ticker.
- **Snapshot logging:** every API pull is logged `{request, response, timestamp}` so any
  note is reproducible against the exact data it saw. As-of tags in notes come from the
  response timestamp, not the wall clock.

## 8. Agent-facing rules (incorporated by Core Block §2–3)

1. Express data needs canonically (security + field/function + period); tag each DATA
   REQUEST line with its transport: `[API]` (execute), `[XLS]` (emit formula block),
   `[TRM]` (function + what to extract), `[URL]`, `[SUPPLIED]`.
2. When emitting `[XLS]` lines, produce the paste-ready formula block, not a description.
3. Per-source mode header: state, per data family, which transport served it —
   e.g. `sources: prices=API · fundamentals=XLS(supplied) · transcript=TRM(pending)`.
4. A transport failure (entitlement, field error, timeout) downgrades that source to the
   next transport and is reported in the header — it never becomes an estimated value.
5. Respect §7 budgets; declare oversize needs instead of chunking around them.
