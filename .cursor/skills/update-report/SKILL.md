---
name: update-report
description: Write or update sections of the final report in report/ — the evaluator-facing account of the trace-marketplace project. Use when asked to build out, update, revise, or fact-check a report doc (report/01–11 or its README), or to add new material to the final report.
---

# Update the Final Report

The report lives in `report/` (index: `report/README.md`). Audience: an evaluator
deciding what was built and whether it holds up. The report's credibility is its
only asset — one inflated claim taints every other one.

## Cardinal rules

1. **Truthful first.** Every claim must be backed by something in the repo:
   spec, demo doc, buildlog, migration, code, or a command the evaluator can
   run. If you can't point to the evidence, don't write the sentence.
2. **Concise second.** Short sentences, plain words, no marketing language.
   Cut anything that doesn't inform a decision the evaluator might make.
3. **Easy to understand third.** Explain the *why* before the *how*. One idea
   per paragraph. Define project jargon on first use (e.g. "HIL review —
   uncertain verdicts routed to a human queue").

## Where claims come from

| Claim type | Source of truth |
|---|---|
| What the system is supposed to do | `docs/spec/stage-1/`, `docs/spec/stage-2/` (normative) |
| What it actually does | The code (`services/api`, `apps/web`, `apps/desktop`, `supabase/migrations`) |
| Quantitative results (agreement %, AUC, counts) | `docs/demos/*.md` — copy numbers verbatim, never round up or paraphrase |
| Behavior guarantees (delivery, consistency, security boundaries) | `docs/explainers/` |
| How/when something was built, drift, known issues | `docs/buildlog/` |
| Design tokens / UI claims | `DESIGN.md` |

When spec and code disagree, the code is what shipped — report the code's
behavior and note the gap (it likely belongs in `09_limitations-and-future-work.md`
or `11_outstanding-items.md`).

## Workflow

1. **Scope** — which doc(s)? Check `report/README.md` for each doc's charter so
   content lands in the right file and isn't duplicated across docs. Read the
   target doc and `01_overview.md` to match the established voice.
2. **Gather evidence** — read the relevant spec, demos, explainers, and code
   before writing. For anything load-bearing (a number, a guarantee, a "never
   happens" claim), verify in code or a demo doc, not from memory.
3. **Write** — see style rules below.
4. **Self-audit** — reread the draft and challenge every factual sentence:
   "where in the repo is this true?" Strip or soften anything you can't ground.
5. **Sync** — if a doc's scope changed, update its row in `report/README.md`.
   Fix any cross-links between report docs.

## Style rules

- **Hedge honestly, not defensively.** "Validated on a 200-trajectory slice"
  is honest scoping; "should mostly work" is mush. State the boundary of what
  was tested, then stop.
- **Limitations are content, not confession.** Known gaps go in 09/11 with the
  same matter-of-fact tone as features. Never hide a weakness an evaluator
  would find in ten minutes.
- **Numbers carry their context.** Never a bare "87.9%" — always metric +
  dataset + size: "87.9% outcome agreement with expert annotators on a
  200-trajectory AgentRewardBench slice."
- **Prefer the verifiable phrasing.** "Downloads are byte-identical to the
  uploaded payload (checked by the smoke script)" beats "data integrity is
  guaranteed."
- **No superlatives** ("robust", "seamless", "production-grade",
  "comprehensive") unless quoting a measurable property.
- **Structure for skimming.** Lead each section with its one-sentence takeaway.
  Use tables for comparisons, bullets for parallel facts, prose for reasoning.
- **Link, don't repeat.** Point to the demo/explainer/code rather than
  restating it; the report is a map, the repo is the territory.

## Banned moves

- Inventing or extrapolating numbers, even plausibly.
- Presenting planned/deferred work as shipped.
- Claiming test coverage, benchmarks, or guarantees not actually in the repo.
- Describing spec intent as implemented behavior without checking the code.
- Padding: throat-clearing intros, restating the obvious, synonym chains.
