# Stage 2 Ideation — Session 2: The Fleet Lens

Second ideation session. Takes a meta-level step back from [session 1](ideation-session-1.md): this project is a technical onsite artifact for Fleet (fleet.ai), and that context should shape what stage 2 is *for*. Non-normative, raw thinking; stage 2 gets a real `spec/stage-2/` before any code.

## Who the evaluator is

Fleet builds **training infrastructure for agents**: simulated "gyms" mirroring real software, tasks defined as *prompt + environment + verifier* (their SDK's core Task object returns a 0–1 score), RL post-training (they maintain a SkyRL fork), and human supervision at scale. Mission: simulated worlds and real-world challenges to understand and shape agent behavior.

## The reframe: traces are ore, not product

Session 1 treats the marketplace as the destination — people browse, buy, download traces. Through Fleet's lens, a trace marketplace is the **supply side of the agent-training flywheel**:

> deployed agents emit traces → traces reveal real tasks, failure modes, and behavior → those get refined into training assets → better agents

The "trace marketplace" prompt wasn't arbitrary: real agent behavioral data is precisely the raw material an environment/task/training business consumes. So the most strategically resonant stage-2 question isn't "how do people find traces?" (#1) or "how do they package them?" (#2) — it's: **what refined products can be smelted out of a trace corpus?**

## Four refinement products, in increasing ambition

### A. Trajectories — traces as post-training data

Convert normalized traces into training-ready trajectory formats: message/tool-call sequences with outcomes, exported as SFT JSONL or an RL-trajectory shape (SkyRL-compatible would be a knowing wink). Upgrades session 1's "eval-ready exports" into something aimed at Fleet's actual pipeline: the marketplace stops selling JSON files and starts selling *training data*.

- Effort: moderate — a transform over data stage 1 already normalizes.
- Demo: "acquire this dataset; here's the JSONL you'd fine-tune on tonight."

### B. Rewards — outcome and process labels

A trace is an *attempt*; the most valuable metadata is whether it succeeded and where it went wrong. Infer outcome labels heuristically (final span status, error cascades, explicit eval attributes), then let the contributor/reviewer confirm or correct — a one-click human-in-the-loop step that maps directly onto Fleet's "human supervision at scale" thesis.

- Failure-mode enrichment (#1) is already half of this: failure labels *are* negative reward signal. The extension is making success/failure a first-class, human-confirmable field.
- Cheap, and it unlocks everything downstream (pairs, leaderboards, task mining).

### C. Tasks — mining task definitions from trace clusters

The boldest, most Fleet-shaped idea. Cluster traces by *intent* (embeddings over root-span goals — infrastructure #1 already builds), then synthesize a **task card** per cluster: natural-language objective, tools/environment touched, difficulty signals (median steps, retry rates), attempts grouped under it. Optionally export in a Fleet-SDK-like shape (prompt + verifier sketch). This is literally Fleet's product input — "real-world challenges drawn from authentic enterprise contexts" — mined automatically from marketplace supply.

- Demo: upload 30 traces → marketplace discovers "these are 5 distinct tasks" → each task page shows attempts, models tried, success rates. The marketplace becomes a *task catalog*, not a file cabinet.
- Two near-free derivatives once tasks exist:
  - **Same-task leaderboards**: success rate, steps, tokens, cost per model/agent on the same task. The marketplace starts selling *comparative evidence about agent capability* — arguably more valuable than the traces themselves.
  - **Preference pairs**: success-vs-failure (or efficient-vs-wasteful) trace pairs on the same task, exported as DPO-style data.

### D. Environments — fingerprinting the world a trace ran in

From tool calls, API shapes, and attributes, derive what software/world the agent operated in: "this corpus contains 40 traces against a Salesforce-like CRM." That's the requirements doc for building one of Fleet's simulated environments. Most speculative, fuzziest heuristics — likely a paragraph in the spec rather than a build, but naming it shows where the flywheel terminates.

## Meta-level notes on the interview itself

1. **The narrative is the deliverable as much as the code.** "I built a marketplace, then realized a trace corpus's real value is as training-data ore — so stage 2 refines traces into rewards, trajectories, and tasks" demonstrates understanding of *their* business, not just the prompt. Ideas never built still earn credit if they're in the spec with clear reasoning about why they were cut.
2. **Don't overfit into pandering.** If everything screams "I read your website," the artifact stops standing on its own. Defensible posture: #1 and #2 remain the core because they're right *for any trace marketplace*; the Fleet lens then selects which stretch to build and how to frame exports.
3. **"What would you do next" will come up at the onsite.** The articulated flywheel — ore → labels → trajectories/pairs → tasks → environments — gives a crisp answer at every level of ambition, and each rung visibly builds on the stage-1 foundation (normalized spans, worker pipeline, pgvector).
4. **This reframes session 1's weaker ideas into stronger ones:**
   - "Annotations" stops being a weak community feature → becomes *supervision/reward labeling*.
   - "Eval exports" stops being a convenience → becomes the product.
   - "Trace diff" gains a purpose → comparing attempts at the same task.

## Working position after this session

- **Built layer:** B (outcome labels with human confirmation) + the trajectory/preference-pair export slice of A. Small, composes cleanly with #1/#2, demoable with ~20 traces.
- **High-risk/high-wow option:** C (task mining). Spectacular if intent clustering works on the dev dataset, embarrassing if clusters come out as mush. Prototype against real data *before* committing it to spec.
- **Spec-only:** D (environment fingerprinting) — name it in the stage-2 spec as the flywheel's terminus; do not build.
- Session 1's core (#1 enrichment + discovery, #2 trace sets) is unchanged as the substrate; this session changes the framing and the choice of stretches on top of it.
