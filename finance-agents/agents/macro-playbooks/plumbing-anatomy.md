# MACRO PLAYBOOKS — PLUMBING ANATOMY

*Depth module for Agent 11 (Liquidity & Plumbing Monitor). Contents: the mechanics a
funding-markets specialist carries in their head — the reserve-demand curve, the repo
market map, RRP/TGA mechanics, dealer balance-sheet constraints, cross-currency basis
anatomy, and the episode library with early-warning sequences. All durable structure;
every level, cap, threshold, and facility parameter is `[pull live]` — the Fed changes
these, and a stale cap in a projection is a wrong projection.*

---

## 1. The reserve-demand curve

The organizing concept behind every scarcity judgment:

- Banks' demand for reserves is a downward-sloping curve that is **flat when reserves
  are abundant** (rates pinned near IORB regardless of quantity) and **kinks steeply**
  as reserves approach the system's lowest comfortable level (LCLoR). The whole game is
  locating the kink *before* the market does — the Fed itself doesn't know where it is
  and says so `[recall — durable]`.
- **Elasticity diagnostics** (the practical kink-detectors, in rough firing order):
  1. EFFR−IORB drifts up from its stable deep-negative-single-digits resting spread;
  2. repo rates (SOFR, GC) trade *above* IORB with rising frequency, not just at
     quarter-ends;
  3. the SOFR 99th percentile detaches from the median (the tail is the marginal
     borrower — it moves first);
  4. repo rates become *responsive to reserve changes* — in the ample regime a $100bn
     reserve swing moves nothing; elasticity appearing at all is the signal;
  5. banks bid for wholesale funding (rising large time deposits, FHLB advances
     `[pull: FHLB debt outstanding]`).
- **Reserves are not evenly distributed:** aggregate "ample" can coexist with scarcity
  at specific banks (2019's lesson — the big four held the reserves but wouldn't lend
  them past internal liquidity buffers). Aggregate ratios (reserves/GDP, reserves/bank
  assets) are necessary context, not sufficient comfort.
- The Fed's stated operating target is "ample reserves" with the SRF as the ceiling
  backstop; the practical question each run: *how far above the kink, and how fast is
  QT + TGA closing the gap.*

## 2. Repo market map

Who lends to whom, and where it shows up:

- **Tri-party (via BNY):** money funds and other cash lenders → dealers, against
  general collateral. The bulk of visible volume; the calm segment.
- **DVP bilateral:** dealer → hedge fund / levered client, security-specific. Where
  basis-trade leverage lives; the segment that transmits a Treasury-market shock into
  a funding shock. Volumes and rates via OFR monitor `[URL, free]`.
- **Sponsored repo (FICC):** dealers sponsor clients into central clearing to net
  balance-sheet usage — growth here is dealers *economizing on balance sheet*, a tell
  that the binding constraint is the dealer, not cash supply.
- **GCF:** interdealer general collateral — the redistribution layer.
- **SOFR construction:** volume-weighted median across tri-party + cleared bilateral;
  dominated by the calm segments, which is exactly why the **99th percentile and the
  distribution** carry the information — stress appears in the tail prints and in
  *volume migration* before it moves the median.
- **The intermediation chokepoint:** cash-rich lenders and cash-poor borrowers can both
  exist in size while the dealer pipe between them is balance-sheet constrained (§5) —
  most modern plumbing events are chokepoint events, not aggregate-shortage events.

## 3. ON RRP mechanics

- **Who uses it:** overwhelmingly government money-market funds. The RRP is their
  outside option; its rate sets their floor.
