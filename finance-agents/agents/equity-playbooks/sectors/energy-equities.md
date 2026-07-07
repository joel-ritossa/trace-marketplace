# SECTOR MODEL — ENERGY EQUITIES (E&P · majors · refiners · midstream · services)

*Full model spec for Agents 01/09. The commodity call belongs to Agent 04
(`commodity-playbooks/energy.md`); this module models the EQUITY — capture,
conversion, and capital allocation at a given commodity deck.*

## 1. Model architecture

**E&P:**
```
1. Production by asset: existing PDP base × decline curve + new wells
   (capex ÷ well cost × type curve × timing) — the treadmill arithmetic:
   maintenance capex = spend to hold production flat at current declines
2. Realizations: benchmark (from agent 04 strip) − differentials (basin basis,
   quality, transport) ± HEDGE BOOK schedule (volumes, structures, strikes by
   quarter — mark it every run)
3. Cash costs: LOE + GP&T + production taxes + cash G&A → cash netback/boe
4. → EBITDA → FCF at strip AND at agent-04 scenario decks (the two-deck discipline:
   never one price)
5. Capital returns waterfall: framework (base div + variable/buyback %) → per-share
   FCF/production growth (absolute growth is the old regime; per-share is the test)
NAV (parallel): PV-10 by reserve category at deck prices + acreage optionality − debt
```
**Refiners:** throughput × **capture rate** (realized margin ÷ indicator crack — the
operations quality metric) − opex/bbl; turnaround calendar; RIN/regulatory costs;
product yield flexibility. **Midstream:** volumes × fee (take-or-pay % vs.
commodity-exposed %); contract tenor ladder; distributable CF coverage. **Services:**
active rig/frac count × pricing (dayrates lead reported revenue ~2 quarters); NAM
short-cycle vs. international/offshore long-cycle mix; backlog quality.

## 2. KPI dictionary

Base decline rate; maintenance capex; reinvestment rate (capex ÷ CFO); FCF breakeven
(the WTI/Brent price where FCF = 0 *after* base dividend); netback/boe; F&D cost and
recycle ratio (netback ÷ F&D — the value-creation test); PDP % of PV-10; hedge
coverage next 4/8 quarters; refiners: capture %, Nelson complexity; midstream:
coverage ratio, leverage vs. IG threshold.

## 3. Valuation framework

FCF yield at strip (the sector's clearing metric in the returns regime) cross-checked
against EV/EBITDA vs. history and **P/NAV at conservative deck**; spot-torque table
(EPS/FCF at ±$10–20/bbl) reported separately from the base case. Reverse: what deck ×
duration does the price imply — energy equities chronically price a lower deck than
strip late-cycle and higher early (state which regime you're in via agent 04's curve).
Refiners on mid-cycle capture × normalized crack; midstream on DCF yield vs. tenor
risk.

## 4. Earnings quality & forensics

Half-cycle well IRR marketing (land/G&A/infrastructure excluded — full-cycle it);
"maintenance capex" definitions that let production slip; type-curve inflation
(compare stated EURs to state-data actuals (verify vendor)); reserve-report
sensitivity to price deck (SEC PV-10 uses trailing prices — normalize); hedge
accounting obscuring realized prices; midstream: coverage propped by deferred
maintenance; "capital discipline" claims — audit capex guidance revisions vs. the
original frame, every quarter.

## 5. Cycle & macro dashboard

The equity's own cycle laid over agent 04's commodity view: capital-discipline regime
integrity (watch aggregate industry capex guidance — the regime breaks when someone
grows), service-cost inflation (eats netbacks with a lag), M&A wave position
(consolidation = inventory scarcity signal), energy policy `[pull live]`. Equity/
commodity beta drifts: energy equities decouple from crude when FCF regime is trusted
— track the rolling beta; it's the market's vote on discipline.

## 6. Data map

Agent 04 (deck, curve, cracks); state production data (TX RRC/ND — verify access);
rig/frac counts (Baker Hughes weekly, free); company hedge tables (10-Q derivative
note); EIA drilling productivity report. BBG DAL consensus; `FA` for segment detail.

## 7. Thesis archetypes & management questions

**Longs:** inventory-depth mispricing (years of core locations at current pace vs.
market's fear); refiner golden-age setups (capacity closures + product tightness —
route from 04); discipline-regime FCF yield with hedge-protected floor. **Shorts:**
treadmill names (decline outrunning capex efficiency, "growth" consuming FCF);
inventory exhaustion masked by M&A; midstream coverage fictions. **Questions:**
maintenance capex at flat production, stated plainly; core inventory years at current
rig count; hedge philosophy at cycle turns; the *use* of the next $10 of FCF/bbl
(returns vs. drilling — the whole thesis in one answer).
