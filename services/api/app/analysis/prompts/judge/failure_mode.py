# V4 (validated on the unconditional AgentRx fm-eval, n=73, after the
# converter's tail-preserving cap fix made guardrail evidence visible): V3's
# absolute boundary rule 1 over-triggered — any visible policy/CAPTCHA error
# anywhere in the trace pulled votes to guardrails_triggered even when the
# agent moved past the block and the doom came elsewhere. V4 subordinates
# every boundary rule to the earliest-unrecovered-derailment rule: guardrail
# evidence only classifies when the block is what the agent never recovered
# from. Otherwise identical to V3.
V4 = """\
An AI agent failed to accomplish its task. You will be shown the recorded
execution trace (chronological steps, possibly truncated where marked) and,
when available, deterministic evidence extracted from it (detected loops,
error spans). Classify the primary cause of failure.

Some traces are multi-agent (an orchestrator directing workers such as web
or file agents). Treat a worker's reply to the orchestrator as a tool
output, and an orchestrator's instruction to a worker as a tool call.

The primary cause is the EARLIEST failure the agent never recovered from —
the point where the task became doomed. Later problems that follow from it
are symptoms: a crash or loop at the end of a run that had already gone
off the rails, or a made-up final answer delivered after the agent failed
to obtain the data, are symptoms of the earlier derailment. Walk the trace
forward and classify the first unrecovered derailment.

Choose exactly one failure mode:

- "plan_adherence_failure" — the agent had the right objective and a sound
  plan but deviated in execution: skipped a required step (e.g. acting
  without a required confirmation), ignored an explicit instruction or
  constraint from the user (wrong item, wrong payment method), or executed
  plan steps so poorly the plan never got carried out.
- "invention_of_information" — the agent fabricated something and then
  acted on it as real: a file or path that was never created, a download
  that never happened, a fact or capability that does not exist. The
  fabrication must be where the task first went wrong — not a last-resort
  final guess after something else already failed.
- "invalid_invocation" — a tool call malformed at the interface: wrong or
  missing arguments, bad types, schema violations, causing an execution
  error.
- "tool_output_misinterpretation" — a tool or worker returned information
  and the agent read it wrong: miscounted items in a result, treated a
  reply as answering the question when it answered something else, drew a
  conclusion the output does not support, or proceeded on a result it
  should have seen was incomplete. Check the agent's claims against the
  tool outputs actually shown.
- "intent_plan_misalignment" — the plan itself was wrong before execution
  began: built on a false assumption about what is allowed or possible
  (e.g. assuming a partial cancellation is permitted when policy forbids
  it), or pursuing a different objective than the user's actual request.
- "underspecified_intent" — the request as stated was missing or wrong
  about information the agent needed and could not obtain: the user asked
  for less or different than the real task required, insisted on an
  invalid action, or never supplied a needed detail when asked.
- "intent_not_supported" — the agent or a worker was asked to do something
  outside its capabilities or the system's supported actions: a tool that
  cannot do what was requested (email, audio, video interaction), or an
  operation the domain does not support at all.
- "guardrails_triggered" — a safety or access policy blocked progress:
  provider content-policy errors, CAPTCHAs or anti-bot checks, blocked
  sites, permission refusals.
- "system_failure" — infrastructure died while the task was otherwise on
  track: timeouts, unreachable endpoints, provider outages, runtime
  crashes, abrupt termination with no earlier derailment.
- "inconclusive" — the trace shows failure but the cause cannot be
  attributed. A valid answer; prefer it over guessing.

Boundary rules — each applies only at the derailment point identified
above, never to incidents the agent recovered from and moved past:

1. A blocking error whose text mentions a content policy, responsible AI
   violation, jailbreak detection, CAPTCHA, "verify you are not a robot",
   or access denial is "guardrails_triggered" — even when it surfaces as
   an HTTP error or exception traceback. But only when that block is what
   the agent never recovered from; a CAPTCHA or refusal the agent worked
   around and continued past is not the root cause. "system_failure" is
   only for infrastructure faults with no policy dimension.
2. If the agent's first wrong move was a misreading of something a tool or
   worker actually returned, classify "tool_output_misinterpretation" —
   even if that misreading later caused off-plan behavior, loops, or a
   wrong answer.
3. Distinguish where the plan went wrong: conceived wrong
   ("intent_plan_misalignment"), executed wrong ("plan_adherence_failure"),
   or impossible for the user's stated request to succeed as given
   ("underspecified_intent").

Respond with JSON: {"failure_mode": "...", "confidence": <0.0-1.0>,
"reasoning": "<1-3 sentences citing specific steps>"}. Reference the
trace's structure (step numbers, tool names, errors), never reproduce long
verbatim content from it.
"""

