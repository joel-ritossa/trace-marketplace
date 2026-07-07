# MACRO PLAYBOOKS — REGIME LIBRARY

*Depth module for Agent 10 (Regime Monitor). Contents: per-quadrant asset playbooks
with episode evidence, the liquidity and vol overlays, stock-bond correlation regime
history, transition signatures, and an episode library. Everything here is durable
craft — regime *frameworks*, historical *base rates*, transition *mechanics*. No
current readings live in this file; the agent's dashboard supplies those. All base
rates are `[recall — durable]` with the standing caveat that macro regime samples are
small (a handful of episodes per quadrant since 1970) — playbooks are priors, and the
agent must say so every time it emits one.*

---

## 1. Quadrant playbooks (growth × inflation)

For each quadrant: what historically led, what lagged, per book. "Led/lagged" means
relative performance while the quadrant persisted, not a forecast of the next one.

### Q1 — Reflation (growth ↑, inflation ↑)

- **Equities:** value over growth, cyclicals (energy, materials, industrials, banks)
  over defensives; small over large; EM participates when USD is falling (check the
  USD leg — reflation with a rising USD is a different, rarer animal). Long-duration
  growth underperforms not because earnings miss but because the discount rate reprices.
- **Rates/FX:** bear steepener is the signature curve move (long end reprices growth +
  term premium); USD typically weak (global growth broadening out of the US — the
  "smile" trough); breakevens outperform nominals.
- **Commodities:** broad participation, energy and industrial metals lead; the quadrant
  where commodity beta is most reliably rewarded; curve structure firms toward
  backwardation as demand pulls inventories.
- **Episodes:** 2003–04, 2009–10, 2016–17 (post-Shanghai-Accord, the cleanest modern
  case), Nov 2020–mid 2021 (vaccine reflation).

### Q2 — Goldilocks (growth ↑, inflation ↓)

- **Equities:** the best quadrant for equity beta overall; growth and quality lead
  (falling inflation → falling discount rates while earnings still rise); multiple
  expansion does the heavy lifting — earnings-revision breadth confirms or warns.
- **Rates/FX:** bull steepener or parallel rally with the front end anchored; carry
  trades work (vol suppressed); USD direction ambiguous — driven by relative growth,
  not the quadrant itself.
- **Commodities:** the weakest quadrant for commodity beta; precious metals lag
  (real rates rising or stable with vol low); this is where commodity length gets
  paid to rotate into carry rather than flat price.
- **Episodes:** 1995–98, 2013–14, 2017 (the vol-suppression year), 2023–24 disinflation
  with resilient growth.

### Q3 — Stagflation (growth ↓, inflation ↑)

- **Equities:** the worst quadrant — both discount rate and earnings work against you.
  Least-bad: energy (often the inflation *source*), commodity producers, defensive
  value with pricing power (staples with brands that pass through). Worst: long-duration
  growth, consumer discretionary (real-income squeeze), small caps. Index-level beta
  should be low; this is the quadrant where "which stocks" matters least and "how much
  equity at all" matters most.
- **Rates/FX:** bear flattener into the hiking response, then the trade migrates to
  timing the growth break; breakevens over nominals early, then both sell off; USD
  strong when the Fed is the most hawkish CB (2022), weak when the inflation is
  US-fiscal-specific — check *relative* reaction functions, not the quadrant label.
