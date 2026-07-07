# ECO PLAYBOOK MODULE — US INFLATION COMPLEX (CPI · PCE · PPI · import prices)

*Loaded by Agent 05. The complex is a pipeline: CPI + PPI print first and jointly
determine most of PCE — the analytical unit is the pipeline, not the single release.
All ids (verify) unless marked verified. Category weights (relative importance) reset
each January — pull current from BLS, never recall a weight.*

---

## CPI — BLS, 8:30 ET, monthly. Tier 1 market-mover (the market trades CPI, the Fed targets PCE).

**Vector — Tier 1 (all m/m % to 3 decimals + 3m/6m annualized):**
headline (`CPIAUCSL` verified), core (`CPILFESL` verified), core goods, core services,
**supercore** = core services ex-shelter (compute it; BLS doesn't publish it as a
headline line — show the construction), food, energy.
**Vector — Tier 2 shelter (the heavyweight):** OER (verify id), rent of primary
residence (verify id), lodging away from home (volatile — separate it). Leading
cross-checks: BLS **New Tenant Rent Index** (quarterly, leads CPI rent ~1y (verify
current name)), private market-rent indices (Zillow/Apartment List `[URL, free]`).
**Vector — Tier 2 core goods:** used vehicles (verify id) — Manheim wholesale leads by
~2 months `[recall — durable]`; new vehicles; apparel (SA-noisy); medical care
commodities; household furnishings (the tariff-sensitive bucket — watch when trade
policy is live).
**Vector — Tier 2 core services ex-shelter:** medical care services (insurance
methodology: retained-earnings method resets each October — a known sawtooth `[recall
— durable]`); motor vehicle insurance (state-regulated repricing arrives in waves —
the 2023–24 lesson); airfares (methodology differs from PCE's); recreation services;
education & communication; personal care.
**Derived (compute + z-score alongside):** trimmed-mean and median CPI (Cleveland Fed,
free URL); sticky-vs-flexible split (Atlanta Fed); core ex-shelter; core ex-shelter
ex-used-cars (the "is it just the lags" series); diffusion = share of basket >4%
annualized.

**Reading (signal hierarchy):**
1. Supercore momentum (3m ann.) > core m/m > headline. But supercore is small-n and
   jumpy — never headline a single supercore print without the trimmed/median
   cross-check.
2. Shelter is a *lagging* input with a known lead indicator — when market rents and
   CPI shelter diverge, the forward path is knowable; say it explicitly and date the
   convergence window.
3. Decompose every surprise into: lag machinery (shelter), episodic (insurance,
   airfares, used cars), and broad (diffusion/trimmed measures). Only the third kind
   changes the inflation regime call.
4. The 0.049 rounding game: report unrounded where BLS provides it; a "0.3" can be
   0.251 or 0.349 — a 40% difference in run-rate.
**Distortions:** Feb seasonal-factor revisions; January price-reset effects
("January effect" in services); weight resets; methodology changes (flag any BLS
notice in the release).
**Reaction fn:** feeds the PCE nowcast (below); market pricing reacts to CPI directly
— the CPI-day trade is usually about the *composition* the market can't see in the
headline algo print. Hand the supercore/trimmed read to agent 03 against the Fed's
current framework.

---

## PCE deflator — BEA, 8:30 ET, monthly (with personal income & outlays). Tier 1 for the Fed, Tier 2 for markets (mostly pre-known).

**Vector:** headline (`PCEPI` verified), core (`PCEPILFE` verified) m/m + 3m/6m ann.;
**market-based core** (strips imputed prices — the cleaner demand signal (verify id));
supercore PCE (core services ex-housing); goods/services split; PCE-vs-CPI wedge
components.
**The nowcast discipline:** after CPI and PPI print, ~90% of core PCE is computable —
the *news* in PCE day is only the residual (imputed financial services, some
weights/scope differences). Maintain the mapping: healthcare services ← **PPI** (not
CPI); airfares ← PPI methodology; portfolio management fees ← PPI, mechanically tracks
equity levels `[recall — durable]`; auto insurance treated differently than CPI (lower
weight, different source); OER weight roughly half of CPI's (pull current). Publish
the nowcast vs. actual gap each month — a persistent gap means the mapping needs
re-verification.
**Reading:** the Fed's target variable; y/y base effects should be pre-computed for
the next 6 months (the "what does 0.2%/m deliver by December" table) — it disciplines
both your view and your read of Fed speeches. Real spending and the saving rate
(revision-prone) carry the growth signal in the same release.
**Reaction fn:** the target itself. Agent 03 should score every Fed inflation
statement against the current supercore-PCE run-rate, not CPI.

---

## PPI — BLS, 8:30 ET, monthly (day after or before CPI). Tier 2, but Tier 1 *conditional* — its job is finishing the PCE nowcast.

**Vector:** final demand; final demand goods ex food/energy; final demand services —
with the PCE-feeder breakout: **healthcare services** (hospital outpatient/inpatient,
physician care (verify ids)), **portfolio management & investment advice**, **airline
passenger services**, **auto insurance**; trade services (= retail/wholesale *margins*
— a genuine margin-pressure read, not a price read `[recall — durable]`); intermediate
demand stages (processed/unprocessed) as weak-lead context.
**Reading:** read PPI *through* the PCE mapping first; the standalone "pipeline
pressure" narrative is weak evidence. Portfolio-management PPI is mechanical equity
beta — strip it mentally before reading services PPI as inflationary. Trade-services
margins compressing while input costs rise = the corporate-margin story, route to
equities (agents 01/02).
**Reaction fn:** completes the PCE nowcast same-day; margin lens for equity margin
theses.

---

## Import/export prices — BLS, ~8:30 ET, monthly. Tier 3, conditional Tier 2 when FX or tariffs are live.

Ex-fuels import prices as the imported-goods-deflation pulse; by-origin detail (China
import prices) when tariff policy is active; pass-through lag to core goods ~2–3
quarters `[recall — durable, weak]`. Becomes a standing watch item when the USD has
moved >5% or tariff schedules changed — otherwise skim.

---

## Cross-release inflation dashboard (maintain in every inflation-complex note)

One table, updated whichever release just printed: supercore CPI 3m ann · trimmed-mean
CPI · median CPI · sticky CPI · core PCE 3m ann · market-based core PCE · NFIB price
plans (from surveys module) · UMich 1y/5-10y expectations · 5y5y breakeven (`USGGBE`
tickers / 5y5y forward (verify)) · New Tenant Rent Index direction. The dashboard *is*
the inflation-regime input to agent 10 — send it every run.
