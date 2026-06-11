# Stage 2 Ideation — Session 4: The Edge Listener / Passive Labeling

Fourth ideation session, building on [session 3](ideation-session-3.md)'s data engine. Proposal on the table: a **local listener** on the contributor's machine that captures traces as they happen, runs heuristics/behavioral enrichment on them, and — when the trace's outcome is uncertain — prompts the contributor for a verdict at the moment of capture. The product model: **contributors passively label outcomes** as a side effect of normal work. Non-normative, raw thinking; stage 2 gets a real `spec/stage-2/` before any code.

## The idea

- A listener on the local machine receives traces as agents emit them (the `tracepush` concept from sessions 1–2, repurposed).
- Each trace is enriched with heuristics, including interesting behavioral aspects.
- When the system is uncertain about a trace's *outcome*, a prompt pops up asking the contributor for the answer.
- Configs control the human involvement:
  - **human-only** — e.g. a consumer who only wants fully human-labeled data;
  - **no-human** — e.g. a contributor who doesn't want to be prompted.

## Why this is the strongest idea yet

**It asks the right person at the right moment.** Session 3's quiet weak spot was *who labels?* — a reviewer in a web queue, reconstructing someone else's context hours later. This version asks the person who *just ran the agent*, seconds after it finished — the one human who knows whether the task succeeded, at the moment they know it best. Ground-truth collection moves to where the ground truth lives; labeling stops being a chore and becomes an ambient micro-interaction.

**It completes the flywheel with a supply story.** Sessions 2–3 built the refinery (cluster → judge → verifier) but ore still arrived by manual file upload. Now: capture (listener) → enrich/judge → *uncertain? ask the human who was there* → labeled corpus → tasks/verifiers → datasets. Every stage feeds the next; the contributor's cost is a keystroke per ambiguous trace.

**Label provenance becomes a market dimension.** The human-only/no-human configs generalize into a provenance axis on every label: `machine_labeled` / `human_confirmed` / `human_labeled`. That's how real training-data buyers think ("I'll pay more for human-verified outcomes"), it gives the marketplace its first honest quality tier, and it's where pricing would eventually attach. It degrades gracefully: a contributor who opts out of prompts just produces machine-provenance data — lower tier, still sellable.

**Fleet alignment.** "Human supervision at scale" is their literal thesis — this is supervision pushed to the edge, harvested passively from people doing their normal work.

## Frictions worth taking seriously

1. **The prompt must arrive while context is fresh — so the judge must be fast.** If the popup shows up 20 minutes later, the magic dies. Implication: the *heuristic* tier of the judge decides whether to prompt (instant); the LLM judge refines afterward. Alternative: digest mode ("3 traces from this session need a verdict"). Lean: immediate-on-heuristic-uncertainty with digest as a fallback config.
2. **Interruption budget.** Prompting on every uncertain trace would make a real developer uninstall it by lunch. The configs are the right instinct; add a prompt rate limit ("at most N asks/day") and make *skip* a first-class answer that leaves the label machine-provenance. The system should never *need* the human — it should only get better when it has them.
3. **Trusting contributor self-labels.** Once labels carry a price premium, contributors have an incentive to answer carelessly or dishonestly. Neat architectural property: the LLM judge doubles as an auditor — contributor-label vs. judge disagreement flags a trace for review. A sentence in the spec; not built in the trial.
4. **Scope — this is now three subsystems** (listener, data engine, provenance-aware marketplace). Saving grace: the listener can be radically simple without losing the demo. No native popup needed — a CLI that receives OTLP on `localhost:4318`, uploads, then prints `Trace "fix payment bug" finished — outcome unclear. Success? [y/n/skip]` in the terminal is *the same product moment* at a tenth of the cost. Keep the listener dumb: it captures and relays questions; all judgment stays server-side (the listener polls a "pending questions" endpoint). Native notifications are polish / future work.

**Build-order lean:** the listener fits the trial as the *final* slice — the terminal-prompt version is roughly a day of work, requires the API-key auth you'd want anyway, and is the single most memorable demo beat. If time gets tight it cuts cleanly and survives as spec.

## The full demo

One terminal runs an agent → listener streams the trace in → enrichment labels it, judge is uncertain → terminal asks "did this succeed?" → one keystroke → marketplace shows the trace inside its task cluster with a `human_labeled` badge → consumer filters the marketplace to human-labeled only → acquires the task dataset with preference pairs. Capture, intelligence, supervision, provenance, market — every thesis beat in ninety seconds, on a laptop.

## Open questions

### How does the per-task "learning" actually work? (the big one)

Session 3 hand-waved "the system learns what success looks like per task." There are several genuinely different mechanisms, and the choice shapes everything:

- **Cluster + train?** Cluster traces into tasks, then learn a per-task judge from the accumulated human labels (few-shot exemplars, kNN in embedding space, or eventually a trained classifier). Per-task quality, but cold-starts badly and depends on clustering being right.
- **Baseline evals, improved over time?** Start from generic, task-agnostic outcome evals (error status, completion heuristics, generic LLM rubric) and refine them with human labels — no clustering dependency, works from trace one, but may never get task-specific sharpness.
- **LLM assigns the evals?** An LLM looks at a trace (or task cluster) and *writes* the evaluation criteria — synthesizes a rubric/verifier for that task, which humans then correct. The judge becomes "generate the eval, then run it" rather than "learn from labels."
- And hybrids of all three. Lots of questions: what's the unit the verifier attaches to (task cluster? trace shape?), what happens to learned verifiers when clusters merge/split, how do human labels feed back (exemplars vs rubric edits), what's the cold-start path for a brand-new task?

Unresolved. Needs its own working session before the stage-2 spec, likely informed by prototyping against the real dev dataset.

### Smaller ones added by this session

- **Prompt timing**: immediate vs digest (and the rate-limit defaults).
- **Listener in build order**: final slice vs spec-only.
- **Provenance in the label model**: probably a `label_source` field per outcome label — small, but needs deciding.
