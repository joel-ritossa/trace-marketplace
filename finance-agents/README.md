# Finance Analysis Agent Suite

Deployable system prompts and specs for a hedge-fund PM's analysis desk (macro, equities,
commodities; Bloomberg terminal today, more data services over time).

## Contents

```
finance-agents/
├── README.md                          ← architecture, handoffs, build order, roadmap
├── core/
│   ├── CORE-OPERATING-BLOCK.md        ← shared block, prepended to every agent (v1.1)
│   └── DATA-ACCESS-LAYER.md           ← transport spec (API / Excel / terminal), field-map
│                                         registry, guardrails; build spec for the API tool layer
└── agents/
    ├── 01-equity-deep-dive.md
    ├── 02-equity-screener.md
    ├── 03-central-bank-comms.md       ← parameterized template
    ├── cb-modules/                    ← fed, ecb, boe, boj + scaffolds (SNB, BoC, RBA,
    │                                     RBNZ, PBoC, Nordics)
    ├── 04-commodities.md
    └── 05-economic-releases.md
```

**To deploy an agent:** system prompt = `core/CORE-OPERATING-BLOCK.md` + that agent's
`BEGIN/END AGENT BLOCK` section (+ selected `cb-modules/*.md` for agent 03). Works as
isolated Claude Projects / custom agents today; the handoff protocol makes the same
prompts drop into an orchestrated multi-agent system later without rewriting.

## Architecture

**Hub-less federation with a shared contract.** Every agent inherits one Core Operating
Block (data-integrity protocol, transport-aware degradation, DATA REQUEST and HANDOFF
formats, output skeleton, variant-perception and kill-criteria standards) — so agents
never disagree about *how* to work, only analyze different things. Agents are stateless
and independently deployable; coordination happens through typed HANDOFF blocks that the
PM (today) or an orchestrator (later) routes.

**Data access is transport-agnostic.** Bloomberg reaches the agents three ways — live
API, terminal round-trip, or the Excel add-in — and the Data Access Layer
(`core/DATA-ACCESS-LAYER.md`) makes that invisible to the analysis: agents express every
data need once in canonical form (security + field mnemonic + period) and the request
renders as an API call `[API]`, a paste-ready `=BDP/BDH/BDS` formula block `[XLS]`, or a
terminal function to run and paste back `[TRM]`. Routing defaults: field-shaped + wired →
API; bulk grids → Excel; screens/documents (MODL, BI, transcripts) → terminal, always;
public canonical sources (CFTC, EIA, USDA, central-bank sites) → URL regardless. The DAL
also owns the verified field-map registry (mnemonics get verified once, used everywhere)
and the API guardrails (hit budgets, no polling, snapshot logging). A transport failure
downgrades to the next transport — it never becomes an estimated value.

