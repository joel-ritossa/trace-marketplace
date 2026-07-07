# SECTOR MODEL — REITs & REAL ESTATE

*Full model spec for Agents 01/09. Scope: towers/data centers, industrial,
residential, retail, office, self-storage, net lease, healthcare. Subsector chooses
the growth model; the wrapper math is shared.*

## 1. Model architecture

```
PROPERTY ENGINE
1. Same-store NOI = occupancy path × rent growth (blended from: in-place escalators,
   releasing spreads on the expiry schedule × % rolling, new/renewal mix)
   — the LEASE EXPIRY SCHEDULE is the model's spine: % of rent expiring by year ×
   mark-to-market (in-place vs. market rent gap)
2. + Acquisitions/dispositions (cap rate in/out) + development deliveries
   (yield-on-cost × stabilization schedule — risk-adjust management's YoC claims)
= Total NOI

CORPORATE WRAPPER
3. − G&A → EBITDA(re)
4. − Interest: the DEBT LADDER schedule (maturities by year × refi rate vs. in-place
   coupon — the refi headwind arithmetic, same back-book logic as banks/insurers)
5. → FFO → AFFO = FFO − maintenance capex − TIs − leasing commissions − straight-line
   rent adjustment (AFFO is the dividend's truth; the FFO→AFFO gap is the sector's
   capex honesty test)
6. Funding: dividend payout vs. AFFO; growth capex funded by retained AFFO /
   dispositions / equity issuance (per-share discipline: NAV/share and AFFO/share
   after funding, not absolute growth)

NAV SCHEDULE (parallel)
Forward NOI by segment ÷ segment cap rate ± development at cost/value + land
− debt at market → NAV/share; track price vs. NAV and vs. implied cap rate.
```

## 2. KPI dictionary

Same-store NOI growth (rate vs. occupancy split); releasing spreads (cash, not GAAP);
in-place vs. market rent gap (the embedded growth); AFFO payout ratio; net
debt/EBITDAre; fixed/floating mix + weighted maturity; implied cap rate =
NOI ÷ (EV) vs. private-market cap rates; development pipeline as % of assets and its
pre-leasing %; subsector-specific: tower colocation/amendment activity, DC leasing MW
and power availability, storage move-in/move-out rate spread, retail occupancy cost
ratio, office physical utilization vs. leased.

## 3. Valuation framework

Triangulate three: **P/AFFO** vs. subsector history and growth; **NAV**
premium/discount (with your cap rates, not management's); **implied cap rate vs.
private market + financing cost** (the accretion test: spread of cap rate over
marginal debt = external-growth capacity). Premium-to-NAV compounders deserve it only
while cost-of-capital advantage persists — model the flywheel breaking. Reverse: what
NOI growth and terminal cap rate does the price imply.

## 4. Earnings quality & forensics

FFO add-backs of recurring items (recurring "transaction costs," casualty); understated
maintenance capex (compare per-sq-ft to peers — the AFFO gap tell); capitalized
interest on perpetually "in-development" assets; straight-line rent divergence (GAAP
rent >> cash rent = free-rent-loaded leases); JV structures hiding leverage
(look-through debt); dispositions dressed as "capital recycling" while selling the
best assets to fund the dividend; ground-lease obligations.

## 5. Cycle & macro dashboard

Rates transmission is the sector macro: cap-rate spread to the 10y (compression cycle
vs. the refi wall), debt-maturity calendar vs. agent 03's path, and **supply** —
subsector construction pipelines (starts data by property type) are the rent-growth
killer with a 2–3y fuse (route from agent 05 housing/nonres data). Demand drivers per
subsector: DC = AI/cloud power procurement; industrial = goods consumption +
e-commerce share; resi = household formation + affordability gap vs. ownership;
office = utilization regime `[pull live per market]`.

## 6. Data map

Company supplements (the real disclosure — lease expirations, same-store detail);
NAREIT data; private-market cap rate surveys (Green Street-type (verify access));
CoStar-type market rent/vacancy (verify); construction pipeline data. BBG: DAL
consensus; `DVD` for distribution history.

## 7. Thesis archetypes & management questions

**Longs:** embedded mark-to-market (in-place rents far under market, expiry schedule
arriving) unpriced; premium-flywheel compounder with durable cost-of-capital edge;
NAV-discount + credible closing catalyst (activist, disposition program at proof-of-
NAV cap rates). **Shorts:** dividend > AFFO funded by dispositions; refi wall ×
floating exposure meeting a higher-path regime; supply wave landing on peak rents.
**Questions:** cash releasing spreads next 8 quarters by expiry cohort; maintenance
capex per foot honesty; development YoC assumptions vs. today's costs; refi plan for
the next 24 months of maturities; where they'd issue equity vs. NAV.
