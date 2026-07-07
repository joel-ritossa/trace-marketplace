# SECTOR MODEL — CONSUMER DISCRETIONARY (retail · restaurants · brands · travel)

*Full model spec for Agents 01/09. Scope: softline/hardline retail, off-price,
restaurants, apparel/footwear brands, travel & leisure.*

## 1. Model architecture

**Retail:**
```
1. Revenue = store count × sales/store + e-commerce
   — comp (SSS) build: TRAFFIC × TICKET (ticket = AUR × UPT); model both;
   ticket-driven comps with falling traffic age badly
2. NEW-UNIT ECONOMICS schedule (the growth quality test): year-1 sales →
   maturation curve, 4-wall margin, build cost → cash-on-cash return & payback;
   cannibalization haircut; the reinvestment runway (remaining whitespace) is
   the terminal-value argument
3. GROSS MARGIN BRIDGE: merch margin (IMU, markdown rate) + freight + shrink +
   mix (e-com dilution fully loaded incl. returns/last-mile) 
4. INVENTORY DISCIPLINE line: inventory growth minus sales growth spread —
   the best forward markdown predictor in the sector `[recall — durable]`
5. SG&A: wage-rate exposure (hourly labor % of sales), occupancy leverage
```
**Restaurants:** units × AUV; comp = traffic × mix/price; company vs. franchised
split (franchise royalty stream = high-multiple annuity; company stores carry the
margin cycle — model separately and value separately); development pipeline net of
closures; commodity basket + labor inflation vs. menu price.
**Brands:** wholesale vs. DTC mix shift (DTC = margin + data but capital + inventory
risk); distribution-quality discipline (off-price channel % = brand-equity thermometer).
**Travel/leisure:** capacity × occupancy/utilization × rate (RevPAR logic);
booking-window data as the forward tape.

## 2. KPI dictionary

SSS split traffic/ticket; inventory-sales spread; markdown rate vs. plan; merch
margin; new-unit cash-on-cash and payback; 4-wall margin; e-com % and its fully
loaded margin; restaurants: AUV trend, company margin, franchise mix, pipeline;
brands: DTC %, off-price exposure; sector-wide: promotional cadence vs. a year ago.

## 3. Valuation framework

P/E–EV/EBITDA vs. own band, with the **unit-growth annuity** cases (restaurants,
concept retail) on DCF of the rollout: units × mature 4-wall × return on incremental
build — the reverse DCF question is "how many units at what returns does the price
require, vs. credible whitespace." Retail without unit growth trades on comp momentum
+ margin normalization — mean-reversion math both directions. Franchise royalty
streams deserve bond-plus multiples; don't blend them with company-store cyclicality.

## 4. Earnings quality & forensics

Calendar games (53rd week, holiday shift — always calendar-adjust comps); "retail
calendar" vs. fiscal in comps definitions; pack-and-hold inventory (off-price)
obscuring freshness; landlord concessions/rent abatements smoothing occupancy;
gift-card breakage assumptions; loyalty deferrals (points liabilities re-measured to
juice revenue); restaurants: refranchising gains dressed as operating earnings;
brands: channel-stuffing wholesale ahead of quarter-end (DSO tell), returns reserves
in DTC.

## 5. Cycle & macro dashboard

Discretionary is the real-income + credit sector: agent 05's real-DPI, savings rate,
and revolving-credit data lead comps; trade-down chains (full-price → off-price →
discount — position names on the chain and trade the *relative*); wage-rate cycle
hits SG&A (hourly-labor names) before it helps comps; housing turnover drives
home-related retail (agent 05 housing module); gas prices = regressive discretionary
tax (agent 04). Weather is a real but overused excuse — grant it once, not twice.

## 6. Data map

Company comps/traffic disclosures; credit/debit-card spend panels (verify vendor);
foot-traffic data (verify vendor); OpenTable/TSA/hotel STR data for travel (mixed
free/paid (verify)); scanner where applicable. BBG DAL consensus.

## 7. Thesis archetypes & management questions

**Longs:** inventory-clean inflection (spread deeply negative, margins troughing →
the markdown cycle ends before consensus models it); unit-growth compounder with
year-1 returns *improving* (cohort table proves it); franchise-mix shift re-rating.
**Shorts:** traffic-negative ticket-flattered comps meeting a promotional cycle;
inventory-sales spread blowing out into a weak season; unit growth outrunning
returns (new cohorts underperforming, whitespace fiction). **Questions:** traffic vs.
ticket now, quarter-to-date; inventory position vs. plan and the markdown plan;
newest unit cohort vs. class-of-two-years-ago; promotional posture vs. the category;
labor-hour investment vs. wage rate assumptions.