# V3 (validated on the unconditional AgentRx fm-eval, n=73): V2's confusion
# matrix concentrated in four patterns — provider content-policy/CAPTCHA
# errors read as system_failure, the plan-adherence/plan-misalignment and
# plan-adherence/underspecified boundaries, misread tool outputs filed
# elsewhere, and fabricated final answers still pulling votes to invention.
# V3 rewrites the definitions in the annotators' own language (mined from
# AgentRx category_reason/step_reason fields), frames multi-agent traces
# (a worker's reply is a tool output; an instruction to a worker is a tool
# call), and adds explicit discrimination rules for those four boundaries.
V3 = """\
An AI agent failed to accomplish its task. You will be shown the recorded
execution trace (chronological steps, possibly truncated where marked) and,
when available, deterministic evidence extracted from it (detected loops,
error spans). Classify the primary cause of failure.

Some traces are multi-agent (an orchestrator directing workers such as web
or file agents). Treat a worker's reply to the orchestrator as a tool
output, and an orchestrator's instruction to a worker as a tool call.

The primary cause is the EARLIEST failure the agent never recovered from —
the point where the task became doomed. Later problems that follow from it
are symptoms: a crash or loop at the end of a run that had already gone
off the rails, or a made-up final answer delivered after the agent failed
to obtain the data, are symptoms of the earlier derailment. Walk the trace
forward and classify the first unrecovered derailment.

Choose exactly one failure mode:

- "plan_adherence_failure" — the agent had the right objective and a sound
  plan but deviated in execution: skipped a required step (e.g. acting
  without a required confirmation), ignored an explicit instruction or
  constraint from the user (wrong item, wrong payment method), or executed
  plan steps so poorly the plan never got carried out.
- "invention_of_information" — the agent fabricated something and then
  acted on it as real: a file or path that was never created, a download
  that never happened, a fact or capability that does not exist. The
  fabrication must be where the task first went wrong — not a last-resort
  final guess after something else already failed.
- "invalid_invocation" — a tool call malformed at the interface: wrong or
  missing arguments, bad types, schema violations, causing an execution
  error.
- "tool_output_misinterpretation" — a tool or worker returned information
  and the agent read it wrong: miscounted items in a result, treated a
  reply as answering the question when it answered something else, drew a
  conclusion the output does not support, or proceeded on a result it
  should have seen was incomplete. Check the agent's claims against the
  tool outputs actually shown.
- "intent_plan_misalignment" — the plan itself was wrong before execution
  began: built on a false assumption about what is allowed or possible
  (e.g. assuming a partial cancellation is permitted when policy forbids
  it), or pursuing a different objective than the user's actual request.
- "underspecified_intent" — the request as stated was missing or wrong
  about information the agent needed and could not obtain: the user asked
  for less or different than the real task required, insisted on an
  invalid action, or never supplied a needed detail when asked.
- "intent_not_supported" — the agent or a worker was asked to do something
  outside its capabilities or the system's supported actions: a tool that
  cannot do what was requested (email, audio, video interaction), or an
  operation the domain does not support at all.
- "guardrails_triggered" — a safety or access policy blocked progress:
  provider content-policy errors, CAPTCHAs or anti-bot checks, blocked
  sites, permission refusals.
- "system_failure" — infrastructure died while the task was otherwise on
  track: timeouts, unreachable endpoints, provider outages, runtime
  crashes, abrupt termination with no earlier derailment.
- "inconclusive" — the trace shows failure but the cause cannot be
  attributed. A valid answer; prefer it over guessing.

Boundary rules, in order:

1. An API or model error whose text mentions a content policy, responsible
   AI violation, jailbreak detection, CAPTCHA, "verify you are not a
   robot", or access denial is "guardrails_triggered" — even when it
   surfaces as an HTTP error or exception traceback. "system_failure" is
   only for infrastructure faults with no policy dimension.
2. If the agent's first wrong move was a misreading of something a tool or
   worker actually returned, classify "tool_output_misinterpretation" —
   even if that misreading later caused off-plan behavior, loops, or a
   wrong answer.
3. Distinguish where the plan went wrong: conceived wrong
   ("intent_plan_misalignment"), executed wrong ("plan_adherence_failure"),
   or impossible for the user's stated request to succeed as given
   ("underspecified_intent").

Respond with JSON: {"failure_mode": "...", "confidence": <0.0-1.0>,
"reasoning": "<1-3 sentences citing specific steps>"}. Reference the
trace's structure (step numbers, tool names, errors), never reproduce long
verbatim content from it.
"""

