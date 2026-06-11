# Family 2: Outcome Judge

The custom LLM judge that produces the trace's labels: `outcome`, `failure_mode`, `task_category`. The one analyzer we own end-to-end rather than borrowing from a library, because disagreement routing and the label model *are* the product story. Base form is zero-shot (rubric + signals); few-shot exemplars are an extension.

## Outputs

| Field | Values | Notes |
|---|---|---|
| `outcome` | `success \| failure \| indeterminate` | The label model (see [README](README.md)) |
| `failure_mode` | closed taxonomy, only on `failure` | ~6–8 values |
| `task_category` | closed enum | ~8–10 values |
| `confidence` | 0–1 | Composed, not purely self-reported |
| `reasoning` | short text | Stored with the result row; shown in review items and trace detail |

## Proposed taxonomies (to be drilled)

Starting points cribbed from TRAIL / AgentRx failure annotations — to be finalized against the actual datasets:

- **failure_mode:** `wrong_output`, `tool_error_unrecovered`, `loop_repetition`, `hallucinated_action`, `gave_up`, `context_overflow`, `incomplete`.
- **task_category:** `web_research`, `customer_ops`, `coding`, `data_analysis`, `scheduling_planning`, `content_generation`, `retrieval_qa`, `other`.

## Judge inputs

1. **Signals object** from family 1 (structured, compact).
2. **Compact trace rendering** — a token-budgeted serialization of the span tree: roles, tool names, truncated inputs/outputs, statuses. Rendering format is an open design item (it dominates judge quality).
3. **Rubric** — the fixed instruction set defining each outcome/failure_mode/category.
4. *(Extension)* **Few-shot exemplars** — human-labeled traces from the exemplar pool (see README Extensions). Base is zero-shot.

Prompts are versioned; the analyzer-version column makes every verdict reproducible.

## Confidence and HIL routing

Routing to the review queue happens when any of:

- The family-1 heuristic verdict and the LLM verdict **disagree** (likely_success vs failure, etc.).
- The LLM outputs `indeterminate`.
- LLM self-reported confidence falls below threshold (kept as a signal, not trusted alone). **Env-var tunable, default 0.7.**
- `task_category` confidence is low (wrong categories silently corrupt subscriptions; HIL covers categories too). Same 0.7 default knob.

The review item asks the human the same questions the judge answered (outcome, failure_mode if failure, category if uncertain) — answer payload is the jsonb shape from infra §4. Human answer overrides machine fields with provenance `human` (or `human_confirmed` when it matches the machine verdict).

## Feedback loop

- Base: human resolutions correct the trace's labels (per-field provenance) — nothing more.
- **Extension — evaluator training:** resolved review items enter the exemplar pool (listed traces only); judge runs select most recent N, preferring same `task_category`. See README Extensions.
- No fine-tuning, no retroactive re-judging of already-labeled traces in base.

## Validation

- Convert an AgentRewardBench slice, run the judge, report agreement vs expert labels.
- TRAIL provides span-level error annotations for sanity-checking failure_mode assignments.
- The paper findings (rule-based evaluators underreport success; no single LLM judge wins everywhere) are the citable rationale for the layered design + HIL.

## Open questions

- Final taxonomy values for `failure_mode` and `task_category` (validate against the candidate datasets before locking).
- Trace rendering format and token budget; behavior on very large traces.
- Which model powers the judge (env-var tunable per `AGENTS.md`; pick a cheap default).

(Exemplar pool policy moved to the extension; thresholds settled at 0.7 env-var default.)
