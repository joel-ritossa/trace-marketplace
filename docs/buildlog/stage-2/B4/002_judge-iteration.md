# B4 pass 2 — Outcome-judge validation loop: baseline, prompt iteration, reliability

Builds on the B4 harness (converter + `agreement` subcommand). Goal: use the
converted AgentRewardBench slice as a regression set for the outcome judge —
establish a baseline number, mine the disagreements, iterate the prompt under
the versioning convention, and harden the judge path's concurrency and
reliability along the way.

## Dataset

`tools/arb_to_otlp.py --count 200 --seed 0` → 200 trajectories, stratified
50/benchmark (assistantbench, visualwebarena, webarena, workarena), outcome
balance 84 success / 114 failure (assistantbench has few annotated
successes; pools exhaust). Conversion verified before any judging:

- all 200 files import cleanly through the stage-1 importer (one trace per
  file, ≥3 spans, llm spans present);
- labels sidecar 1:1 with files (no orphans either way);
- rendering eyeball (goal as first user message, browsergym actions as
  embedded `tool_call` parts, observations paired back as `tool_result`s,
  step-shifted `last_action_error` as span errors);
- span counts: min 3 / median 18.5 / max 32; 88 traces carry error spans.

AgentRx (the failure-mode half of B4 validation) remains blocked on an
`HF_TOKEN` with the dataset's gate accepted; outcome agreement here is
ARB-only.

## Reliability / concurrency changes (no semantic change)

- **Judge internal concurrency** (`judge.py`): the category call depends
  only on the goal surface, never on the outcome fold — outcome→failure-mode
  now runs concurrently with category. Both branches settle before the
  first error re-raises (same convention as vote gathering), so the typed
  permanent/transient classification survives and no sibling calls leak.
  Cuts judge wall latency ~30–45% per trace. Composition, prompts, and
  voting are unchanged.
- **Version-stamped verdict cache** (`cli/analyze.py`): `RouteReport` now
  carries `judge_version`/`judge_model`; the agreement cache discards
  stale (other prompt rev) or corrupt entries instead of folding them — a
  prompt bump can never silently compare against old verdicts. Reports
  carry the same stamp (`AgreementReport.judge_version/judge_model`).
- **Atomic cache writes**: temp-file + rename, so a kill mid-write can't
  poison a resume.
- **Per-trace fault tolerance**: one trace's transient provider failure no
  longer aborts the whole 200-trace gather; failures are reported, excluded
  from the fold, and the exit code flips — re-running judges only the
  missing traces (cache resume).

Vote-level provider retries were considered and rejected: the worker
already retries `analyze_trace` with backoff (typed transient
classification), and the agreement runner now degrades per trace — a third
retry layer would blur the no-blanket-retries rule for marginal gain.

## Baseline (outcome V1, JUDGE_VERSION 1, gpt-5-mini, N=3)

`out/arb-judge1`, 200 traces, $4.16, ~7 min at concurrency 8:

- decided agreement **87.9%** (175/199), abstention 0.5%, strict 87.5%
- confusion: 13 false-failure, 11 false-success, 1 abstention-on-success
- judge-wrong traces routed to review: 8/24 (most misses are unanimous
  3/3 votes at confidence 1.0 — confidently wrong, not uncertain)
- looping signal vs ARB human annotation: 85% agreement (26 false
  positives, 4 false negatives — converter now exposes browsergym actions
  as tool calls, so loop detection has real signatures to chew on)

### Disagreement taxonomy (25 traces, all reasoning read)

1. **Gullibility (11):** the agent `send_msg_to_user`'d a confident answer
   and the judge took delivery as success; ground truth knows the answer
   was wrong (wrong filter → "0 records", wrong page scraped, etc.).
2. **Process strictness (13):** the answer matched ground truth but the
   judge failed it for skipping explicit constraint verification
   ("never confirmed <200m", "no evidence Department was filled").
