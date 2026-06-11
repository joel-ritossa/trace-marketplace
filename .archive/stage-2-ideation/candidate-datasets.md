# Stage 2 Candidate Datasets

Public datasets that could power the stage-2 data-engine demo ([session 3](ideation-session-3.md)): task clustering, outcome labeling, judge validation. Found during ideation; licenses unverified — check before use. Non-normative.

Ground rules (per `AGENTS.md`): these are local dev/demo data only; committed fixtures stay synthetic. Format is not a blocker — an offline convert-to-OTLP script turns any of these into upload-ready files without touching the stage-1 "one importer" decision (conversion happens before upload).

Useful structural insight: **any trace corpus dumped from a benchmark run is auto-labeled** — the benchmark's own verifier (GAIA exact-match, TAU-bench DB-state check, WebArena evaluators) already scored each episode. The rare commodity is labels *with human reasoning attached*.

## Primary picks

### Exgentic/agent-llm-traces — task-clustering corpus (OTel-native)

<https://huggingface.co/datasets/Exgentic/agent-llm-traces>

- 1,781 execution traces, **already OpenTelemetry** with proper `gen_ai.*` attributes (input/output messages, token usage, tool definitions, status). Transform to the OTLP envelope is trivial.
- 6 benchmarks; **4 non-coding**: TAU-Bench Airline/Retail/Telecom (customer-service tool use — maximally enterprise/Fleet-flavored), BrowseCompPlus, AppWorld. Exclude SWE-bench for the non-coding preference.
- 5 models × 5 agent frameworks attempting the *same benchmark tasks* → task clusters exist by construction, with ground truth to recover. De-risks the scariest part of the pivot (does intent clustering produce mush?) and enables same-task leaderboards immediately.
- Benchmark tasks have known pass/fail criteria → outcome labels anchorable to ground truth.
- License not visible on the card — verify.

### McGill-NLP/agent-reward-bench — human outcome labels (the "learning" corpus)

<https://huggingface.co/datasets/McGill-NLP/agent-reward-bench> · [paper](https://arxiv.org/abs/2504.08942)

- **1,302 web-agent trajectories, each expert-annotated for success, side effects, and repetition cycles.** Built specifically to evaluate LLM judges against human labels — exactly the loop we want to demo.
- 5 benchmarks × 4 LLM agents → same-task multi-attempt structure. **WorkArena = ServiceNow enterprise tasks** (non-coding, very Fleet).
- Trajectories include agent reasoning chains, actions, screenshots; repo also ships **LLM judge outputs** alongside human labels — we can benchmark our judge ensemble against both.
- Paper findings are citable design rationale: rule-based evaluators *underreport* success; no single LLM judge wins across benchmarks → argument for the layered judge + human-in-the-loop.
- Trajectories are browsergym-shaped (action/observation steps) — converter produces browser-step spans, not LLM-call spans. Fine, but design the converter knowingly.

### microsoft/AgentRx — failure labels *with reasoning*

<https://huggingface.co/datasets/microsoft/AgentRx> · [paper](https://arxiv.org/abs/2602.02475)

- 115 failed trajectories; every failure annotated with `step_number`, `step_reason`, `failure_category`, `category_reason`, plus a root cause with `reason_for_root_cause` — **human-written explanations of why it failed**, step-located. The "reasoning bonus" item.
- One split is **`tau_retail`** — same task world as Exgentic's TAU-bench traces, so the corpora interlock: Exgentic = OTel-native attempts, AgentRx = reasoned failure diagnoses in the same domain.
- Small but dense; ideal as few-shot exemplars for the judge's rubric and for "show your work" label explanations.

### PatronusAI/TRAIL — span-level error ground truth (OTel-native)

<https://huggingface.co/datasets/PatronusAI/TRAIL>

- 148 traces (118 GAIA open-world search — non-coding; 30 SWE-bench), 1,987 **OpenTelemetry/OpenInference spans**, **841 human-annotated errors** with span IDs, category, evidence, description, impact level. High inter-annotator agreement.
- Lowest transform cost (already OTel). Role: validation set — score the auto-labeler against human annotations ("our labeler agrees with human annotators X% of the time" is a demo sentence few take-homes get to say).

## Reserve / situational

- **ZBox008003/AFTraj (AFTraj-2K)** — <https://huggingface.co/datasets/ZBox008003/AFTraj>. 2,276 multi-agent trajectories, near-balanced safe/unsafe; unsafe ones carry decisive-error step, responsible agent, and (diagnosed subset) `mistake_reason`. Volume for the embedding/neighbor-vote layer; domains are math/coding/agentic so filter.
- **juliensimon/open-agent-traces** — <https://huggingface.co/datasets/juliensimon/open-agent-traces>. 500 fully synthetic multi-agent workflow runs, 10 business domains, with normative workflow models + injected-deviation ground truth. Clean for committing samples (synthetic). OCEL 2.0 format — bigger conceptual transform; hold in reserve.
- **OpenTraces/lambda-hermes** — <https://huggingface.co/datasets/OpenTraces/lambda-hermes-agent-reasoning-opentraces>. 7,645 traces with explicit `task` metadata and `outcome` field, CC-BY-4.0. Single model/agent, domain unclear, 675 MB. Only if Exgentic volume feels thin.
- **NJU-LINK/CodeTraceBench** — <https://huggingface.co/datasets/NJU-LINK/CodeTraceBench>. 4,316 coding-agent trajectories with `solved` bool + human-verified step-level incorrect/unuseful labels across 26 categories. Excellent structure but coding-domain — counter to the non-coding preference.
- **HF `agent-traces` format datasets** (julien-c/synthtraces, lewtun/ml-intern-sessions, etc.) — Claude Code/Pi session JSONL, all coding sessions; some carry explicit sensitive-content warnings. Skip.

## How the portfolio assembles

| Need | Dataset |
|---|---|
| Task clustering + leaderboards, OTel-native | Exgentic (non-coding subsets) |
| Trace-level success labels (human, expert) | AgentRewardBench |
| Failure reasoning / root-cause exemplars | AgentRx, TRAIL |
| Judge validation vs. human labels | AgentRewardBench + TRAIL |
| Bulk for embedding layer (if needed) | AFTraj |

Together these support every claim in the session-3 demo script: clustering has ground truth to recover, the judge has human labels for few-shot rubrics *and* to be scored against, and the reasoning-annotated sets let the system explain its labels the way human annotators did.

Caveats: (1) all except Exgentic/TRAIL need a trajectory→OTLP converter; (2) verify each license before use, and never commit converted real data — synthetic fixtures only; (3) the spec says the project owner provides a dev dataset — these supplement it specifically for clustering/labeling work, which needs *many attempts at overlapping tasks* that a generic dev dataset likely won't have.
