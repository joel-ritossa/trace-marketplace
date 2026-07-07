# ECO PLAYBOOK MODULE — US EMPLOYMENT COMPLEX

*Loaded by Agent 05. Schema per release: vector (component · transform · id) → derived
aggregates → reading (signal hierarchy, distortions) → reaction-function mapping. All
ids (verify) unless marked verified; BLS/DOL source tables are canonical when ids fail.
Weights/benchmarks change annually — pull current, never recall.*

---

## NFP / Employment Situation — BLS, first Fri 8:30 ET, monthly. Tier 1 market-mover.

**Vector — Tier 1 aggregates (Δ m/m thousands unless noted):**
headline (`PAYEMS` verified), private (`USPRIV`), government (`USGOVT` (verify)) with
federal/state/local split (Table B); AHE m/m % — all employees AND
production/nonsupervisory separately (the P&NS series is less composition-distorted
(verify ids)); avg weekly hours change (verify id); **aggregate payrolls proxy** =
jobs × hours × AHE (the income-side read — can rise on a weak jobs print); U3 change
(`UNRATE` verified), U6 change (verify id), participation change (`CIVPART` verified),
prime-age (25–54) EPOP change (verify id); household employment Δ (`CE16OV`) and the
adjusted payroll-concept household series (BLS publishes it — closes definitional gaps
(verify)); diffusion index level (Table B); net 2-month revisions (ALFRED /
BLS archive — point-in-time by construction).

**Vector — Tier 2 industry (each z-scored, each in the contribution table):**
mining & logging (`USMINE` (verify)); construction (`USCONS` (verify)),
residential/nonresidential split from Table B (rates-transmission read); manufacturing
(`MANEMP` verified), durable/nondurable; wholesale (`USWTRADE` (verify)); retail
(`USTRADE` (verify)); transportation & warehousing (verify id) — couriers/warehousing
breakout for the e-commerce SA quirk; utilities; information (`USINFO` (verify));
financial activities (`USFIRE` (verify)); professional & business services (`USPBS`
(verify)) **with temporary-help breakout** (`TEMPHELPS` (verify)); private education &
health (`USEHS` (verify)) **with health care & social assistance breakout** (CES id
(verify)); leisure & hospitality (`USLAH` (verify)); other services.

**Derived (compute + z-score):** cyclical-core payrolls = private ex-health/ex-private-
education; goods vs. services split; government share of headline gain; breadth =
diffusion + share of industries positive; the payrolls-vs-household 12m gap.

**Reading (signal hierarchy):**
1. Cyclical core + diffusion outrank the headline. A health/government-driven beat is
   a weaker labor market than the same headline from cyclical industries.
2. Temp help + diffusion turning together is the strongest early-cycle signal in the
   report `[recall — durable]`; a single-industry anomaly is usually noise or a strike.
3. Hours are the quiet lever: −0.1 weekly hours ≈ a few hundred thousand jobs of labor
   input — compute the aggregate-payrolls proxy before calling a print strong/weak.
4. AHE composition trap: low-wage hiring surges *depress* AHE mechanically — check
   P&NS series and the industry mix before reading wage inflation.
5. Household-survey divergence matters only sustained (6m+); month-to-month it's noise
   (smaller sample). Participation moves change the meaning of U3 — always read the
   pair.
