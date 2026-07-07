# SECTOR MODEL — UTILITIES & INFRASTRUCTURE

*Full model spec for Agents 01/09. Scope: regulated electric/gas/water, hybrid
utilities with competitive arms, IPPs/renewables developers, contracted infra
(pipelines covered in energy-equities midstream).*

## 1. Model architecture

**Regulated core — the EPS algorithm is mechanical; model the inputs:**
```
1. RATE BASE roll-forward: opening + capex placed in service − depreciation
   (by jurisdiction — each state commission is its own P&L)
2. × allowed ROE × equity layer (the authorized capital structure)
   = authorized earnings power
3. − REGULATORY LAG (earned vs. allowed ROE gap: cost inflation between rate
   cases erodes earned ROE; riders/trackers reduce lag — model which costs have
   trackers) = earned earnings
4. FINANCING: capex − retained cash = external needs → debt (FFO/debt vs. agency
   thresholds) + EQUITY ISSUANCE (the per-share discipline: rate-base CAGR is
   marketing; EPS CAGR net of dilution is the truth)
5. Rate-case calendar: filed asks vs. historical granted (by commission), test-year
   mechanics, settlement patterns — the earnings-revision calendar
```
**IPP/renewables:** contracted (PPA price × P50 generation × availability) vs.
merchant (power curves from agent 04-adjacent power markets (verify data)) split;
development pipeline: MW by stage × success rate × development margin; tax-credit
monetization (transferability/structures `[pull live policy]`); interconnection-queue
position as the real scarcity asset.

## 2. KPI dictionary

Rate-base CAGR (by jurisdiction); earned vs. allowed ROE gap; capex plan and % with
riders; FFO/debt vs. downgrade threshold; equity needs as % of market cap (the
dilution overhang number); pending rate cases (ask, stage, expected order date);
**load growth** — the input that changed: data-center demand turned flat-load
utilities into growth stories; verify per service territory, including contracted vs.
speculative interconnection requests `[pull live]`; renewables: backlog MW, PPA price
trends, development cost/W.

## 3. Valuation framework

P/E vs. the group and its own band, adjusted for: rate-base growth × jurisdiction
quality × balance-sheet headroom (the three-factor sort explains most sector
dispersion); dividend-growth model cross-check (utilities are duration — agent 10
Axis 4 and real rates set the group multiple; the *relative* trade is jurisdiction +
growth mix). Reverse: implied rate-base growth and earned ROE vs. the filed capex
plan. IPPs: EV/EBITDA on contracted vs. merchant split — never blended.

## 4. Earnings quality & forensics

Rate-base growth funded by perpetual equity (per-share math first — some "growth
utilities" have flat EPS/share across a decade of rate-base CAGR); holdco leverage
atop regulated opcos (structural subordination); deferred costs/regulatory assets
ballooning (earnings booked, cash pending commission approval — disallowance risk);
pension assumptions; renewables developers: development-margin claims on
uncontracted pipeline, PPA escalators vs. cost inflation mismatch; wildfire/storm
liability regimes by state `[pull live]` — the tail risk that voids the bond-proxy
assumption.

## 5. Cycle & macro dashboard

Rates duration: group multiple tracks long real rates (agent 10); the sector's alpha
is idiosyncratic — commission calendars, load-growth announcements (data-center PPAs/
interconnection filings `[pull live]`), fuel-cost pass-through timing (gas prices via
agent 04 — lag mechanics differ by state), and policy (IRA-style credits, EPA rules)
`[pull live]`. Storm/wildfire season as event risk by territory (agent 08 gap-risk
input).

## 6. Data map

Commission dockets (free — the primary source: rate-case filings and orders); FERC
Form 1 (free, granular); EIA load and generation data (free); EEI industry data;
interconnection queues (RTO websites, free). BBG DAL consensus; `DVD` history.

## 7. Thesis archetypes & management questions

**Longs:** load-growth repricing (data-center demand contracts turning a 4% rate-base
story into 7%+ with the multiple still at flat-load levels); constructive-commission
transition underappreciated (new precedent order); post-crisis rehabilitation
(wildfire/storm overhang priced permanent, liability regime actually capped).
**Shorts:** equity-needs overhang meeting a downgrade threshold; earned-ROE erosion in
adversarial jurisdictions with no tracker relief; renewables developer with
uncontracted-margin fiction into rising costs. **Questions:** equity needs next 3
years, stated precisely; earned vs. allowed by jurisdiction and the lag plan; rate-
case asks and settlement read; load-growth pipeline — contracted vs. queue
speculation; wildfire/storm liability mitigation status.