3. A long tail that is genuinely unknowable from the trace alone (the
   benchmark's ground truth encodes out-of-trace information).

## Prompt iteration (versioned per the prompts convention)

| run | prompt | decided | strict | abst | false-succ | false-fail |
|---|---|---|---|---|---|---|
| `out/arb-judge1` | V1 | 87.9% | 87.5% | 1 | 11 | 13 |
| `out/arb-judge2` | V2 | 83.6% | 81.5% | 5 | 7 | 25 |
| `out/arb-judge3` | V3 | 87.9% | 87.5% | 1 | 9 | 15 |

- **V2** attacked both modes head-on ("a delivered message is a claim, not
  proof; check it against observed evidence"). Regression: the skepticism
  clause dominated and the judge began failing correct answers whose
  supporting observations the renderer had capped/elided — 16 broken vs 4
  fixed. Lesson recorded in the prompt module: evidence-checking
  instructions interact badly with truncated renderings.
- **V3** keeps V1's result-focused base and narrows skepticism to
  *positive contradiction only*, with an explicit "absent evidence is not
  evidence of failure" clause. Net wash on the headline (2 fixed, 2
  broken) but a slightly better error balance on the false-success side
  (11→9) — kept as the pinned version (`JUDGE_VERSION = "3"`).
- Truncation is not the bottleneck: error rate on truncated renderings
  (10.1%) is *lower* than on untruncated ones (14.4%).

The honest read: ~88% decided agreement is the plateau for
prompt-iteration at gpt-5-mini on this slice. Roughly half the residual
misses need information the trace doesn't contain; the other half are
judgment-call disagreements a stronger judge model may decide differently
(probe below). Run-to-run sampling noise at N=3/temp 0.7 is ±2–3 traces,
so single-trace deltas between prompt revs are not signal.

## Stronger-model probe

50-trace probe set (the 25 V3 misses + 25 random V3 hits) judged with
`ANALYSIS_JUDGE_MODEL=openai/gpt-5` (`out/arb-judge3-gpt5-subset`, $6.89
for 50 traces — $0.138/trace vs mini's $0.021, ≈ 6.6×):

- of mini's 25 misses, gpt-5 fixes **7**, leaves 18 wrong;
- of mini's 25 hits, gpt-5 breaks **1** — a 4% break rate that
  extrapolates to ~7 flipped-to-wrong across the full set's 175 hits;
- zero abstentions, and its residual misses skew 14 false-failure /
  5 false-success — gpt-5 is *stricter*, re-expressing the same
  process-strictness mode (fails correct answers for unverified
  constraints or incomplete multi-part presentation), while its fixes
  concentrate where mini lacked capability: arithmetic/aggregation
  checks and contradiction-spotting across distant steps.

Net expected full-set delta ≈ 0 at 6.6× cost: not a win. 18/25 misses
survive a much stronger judge, which corroborates the taxonomy — the
residual disagreement is dominated by information the trace does not
contain (benchmark ground truth knows whether the delivered answer was
*actually* right; the trajectory alone often cannot). The cheap default
model stands.

## AgentRx (failure-mode half)

Token granted mid-pass; `tools/agentrx_to_otlp.py` written against the real
files (B4 decision 5's deferred mapping, now pinned):

- **tau_retail** (29): one chat span per assistant turn; buffered
  system/user/tool messages become the span's input; assistant tool-call
  JSON becomes `tool_call` parts with ids, tool results pair back FIFO as
  `tool_call_response` parts. Trailing non-assistant evidence gets a final
  no-response span.
- **magentic_one** (44 annotated of 58; unannotated skipped): one chat span
  per agent utterance, speaker as `gen_ai.agent.name`; `human` turns buffer
  as user input. Annotation ids join trajectories via the `tau_retail_`
  prefix; magentic joins directly.
- **Drift vs decision 6:** the dataset's category strings are freeform
  variants ("Instruction/Plan Adherence Failure", "Intent not supported",
  "Invention of new information"), so pure snake_casing cannot land in
  `FAILURE_MODES`. The converter normalizes through an explicit 1:1 alias
  table (case/punctuation-insensitive); an unknown string is still a hard
  converter error, and `load_labels` re-validates against the app taxonomy.
  No semantic remapping.
- Ground truth never leaks into the trace: failure annotations exist only
  in the sidecar; spans carry no error statuses derived from them.
- Verified like ARB: all 73 import cleanly, labels 1:1, every trace has an
  extractable first user message, renderings eyeballed per split (redaction
  placeholders on number-like ids confirm the conversions take the real
  ingestion path).

Results (all 73 are ground-truth failures):

| run | judge | outcome called failure | root-cause match | any-category match |
|---|---|---|---|---|
| `out/agentrx-judge3` | v3 (fm V1) | 47/73 | 14.9% (7/47) | 29.8% (14/47) |
| `out/agentrx-judge4` | v4 (fm V2) | 46/73 | 17.4% (8/46) | 30.4% (14/46) |

- The judge calls ~⅓ of AgentRx failures "success" — almost all are
  traces where the agent delivered a confident, plausible, *wrong* answer
  (tau tasks fail against a hidden ground-truth DB state the trace never
  shows: "the incorrect count does not correspond with ground truth").
  Same information limit as ARB, amplified because this corpus is 100%
  failures of exactly that flavor.
- **failure_mode V2** targets the two confusions read out of the V1 votes:
  terminal-symptom anchoring (a runtime crash ending an already-doomed run
  → `system_failure`; a fabricated final answer after data was never
  obtained → `invention_of_information`) and `plan_adherence_failure` as
  the repetition catch-all. V2 defines the root cause as the earliest
  unrecovered derailment and adds boundary notes. Effect: directionally
  right (plan-adherence picks 18→13, symptom-inventions 6→3, root-cause
  match +2.5pts) but small on n=46 — within noise. Kept: the sharper
  definitions cost nothing and the distribution shift is the intended one.
- Honest framing for the demo: AgentRx root-cause attribution against
  annotators who saw the ground truth is a hard upper bound; the judge's
  classifications are frequently defensible readings of the visible trace
  (verified by reading votes on the confusion diagonal).

## Outcome

- Baseline established and reproducible: the agreement harness + cache are
  version-aware, fault-tolerant, and resumable; reports are stamped with
  judge version/model.
- Judge wall latency reduced (parallel outcome/category) with no semantic
  change; full unit suite green.
- Pinned ensemble: outcome V3 + failure_mode V2 (`JUDGE_VERSION = "4"`);
  superseded prompt versions retained in their modules with the measured
  rationale, per the never-edit-in-place convention. (Superseded by pass 3:
  failure_mode V4 / `JUDGE_VERSION = "5"` —
  see `003_failure-mode-iteration.md`.)
- Headline for the demo: **87.9% decided agreement with expert annotators
  on 200 AgentRewardBench trajectories** (0.5% abstention; $3.67–4.16 and
  ~7 min per full run at concurrency 8).
- Known gap recorded honestly: most wrong verdicts are unanimous
  confident votes, so only ~a third carry routing reasons — confidence
  voting catches uncertainty, not confident error. Raising recall there
  means widening routing triggers (e.g. routing `failure` verdicts on
  listed-for-sale traces, or sampling-based audit), a product decision,
  not a prompt fix.