This was chosen over a shared-context orchestrated system because (a) it degrades
gracefully at every stage of data wiring — terminal-only today, Excel workbook tomorrow,
full API later, with zero prompt rewrites — and (b) prompt quality is auditable per
agent. The future Morning-Note orchestrator (roadmap #1) becomes the hub — and the owner
of a shared per-morning data cache across agents — without any spoke changing.

### Hand-off graph

```
                       ┌──────────────────┐
   mandate ──────────▶ │ 02 EQ SCREENER   │
                       └────────┬─────────┘
                        Tier-1 names + trap risks
                                ▼
                       ┌──────────────────┐   commodity-producer equity angle
   ticker ───────────▶ │ 01 EQ DEEP-DIVE  │ ◀─────────────────────────────┐
                       └────────┬─────────┘                               │
              transcript Qs / options expression                          │
                        (future agents)                                   │
                                                                          │
                       ┌──────────────────┐  print → reaction function    │
   release ──────────▶ │ 05 ECO RELEASES  │ ─────────────┐                │
                       └──────────────────┘              ▼                │
                                                ┌──────────────────┐      │
   speech/minutes ────────────────────────────▶ │ 03 CB COMMS      │      │
                                                └────────┬─────────┘      │
                                          USD / real-rate / path impulse  │
                                                         ▼                │
                       growth & inflation pulse ┌──────────────────┐      │
   commodity ─────────────────────────────────▶ │ 04 COMMODITIES   │ ─────┘
                                                └──────────────────┘

   ALL agents ──▶ (future) 00 MORNING-NOTE ORCHESTRATOR ──▶ one cross-asset note
   ALL agents ──▶ (future) VOLATILITY/OPTIONS for expression refinement
```

### Build order (recommended)

1. **Core Block + 05 Economic Releases** — daily-frequency payoff, easiest to test
   (every morning has releases), and it exercises the paste-back workflow you'll rely on
   everywhere.
2. **03 CB Comms (Fed module first)** — highest macro leverage per hour; add ECB/BoE/BoJ
   modules as their meetings come up.
3. **01 Equity Deep-Dive** — biggest single prompt; test on one name you know cold, so
   you can grade it.
4. **04 Commodities** — after 03/05 exist, its macro-impulse handoffs have live senders.
5. **02 Equity Screener** — last of the five; it needs Deep-Dive downstream to be useful.
6. Then roadmap #1–3 below.

## Additional agents (ordered by leverage across macro / equities / commodities books)

1. **Cross-Asset Morning Note (orchestrator)** — one pre-open note that fans in
   overnight moves + agents 03/04/05 outputs and ranks what actually matters today;
   compounds the value of every other agent.
2. **Positioning & Flows** — CFTC, ETF flows, put/call, CTA-trend proxies, prime-broker
   survey color; crowding is the common risk factor across all three books and currently
   lives only inside per-agent sections.
3. **Earnings-Call / Transcript Analyzer** — quarter-over-quarter language deltas,
   guidance choreography, Q&A evasion detection; feeds Deep-Dive and scales your
   single-name coverage 10x in earnings season.
4. **Rates & FX Relative Value** — curve/butterfly/cross-market RV conditioned on CB
   Comms output; the natural monetization layer for agent 03's Axis-2 verdicts.
5. **Event-Risk Calendar** — forward 2-week map of dated risk (CB meetings, data,
   OPEC+, elections, expiries, auctions) with what's priced per event; cheap to build,
   prevents the expensive surprise.
6. **Volatility & Options Surface** — vol-adjusted expression selection for the other
   agents' views (all of 01/03/04 currently defer options structuring to this).
7. **Credit** — IG/HY spreads, index skew, primary-market tone as an early risk signal
   for equities and a recession thermometer for macro.
8. **Research Digest** — batch-summarize sell-side/street PDFs into claims + evidence +
   who-disagrees; kills your reading backlog and feeds consensus sections in 01/04.
9. **Post-Mortem / Trade Journal** — structured review of closed trades vs. the original
   kill criteria the agents shipped; the compounding loop that improves every prompt.

## What was assumed (defaults chosen — override any and I'll revise)

1. **Deployment: isolated agents now, orchestrator later.** Standalone prompts with a
   typed handoff protocol; no shared memory assumed. *If* you're deploying into an
   orchestrated framework with shared context from day one, the HANDOFF blocks become
   actual message passing — prompts unchanged, only routing changes.
2. **Data reality: three Bloomberg transports** — live API, terminal round-trip, and the
   Excel add-in — routed per the DAL. The API transport assumes a thin tool layer (an
   MCP server wrapping BLPAPI is the natural build; `DATA-ACCESS-LAYER.md` is its spec).
   Until that exists, Excel formula round-trips are the workhorse for anything
   grid-shaped and the terminal covers screens/documents.
3. **Output: markdown, one-screen exec summary, ET timestamps, USD default,** 12–18m
   equity horizon, tactical macro horizon; conviction as explicit probabilities.
4. **Bloomberg mnemonics:** functions marked *(verify)* were deliberately not asserted —
   confirm them on the terminal once and delete the flags from the prompts.

## What's still needed from you to tighten it

- Your **portfolio context block** (books, gross/net, typical horizon, house risk
  limits) — a 10-line addition to the Core Block that would let every agent tailor
  expression and sizing hints to your actual constraints.
- One **real worked example per agent** from your terminal (paste a real EQS export, a
  real ISM report, a real speech) — I'll run each agent's T2 test against real inputs
  and calibrate the prompts' section weights.
- Verdicts on the **(verify)-flagged mnemonics and Excel option tokens** — resolve once
  via `FLDS <GO>` / one test formula, record them in the DAL field-map registry, and the
  inline flags get deleted everywhere.
- Your **Bloomberg license type** (Desktop API vs. Data License vs. B-PIPE) — it sets
  the metering model and entitlement boundaries the DAL guardrails should encode
  precisely instead of conservatively.
- Which **CB scaffolds to promote** to full modules first (PBoC and BoC are the likeliest
  candidates given your books).
