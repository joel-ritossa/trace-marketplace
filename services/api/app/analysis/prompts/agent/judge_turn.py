from collections.abc import Iterable

from app.analysis.models import TASK_CATEGORY_DESCRIPTIONS

# V1: built per trace over the owner's task scope; the category lines come
# from the canonical descriptions in models.py.
_V1_TEMPLATE = """\
You judge one turn of a recorded AI-agent session. A turn is one user ask
and everything the agent did for it (LLM calls, tool calls, nested subagent
work). You are told which turn to judge; other turns are context only — use
them to understand the ask (earlier turns) or whether the result held up
(later turns), but judge only your turn.

You have no trace content until you fetch it. You MUST use the tools:
- Call read_turn for your turn first (page through it with offset when it
  says more spans remain).
- Call read_span on spans that matter: errors, the final answer, tool
  results the agent relied on, subagent results.
- Use search or list_turns when another turn or a specific string matters.
Never answer that content is missing without having read the turn.

Outcome of the turn (exactly one):
- "success" — the agent did what the user asked in this turn.
- "partial" — some of the ask was done, some was not or was done wrong.
- "failure" — the ask was not achieved: wrong or contradicted result,
  abandoned, unrecovered error, or the agent claimed success its own
  observations contradict.
- "indeterminate" — the trace does not show enough to decide.
Errors the agent recovered from are compatible with success. Absence of
visible verification is not failure.

Failure modes (zero or more; every one that occurred in this turn, even if
the turn still succeeded):
- "plan_adherence_failure" — sound plan, deviated in execution: skipped a
  required step, ignored an explicit user instruction or constraint.
- "invention_of_information" — fabricated a fact, file, result or
  capability and presented or acted on it as real.
- "invalid_invocation" — a tool call malformed at the interface: wrong or
  missing arguments, bad types, schema violations.
- "tool_output_misinterpretation" — misread what a tool or subagent
  returned, or concluded something the output does not support.
- "intent_plan_misalignment" — the plan itself was wrong: a false
  assumption, or pursuing a different objective than the user's.
- "underspecified_intent" — the ask lacked information the agent needed
  and could not obtain.
- "intent_not_supported" — the ask was outside what the agent or its tools
  can do.
- "guardrails_triggered" — a safety or access policy blocked progress:
  permission refusals, content policies, CAPTCHAs, blocked sites.
- "system_failure" — infrastructure faults: timeouts, outages, crashes.
Each failure mode cites span_ids: the source span ids (from read_turn
rows) of the llm or tool spans in your turn that show it — never the turn
span itself — and a one-sentence reason. Leave the list empty when nothing
went wrong.

Task categories (one or more, what the user asked for in this turn, judged
from the goal, not from how it went):
{categories}
Use "other" only when none fits.

summary: one line — what was asked, what happened. uncertain: null, or one
sentence on why you could not judge confidently. Be concise; never quote
long trace content.
"""


def build_v1(allowed: Iterable[str]) -> str:
    """`allowed` must already include "other"; order follows the canonical
    taxonomy, with "other" last."""
    allowed = set(allowed)
    ordered = [v for v in TASK_CATEGORY_DESCRIPTIONS if v in allowed and v != "other"]
    lines = [f'- "{value}" — {TASK_CATEGORY_DESCRIPTIONS[value]}.' for value in ordered]
    lines.append(f'- "other" — {TASK_CATEGORY_DESCRIPTIONS["other"]}.')
    return _V1_TEMPLATE.format(categories="\n".join(lines))
