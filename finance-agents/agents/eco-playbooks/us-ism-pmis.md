# ECO PLAYBOOK MODULE — ISM & PMI COMPLEX (ISM mfg · ISM services · S&P Global · regional Feds)

*Loaded by Agent 05. Report-reader mode applies throughout — these releases publish
full reports with respondent comments; the comments often lead the diffusion indices.
ISM sub-index history left FRED years ago — history via Bloomberg legacy tickers
(NAPM… roots (verify)) or captured from ismworld.org reports.*

---

## ISM Manufacturing — ISM, 1st business day, 10:00 ET. Tier 1.

**Vector (all diffusion indices, level + m/m change, months-in-direction):**
PMI composite — equal-weighted average of **New Orders, Production, Employment,
Supplier Deliveries, Inventories** (know the construction: you can reverse-engineer
which component drove the composite — do it every month). Reported but non-composite:
**Prices Paid**, Backlog, New Export Orders, Imports, **Customers' Inventories**.
**Derived (compute + z-score):** New Orders − Inventories spread (the forward
production signal); New Orders − Customers' Inventories; Prices-Paid-vs-New-Orders
divergence (the stagflation flag); breadth = count of 18 industries expanding (from
the text — report-reader extracts it); Employment-vs-New-Orders gap (labor hoarding
vs. shedding).
**Reading (signal hierarchy):**
1. New Orders is the cycle; the composite is packaging. Customers' Inventories "too
   low" is the most reliable bullish line in the report `[recall — durable]`.
2. **Supplier Deliveries paradox:** slower deliveries lift the composite — bullish
   when demand-driven, stagflationary when supply-shock-driven. Disambiguate with
   Prices Paid + comments; never let a supply-shock composite read as growth.
3. The 50 line matters less than distance-from-own-trend (that's what §3's z-scores
   are for); the GDP-consistent threshold is stated in each report — quote it from
   the report, don't recall it.
4. Employment sub-index is a poor month-to-month NFP predictor, better at turns.
5. Comments-by-industry: classify demand/supply/prices/labor, count net tone by
   industry, and flag comment-vs-index divergence — comments lead.
**Distortions:** ISM is a *survey of purchasing managers' direction, not magnitude* —
a long sub-50 grind can coexist with flat output (post-2022 lesson); sector weightings
favor large firms.
**Reaction fn:** growth leg for agents 10/03; Prices Paid → inflation dashboard;
industry comments → read-throughs for agents 01/02/04 (name the industries).

---

## ISM Services — ISM, +2 business days, 10:00 ET. Tier 1 (bigger economy share, shorter history, noisier).

**Vector:** composite = equal-weighted **Business Activity, New Orders, Employment,
Supplier Deliveries**. Non-composite: **Prices Paid** (the Fed-relevant line — services
inflation at the survey frontier), Backlog, Export Orders, Inventories, Inventory
Sentiment.
**Derived:** Business-Activity-minus-Employment (margin/productivity read); services
Prices Paid vs. supercore CPI direction (survey-vs-realized gap); mfg-vs-services
composite spread (the two-speed-economy measure — a durable macro theme when wide).
**Reading:** services PMI history only goes to 1997 and the series is jumpier — wider
z-bands before calling anomalies (§3 handles this via its own EWMSD, but say it).
Prices Paid here moves Fed pricing more than the composite does in
inflation-fight regimes. Comments skew to logistics/health/finance industries — note
composition before generalizing.
**Reaction fn:** services Prices Paid → inflation dashboard + agent 03; composite →
growth leg.

---

## S&P Global PMIs (US) — flash ~3rd week (the *earliest* monthly read), final start of month. Tier 2.

Mfg, services, composite + the sub-detail in the text (new orders, employment,
input/output prices — **output prices** is the margin signal ISM lacks). Flash timing
is its whole value: it's the first hard survey point for the current month — weight
it for *timing*, not level. ISM-vs-S&P divergences: different panels (S&P skews
smaller/exporters) — persistent divergence is usually composition, not information
`[recall — durable]`.

---

## Regional Fed surveys — Empire (NY, ~15th), Philly (~3rd Thu), Richmond, Dallas, KC; Chicago PMI (last business day). Tier 3 inputs, Tier 2 as an ensemble.

**Use as ensemble, never singly:** each is one district, volatile, and
manufacturing-skewed. Maintain the simple ISM-nowcast: standardized average of
available regionals' new-orders and employment components → direction call for ISM
(the ensemble has modest but real predictive value `[recall — durable]`; show the
month's inputs). Philly and Empire's **6-month-ahead capex intentions** are the
underrated lines — they lead equipment investment. Prices-paid components feed the
inflation dashboard. Chicago PMI releases minutes early to subscribers — the tape
moves before the public print (verify current practice); treat the public release as
already-traded.

---

## NFIB Small Business — NFIB, ~2nd Tue, 6:00 ET. Tier 2 (belongs to surveys module too; inflation-relevant lines listed here).

**Price plans** (net % raising prices, 3m lead on core inflation `[recall — durable,
approximate]`), **compensation plans** (leads AHE), hiring plans, job openings
hard-to-fill (JOLTS cross-check), credit availability (the SME credit-crunch
early-warning), capex plans. Small-firm panel = the part of the economy the S&P 500
isn't; divergence from large-firm surveys is a breadth signal for agents 02/10.
