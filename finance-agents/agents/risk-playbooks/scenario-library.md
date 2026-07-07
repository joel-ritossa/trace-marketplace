# RISK PLAYBOOK MODULE — SCENARIO LIBRARY & HEDGE MATRIX

*Loaded by Agent 08. Historical episodes are durable facts but cited magnitudes are
from recall — `[recall — verify exact figures before publishing them in a note]`.
Use episodes as severity calibration and correlation templates, never as forecasts.*

---

## 1. Historical episode library (severity + correlation templates)

For each episode: the mechanism, the cross-asset signature, and what hedged vs. what
failed. Approximate magnitudes flagged; verify before quoting.

- **GFC liquidation phase (Sep–Nov 2008):** everything-correlates regime; equities
  ~−30%+ in weeks, HY spreads toward extreme wides, oil halved, gold *fell first*
  (dash-for-cash) then led recovery. Lesson: in true deleveraging, only duration,
  USD, and vol hedge; diversification is an illusion measured in calm markets.
- **Taper tantrum (May–Sep 2013):** real-rate shock; US 10y ~+130bp, EM FX/local
  rates crushed, gold −20%+, equities chopped but survived. Template for
  "policy-communication shock in a levered carry world."
- **CNY devaluation (Aug 2015; echo Jan 2016):** China-credibility shock; commodity
  currencies and metals led down, SPX ~−11% flash, vol-control/CTA amplification.
  Template for China-policy surprise.
- **Vol unwind (Feb 2018, "Volmageddon"):** positioning-mechanics shock — short-vol
  products; SPX ~−10% in days with *no macro news*. Template for crowded-structure
  unwinds: the trigger is flow, not fundamentals.
- **Q4 2018:** QT + hiking into slowing growth; SPX ~−20% peak-trough, credit shut,
  Powell pivot ended it. Template for "policy overtightening" scenario and for how
  fast policy reaction functions flip.
- **COVID crash (Feb–Mar 2020):** fastest −30%+ ever; **Treasury-basis blowup** —
  even USTs sold in the worst week (leveraged-fund unwinds), gold −12% mid-crash;
  then the largest policy response ever. Template for exogenous shock + market-
  structure failure: your hedges must survive the week when *everything* is sold.
- **2022 hiking cycle:** the slow-motion regime change; US 10y +~240bp over the year,
  equities and bonds down together (stock-bond correlation flipped positive), 60/40's
  worst year in decades, USD wrecking ball, UK LDI blowup (Sep–Oct) as the levered-
  duration casualty. Template for inflation-shock world — the regime where agent 10's
  Axis-4 sign is positive.
- **SVB / regional banks (Mar 2023):** rate risk realized as credit event; 2y yields
  fell at record speed (−100bp+ in days), front-end vol exploded, equities *rose*
  within weeks. Template for "the hike breaks something": the winning hedge was
  front-end receivers/calls, not equity puts `[recall — durable lesson]`.

**Usage rules:** (1) pick the 2–3 episodes closest to the *current* regime (from agent
10) as the correlation template for §5 joint scenarios; (2) severity calibration =
"a 1-in-10-year event in this regime looked like X"; (3) always note what *failed to
hedge* in the template episode — that's the basis-risk warning for §8.

## 2. Factor shock-sizing conventions (for the §5 grid)

Express scenario shocks in regime-conditional σ, not just fixed percentages: pull
current 1y realized vol per factor via DAL, then standard grid = ±1σ, ±2σ, and the
episode-calibrated tail (from §1). Fixed-percentage scenarios (equities −10% etc.)
stay in the grid for comparability across runs — report both. Never let a
"conservative" fixed shock understate a high-vol regime.

## 3. Hedge instrument matrix (exposure → instruments → cost → basis risk)

| Unintended exposure | First-line hedge | Cost profile | Basis risk / failure mode |
|---|---|---|---|
| Broad equity beta | Index futures reduction; put spreads when vol cheap vs. realized | Futures: carry ≈ 0; puts: premium, check skew richness | Single-name gap risk unhedged; put spreads cap protection |
| Rates duration | Futures/swaps at the exposed curve point | Carry = curve slope at that point | Key-rate mismatch (hedged 10y, hurt at 2y); convexity on big moves |
| USD (aggregate) | DXY-proxy basket or the specific crosses | Carry = rate differentials (can be expensive short EM) | Your USD exposure is rarely DXY-weighted — hedge the actual crosses |
| China/EM growth cluster | Trim first (usually the answer); else AUD or copper shorts as liquid proxies | Proxy carry varies | Proxy correlation breaks when the shock is idiosyncratic to your holding |
| Energy complex | Calendar-matched futures; producer-equity exposure hedged with commodity not equity index | Roll yield can dominate — compute | Curve-point mismatch; equity/commodity beta drift |
| Net short vol (incl. structural: levered longs, illiquids) | VIX call spreads / index puts sized to the §1 template episode | Persistent negative carry — date-limit it | Vol spikes cluster at the *wrong* strikes; term-structure roll-down bleeds |
| Credit-sensitive equity book | Index CDS/HY proxies (when built: Credit agent) | Carry = spread | Basis between your names and the index; docs/liquidity in stress |
| Gap/event risk (dated) | Options *through* the date, not calendar-matched to comfort | Priced event vol — compare to §1 severity | Buying the event after the market has (implied already wide) |

**Trim-first doctrine restated:** the matrix is for exposures worth paying to keep.
An unintended exposure with no thesis behind it is cut, not hedged — carry spent
neutralizing an accident is pure leak.

## 4. Correlation-convergence table (which pairs go to 1 in stress)

Diversification the book may be crediting that historically vanishes: equities/credit
(always in deleveraging); EMFX/commodities (China or USD shocks); "defensive" crowded
longs/the crowd's other longs (positioning beats fundamentals in the first week);
bonds/equities (only in inflation-shock regimes — check agent 10 Axis 4 before
crediting the bond hedge at all); gold/risk assets (gold fails *early* in liquidity
crunches, works after — §1 GFC/COVID pattern). Apply the table to §4's flagged pairs
with the current regime as the selector.