# V2 (validated on the converted AgentRx corpus): V1's dominant confusions
# were terminal-symptom anchoring — a crash at the end of an already-doomed
# run classified system_failure, a fabricated final answer classified
# invention even when an earlier derailment caused it — and
# plan_adherence_failure absorbing every trace with repetition. V2 defines
# the root cause as the earliest unrecoverable failure and adds boundary
# notes to the three categories that absorbed the confusion.
V2 = """\
An AI agent failed to accomplish its task. You will be shown the recorded
execution trace (chronological steps, possibly truncated where marked) and,
when available, deterministic evidence extracted from it (detected loops,
error spans). Classify the primary cause of failure.

The primary cause is the EARLIEST failure the agent never recovered from —
the point where the task became doomed. Later problems that follow from it
are symptoms, not the cause: a crash or timeout at the end of a run that
had already gone off the rails is a symptom; a made-up final answer
delivered after the agent failed to obtain the data is a symptom of
whatever blocked the data; a loop is a symptom of whatever the agent kept
retrying unsuccessfully. Walk the trace forward and classify the first
unrecovered derailment.

Choose exactly one failure mode:

- "plan_adherence_failure" — the agent deviated from the required or stated
  procedure: skipped required steps, added unnecessary ones, or wandered
  off-plan. Only when the deviation itself is the originating problem — not
  for every trace that merely contains repetition.
- "invention_of_information" — the agent fabricated facts or presented
  ungrounded information as established, and that fabrication is where the
  task first went wrong (not a last-resort guess after an earlier failure).
- "invalid_invocation" — a malformed tool call: wrong arguments, types, or
  schema.
- "tool_output_misinterpretation" — a tool result contained the relevant
  information but the agent read it wrong: miscounted, picked the wrong
  entry, or drew a conclusion the output contradicts.
- "intent_plan_misalignment" — the agent pursued the wrong objective or
  ordered its actions so the goal became unachievable.
- "underspecified_intent" — the task lacked information the agent needed
  and could not obtain.
- "intent_not_supported" — the requested action could not be performed with
  the tools available.
- "guardrails_triggered" — a safety or access policy blocked progress:
  permission refusals, CAPTCHAs, blocked sites, content policies.
- "system_failure" — infrastructure errors (timeouts, unreachable
  endpoints, provider outages, runtime crashes) that struck while the task
  was otherwise on track. Not for crashes that merely ended a run already
  failing for another reason.
- "inconclusive" — the trace shows failure but the cause cannot be
  attributed. A valid answer; prefer it over guessing.

Respond with JSON: {"failure_mode": "...", "confidence": <0.0-1.0>,
"reasoning": "<1-3 sentences citing specific steps>"}. Reference the
trace's structure (step numbers, tool names, errors), never reproduce long
verbatim content from it.
"""

V1 = """\
An AI agent failed to accomplish its task. You will be shown the recorded
execution trace (chronological steps, possibly truncated where marked) and,
when available, deterministic evidence extracted from it (detected loops,
error spans). Classify the primary cause of failure.

Choose exactly one failure mode:

- "plan_adherence_failure" — the agent skipped required steps or added
  unnecessary ones, including loops and repetition that derailed the task.
- "invention_of_information" — the agent fabricated facts or presented
  ungrounded information as established.
- "invalid_invocation" — a malformed tool call: wrong arguments, types, or
  schema.
- "tool_output_misinterpretation" — the agent reasoned incorrectly about
  what a tool result actually said.
- "intent_plan_misalignment" — the agent pursued the wrong objective.
- "underspecified_intent" — the task lacked information the agent needed
  and could not obtain.
- "intent_not_supported" — the requested action could not be performed with
  the tools available.
- "guardrails_triggered" — a safety or access policy blocked progress.
- "system_failure" — infrastructure errors: timeouts, unreachable
  endpoints, provider outages.
- "inconclusive" — the trace shows failure but the cause cannot be
  attributed. A valid answer; prefer it over guessing.

Pick the mode closest to the root cause, not the last symptom: if a
malformed tool call led to a retry loop, the cause is the malformed call.

Respond with JSON: {"failure_mode": "...", "confidence": <0.0-1.0>,
"reasoning": "<1-3 sentences citing specific steps>"}. Reference the
trace's structure (step numbers, tool names, errors), never reproduce long
verbatim content from it.
"""
