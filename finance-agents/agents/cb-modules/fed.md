# CB MODULE — FEDERAL RESERVE (FOMC)

*Durable structure only. Everything in §8 must be pulled live every time.
All personnel/priority entries dated `[as of training cutoff — verify]`.*

## 1. Mandate & framework
Dual mandate: maximum employment + price stability (2% PCE inflation). Operating
framework: ample-reserves regime; policy rate = fed funds target **range**, steered via
IORB and ON RRP. The 2020 FAIT framework was subject to a 2025 framework review —
**treat the current framework description as [verify]**; do not assume FAIT language
survives.

## 2. Committee mechanics
12 voters: 7 governors (always vote) + NY Fed president (always votes, committee vice
chair) + 4 of the remaining 11 regional presidents on annual rotation. All 19 speak and
submit SEP projections; only voters vote. Dissents are meaningful but not rare.
Blackout: roughly the second Saturday before a meeting through the Thursday after —
communication inside blackout is by design limited; anything unscheduled inside blackout
is a five-alarm signal. 8 scheduled meetings/year.

## 3. Communication hierarchy (weight, descending)
1. Statement (meeting day, 2pm ET) — read as a diff vs. prior statement, word by word.
2. Chair presser (2:30pm ET) — the Q&A moves markets more than prepared remarks.
3. SEP + dot plot (quarterly meetings: Mar/Jun/Sep/Dec) — medians and dispersion.
4. Minutes (3 weeks after) — committee distribution: "some/several/many/most" ladder.
5. Chair testimony (semiannual Humphrey-Hawkins) and chair speeches (esp. Jackson Hole, late Aug).
6. Governor speeches > president speeches, generally; but a known bellwether president
   can outrank (see People).
7. Nikkei/WSJ-style "Fed whisperer" articles during blackout — historically the leak
   channel; treat sourced blackout journalism as quasi-communication.

## 4. Current-priority variables `[as of cutoff — verify each use]`
Core PCE (esp. services ex-housing), payrolls/unemployment balance-of-risks, inflation
expectations (UMich, breakevens), financial conditions indices, QT/reserve-scarcity
indicators (repo spreads). Verify: the framework review and 2025–26 inflation/labor mix
may have reordered these.

## 5. People — ALL entries `[verify before use]`
**Chair: [verify — the chair's four-year term as chair expired May 2026; a transition
was in play. Do not assume the incumbent. Pull current leadership from
federalreserve.gov/aboutthefed before attributing chair-weight to anyone.]**
Historical leanings of longstanding members may be cited from recall with dates, but
current composition, vice chair, and this year's rotating voters: always pull. Rotation
membership is listed at federalreserve.gov/monetarypolicy/fomc.htm.

## 6. Instruments to watch
- Fed funds futures: `FF1`–`FF24 Comdty` (verified root) — meeting-dated path arithmetic.
- 3M SOFR futures: CME SR3 (Bloomberg root (verify)) — path + convexity further out.
- OIS meeting-dated curve: BBG `WIRP` (verify current name) or OIS strip (`USOSFR...` (verify)).
- Target range ticker: `FDTR Index` (verified); effective rate `FEDL01 Index` (verified).
- 2y note `USGG2YR Index`, 10y `USGG10YR Index`, breakevens `USGGBE10 Index` (verified).
- USD: `DXY Curncy` (verified).

## 7. Known traps
- Dot plot ≠ commitment; medians shift with composition, and the chair routinely
  disavows dots in the presser that follows them.
- Statement-diff overreads: some edits are marked-to-market description, not signal —
  check whether the *policy-guidance* paragraph moved, not just the economy paragraph.
- Presser Q&A: the chair's first answer is prepared; follow-ups are where news happens.
- Regional-president speeches spike around rotation years — weight by voter status.
- Blackout journalism is deniable; treat direction as signal, magnitude as noise.

## 8. STALE BOUNDARY — always pull live, never recall
Current target range; current chair/vice chairs/governors; this year's voting rotation;
latest dot plot medians; current QT pace and balance-sheet policy; current framework
document; current statement language; who is a hawk/dove *today*.
Sources: federalreserve.gov (statements/minutes/SEP), BBG `WIRP` (verify), `FDTR Index`.
