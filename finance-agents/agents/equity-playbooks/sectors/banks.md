# SECTOR MODEL — BANKS

*Full model spec for Agents 01/09. Scope: money-center, regionals, trust/custody;
brokers/asset managers share the fee-line logic only.*

## 1. Model architecture

**Balance-sheet first, P&L second.** Build in this order:
```
1. Deposits by type (NIB / interest-bearing checking / savings / CDs / brokered)
   — each with its own beta to policy rates and a mix-migration assumption
2. Loans by category (C&I, CRE by property type, resi, cards, other consumer)
   — growth tied to macro (agent 10) and management appetite; spreads per category
3. Securities book (AFS/HTM split, duration, roll-off reinvestment yields)
4. → NII = earning assets × NIM, where NIM is OUTPUT of the repricing schedule:
   asset repricing (fixed-rate roll into current yields = the tailwind/headwind
   arithmetic — model the back-book yield vs. new-money yield gap explicitly)
   minus funding cost path (betas × policy path from agent 03's pricing input)
5. Fee income by line (service charges, cards/interchange, wealth, IB/trading,
   mortgage — each with its own driver)
6. Provisions = expected NCOs by loan category (loss curves × balances) ± reserve
   build/release to target coverage ratios (CECL is front-loaded: growth costs
   provisions today)
7. Opex (efficiency-ratio bridge with stated investments), taxes
8. Capital schedule: RWA growth, CET1 target vs. requirement (+ buffers/SCB),
   AOCI burn-down schedule → distributable capital → buyback/dividend → share count
```
**Mandatory sensitivity table:** NII at ±100bp parallel and at steepener/flattener —
disclosed IRR tables cross-checked against your own repricing model.

## 2. KPI dictionary

NIM (and the *exit-rate* NIM vs. average); deposit beta cumulative-cycle-to-date; NIB
mix %; loan/deposit ratio; efficiency ratio; NCO % by category vs. reserve % by
category (coverage); criticized/classified migration; CET1 vs. requirement; ROTE;
TBV/share growth **including AOCI** (the honest compounding line); uninsured-deposit
share (the 2023 run-risk metric).

## 3. Valuation framework

**P/TBV regressed on ROTE across peers** — the sector's pricing law
(Gordon-consistent: justified P/TBV ≈ (ROTE − g)/(COE − g)); buy the residual with a
reason. Cross-check: capital-return yield (buyback + dividend ÷ market cap) at
sustainable payout. Reverse: what through-cycle ROTE and credit cost does the price
imply — test vs. the bank's own history and mix. Never EV/EBITDA; never "cheap on
P/E" without the credit-cycle position stated.

## 4. Earnings quality & forensics

Reserve releases doing the EPS work (split "PPNR beat" from "provision beat" every
quarter — agent 09's decomposition); securities restructurings (crystallize AOCI loss,
re-risk longer — read the re-invested duration); HTM as a mark-avoidance parking lot
(mark it yourself: disclosed fair values); CRE granularity refusal (demand office %,
maturity wall by year, reserve per office loan); modified/extended loans
("extend-and-pretend" shows in Stage-2-style disclosures and rising accruing-past-due);
brokered/wholesale funding creep; gain-on-sale income classified as recurring.

## 5. Cycle & macro dashboard

Banks are a rates + credit + regulation sandwich: curve shape (steeper = NIM relief
with a lag via reinvestment), policy path (deposit betas peak late-cycle), credit
cycle position (agent 10 quadrant; NCOs lag unemployment), loan demand (SLOOS —
quarterly Fed survey, the sector's own leading indicator `[URL, free]`), regulatory
calendar (capital-rule proposals reprice payout capacity `[pull live]`). Funding
stress: agent 11's dashboard is directly relevant (reserve scarcity → deposit
competition).

## 6. Data map

Call reports / FFIEC (free, granular — loan detail beyond the 10-Q (verify access
path)); FDIC QBP (industry aggregates); SLOOS; company Y-9C. BBG: `DDIS` for holdco
debt (verify), DAL fields for consensus; KBW indices for relative context (verify
tickers).

## 7. Thesis archetypes & management questions

**Longs:** back-book repricing tailwind not in estimates (fixed-asset roll math);
over-reserved franchise exiting a feared credit cycle; deposit-franchise quality
mispriced after a sector-wide run scare. **Shorts:** deposit beta catching up to a
"cheap funding" story; CRE office wall meeting thin reserves; NIM guide assuming betas
stop while competition says otherwise. **Questions:** cumulative deposit beta
assumption to cycle-end and what competitors force; new-money yields vs. back book by
bucket; office reserve % and appraisal vintage; buyback appetite vs. AOCI burn-down
and rule proposals.
