# SECTOR MODEL — SEMICONDUCTORS & SEMICAP

*Full model spec for Agents 01/09. Scope: fabless, IDM, foundry, memory, analog,
semicap equipment, EDA/IP.*

## 1. Model architecture

**Fabless/analog:** revenue = units × ASP by end market (auto, industrial, comms,
consumer, DC/AI — model each end market's unit cycle separately; blended extrapolation
is how everyone misses turns). Gross margin = f(utilization at foundry, mix, pricing);
opex mostly R&D (tape-out cadence lumps).
**IDM/foundry:** capacity model — wafer starts × yield × die/wafer × ASP; utilization
→ gross margin leverage is the P&L (fixed-cost absorption swings are most of the
margin move); capex → depreciation schedule (multi-year drag — model explicitly).
**Memory:** bit growth (supply: wafer adds + node migration; demand by application) ×
price-per-bit (cost curve declines ~annually; price tracks cost long-run, diverges
violently short-run); cash cost vs. price = the cycle P&L.
**Semicap:** WFE TAM × segment share (litho/etch/dep) × share shifts + **services**
(installed base × intensity — the ballast; model separately). Backlog/lead-time
conversion schedule.
**Mandatory schedule — the inventory triangle:** own inventory (days), channel
(distributor weeks), customer/hyperscaler inventory commentary. The cycle turns here
before revenue.

## 2. KPI dictionary

Book-to-bill; lead times (direction > level); utilization %; inventory days at each
triangle node; memory: spot vs. contract price spread (spot leads); semicap: WFE
guidance revisions, service attach %; content-per-unit trends (the secular line — $
of semis per car/server); China % of revenue and of *orders* (export-control exposure).

## 3. Valuation framework

**Through-cycle discipline:** normalize EPS over a full cycle (or use mid-cycle
margins on current revenue scale) — peak-EPS × peak-multiple is the classic top-tick
error; cheap-on-peak is expensive. Memory: P/B vs. the book's own cycle history
(trough ~1x, argue why this trough differs `[recall — durable, verify range]`).
Analog/semicap quality names: FCF yield through cycle + capital-return consistency.
Reverse DCF: what content growth + cycle assumption is priced; test vs. unit-cycle
base rates.

## 4. Earnings quality & forensics

Shipping into channel ahead of sell-through (distributor inventory build with "demand
strong" commentary); "design wins" narrated as revenue (they're options, discount
heavily); capitalization of R&D via customer-funded NRE classification; memory:
inventory carried at cost into a falling price market (writedown timing games);
utilization commentary vs. depreciation trend contradiction.

## 5. Cycle & macro dashboard

Global semis run one cycle: SIA sales 3mma y/y, WSTS revisions, Korea/Taiwan monthly
exports (the earliest public tape — agent 05's Korea line), TSMC monthly revenue,
distributor commentary, memory spot. Double-ordering builds when lead times stretch —
the down-cycle's fuel is always the up-cycle's order book. Policy layer: export
controls, CHIPS-style subsidies, tariffs — model China revenue at risk explicitly
`[pull current rules live]`. Rate/regime link: long-duration AI narratives compress
with real rates; unit cycles track global IP/PMIs (agent 10).

## 6. Data map

BBG: end-market splits from company decks; SIA/WSTS (public); TSMC monthlies (public);
DRAMeXchange-type spot pricing (verify vendor/access); distributor prints
(Arrow/Avnet) as channel truth. DAL fields for consensus; peer RV manual.

## 7. Thesis archetypes & management questions

**Longs:** trough-recognition (orders bottoming while consensus extrapolates the
down-cycle; inventory triangle draining); content-growth compounder priced as
cyclical; semicap services annuity underrated. **Shorts:** peak-margin "secular"
claims; channel stuffed + lead times collapsing; export-control revenue cliff
unpriced. **Questions:** where are customer inventories in weeks, by end market;
current lead times vs. 90 days ago; pricing assumptions in guidance (esp. memory
contract talks); China order behavior post-controls; utilization exit-rate.