**Distortions:** strikes (BLS strike report — add back), weather (construction/L&H;
check the "away from work due to weather" household series (verify)), annual benchmark
revision (Feb print), birth-death model contribution (note, don't subtract), January
population-control jumps in the household survey (never trend Jan household data),
holiday SA on retail/couriers (Nov–Jan).
**Reaction fn:** Fed employment leg. The bar moves with the cycle: in a
labor-market-cooling regime, U3 and cyclical core outrank AHE; in an inflation-fight
regime, AHE/hours income proxy outranks the count. State which regime (from agent 10)
you're scoring against.

---

## JOLTS — BLS, ~10:00 ET, monthly (1-month extra lag). Tier 2.

**Vector:** openings level (`JTSJOL` (verify)) and **V/U ratio** (openings ÷ unemployed
— the Fed's favored slack summary); quits rate total + private (`JTSQUR` (verify));
hires rate; layoffs & discharges rate; by-industry openings for the same tier-2 split
as NFP (verify ids).
**Derived:** V/U change vs. pre-2020 norm; quits-vs-AHE lead (quits lead wage growth
~2–3 quarters `[recall — durable]`); hires-minus-quits (net churn).
**Reading:** the modern regime question is **low-hire/low-fire vs. high-churn** — a
falling openings + stable layoffs mix cools wages without raising U3 (the "soft
landing" path); layoffs rising is the regime break, openings falling is not. Response
rate is ~low-30s% and falling — treat levels skeptically, trends cautiously, and
cross-check with private postings data (Indeed job postings index `[URL, free]`) which
leads JOLTS by a month+.
**Distortions:** small sample; large revisions; openings inflated by ghost postings
(level bias, not trend bias).
**Reaction fn:** Fed slack assessment (V/U is citable in speeches — watch agent 03 for
it); quits → wage → services-inflation pipeline.

---

## Weekly claims — DOL, Thu 8:30 ET. Tier 2 (Tier 1 in turning-point regimes).

**Vector:** initial claims SA (`ICSA` (verify)) + 4-week avg; **NSA initial** with the
same-week-of-year comparison (the honest read when SA factors are stressed);
continuing claims SA (`CCSA` (verify)) + insured unemployment rate; state-level detail
(largest movers, NSA).
**Derived:** initial claims vs. 6m low (the "+X% off the low" recession heuristics are
weak — use as context, never as a rule `[recall — durable caveat]`); continuing-claims
trend as the *hiring* signal (rising continuing + flat initial = laid-off workers not
being reabsorbed — the low-hire regime signature).
**Reading:** initial = firing; continuing = (lack of) hiring. In low-hire/low-fire
regimes continuing claims is the more informative series. Single-state spikes are
processing/fraud noise until confirmed (check the state NSA detail); holiday weeks,
auto-retooling (July), and school-calendar quirks distort SA factors — the NSA
year-over-year comparison is the tiebreaker.
**Reaction fn:** highest-frequency labor input to the Fed leg; a sustained claims break
re-dates the whole easing path — flag to agents 03/10 when the 4-week avg crosses its
threshold (set the threshold in the standing monitor).

---

## ECI (Employment Cost Index) — BLS, quarterly (~last week of Jan/Apr/Jul/Oct, 8:30 ET). Tier 2, Fed-heavyweight.

**Vector:** total compensation q/q and y/y; **wages & salaries, private**; benefits;
**private wages ex-incentive-paid occupations** (the composition-cleanest series —
the one the Fed actually cites (verify series)); by-industry detail for union/non-union
and the health-benefits pass-through.
**Reading:** ECI is the composition-controlled wage measure — when AHE and ECI
disagree, believe ECI. Quarterly cadence means each print re-anchors the wage
narrative for 3 months; the q/q annualized run-rate vs. the productivity-consistent
benchmark (state the arithmetic: target inflation + trend productivity) is the verdict
line. Benefits spikes are often health-insurance repricing — check before reading
labor-market heat.
**Reaction fn:** direct input to the Fed's services-inflation logic; also the wage
anchor agent 03 should score speeches against.

---

## ADP — ADP/Stanford lab, Wed before NFP, 8:15 ET. Tier 3 — context only.

Post-2022 methodology (payroll-microdata weekly model). Poor month-to-month NFP
predictor; usable for trend and for the by-size-of-firm and by-industry splits, and
its **pay growth for job-stayers vs. job-changers** series (the churn premium — a
clean wage-pressure read `[recall — durable]`). Never trade an NFP position off ADP;
never let it move the NFP prior more than marginally.
