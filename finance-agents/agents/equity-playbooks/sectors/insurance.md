# SECTOR MODEL — INSURANCE

*Full model spec for Agents 01/09. Scope: P&C (personal/commercial/specialty),
reinsurance, brokers; life covered as a discipline note — underwrite life only with a
specialist edge.*

## 1. Model architecture

**P&C — two engines, model both:**
```
UNDERWRITING ENGINE
1. Net written premium = exposure growth × rate change (track written rate vs.
   earned rate — earned lags written ~1y: today's margin is last year's pricing)
2. Earned premium (the lag schedule is the model's spine)
3. Loss ratio = underlying (current accident year ex-cat) + cat load (normalized,
   not last year's) ± prior-year development (PYD)
4. Expense ratio (acquisition + G&A) → combined ratio → underwriting profit

INVESTMENT ENGINE
5. Float = reserves + unearned premium − receivables; invested assets
6. Book yield vs. new-money yield (the rate tailwind/headwind arithmetic — same
   back-book logic as banks); realized/unrealized marks separated
```
**The margin call is rate vs. trend:** written rate change minus loss-cost trend
(severity + frequency) = margin *direction* regardless of today's combined ratio —
model it by line. **Reserve schedule:** accident-year triangles by line; consistent
favorable PYD = conservatism (quality signal); adverse PYD = the classic value-trap
mechanism (reserves are management's estimate of their own product cost, revealed
years later).
**Reinsurance:** ceded schedule (attachment points, reinstatements); hard/soft market
cycle position. **Brokers:** organic growth × margin — a compounder model (fee, not
risk), don't apply carrier math.

## 2. KPI dictionary

Combined ratio (and ex-cat, ex-PYD "underlying"); written vs. earned rate change by
line; loss-cost trend assumption; PYD as % of earned (sign and trend); reserve
duration; cat load vs. modeled AAL; float per share and cost of float (negative =
being paid to invest); book yield vs. new money; P&C: policies-in-force growth vs.
rate (volume-vs-price honesty, same as staples).

## 3. Valuation framework

P/B (tangible, ex-AOCI where distorting) regressed on ROE, cat-normalized; quality
franchises: float-adjusted earnings power (underwriting profit + float × yield).
Reverse: implied combined ratio / ROE path vs. the franchise's demonstrated range.
Brokers: EV/EBITDA vs. organic growth like business services, not like carriers.

## 4. Earnings quality & forensics

Reserve-release EPS (split underlying vs. PYD every print — agent 09); cat-load
lowballing (compare stated load to 5–10y actuals); loss-trend assumptions lagging
observed severity (social inflation episodes `[recall — durable pattern]`);
reinsurance dependency masking gross deterioration; life: assumption-review deferrals,
statutory-vs-GAAP capital divergence, captive reinsurance opacity — the complexity
discount is earned.

## 5. Cycle & macro dashboard

The **pricing cycle** is the sector's own weather: capacity (capital) in ↔ rates soft;
capital destroyed (big cat year) ↔ hard market. Track: renewal-rate surveys
(Jan/Apr/Jul reinsurance renewals), industry capital estimates, cat activity, and the
rate-vs-trend spread by line. Rates macro: book-yield repricing is a multi-year
earnings tailwind/headwind (agent 03 path input); inflation feeds loss-cost trend
directly (agent 05 CPI internals — used cars, medical, construction costs map to
auto/liability/property severity).

## 6. Data map

Statutory filings (NAIC/S&P Cap IQ vintage triangles (verify access)); company
supplements (the real disclosure — download every quarter); renewal-rate publications
(broker reports); cat-model vendor commentary. BBG consensus via DAL.

## 7. Thesis archetypes & management questions

**Longs:** hard-market compounder early in the earned-premium lag (written rate
already booked, margin arriving on schedule); consistent-PYD franchise at commodity-
carrier multiple; float quality + new-money yield tailwind unmodeled. **Shorts:**
soft-market share-grower ("growth" = underpriced risk, revealed in 2–3 years);
adverse-PYD serial offender guiding "one-time"; cat-load fiction. **Questions:**
rate vs. trend by line, this quarter's written; reserve philosophy (what percentile);
PYD by accident year; cat load derivation; new-money yield vs. book.