- **Commodities:** energy leads and is the quadrant's defining long; gold works once
  real rates *peak* (not before — 2022's first three quarters punished early gold longs);
  ags idiosyncratic.
- **Episodes:** 1973–74, 1979–80, 2021 H2–2022 (the modern reference: both stocks and
  bonds down double digits — the quadrant that breaks 60/40).

### Q4 — Deflationary slowdown (growth ↓, inflation ↓)

- **Equities:** defensives (staples, utilities, healthcare) and long-duration quality
  growth lead *if* the correlation regime is negative (bonds rallying = discount-rate
  tailwind cushions the earnings hit); banks and cyclicals worst; the quadrant where
  duration in equities is a hedge, not a risk.
- **Rates/FX:** the long-bond quadrant — bull steepener once cuts get priced, bull
  flattener before; receive-fixed is the anchor trade; USD typically strong early
  (risk-off, dollar shortage) then weak once the Fed eases hard; JPY strength.
- **Commodities:** broad weakness, energy worst (demand destruction); gold bid on
  falling real rates once the policy response starts; the quadrant to be short
  commodity carry.
- **Episodes:** 2001–02, 2008–09 (compressed and extreme), 2011–12 (euro crisis, mild
  US version), 2019 (mini-cycle version, resolved by insurance cuts).

**Standing honesty rule:** quadrant samples are 4–8 episodes each; leadership patterns
above held in *most* but not all. When the agent's specialist siblings (01/04) disagree
with the quadrant prior on a specific name or commodity, the specialist wins — the
quadrant sets the base rate, not the verdict.

## 2. Liquidity overlay

The liquidity axis modifies the quadrant playbook rather than replacing it:

- **Expanding liquidity** amplifies the risk-asset-friendly quadrants (Q1/Q2) and
  cushions the hostile ones — the 2019 and 2023 slowdown scares were bought largely
  because net liquidity was rising into them `[recall — durable, contested — flag]`.
- **Contracting liquidity** does the reverse and adds a *fragility* term: the
  longest-duration, most flow-sensitive assets (unprofitable growth, crypto-adjacent,
  the year's crowded longs) underperform their quadrant playbook. 2018 Q4 is the
  template: mild growth slowdown + QT acceleration = a drawdown far larger than the
  macro justified.
- The overlay matters most at **quadrant boundaries** — contracting liquidity makes
  the market trade the *bad* interpretation of ambiguous data; expanding liquidity the
  good one. Same print, different tape.

## 3. Volatility regime craft

- **Term structure beats level.** VIX 18 in contango and VIX 18 in backwardation are
  different regimes; inversion (spot > 3m) is the stress marker, and its *persistence*
  (days inverted) separates an event from a regime change.
- **Suppressed-vol regimes are supply-driven:** systematic vol selling (overwriting,
  short-vol ETPs, dealer long gamma from structured products) pins realized vol below
  implied for long stretches; the regime ends via a *flow* event (Feb 2018 XIV, the
  gamma flip), not a macro one — which is why the plumbing/positioning agents, not the
  eco calendar, warn of it.
- **Dealer gamma sign** `[when supplied]`: long gamma = mean-reverting intraday tape,
  vol suppressed; short gamma = trending, gap-prone. The sign flip around big expiries
  is a known transition window.
- **Vol regime transitions lead equity regime transitions** more often than the
  reverse: realized creeping up under a stable VIX, or the realized-implied gap closing
  from below, precedes most suppressed→elevated moves. The agent's threshold discipline
  (stated, versioned) exists because vol regimes are where narrative most contaminates
  classification.

## 4. Stock-bond correlation regime history

The sign is inflation-governed `[recall — durable]`:

- **Positive-correlation era (roughly 1970s–late 1990s):** inflation high and volatile;
  bonds and stocks shared the discount-rate shock; 60/40 diversification didn't exist
  as an assumption.
- **Negative-correlation era (~2000–2021):** inflation low and anchored; growth shocks
  dominated; bonds hedged equities; every risk-parity and 60/40 structure was built on
  this era's covariance.
- **2022 flip:** correlation turned positive as inflation became the dominant shock;
  both legs of 60/40 fell together — the mechanism behind that year's outsized
  multi-asset drawdowns.
- **The governing variable is the *level and volatility* of inflation** — the durable
  approximation: correlation goes/stays positive when core inflation is above roughly
  3% and unanchored; reverts negative when inflation is credibly back toward target.
  Track the *cause*, not just the rolling window: a 60d correlation flip during an
  inflation scare means something different from one during a growth scare.
- **Downstream consequences the agent must push, not bury:** positive correlation ⇒
  bonds are not the equity hedge (agent 08 must re-derive hedges — this is the standing
  push trigger), gold and USD take over parts of the hedge role, target-vol and
  risk-parity strategies de-lever mechanically (a flow, not a view), and "risk-off"
  stops meaning "bonds up."

## 5. Transition signatures

What historically fires *before* each axis flips — the watch-list logic behind the
agent's transition-detection section:

- **Growth ↑→↓:** ISM New Orders drops below 50 before the composite; new orders minus
  inventories goes negative first; temp-help employment rolls over (the payroll leader —
  see eco-playbooks/us-employment); consumer confidence expectations-minus-present
  spread collapses; credit spreads start widening while equities still hold. Sequence
  matters: orders → surveys → employment → the hard data everyone waits for.
- **Growth ↓→↑:** the same chain in reverse, plus: Korea/Taiwan exports turn first
  (global trade bellwether), housing (rate-sensitive, earliest domestic responder)
  inflects with mortgage rates, and the *rate of layoffs* (claims 4wk avg) peaks before
  payrolls trough.
- **Inflation ↑→↓:** pipeline order — commodities/PPI/import prices → goods CPI →
  shelter (with its known ~12m lag from spot rents) → services ex-shelter last (wage-
  linked; follows the labor market with a lag). Supercore momentum is the last domino,
  which is why CBs anchor on it.
- **Inflation ↓→↑:** commodity impulse + a positive output gap + wage acceleration
  together; one alone historically fails to move core durably (the 2011 commodity spike
  vs. anchored wages is the reference non-event).
- **Liquidity flips:** mechanical and calendar-knowable more often than not — QT
  announcements, TGA rebuild after a debt-limit resolution, RRP exhaustion. Agent 11
  owns the projection; the signature here is simply *believe the arithmetic over the
  narrative*.
- **Correlation flips:** follow inflation-regime flips with a lag of months; the 60d
  window disagreeing with the 1y window is the in-progress marker the agent already
  flags.

## 6. Episode library (compressed)

For analogue discipline — each entry: what the dashboard would have shown, what
resolved it. Use as *reference class*, never as a forecast template (analogue over-fit
is a named failure mode in agent 06's library).

- **2013 taper tantrum:** Goldilocks quadrant intact; the *liquidity expectation*
  flipped, not growth — real rates +100bp in months, EM and duration proxies hit while
  SPX barely corrected. Lesson: the liquidity axis can reprice alone, and its victims
  are duration-sorted.
- **2015–16 industrial recession:** growth axis flipped down (ISM sub-50 for months)
  without a US recession; USD strength + China + oil capex were the channel; resolved
  by the Shanghai-Accord USD stand-down + China credit impulse → the 2016 reflation.
  Lesson: manufacturing quadrant flips can be sectoral, not economy-wide — breadth
  across indicators is the tell.
- **2018 Q4:** mild growth deceleration + liquidity contraction (QT autopilot) + a
  hawkish policy error; −20% SPX in a quarter with credit confirming late; resolved by
  the Powell pivot in weeks. Lesson: the liquidity overlay (§2) can dominate a mild
  quadrant signal; and policy reaction-function flips (agent 03's axis) end regimes
  fast.
- **2020:** the fastest full cycle on record — Q4 deflation crash to Q1 reflation in
  ~2 quarters on unprecedented fiscal+monetary response. Lesson: regime *duration*
  priors are policy-conditional; months-in-quadrant statistics assume a reaction
  function.
- **2021–22:** Goldilocks → reflation → stagflation, with the correlation-sign flip
  (§4) as the structural casualty; the dashboard's inflation composite (breakevens,
  supercore momentum) crossed boundaries quarters before the Fed's own framework
  conceded. Lesson: composite-vs-narrative divergence is the alpha; the indicator set
  called it while "transitory" was consensus.
- **2023:** the most-forecast recession that didn't arrive — growth composite dipped
  toward the boundary (ISM sub-50 for a year) while employment/GDPNow dissented and
  liquidity quietly expanded (RRP drain funding TGA issuance). Lesson: *show the vote* —
  6-of-8 with two strong dissents resolved toward the dissents; and the liquidity axis
  explained equities defying the manufacturing data.

## 7. Classification craft (the meta-rules)

- **Persistence beats precision:** regimes are classified on ~3m direction precisely
  because monthly prints whipsaw; a boundary crossed by one print is a *watch item*,
  crossed by three is a flip. The cost asymmetry: flipping the call late costs a little,
  flipping it twice costs credibility and P&L.
- **Incoherence is information:** axes disagreeing (vol suppressed + liquidity
  contracting; goldilocks quadrant + positive correlation) marks unstable states that
  historically resolve *toward* the hostile axis — flag, don't force coherence.
- **Small-sample honesty is a standing output requirement:** every playbook line above
  rests on single-digit episode counts. The agent states this whenever a playbook is
  emitted, and treats specialist-agent disagreement as senior to the quadrant prior.
- **Never change the ruler mid-regime:** indicator-set changes are versioned amendments
  (the agent's hard rule); this file is the versioned home for the *playbook* content —
  amend it here, not ad hoc in outputs.
