# Integrations — vetted external agents & tools (researched 2026-07)

What exists in the wild, what's worth wiring into this suite, and what to steal ideas
from. Ordered by integration value. Statuses: **wire now** (direct fit), **adopt
selectively**, **pattern only** (steal the idea, not the code), **watch**.

## 1. Bloomberg MCP servers — wire now (changes the build order)

The DAL's `[API]` transport **already exists as open source**. Community MCP servers
wrap BLPAPI against a logged-in terminal (localhost:8194):

| Project | What it exposes | Notes |
|---|---|---|
| [QmQsun/Bloomberg-MCP](https://github.com/QmQsun/Bloomberg-MCP) | 18 tools: BDP/BDH/BDS, intraday, **BQL**, estimates w/ revision momentum, ownership, SPLC, field discovery (`search_fields` = FLDS-equivalent), **saved EQS screens + dynamic screening + index universes**, economic & earnings calendars; TTL caching | MIT. Near 1:1 coverage of this suite's needs — incl. the Screener's Path 1/2 and the DAL field-map problem (field discovery is a tool) |
| [tallinn102/bloomberg-mcp](https://github.com/tallinn102/bloomberg-mcp) | Simpler data-access layer, same terminal-session auth | The base QmQsun forked from |
| [djsamseng/blpapi-mcp](https://github.com/djsamseng/blpapi-mcp) | Original minimal blpapi MCP | Reference |

**Integration:** fork QmQsun (don't depend on upstream — ~10 stars, young), code-review
it (it sits on your terminal entitlements), self-host next to the terminal, and map its
tools to the DAL §4 renderings. **Caveats:** Desktop API data is licensed to the
logged-in user — fine for your own agents, no redistribution; entitlement gaps (BEst
etc.) surface as errors → DAL downgrade rules apply; terminal must be running, so
`[XLS]`/`[TRM]` remain the fallback transports exactly as designed.

## 2. Anthropic financial-services plugins — adopt selectively

[anthropics/financial-services](https://github.com/anthropics/financial-services)
(announced 2026-05): 10 agent templates + vertical plugins for Claude Code/Cowork, with
governed connectors to FactSet, S&P Global, LSEG, Morningstar, Moody's, **Aiera
(earnings calls)**, MT Newswires, Daloopa, PitchBook.

- **Use their plumbing, keep our prompts.** The analytical standards here (variant
  perception, kill criteria, two-axis CB scoring, reverse DCF) are stricter and
  buy-side-shaped; theirs are broad workflow templates. But their **skills** are
  excellent subcomponents: `xlsx-author`/`dcf-model` (live Excel model output for
  Deep-Dive §5), `earnings-analysis` + Aiera connector (makes the roadmap Transcript
  agent mostly assembly), `catalyst-calendar`, `thesis-tracker`.
- The connector catalog is the shopping list for "more data services over time" —
  each one arrives as a governed MCP connector, i.e., a new DAL transport, zero prompt
  changes.

## 3. SEC EDGAR tooling — wire now (free)

[edgartools](https://github.com/dgunning/edgartools) +
[sec-edgar-mcp](https://github.com/stefanoamorelli/sec-edgar-mcp): filings, XBRL
as-reported financials, Form 3/4/5 insider transactions, 13F holdings, 8-K feeds —
exact values with filing-URL citations (matches the Core Block's tagging rule natively).

**Integration:** Deep-Dive §3 (earnings quality on *as-reported* XBRL, not vendor-
adjusted), §6 (13F deltas, insider clusters — currently `[TRM]`/manual), and it enables
the new **Filings & Insider Monitor** agent (roadmap). Zero cost, no entitlements.

## 4. CFTC Socrata API — wire now (free)

COT is a **public JSON API**, no auth: `publicreporting.cftc.gov` (Socrata; all report
variants — legacy, disaggregated, TFF, supplemental — back to 2006), plus the
[cot_reports](https://github.com/NDelventhal/cot_reports) Python lib.
**Integration:** upgrades Commodities §5 and the roadmap Positioning & Flows agent from
weekly `[URL]` paste to `[API]` — percentile/z-score of managed-money length computed
over full history instead of eyeballed.

## 5. FRED MCP servers — wire now (free)

Several implementations (e.g. [mcp-fredapi](https://github.com/Jaldekoa/mcp-fredapi))
expose FRED series with frequency/units transforms. **Integration:** Economic Releases
§3 trend placement and revision history without burning Bloomberg hits; second source
for rates/macro series.

## 6. OpenBB Platform + Workspace MCP — watch / phase 2

[OpenBB](https://github.com/OpenBB-finance/OpenBB) is an open data platform
("connect once, consume everywhere": Python, Excel, REST, MCP) and its Workspace now
takes MCP agents that operate dashboards. Strong candidate for the **non-Bloomberg
consolidation layer + auditable UI** once agent count grows — every DAL pull could
land as an inspectable widget. Heavier lift; not needed for the five-agent stage.

## 7. Alpha Vantage official MCP — optional redundancy

Official MCP server (equities, FX, commodities, fundamentals, macro). Rate-limited
retail-grade data — useful only as a cheap off-terminal fallback transport for
non-critical series. Never the primary print source.

## Frameworks & products — pattern only

- **[TradingAgents](https://github.com/TauricResearch/TradingAgents)** (LangGraph,
  bull/bear researcher **debate** → trader → risk team): don't adopt (backtest-oriented,
  US-equity day-cadence, and its analysts are thinner than ours). **Steal the explicit
  adversarial debate step** → new Red-Team agent (roadmap #2). Its research/risk/trader
  separation independently validates this suite's "agents characterize conviction, PM
  sizes" boundary.
- **[virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund)** (~45k stars):
  investor-persona panel (Buffett/Burry/etc. agents) + risk-manager → portfolio-manager
  pipeline. Personas are a gimmick for institutional use, but as a *judge-panel
  diversity trick* inside a Red-Team pass they're cheap and effective.
- **Look-ahead-bias research** ([Look-Ahead-Bench](https://arxiv.org/pdf/2601.13770)):
  benchmarks LLMs leaking post-hoc knowledge into "historical" analysis — the measured
  version of why the Core Block's stale-training-data rule exists. Any backtest-flavored
  agent must use point-in-time data discipline; cite this when tempted otherwise.
- **Commercial research platforms** (AlphaSense — multi-agent search over broker
  research/expert calls; Hebbia; Fintool — SEC-filings QA; Rogo — IB-workflow-shaped,
  weak hedge-fund fit per competitor comparisons (biased sources, verify); Brightwave —
  private markets): **buy-not-build for document breadth.** If the fund licenses
  AlphaSense/Hebbia, the roadmap Research Digest agent becomes an orchestrator over its
  API instead of a from-scratch build. None replaces the analytical agents here — they
  summarize; this suite takes positions with kill criteria.

## Net effect on the suite

1. **API wiring moved from "later" to "fork and deploy":** Bloomberg-MCP fork = DAL
   `[API]` transport; EDGAR + CFTC + FRED MCPs wire the free public sources. The
   Morning-Note orchestrator's shared-cache rationale strengthens accordingly.
2. **Two roadmap additions** (see README): Red-Team/Pre-Mortem agent; Filings & Insider
   Monitor.
3. **Transcript agent de-risked:** Aiera connector (via Anthropic plugin ecosystem) or
   EDGAR/vendor transcripts make it mostly assembly work.
