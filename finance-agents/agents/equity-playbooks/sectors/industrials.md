# SECTOR MODEL — INDUSTRIALS (machinery · multis · electrical · A&D)

*Full model spec for Agents 01/09. Scope: machinery, multi-industry, electrical
equipment, aerospace & defense, capital goods.*

## 1. Model architecture

```
1. BY SEGMENT: orders → backlog → revenue conversion (the timing schedule:
   book-to-bill × backlog turn rate; long-cycle segments convert over years,
   short-cycle books-and-ships in-quarter — model the mix explicitly)
2. Volume drivers per segment tied to observables: PMIs/capex intentions
   (short-cycle), megaproject/infrastructure awards (long-cycle), aircraft build
   rates (aero supply chain), defense budgets/program schedules (A&D)
3. PRICE/COST BRIDGE (the quarterly margin truth): carryover price + new price
   − input inflation (steel, components, labor) − freight = spread; model in bps
4. Incremental margins by segment (volume leverage) ± mix (aftermarket vs. OE)
5. AFTERMARKET/SERVICES separately: installed base × attach rate × pricing —
   higher margin, less cyclical, the quality ballast; its % of segment profit is
   the multiple argument
6. Below the line: restructuring (audit if perennial), M&A contribution vs.
   "organic" definition, FCF conversion (target ≥100% of NI; inventory cycles
   distort — normalize)
```
**A&D specifics:** program accounting (EACs — estimate-at-completion revisions are
the earnings events; cume-catch-up adjustments both ways), fixed-price development
risk vs. cost-plus mix, aftermarket tied to flight hours/fleet age.

## 2. KPI dictionary

Orders growth, book-to-bill by segment; backlog + backlog margin (vs. P&L margin =
forward mix signal); price/cost spread bps; incremental/decremental margins;
aftermarket %; channel inventory (distributor weeks); FCF conversion; ROIC vs. WACC
through cycle; A&D: EAC net adjustments, book-to-bill on programs, flight-hour
recovery.

## 3. Valuation framework

EV/EBITA on **mid-cycle** earnings (state where you think the cycle is and the
mid-cycle bridge); quality multis re-rate on aftermarket mix + FCF consistency —
compare multiple to its *own* mix history, not just peers; SOTP only with a breakup
path. Reverse: implied incremental margins and cycle duration vs. the segment
evidence.

## 4. Earnings quality & forensics

Organic-growth definition games (acquisitions entering "organic" at month 13 —
check); perennial restructuring add-backs (10 years of "one-time" = the cost
structure); percentage-of-completion claims and unapproved change orders swelling
contract assets (megaproject names); channel stuffing ahead of price increases
(distributor pre-buys pull forward demand — ask, and watch the following quarter);
EAC adjustment asymmetry (favorable catch-ups clustering before comp dates);
capitalized development on programs likely to cancel.

## 5. Cycle & macro dashboard

Short-cycle: global PMIs/new orders (agent 05's ISM module — orders-minus-inventories
is this sector's demand line), distributor destocking phase, small-business capex
plans (NFIB). Long-cycle: nonres construction awards, infrastructure/energy-transition
project FIDs, reshoring capex announcements `[pull live]`. A&D: defense budget
cycles + geopolitical regime (agent 10), aircraft build-rate announcements. Price/cost:
steel/copper (agent 04) and freight lead the bridge by ~2 quarters.

## 6. Data map

Company order/backlog disclosures; distributor prints (Fastenal/Grainger monthlies —
free, high-frequency channel truth `[verify cadence]`); AIA architecture billings,
Dodge construction data (verify access); defense budget docs `[URL]`. BBG DAL
consensus; `SPLC` for supply-chain positions (verify).

## 7. Thesis archetypes & management questions

**Longs:** destocking trough with orders inflecting while consensus extrapolates;
aftermarket mix-shift re-rating unrecognized; megaproject cycle beneficiary with
backlog margin above P&L margin. **Shorts:** price/cost squeeze arriving as carryover
price fades into sticky input costs; backlog burn without replacement (book-to-bill
<1 masked by long-cycle revenue); roll-up whose organic engine stalled. **Questions:**
backlog margin vs. shipping margin; price carryover remaining by quarter; channel
inventory weeks vs. normal; incremental-margin guidance by segment and the
decremental commitment if volumes fall; EAC assumption changes this quarter (A&D).
