# Data-Engine Candidates

The dropped core of the stage-2 ideation arc (`.archive/stage-2-planning/ideation/`, sessions 2–4): task clustering and everything that depended on it. The requirements pass dropped it with one locked decision ("Task clustering: **Dropped**"); the pieces lost on scope and on the rule-based-matching principle, not on merit. Recorded here so picking any of them up doesn't require re-deriving the rationale from superseded ideation docs.

**Shared gate:** every candidate below depends on intent clustering producing real task groups on real data — the load-bearing, fragile step that motivated the drop. The base system's rule-based shadow of it is `task_category` (closed enum) + filter subscriptions; these candidates return only if that shadow proves too coarse in practice.

## Candidates

| Candidate | What it is | Why it lost | What would change the call |
|---|---|---|---|
| Task clustering | Cluster traces by intent (embeddings over goals) into task groups; the marketplace's unit of value shifts from "trace" to "task dataset" (session 3) | Load-bearing and fragile — the story collapses if clusters come out as mush; conflicts with the rule-based principle (embedding clusters aren't rule-matchable); large surface | Evidence that flat `task_category` is too coarse for subscriptions/bounties, plus a corpus with real task overlap (e.g. Exgentic's same-task structure) to validate clustering against. The hierarchical-category follow-up ([judging-post-v1-candidates.md](judging-post-v1-candidates.md)) is the cheaper first step |
| Learned per-task verifiers | The session-3 north star: per-task outcome judges learned from accumulated human labels; sellable unit = task + labeled corpus + runnable verifier | Attaches to a task unit that no longer exists once clustering dropped; cold-starts badly at trial scale; "future-work narrative only" per the locked decision | Clustering (or session stitching) lands and the per-category exemplar pool ([docs/extensions/evaluator-training.md](../extensions/evaluator-training.md)) demonstrably sharpens per-task judgment |
| Same-task leaderboards | Success rate / steps / tokens per model on the same task — comparative capability evidence | Requires task identity; no rule-based equivalent exists | Task identity from clustering, or session/task metadata with adequate hit rate on real uploads |
| Preference pairs + SFT/trajectory exports | Success-vs-failure pairs on the same task (DPO-style) and training-ready trajectory formats; "future-work narrative, not stage 2" in the spec's own words | Pairs require task identity; trajectory exports lost to `labels.jsonl` as the smallest useful artifact | Consumer demand for training-shaped downloads; pairs additionally need task identity. The renderer (spans → message list) already does most of the trajectory-export transform |
| Environment fingerprinting | Derive what software/world a trace corpus ran against (session 2's product D) — requirements material for environment builders | Fuzziest heuristics of the arc; was spec-only even at ideation | A consumer surface that needs it; concretely useful only with enough corpus volume per environment |

## Why this is one file

These candidates form a ladder (clustering → verifiers/leaderboards/pairs → environments): each rung needs the one below, so they get revisited together, in order, starting from whether clustering's premise holds on real data.
