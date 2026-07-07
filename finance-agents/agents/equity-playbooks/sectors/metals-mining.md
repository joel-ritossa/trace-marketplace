# SECTOR MODEL — METALS & MINING EQUITIES

*Full model spec for Agents 01/09. Commodity view from Agent 04
(`commodity-playbooks/metals.md`); this module models the miner — grade, cost curve
position, capex phase, and jurisdiction.*

## 1. Model architecture

```
1. Production by mine: ore tonnes × grade × recovery = payable metal
   — model GRADE TRAJECTORY explicitly (mine plan grade vs. reserve grade:
   high-grading now = lower grade later; the sequencing is in the technical reports)
2. Costs by mine: mining + processing + site G&A → C1 cash cost; + sustaining capex
   + royalties → AISC. BY-PRODUCT ACCOUNTING AUDIT: by-product credits can turn a
   high-cost mine "low-cost" — always compute co-product AISC too
3. Capex schedule: sustaining vs. growth by project, phase (study → build → ramp);
   ramp curves risk-adjusted (base rate: new mines slip and overrun `[recall —
   durable]`)
4. → EBITDA by mine at agent-04 deck + spot; consolidated FCF at both
5. NAV: DCF per mine at conservative long-run price ÷ discount rate reflecting
   jurisdiction (tiered country risk) + development projects (risked) + exploration
   (option value, small) − net debt − closure liabilities
6. Balance-sheet cycle test: net debt/EBITDA at TROUGH prices, not spot
```

## 2. KPI dictionary

AISC positioning (which quartile of agent 04's cost curve); AISC margin = price −
AISC; reserve life at current throughput + reserve-grade trend (the depletion truth);
capital intensity ($/t of new capacity); ramp progress vs. feasibility schedule;
jurisdiction mix (% NAV by country tier); dividend framework linkage (payout % of FCF
vs. balance-sheet triggers).

## 3. Valuation framework

**P/NAV at conservative deck** (the sector's anchor) + **spot-torque table** (NAV and
FCF at spot vs. deck — the trade is often the gap between the two); EV/EBITDA only
within same capex phase (builders always look expensive, harvesters cheap —
phase-adjust). Reverse: implied long-run price in the equity vs. incentive price
(the price needed to bring new supply — from 04's cost curve): equities pricing above
incentive = supply response coming; below = the long thesis.

## 4. Earnings quality & forensics

Feasibility-study inflation (development names: compare study capex/opex to built
analogues); M&I resources marketed as reserves; royalty/streaming obligations netted
quietly out of realized price; capitalization of stripping/waste (deferred stripping
swings costs); "sustaining" capex reclassified as growth to flatter AISC; closure
liabilities discounted at heroic rates; JV/attributable confusion in headline
production.

## 5. Cycle & macro dashboard

Overlay of agent 04 (metal balance) + the *equity* cycle: industry capital discipline
(aggregate capex guidance — the supply response everyone denies until it arrives),
M&A wave (buying vs. building signal: paying premia for built assets = incentive
price below build cost), grade decline industry-wide (structural cost inflation),
energy costs (diesel/power in AISC), jurisdiction events calendar (elections, mining
codes, permits `[pull live]`). China demand pulse via agent 05's TSF/property →
agent 04 → here.

## 6. Data map

Technical reports (NI 43-101 / JORC — the primary documents; read the mine plan and
sensitivity tables); company AISC bridges; WoodMac-type cost curves via agent 04
(verify access); country risk rankings (Fraser Institute survey (verify)). BBG DAL
consensus; production results in quarterlies.

## 7. Thesis archetypes & management questions

**Longs:** cost-curve-position mispricing (quartile-1 asset priced as quartile-3 on
stale costs); successful ramp de-risking unpriced (the study-to-production discount
closing); commodity thesis (from 04) with the equity offering cheap torque + balance
sheet that survives being wrong. **Shorts:** grade cliff in the mine plan the market
hasn't read; builder meeting capex overrun base rates with financing gap; by-product-
flattered "low-cost" name into a co-product price break. **Questions:** mined grade
vs. reserve grade next 3 years; AISC bridge components and FX/energy assumptions;
ramp milestones and the slip plan; capital-returns trigger points; permitting critical
path with dates.
