# SECTOR MODEL — TRANSPORTS (rails · trucking · parcel · airlines · shipping)

*Full model spec for Agents 01/09. Freight doubles as a macro tell — route weekly
volume data to Agent 10's growth composite regardless of position.*

## 1. Model architecture

**Rails:** volumes by commodity group (coal, grain, intermodal, chemicals, autos —
each with its own driver; weekly AAR carloads are public) × revenue per car (core
price + fuel surcharge — model separately; surcharge lags fuel) → revenue; OR
(operating ratio) bridge: volume leverage + price/inflation spread + service-driven
costs (velocity/dwell degrade → crews/overtime → OR). Service metrics are *leading*
cost indicators — model them, don't just note them.
**Truckload:** tractor count × utilization (loaded miles/tractor) × rate/mile with
**spot/contract mix schedule** — the cycle model: spot < contract → shippers defect
to spot, contract reprices down at bid season (the lag is the P&L); capacity exits at
spot below operating cost → tighten → spot spikes. Model where in that clock you are.
**LTL:** shipments × weight/shipment × yield; network density = incremental margin;
pricing discipline is oligopolistic (vs. TL's atomized boom-bust).
**Parcel:** volumes by product × yield (net of surcharges), B2B/B2C mix (density
economics), capex cycle (network build vs. sweat).
**Airlines:** capacity (ASMs) × load factor × yield → RASM vs. CASM-ex + fuel
(hedge schedule where applicable); model *industry scheduled capacity* (published
forward — the discipline test) against demand; balance sheet (leases + debt) makes
equity a call option on the cycle — say so in sizing notes.
**Shipping (dry/tanker/container):** spot vs. time-charter mix, fleet supply
(orderbook % of fleet, delivery schedule, scrapping age profile) — the supply model
IS the thesis; demand in tonne-miles (routes matter — route from agent 04
geopolitics/chokepoints).

## 2. KPI dictionary

Rails: OR (mix-adjusted), carloads y/y by group, velocity/dwell, revenue-per-car ex
fuel. TL: rate/mile spot vs. contract, tender rejection rate (the real-time tightness
gauge (verify source)), tractor utilization. Parcel: volume growth vs. yield growth
(the trade-off line), density proxies. Airlines: RASM/CASM-ex spread, forward
capacity vs. GDP-trend demand, fuel hedge %. Shipping: orderbook %, spot rates vs.
cash breakeven, fleet age.

## 3. Valuation framework

Rails: P/E vs. quality history (OR improvement stories re-rate; audit vs. §4);
TL/LTL: through-cycle EPS (never peak-spot earnings × multiple), P/B floors for
asset-heavy; airlines: EV/EBITDAR through cycle with the equity-optionality caveat;
shipping: P/NAV (vessel values — public sale-and-purchase marks) and cycle position
over multiples. Reverse: what freight-cycle duration does the price imply.

## 4. Earnings quality & forensics

Fuel surcharge flattering yields (strip it everywhere); rails: "structural" OR gains
that are mix (intermodal vs. merchandise) or deferred maintenance (service metrics
reveal it later); accessorial/surcharge dependence in parcel yields; airlines:
capacity "discipline" claims vs. published schedules (check the schedules, not the
calls); loyalty-program accounting (deferred revenue assumptions); shipping:
time-charter "coverage" at below-market rates dressed as stability.

## 5. Cycle & macro dashboard

The freight cycle leads the goods economy: tender rejections, spot rates, and Class-8
truck orders (capacity investment = late-cycle marker `[recall — durable]`) lead
reported earnings by quarters. Inventory cycles (agent 05: retail inventory/sales)
drive freight demand directly. Airlines track services consumption + fuel (agent 04).
Shipping is agent 04's freight/chokepoint section wearing equity clothing — Red Sea
style route disruptions are tonne-mile demand shocks `[route from 04]`.

## 6. Data map

AAR weekly carloads (free); Cass Freight Index (free monthly); DAT/FreightWaves spot
and tender data (verify access); TSA throughput (free); airline schedule data (verify
vendor); Clarksons-type shipping data (verify). BBG DAL consensus.

## 7. Thesis archetypes & management questions

**Longs:** freight-cycle trough (rejections inflecting, capacity exited) before bid
season reprices contract up; rail service inflection → OR path credible; shipping
supply story (low orderbook + demand shock) with NAV support. **Shorts:** peak-spot
earnings capitalized as permanent; airline capacity indiscipline arriving into soft
demand; parcel density erosion (B2C mix) behind headline volume growth. **Questions:**
rails — service metrics trajectory and the OR bridge; TL — contract-rate expectations
into bid season, fleet plan; airlines — forward capacity vs. published industry
schedules; shipping — charter-cover strategy and vessel-value marks.
