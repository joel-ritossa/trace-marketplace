# SECTOR MODEL — MEDIA & TELECOM

*Full model spec for Agents 01/09. Scope: streaming/studios, advertising-driven
media, cable/broadband, wireless, towers (REIT-wrapped but modeled here).*

## 1. Model architecture

**Subscription media (streaming):**
```
1. Subs by region: gross adds × conversion − churn (COHORT model — churn by
   vintage and by acquisition channel; password-sharing/ad-tier policy changes
   are step inputs) 
2. × ARPU by tier (ad tier economics separately: subscription ARPU + ad ARPU —
   the blended number hides the trade-off)
3. − CONTENT: cash spend vs. amortization policy (the accounting gap — aggressive
   curves flatter early profits; model cash content per sub as the honest unit
   cost) → contribution by region → FCF after all content
```
**Advertising media:** audience (ratings/reach decline curves) × pricing (CPM
upfront vs. scatter) — structural-decline modeling discipline: straight-lining a
melting audience is the sector's chronic consensus error (both directions).
**Cable/broadband:** homes passed × penetration × ARPU; broadband net adds vs.
fixed-wireless/fiber overbuild competition (model competitor footprint overlap
explicitly); video as a declining attach; capex cycle (network upgrades) → FCF.
**Wireless:** subs (postpaid phone = the metric) × ARPU (service revenue growth =
the honest line; equipment revenue is pass-through noise); churn × CAC economics;
promotional-intensity cycle (the oligopoly's discipline thermometer); spectrum
capex cycle → FCF after spectrum.
**Towers:** covered in REIT logic (`reits.md`) — colocation/amendment growth off
carrier capex cycles; escalators vs. churn (carrier consolidation risk).

## 2. KPI dictionary

Streaming: net adds by region, churn by vintage, ARPU by tier, cash content/sub,
engagement (hours — the churn predictor); ad media: audience decline rate, upfront
pricing, digital substitution rate; broadband: net adds, penetration, overbuild
exposure %, ARPU trend; wireless: postpaid phone net adds, service-revenue growth,
churn, upgrade rate, promo amortization; all: FCF after full capex/content/spectrum.

## 3. Valuation framework

Streaming: EV/subscriber sanity-checked against contribution-per-sub maturity path;
DCF with content-cash-flow honesty (amortization-based EBITDA misleads — use cash
conversion); ad media: value as declining annuity (exit multiples compress — model
terminal decline, not terminal growth); broadband/wireless: FCF yield + leverage
path (these are levered-return stories — equity FCF/share after deleveraging is the
model); SOTP where infrastructure (towers/fiber) hides inside integrated names with
a separation precedent. Reverse: implied sub growth × terminal ARPU vs. penetration
arithmetic.

## 4. Earnings quality & forensics

Content amortization curve changes (extending useful lives = earnings print);
"adjusted EBITDA" in content businesses (cash content >> amortization during growth
= EBITDA fiction); sub definition changes (paid-sharing accounts, bundled
"subscribers" via telco deals — log definitions); churn masked by bundle
reclassification; wireless: promotional costs capitalized as "device payments"
receivables (aging tells); one-time rights step-ups (sports) treated as recurring;
broadband: "homes passed" inflation vs. serviceable actual.

## 5. Cycle & macro dashboard

Advertising is early-cyclical (agent 05 growth composite leads it; political years
add a stimulus `[durable cadence]`); streaming is consumer-discretionary-lite (churn
rises with real-income squeezes — trade-down to ad tiers); wireless/broadband are
utility-like (defensive) *except* the promo cycle — track competitive intensity, not
macro; capex cycles (fiber builds, spectrum auctions `[pull calendar live]`) set the
FCF harvest/build phase; content-cost inflation vs. consolidation.

## 6. Data map

Company sub/ARPU disclosures (definitions logged); Nielsen-type ratings (verify
access); streaming engagement trackers (verify vendor); FCC broadband data (free);
spectrum auction calendars (FCC, free); upfront-market press. BBG DAL consensus.

## 7. Thesis archetypes & management questions

**Longs:** streaming scale-inflection (content spend flattening while subs compound —
contribution margin arrives on schedule); broadband franchise priced for overbuild
that isn't coming to its footprint; harvest-phase FCF (capex cycle ending) with
deleveraging math unmodeled. **Shorts:** melting-audience annuity priced as stable
(linear-heavy names); promo war breaking a "rational oligopoly" thesis; content
EBITDA fiction meeting a cash-conversion test. **Questions:** churn by cohort and
tier; cash content plan vs. amortization next 2 years; promo posture vs. named
competitors; capex trajectory to maintenance level and the FCF number there;
sub-definition changes this year.
