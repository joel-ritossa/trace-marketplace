# SECTOR MODEL — SOFTWARE / SAAS

*Full model spec for Agents 01/09. Scope: subscription software (seat + consumption),
infrastructure software, vertical SaaS; on-prem/license-transition names use the same
skeleton with a mix-shift schedule.*

## 1. Model architecture

**The ARR waterfall is the model.** Revenue is an output, not an input:
```
Beginning ARR
 + New-logo ARR            (reps ramped × productivity × win rate — the S&M linkage)
 + Expansion ARR           (installed base × expansion rate)
 − Contraction ARR
 − Churned ARR             (gross churn on base)
 = Ending ARR              → subscription revenue via in-period timing (~midpoint convention)
 + Services revenue        (low margin; flag if growing faster than subscription — implementation drag)
```
- **Consumption models** replace the waterfall with: customers × usage/customer ×
  unit price; NRR decomposes into usage growth vs. price — macro-sensitive in a way
  seat models aren't (usage cuts show in weeks, seats at renewal).
- **Reconciliation schedules (mandatory):** cRPO roll-forward vs. modeled ARR
  (forward truth check); billings = revenue + ΔDeferred (duration-adjust); the three
  must triangulate or the disclosure is hiding something.
- **Opex build is headcount-first:** S&M = ramped reps × loaded cost, tied to the
  new-ARR line via productivity (the "magic number" sanity: net-new ARR ÷ trailing
  S&M); R&D and G&A stepped, not %-smoothed. FCF nets SBC; model dilution share count
  explicitly (SBC ÷ avg price + options).

## 2. KPI dictionary

NRR = (base cohort ARR now ÷ same cohort 12m ago), audit the definition (multi-year
ramps, timing of downgrades). GRR = same, excluding expansion — floor of the business.
CAC payback (months) = S&M of prior period ÷ (new ARR × gross margin) × 12. Rule of 40
= growth % + FCF margin % *including SBC*. cRPO growth = the forward organic-truth
line. Net-new ARR sequential = the honest second-derivative once base is large.

## 3. Valuation framework

Primary: **EV/NTM gross profit (or ARR) regressed on growth + profitability** across
the peer set — buy residuals, not multiples. DCF: terminal FCF margin argued from
gross margin minus a mature-vendor opex structure (use aged large-cap software as the
existence proof), not asserted. Reverse DCF: solve for implied ARR CAGR and terminal
margin; compare against base rates for software at that scale — the crux exhibit.
License-transition names: value the post-transition state, bridge separately.

## 4. Earnings quality & forensics (sector-specific)

Billings duration games (multi-year invoicing juices billings); capitalized
commissions (amortization vs. new bookings trend); "one-time" items inside NRR;
contract assets rising (recognition ahead of invoicing); non-GAAP definition drift in
"adjusted FCF"; services margin as canary (negative services margin = paying to
install = product friction); channel/reseller stuffing at year-end (Q4 linearity
commentary); acquired-ARR mixed into "organic" after 12 months.

## 5. Cycle & macro dashboard

Seat models: lagging (headcount-linked — watch customer-industry layoffs); consumption:
coincident (cloud-cost optimization cycles — the 2022–23 pattern `[recall — durable]`).
Watch: hyperscaler capex + optimization commentary (the tide), IT-budget surveys, job
postings for the vendor's admins/developers (adoption proxy), seat-count exposure to
tech vs. non-tech end markets. Rate sensitivity: long-duration cash flows — multiple
compresses with real rates (regime input from agent 10).

## 6. Data map

Company disclosures carry the sector (ARR/NRR aren't standardized BBG fields — build
from filings/decks; flag any vendor-normalized "ARR" as approximate). BBG: consensus
via DAL BEst (verify); `RV` peer sets need manual curation (GAAP screens misrank
SaaS). Alt: job postings, G2/review velocity, BuiltWith-style install data (verify
vendor).

## 7. Thesis archetypes & management questions

**Long archetypes:** durable-NRR compounder priced as decelerator; margin inflection
as S&M efficiency turns (watch magic number trend); consumption trough after an
optimization cycle. **Short archetypes:** seat saturation + AI-substitution risk on
per-seat pricing; NRR broken but masked by definition; transition story where license
decline outruns cloud growth. **Questions:** gross logo retention by cohort and
segment; % of new ARR from existing vs. new logos; ramped-rep count and attainment;
pricing-model exposure to per-seat → usage shift; where AI features are priced vs.
given away.
