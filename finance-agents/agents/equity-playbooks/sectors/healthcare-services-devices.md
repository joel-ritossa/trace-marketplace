# SECTOR MODEL — HEALTHCARE SERVICES, MANAGED CARE & MEDTECH

*Full model spec for Agents 01/09. Scope: managed care (MCOs), providers (hospitals,
ambulatory), distributors/PBMs, medical devices, life-science tools & diagnostics.*

## 1. Model architecture

**Managed care:**
```
1. Membership by line (Commercial group/individual, Medicare Advantage, Medicaid,
   exchange) — each line has its own margin structure, growth driver, and
   regulatory throttle; model separately, never blended
2. Premium yield per member (rate updates: MA rate notice `[annual, pull live]`,
   Medicaid state rates, commercial renewals) 
3. − Medical costs: UTILIZATION (the whole print — trend by inpatient/outpatient/
   physician/Rx) × unit cost → MLR by line
4. − SG&A → operating margin; STAR ratings schedule (MA bonus revenue with a
   2-year lag — a knowable forward earnings input `[recall — durable mechanics]`)
5. Membership-flow risks: redeterminations, exchange subsidy policy `[pull live]`
```
**Providers:** volumes (admissions/surgeries by service line) × revenue per case
(payer mix: Medicare/Medicaid/commercial rates differ ~2x — mix shift IS the margin
story) − labor (the cost line: contract/agency staffing ratio vs. employed) − supplies.
**Devices:** procedure volumes by category (elective vs. acute — different macro
sensitivity) × ASP (pricing pressure by category; innovation resets ASP) × attach/
disposables mix (razor-razorblade installed-base models — model consumables
separately: that's the annuity). **Tools/diagnostics:** instruments (capex-cycle,
lumpy) vs. consumables/services (the base); end-market split (biopharma R&D budgets
vs. clinical demand). **PBM/distribution:** volume × cents-per-script/basis-point
economics; policy scrutiny as a standing multiple governor `[pull live]`.

## 2. KPI dictionary

MCO: MLR by line vs. guide, membership by line, utilization commentary specifics,
STAR trajectory, days-claims-payable (reserve adequacy tell). Providers: same-facility
volumes, payer mix, contract-labor %, length-of-stay. Devices: procedure growth by
category, ASP trend, installed base + utilization per box, new-product mix %.
Tools: instrument book-to-bill, consumables pull-through, biopharma end-market
commentary.

## 3. Valuation framework

MCOs: P/E vs. own band with the regulatory-cycle overlay (rate-notice and election
years compress); providers: EV/EBITDA with leverage scrutiny (labor inflation ×
fixed rates = the squeeze); devices: P/E–EV/EBITDA premium for consumables mix +
category growth — reverse DCF against procedure-growth base rates; tools: separate
the instrument cycle from the consumables annuity before comping.

## 4. Earnings quality & forensics

MCO: reserve development (favorable PYD releases juicing MLR — the insurance
discipline applies), days-claims-payable falling while MLR beats (paying claims
slower ≠ lower cost trend); utilization "normalization" claims each January;
risk-adjustment coding intensity (MA — regulatory audit exposure `[pull status]`).
Providers: contract-labor "one-time" framing; supply-cost capitalization. Devices:
channel stocking on launches (track utilization, not shipments); "recurring" revenue
definitions stretching consumables; tools: backlog quality after order-pull-forward
cycles (the post-2021 lesson `[recall — durable]`).

## 5. Cycle & macro dashboard

Utilization cycle (post-pandemic backlog burn vs. steady state — the sector's own
inventory cycle); policy calendar: MA rate notices (Jan/Apr), redetermination waves,
drug-pricing spillovers, election-year headline risk (agent 10 event overlay); labor
market for nurses (agent 05 employment detail — healthcare hiring is *your cost line*
here, inverted); device elective-procedure sensitivity to consumer health (mild) and
GLP-1 second-order theses `[contested — demand evidence, pull live]`; tools track
biopharma funding cycles (XBI/venture funding as the leading tape).

## 6. Data map

CMS (rate notices, STAR data, enrollment files — free); state Medicaid rate filings;
company MLR/membership supplements; procedure-volume proxies (claims data vendors
(verify)); hospital association data. BBG DAL consensus.

## 7. Thesis archetypes & management questions

**Longs:** utilization normalizing while pricing (rates) catches up with a lag — the
MCO margin-recovery arc; device category with procedure backlog + new-product ASP
reset; tools at instrument-cycle trough with consumables intact. **Shorts:** MLR
guide assuming utilization mean-reverts against evidence; provider labor squeeze with
fixed reimbursement; device consumables story where utilization-per-box is quietly
falling. **Questions:** MCO — utilization by category *this quarter*, DCP trend, STAR
trajectory by contract; provider — agency-labor % path, payer-mix trend; device —
procedure vs. shipment growth, ASP by category; tools — instrument orders vs.
consumables pull-through divergence.