- **The drain/refill logic the projection depends on:** money funds allocate between
  RRP and T-bills on spread. Heavy bill issuance at yields above RRP → funds rotate
  out (RRP drains, reserves *don't* fall — the drain absorbs the issuance); light bill
  supply → balances rebuild. This single allocation choice determined whether
  2022–24 QT drained reserves or just the RRP `[recall — durable mechanism]`.
- **Mechanical vs. behavioral split (the agent's hard rule, grounded):** bill issuance
  calendar = mechanical, knowable from the QRA; money-fund allocation = behavioral,
  an assumption to label. WAM posture of the fund complex and the bills−RRP spread are
  the two behavioral inputs worth stating.
- **RRP near exhaustion changes the QT arithmetic discretely:** once the buffer is
  gone, every dollar of QT/TGA-rebuild comes out of *reserves* one-for-one — the
  projection's risk regime shifts even though nothing visible breaks that day. Flag the
  crossover date explicitly whenever the projection includes it.
- Quarter-end RRP spikes are window dressing (dealers shed repo, money funds park at
  the Fed) — routine, sized vs. prior quarter-ends, not stress.

## 4. TGA mechanics

- The TGA is a **reserve seesaw**: Treasury building its cash balance drains reserves
  (or RRP), spending it injects them. The path is knowable to first order: the QRA
  states the target end-of-quarter balance; tax dates (Mar/Apr/Jun/Sep/Dec 15) spike
  it; settlement calendars time the drains within the week.
- **Debt-limit episodes invert the sign twice:** the binding period forces TGA
  *drawdown* (stealth liquidity injection — risk assets get a tailwind nobody voted
  for), resolution forces a rapid *rebuild* (the drain arrives in weeks). The 2023
  resolution avoided the feared reserve drain because bills priced to pull from the
  RRP instead — the §3 allocation mechanism deciding the outcome. Model both legs
  whenever a debt-limit window is live.
- April tax receipts are the single largest annual TGA swing — the mid-April reserve
  drain is calendar-mechanical and repeats every year; its *size* varies with capital
  gains (behavioral, label it).

## 5. Dealer balance-sheet constraints

Why the pipe clogs on schedule:

- **SLR** is risk-insensitive: a Treasury or a repo consumes the same denominator as a
  loan — when the SLR binds, dealers ration exactly the low-margin intermediation
  (repo, Treasury market-making) that plumbing depends on. Any live SLR-reform
  proposal is a structural input to the stress outlook `[pull live]`.
- **G-SIB surcharge scores use year-end snapshots** `[recall — durable]`: banks compress
  repo and derivatives books into December 31 to manage their bucket — the mechanical
  cause of the **year-end turn** (repo and FX-basis spikes over the turn date). Priced
  in advance in forward repo and the December basis; the *size* of the priced turn is
  itself a dealer-constraint gauge.
- **Quarter-ends** are the same behavior at lower stakes (European banks' leverage
  ratios snapshot quarterly — the marginal squeezers of quarter-end dollar funding).
- Reported dealer positions (FR 2004 via NY Fed `[URL, free]`) and sponsored-repo
  growth (§2) are the slow gauges of how loaded the pipe is between snapshots.

## 6. Cross-currency basis anatomy

- The basis is the **price of borrowing dollars against another currency** when CIP
  fails to hold; persistently negative EUR/JPY 3m basis = structural dollar demand
  from hedged foreign investors + constrained arbitrage capital (§5 again — the same
  dealer balance sheet arbitrages the basis).
- **Read it as a dollar-shortage thermometer with two modes:** a slow grind wider
  (hedging demand, year-end turn — structural, calendar-explicable) vs. a **gap wider
  in days** (funding stress — 2008, Mar 2020). The gap mode co-fires with §2 tail
  prints and FRA-OIS; that co-firing is the confirmation that it's systemic.
- Central-bank **FX swap lines are the designated firebreak**: usage `[pull: NY Fed
  swap-line operations, free]` is the direct read on offshore dollar stress — like the
  discount window, any material usage is signal, and stigma means it understates.
- Year-end turn in the basis: same G-SIB mechanics as §5; compare the priced turn to
  prior years before calling it stress.

## 7. Episode anatomy library

Each: sequence → which §1–6 gauges fired early → policy response → the lesson encoded
in the agent's protocol.

- **Sep 2019 repo spike:** corporate tax date + heavy coupon settlement into reserves
  already drained by two years of QT; GC printed near 10% intraday; EFFR broke above
  its band. *Early gauges:* EFFR−IORB drift all summer, repo elasticity appearing
  (§1.4), reserves/GDP at the post-crisis low. *Response:* ad-hoc repos → bill
  purchases → (eventually) the standing SRF. *Lesson:* the kink announces itself in
  the tails for months; calendar coincidences (tax + settlement) are the trigger, not
  the cause — which is why §3 of the agent tracks the windows where they coincide.
- **Mar 2020 dash-for-cash:** the Treasury basis trade unwound as everyone sold the
  most liquid asset; DVP repo (§2) transmitted it; xccy basis gapped (§6 gap mode);
  even bills cheapened. *Response:* unlimited QE + swap lines + a temporary SLR
  exemption — note that the *SLR relief* was part of the fix (the chokepoint was the
  pipe, §5). *Lesson:* Treasury-market stress and funding stress are one system;
  levered-basis positioning size `[pull: OFR/CFTC when available]` is a standing
  vulnerability metric.
- **Oct 2022 UK LDI (non-USD template):** a rate spike forced collateral calls on
  levered pension hedges → forced gilt selling → further spikes — the margin spiral in
  its purest form. *Lesson:* the generic template is *levered holder + collateral call
  + one-way market*; the agent's job in any sell-off is to ask who is the levered
  holder and what is their margin trigger. Resolution required the CB to buy the asset
  its policy was selling — reaction functions bend when plumbing breaks (route to 03).
- **Mar 2023 SVB:** not a market-plumbing failure but a deposit run meeting §1's
  distribution point — reserves were aggregate-ample, wrongly distributed against
  HTM-loss balance sheets. *Response:* BTFP (par-value collateral lending — a new
  facility invented in a weekend). *Lesson:* discount-window + new-facility usage
  (H.4.1, weekly) is the run thermometer; and facility *design* tells you what the
  authorities feared.
- **2018 QT endgame:** the first QT ran on "autopilot" into visible EFFR drift and
  ended via the 2019 events above. *Lesson:* QT's end is diagnosed from §1's
  elasticity gauges, not announced in advance; the agent's scarcity-assessment section
  exists to make that call earlier than the Fed's own taper.

## 8. Early-warning sequence (the composite craft)

The gauges fire in a rough order; the dashboard's amber/red logic follows it:

1. **Slow burn (weeks–months):** EFFR−IORB drift; SOFR 99th-percentile detachment;
   sponsored-repo growth; reserves-ratio erosion; RRP buffer approaching zero.
2. **Calendar aggravators (dated in advance):** tax dates, settlement clustering,
   quarter/year-end turns, TGA rebuild legs — stress *events* overwhelmingly land
   where a slow burn meets an aggravator (2019 the type case).
3. **Fast confirmation (days):** GC/SOFR above IORB persistently; FRA-OIS widening
   with xccy basis gapping (§6 co-fire); backstop usage appearing (SRF, discount
   window, swap lines).
4. **Systemic (hours–days):** Treasury-basis unwind signatures — off-the-run spreads,
   failed-trade volumes `[pull: DTCC/OFR]`, futures-cash dislocation.

The agent's verdict line maps to this ladder: NORMAL = nothing beyond isolated stage-1
flickers; TIGHTENING = persistent stage-1 with dated stage-2 aggravators inside the
projection window; STRESS = any stage-3 confirmation. State the stage evidence, not
just the color.
