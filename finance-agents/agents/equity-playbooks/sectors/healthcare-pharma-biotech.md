# SECTOR MODEL — PHARMA & BIOTECH

*Full model spec for Agents 01/09. Scope: big pharma, specialty pharma, biotech
(commercial and clinical-stage). The unit of analysis is the ASSET (drug), not the
company — the company is a portfolio of asset DCFs plus a pipeline of options.*

## 1. Model architecture

**Per marketed asset:**
```
1. Patient funnel: prevalent/incident population × diagnosis rate × treatment rate
   × line-of-therapy position × market share (ramp curve benchmarked to analogue
   launches — launch trajectories cluster by specialty vs. primary care
   `[recall — durable]`)
2. × Net price: LIST price − gross-to-net (rebates, discounts — G2N spread by
   channel; list-price "growth" is not revenue growth), price by geography
   (US/EU/JP tiers), IRA-negotiation exposure by date `[pull live]`
3. × Duration/compliance → revenue by asset by year
4. EROSION SCHEDULE: LOE (loss of exclusivity) map by asset — patent/regulatory
   exclusivity dates, erosion curve small-molecule (fast, generic cliff) vs.
   biologic (slower, biosimilar glide) `[recall — durable shapes]`
```
**Pipeline (per clinical asset):** rNPV = peak sales scenario × PoS (probability of
success **by phase × indication base rates** — use published PoS tables (verify
current source), never management's confidence) − remaining R&D − launch costs,
discounted. Sum of parts: marketed DCFs + risked pipeline + platform/BD optionality
− net debt.
**Clinical-stage biotech addendum:** cash runway (quarters at current burn) vs.
catalyst calendar — the financing model IS the model: dilution *before* the readout
is the base case; model the raise (size, price) explicitly.

## 2. KPI dictionary

Scripts (TRx/NRx trends — weekly US data (verify vendor access)); G2N spread and
direction; net price growth vs. volume growth split (the staples discipline applies);
LOE revenue-at-risk by year as % of total; pipeline rNPV as % of EV; R&D productivity
(approvals/pivotal wins per $ R&D over 5y); runway quarters (biotech); short interest
+ options skew into readouts (positioning is half of biotech event trades — route to
agent 08).

## 3. Valuation framework

SOTP rNPV (the anchor); big pharma cross-check: P/E on **cliff-adjusted EPS**
(earnings net of the LOE hole — consensus routinely under-models erosion 3+ years out
`[recall — durable]`). Reverse: what does the price imply for the lead pipeline
asset's PoS/peak — compare to base rates; "the pipeline is free" is a real setup,
verify the marketed base covers EV first. Biotech: EV vs. risked rNPV with the
financing haircut; platform premium only with repeat clinical proof.

## 4. Earnings quality & forensics (incl. trial-design forensics)

**Financial:** G2N reserve true-ups (revenue quality); channel inventory in launch
quarters (stocking vs. demand — scripts arbitrate); "adjusted" EPS excluding
milestones/amortization games; R&D capitalization via BD structures (in-process R&D).
**Trial-design red flags (each has a base rate of ending badly):** endpoint switched
mid-trial; open-label with subjective endpoints; post-hoc subgroup "wins"; single-arm
vs. historical controls in indications with placebo drift; underpowered phase-2
"trends" marketed as efficacy; comparator dosed unfairly; enrollment slippage
(predicts readout slippage and site desperation). Score every catalyst thesis against
this list before sizing.

## 5. Cycle & macro dashboard

Policy is the sector's macro: IRA negotiation lists/timelines, FTC posture on M&A,
FDA leadership/approval standards drift `[all pull live]`; XBI-style biotech risk
appetite tracks real rates (long-duration cash flows — agent 10); M&A wave position
(big-pharma cliff pressure = BD demand for biotech — the sector's own liquidity
cycle). Readout calendar = the event-risk map (feed agent 08's gap-risk section for
held names).

## 6. Data map

ClinicalTrials.gov (free — enrollment, design, dates); FDA calendars (PDUFA dates,
AdComm schedules — free); script data (verify vendor); company G2N disclosures;
PoS base-rate literature (verify current edition); patent/exclusivity: FDA Orange/
Purple Book (free). BBG DAL consensus; `CN` for readout headlines.

## 7. Thesis archetypes & management questions

**Longs:** pipeline-is-free (marketed assets cover EV, lead asset optionality
unpriced); LOE fear overdone (erosion curve modeled too fast vs. formulation/biologic
reality); launch inflection visible in weekly scripts before consensus revises.
**Shorts:** cliff denial (consensus flat through a dated LOE); phase-3 readout with
stacked design red flags and crowded long positioning; specialty pharma price-hike
model exhausted (G2N eating list). **Questions:** G2N direction and payer-mix drivers;
launch trajectory vs. named analogue; enrollment status vs. plan; lifecycle plan for
the LOE (reformulation, combos — and their honest PoS); BD appetite and capacity.
