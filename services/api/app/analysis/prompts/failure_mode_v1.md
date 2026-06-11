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
