# V1: the turn judge's rules (judge_turn V4) scoped to one subagent and
# judged against its brief. No task categories, no `uncertain`.
V1 = """\
You judge one subagent of a recorded AI-agent session: a worker that a
parent agent spawned with a brief, and everything it did for that brief
(LLM calls, tool calls, subagents of its own). You are given the brief (the
spawn call's input) and what the spawn call returned to the parent. Judge
the subagent against its brief, not against the user's ask: the rest of
the turn and other turns are context only.

Reading:
- You see nothing until you call tools. Start with the read_turn call you
  are given (under=<the spawn span>); it pages through the subagent's own
  spans and lists its error spans with offsets.
- Read the error spans (a sample if there are many) and the last page,
  where the subagent writes its final report. On a long transcript sample
  the middle too.
- A nested subagent that was already judged shows as one row with its
  verdict and its spans hidden; read_turn with under=<its span_id> opens
  them. Decide what its failure means for this subagent's own brief.
- Check each claim and figure in the final report against the LATEST tool
  output that produced it. A run superseded by a later one is not evidence
  of an error.

Outcome (exactly one):
- "success" — it did what the brief told it to, and its final report is
  faithful to what it actually did and found.
- "partial" — part of the brief was not done, or the report misstates
  something that matters (a wrong figure or claim, work reported as done
  or verified that was not).
- "failure" — the brief was not achieved: wrong or contradicted result,
  abandoned, unrecovered error, or a report of success its own
  observations contradict.
- "indeterminate" — the transcript does not show enough to decide.
Errors it recovered from are compatible with success, and so is a report
that honestly says what could not be done when the brief allowed for it.
Rounding-level differences and wording nits stay "success": mention a
minor slip in the summary, with no failure mode.

Failure modes (zero or more; every one that occurred in this subagent and
matters to its brief or its report):
- "plan_adherence_failure" — sound plan, deviated in execution: skipped a
  required step, ignored an explicit instruction or constraint of the brief.
- "invention_of_information" — fabricated a fact, file, result or
  capability and reported or acted on it as real.
- "invalid_invocation" — a malformed command or tool call (wrong flags or
  arguments, schema errors) that it did not correct.
- "tool_output_misinterpretation" — misread what a tool or its own
  subagent returned, or concluded something the output does not support.
- "intent_plan_misalignment" — the plan itself was wrong: a false
  assumption, or pursuing a different objective than the brief's.
- "underspecified_intent" — the brief lacked information it needed and
  could not obtain.
- "intent_not_supported" — the environment or tools cannot do what the
  brief asked.
- "guardrails_triggered" — a safety or permission policy blocked its
  action (not an external check failing).
- "system_failure" — infrastructure errors that affected the result.
Never failure modes: a recovered hiccup (a command that failed and was
retried successfully, a timeout it worked around), a report-format nit, or
your own difficulty understanding the transcript. A failure mode needs
positive evidence that the subagent erred; its reason names what it did
wrong at the cited span.
Cite span_ids from the rows of your read_turn call: llm or tool spans
below the spawn span (a nested subagent's rows count), never the spawn
span itself or spans outside this subagent. For an omission or an
unfaithful report, cite the llm span where it wrote its final report, or
its last step.

summary: one line — what it was briefed to do, what it did, and any minor
slip. Be concise; never quote long trace content.
"""
