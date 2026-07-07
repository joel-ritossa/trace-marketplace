# SECTOR MODEL — INTERNET / PLATFORMS / MARKETPLACES

*Full model spec for Agents 01/09. Scope: advertising platforms, marketplaces,
e-commerce, subscription consumer internet, ride/delivery.*

## 1. Model architecture

**Ad platforms:** revenue = users × time/engagement × ad load × price-per-ad (CPM/CPC).
Model ad load and price *separately* — load increases are finite (user-experience
ceiling), price rides advertiser demand (cyclical) and targeting efficacy
(privacy/policy shocks hit here). Advertiser mix (brand vs. DR, verticals) drives
cyclicality.
**Marketplaces:** GMV = buyers × frequency × AOV; revenue = GMV × take rate. Model
take rate by line (core commission + payments + ads + logistics) — "take-rate
expansion" theses must name which line and its ceiling (seller economics cap it:
model seller margin after all platform fees).
**E-commerce/1P:** GMV split 1P (revenue = GMV) vs. 3P (revenue = fees) — mix shift
distorts revenue growth vs. GMV growth; fulfillment cost per unit × density curve.
**Subscription consumer:** cohort model — adds × conversion × churn curve by cohort
age; price increases tested against churn elasticity by vintage.
**Shared schedules:** capex → depreciation (infra cycles compress margins with a lag
— model the D&A wave from disclosed capex, don't let "EBITDA margin stable" hide it);
SBC and share count; regulatory line items (DSA/DMA-type compliance, app-store fee
rulings `[pull live]`).

## 2. KPI dictionary

DAU/MAU (+ ratio as engagement quality); ARPU by geography (mix masquerades as
growth — model regions separately); GMV, take rate by revenue line; CAC by channel,
paid vs. organic mix; contribution margin per order (ride/delivery: fully loaded
incl. incentives — the profitability truth); incremental margins (the operating-
leverage story lives or dies here); FCF after *all* capex.

## 3. Valuation framework

EV/gross profit for marketplaces (revenue mixes 1P/3P incomparably); ad platforms on
EV/EBIT with capex-cycle adjustment; DCF with explicit maturity S-curve (penetration
ceilings by market); reverse DCF: implied users × ARPU at terminal — sanity-check
against population/wallet math (the "TAM arithmetic" test kills more internet theses
than any multiple argument). SOTP only where segments have real external comps and a
separation path.

## 4. Earnings quality & forensics

Metric retirement (a KPI that stops being disclosed was about to inflect); user
definition changes (family-of-apps aggregation, bot policies); contra-revenue
(incentives netted vs. grossed — ride/delivery growth rates depend on it); "adjusted
EBITDA" excluding SBC in SBC-heavy comps; capitalized content/software drift;
related-party GMV (emerging-market marketplaces); cohort disclosure vanishing when
vintages age badly.

## 5. Cycle & macro dashboard

Advertising is early-cyclical (DR pulls back first, brand follows); e-commerce tracks
goods consumption (agent 05 retail control + discretionary basket); privacy/platform
policy shocks (OS-level changes) are step-function risks — track the policy calendar.
Rates: long-duration growth multiple sensitivity (agent 10 Axis 3/4). Watch: ad-agency
commentary, app-download/engagement trackers, aggregate e-commerce data.

## 6. Data map

Company KPIs from filings/decks (definitions logged per §4); app-ranking and
engagement trackers (verify vendor); web traffic (verify vendor); advertising
industry forecasts (Magna/GroupM-type, public summaries). BBG consensus via DAL;
regulatory dockets `[URL]`.

## 7. Thesis archetypes & management questions

**Longs:** monetization gap (engagement grown, ad load/pricing not yet harvested);
take-rate line with genuine headroom (ads attach on marketplaces); margin inflection
as incentives roll off with density. **Shorts:** saturation + ARPU mix deterioration;
take-rate at seller-economics ceiling with competition arriving; capex wave about to
hit the P&L as D&A while growth decelerates. **Questions:** ad load today vs. stated
comfort ceiling; seller P&L after all fees (can you raise take rate and *show* seller
health); incrementality of ads revenue vs. cannibalizing organic GMV; cohort payback
by vintage, not blended.
