# Stage 2 Ideation — Session 3: The Data-Engine Pivot

Third ideation session, building on [session 2](ideation-session-2.md)'s Fleet lens. Proposal on the table: shift the product framing from "trace marketplace" to **a marketplace for task trace training data / labelling for RL**. Non-normative, raw thinking; stage 2 gets a real `spec/stage-2/` before any code.

> **Status: current leading candidate for the stage-2 direction.** A candidate, not a decision — see open items in the README and the open question at the bottom of this doc.

Public datasets that could power this (clustering corpora, human outcome labels, failure-reasoning annotations) are catalogued in [candidate-datasets.md](candidate-datasets.md).

## The proposed loop

Users upload traces → system clusters them into **tasks** → humans label attempts success/failure → system "learns" what success looks like per task → proactively labels new attempts → human-in-the-loop on the uncertain ones.

Strip the marketplace language away and this is a **data engine with active learning**: human labels seed it → system proposes labels → uncertainty routes hard cases back to humans → repeat. The Scale-AI-style flywheel, applied to agent outcomes.

## The sharpening: the learned thing is a verifier

The killer insight: what the system "learns" per task **is a verifier**. Fleet's SDK Task object is literally `prompt + environment + verifier returning 0–1`. The end-state of the loop isn't "a pile of labeled traces" — it's *the marketplace learns a verifier for each task from human labels*. The sellable unit becomes: **task definition + labeled attempt corpus + a verifier you can run on new attempts**. Not adjacent to Fleet's product — the input to it. The verifier is the explicit north star of the framing.

## What "learn" means at trial scale (be honest — interviewers will probe)

With tens of traces and a handful of labels per task, nothing trains in the gradient-descent sense. The defensible version is a **layered judge**:

1. **Heuristic prior** — stage 1 already computes error status, error cascades, etc. Free.
2. **Embedding nearest-neighbor vote** — "this attempt looks like the ones labeled failure." The pgvector infrastructure from enrichment (#1) does this for free; distance-to-labeled-examples is a natural uncertainty signal.
3. **Few-shot LLM judge** — human-labeled examples become the few-shot rubric; the "learning" is accumulation of labeled exemplars plus a synthesized per-task rubric ("for this task, success means the refund was issued and confirmed"). This is genuinely how outcome-labeling is bootstrapped in practice at small n — not a hack.

**Uncertainty = ensemble disagreement, not self-reported confidence.** Heuristic + neighbor-vote + judge agree → auto-label, high confidence. Disagree → review queue. Principled (this is uncertainty sampling / active learning — say so at the onsite), explainable, and doesn't require trusting an LLM's confidence estimate, which you shouldn't.

## Pivot vs. layer

**Nothing in this invalidates stage 1.** Upload → preserve raw → normalize → inspect → list/acquire is exactly the substrate this needs. The pivot is in what stage 2 builds and how the product is narrated. Onsite framing: *revelation, not pivot* — "Stage 1 built a trace marketplace; building it revealed the real product is outcome-labeled task data for RL; stage 2 re-aims the marketplace around that." Iterative product thinking is itself good signal. Do not touch the stage-1 spec.

What changes: the marketplace's unit of value shifts from "a trace" to "a task dataset." Per-trace listing/acquiring stays (mechanically works), but the headline consumer flow becomes acquiring a *task* — attempts, labels, pairs, verifier. This is also where pricing finally makes sense if asked: raw traces are cheap, verified labels are expensive, learned verifiers are the asset.

## The two real risks

### 1. Clustering is load-bearing and fragile

The story collapses if "cluster into tasks" produces mush on the demo corpus. Mitigations:

- **Prototype intent-clustering against the real dev dataset before spec'ing it** (session 2's caveat, now doubly important).
- **Control the demo corpus**: generate it by running a scripted agent over N tasks × M variations, some forced to fail. A synthetic corpus where 60 traces demonstrably cluster into 6 tasks isn't cheating — it's a fixture, and it makes the demo deterministic.
- **Manual escape hatch**: let users merge/split/assign clusters. Honest (clustering is assistive; humans curate) and doubles as the demo safety net.

### 2. Scope

Clustering + task pages + labeling UI + judge ensemble + uncertainty queue is a lot of surface. The slicing saves it — each layer demos independently:

1. Cluster traces into tasks; task pages with attempt lists — *demos alone*
2. One-click success/failure labeling on attempts — *demos alone*
3. Auto-proposed labels with agreement/disagreement confidence — *the wow*
4. Review queue sorted by uncertainty — *the flywheel made visible*
5. Exports: labeled SFT/trajectory data, preference pairs, verifier spec — *the Fleet connection*

Cut from the bottom; landing 1–3 is a complete story, with 4–5 articulated in the spec.

## The demo script this buys

Upload corpus → marketplace discovers 6 tasks → open a task, label 4 attempts → system proposes labels for the rest, most high-confidence, two flagged uncertain → resolve those two in the review queue → export the task as a labeled dataset + preference pairs. Every beat shows a different capability, works at laptop scale, and the closing line writes itself: *"every label makes the verifier better — this is the supply side of an RL training pipeline."*

## Open question: binary vs. graded labels

**Is the outcome label binary success/failure, or graded?** Fleet's verifiers return 0–1; partial credit ("completed but inefficient") is more realistic but makes the judge, the UI, and the uncertainty math all harder.

Current lean (undecided): **binary, with an optional failure-mode tag** (which #1's enrichment taxonomy already provides), noting graded scoring as the obvious extension. Cheap to demo, honest about the path. To be settled before the stage-2 spec is drafted, since it shapes the labeling UI, the judge ensemble, and the export formats.
