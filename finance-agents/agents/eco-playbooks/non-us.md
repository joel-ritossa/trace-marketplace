# ECO PLAYBOOK MODULE — NON-US (Eurozone · UK · Japan · China)

*Loaded by Agent 05. Same schema; each block names the domestic central bank whose
reaction function the release feeds (translate to THAT bank via agent 03's module,
never the Fed's). Ids/tickers largely (verify) — non-US mnemonics are less standardized;
national statistical offices are canonical.*

---

## EUROZONE → feeds ECB module

**HICP flash — Eurostat, ~1st of month, 11:00 CET; final mid-month. Tier 1.**
Vector: headline, **core (ex energy, food, alcohol, tobacco)**, services, goods
(NEIG), energy, food — y/y and the **m/m SA momentum** (ECB's own seasonal adjustment;
3m ann. services momentum is the line the GC debates (verify current publication));
**country sequence is tradeable structure:** Spain prints first (~2–3 days before EZ
flash), then German states → German national, France, Italy — by EZ-flash day the
aggregate is largely nowcastable; maintain the country-weights nowcast and trade the
*residual*, not the print.
Derived: supercore proxy (services ex package-holidays — the volatile item `[recall —
durable]`); wage-sensitive services basket (ECB publishes variants (verify)).
Distortions: package holidays/German methodology quirks; January weight resets
(bigger effect than US `[recall — durable]`); energy base effects — pre-compute 6m.
**Negotiated wages (ECB tracker, quarterly) + compensation per employee** — the ECB's
wage anchor; one-offs vs. permanent components split (the tracker publishes it).
**PMIs (HCOB flash, ~23rd):** country splits (Germany/France vs. periphery gap),
mfg-services divergence, and the *output prices* line for ECB pass-through.
**IFO (Germany, ~25th):** expectations vs. current assessment — the **spread** is the
German cycle signal; expectations lead by ~2 quarters `[recall — durable]`. ZEW
(analysts, noisy) only as an IFO preview. German factory orders/IP: big-ticket lumpy —
3m averages only. EZ unemployment, retail: lagging context.
Reaction fn: services momentum + negotiated wages → ECB (agent 03); German
manufacturing complex → the EUR cyclical leg and European equity read-throughs.

---

## UK → feeds BoE module

**CPI — ONS, ~mid-month, 7:00 UK. Tier 1.** Vector: headline, core, **services CPI**
(the MPC's stated focus — always lead with it), goods; RPI (legacy — but index-linked
gilts and many contracts still reference it: the RPI-CPI wedge is a rates-relevant
line, not trivia). Distortions: airfares around Easter timing (the annual April/May
services head-fake `[recall — durable]`), energy via the **Ofgem price cap** — cap
resets (Jan/Apr/Jul/Oct) move headline mechanically and are knowable months ahead:
pre-compute and publish the path.
**Labor market — ONS, ~mid-month:** AWE total vs. **private-sector regular pay** (the
MPC line); LFS unemployment — **known data-quality problems** (response-rate collapse;
transformation ongoing (verify status)): cross-check with HMRC RTI payrolled employees
(timelier, administrative) and vacancy counts. When LFS and RTI disagree, weight RTI.
**Activity:** monthly GDP (noisy, revise-prone), PMIs, GfK consumer confidence
(long-running, decent turning-point record for UK specifically `[recall — durable]`),
RICS housing survey (leads prices ~6m).
Reaction fn: services CPI + private regular pay are the two numbers that move Bank
pricing; everything else is context. Ofgem-cap arithmetic belongs in every UK
inflation note.

---

## JAPAN → feeds BoJ module

**Tokyo CPI (leads national by ~3–4 weeks — the tradeable print) and national CPI.
Tier 1 (Tokyo), Tier 3 (national — pre-known).** Vector — **definitional trap first:**
Japanese "core" = ex fresh food only; "core-core" = ex fresh food & energy (≈ western
core). Always state which. Components: services vs. goods (services is the
BoJ-relevant half — decades of flat services prices breaking is *the* regime question
`[recall — durable]`); rent (structurally sticky-low, drags the index — read ex-rent
services); administered/subsidized items (energy subsidies, travel programs, education
waivers — government one-offs routinely distort y/y by tenths: maintain the
known-subsidy calendar and strip).
**Shunto (spring wage rounds, Feb–Jul):** Rengo tallies — first tally (mid-March)
skews large-firm/upward; later tallies fold in SMEs and drift down `[recall —
durable]`; base-pay (bashi-appu) vs. total including seniority steps — base pay is
the signal. The BoJ's sustainability test runs through Shunto → services CPI.
**Tankan (BoJ, quarterly):** large-manufacturer DI is the headline; the value is in
capex plans (follow the intra-year revision pattern — plans revise UP through the year
in expansions `[recall — durable]`), employment DI (labor shortage), and the inflation
expectations of firms (1y/3y/5y — the BoJ cites these).
**Labor cash earnings:** sample-rotation noise is chronic — use the same-sample /
full-sample distinction (verify series names) and scheduled vs. total (bonus months
distort); real wages = the political line.
Reaction fn: Tokyo services ex-rent + Shunto base-pay + Tankan expectations = the BoJ
normalization dashboard (agent 03). USDJPY pass-through runs the other way — flag
import-price episodes.

---

## CHINA → feeds PBoC module (and agent 04 demand-side)

**PMIs:** **NBS (~last day of month;** large/SOE-skewed**) vs. Caixin (~1st–3rd;**
private/coastal/exporter-skewed**)** — the *divergence* is the composition signal
(domestic stimulus vs. export cycle). Sub-indices: new orders vs. new export orders
split (domestic/external demand separation), and the employment lines (chronically
sub-50 — level uninformative, changes matter).
**Credit — TSF/aggregate financing, new loans (~9th–15th; PBoC). Tier 1 for the
macro/commodity read.** Vector: TSF total and **composition** — government bonds
(fiscal-in-disguise), corporate bonds, medium/long-term corporate loans (the real
capex line `[recall — durable]`), household medium/long-term (mortgages = property
pulse), shadow components (trust/entrusted/bankers' acceptances — the deleveraging
gauge). Derived: **credit impulse** (12m change in new credit as % GDP — the series
that leads global commodity demand ~6–12m `[recall — durable, contested]`); January
front-loading seasonality — never y/y January alone, use Jan+Feb combined.
**Activity set (~15th; IP, retail, FAI, property):** Jan–Feb published combined (LNY
distortion); property detail is the heart of it — **starts lead, sales fund, completions
deliver**: starts-vs-completions divergence maps the developer distress pipeline;
route directly to agent 04 (steel/copper) with the split. FAI by
infrastructure/manufacturing/property (the policy-offset arithmetic).
**Trade (~7th):** exports by destination and *volumes vs. values* (deflator wedge);
imports of copper/iron ore/crude in tonnes → agent 04 directly.
**Data-integrity note (structural):** publication of inconvenient series has been
suspended/redefined before (youth unemployment episode `[verify current status]`);
GDP smoothness is assumed — weight the credit/property/trade complex over headline
GDP, and say so in any China note.
Reaction fn: credit impulse + property → PBoC easing calculus (agent 03 scaffold) and
the commodity-demand leg (agent 04); PMI divergence → the export-cycle read for EM/FX.
