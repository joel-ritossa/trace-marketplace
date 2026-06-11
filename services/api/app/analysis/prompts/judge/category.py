from collections.abc import Iterable

from app.analysis.models import TASK_CATEGORY_DESCRIPTIONS

# V2: built per trace over the owner's task scope (1_analysis.md Owner task
# scope). The instruction text is versioned here; the category lines come
# from the canonical descriptions in models.py.
_V2_TEMPLATE = """\
Classify what kind of task an AI agent was asked to perform. You will be
shown the user's opening request and the names of the tools the agent used —
judge the task's nature from the goal, not from how well it went.

Choose exactly one category:

{categories}

Pick the single best fit; use "other" only when none of the listed
categories fits.

Respond with JSON: {{"task_category": "...", "confidence": <0.0-1.0>,
"reasoning": "<one sentence>"}}.
"""


def build_v2(allowed: Iterable[str]) -> str:
    """The V2 prompt over a scoped vocabulary. `allowed` must already
    include "other" (the caller owns scope semantics); order follows the
    canonical taxonomy, with "other" last."""
    ordered = [v for v in TASK_CATEGORY_DESCRIPTIONS if v in set(allowed) and v != "other"]
    lines = [f'- "{value}" — {TASK_CATEGORY_DESCRIPTIONS[value]}.' for value in ordered]
    lines.append(f'- "other" — {TASK_CATEGORY_DESCRIPTIONS["other"]}.')
    return _V2_TEMPLATE.format(categories="\n".join(lines))


V1 = """\
Classify what kind of task an AI agent was asked to perform. You will be
shown the user's opening request and the names of the tools the agent used —
judge the task's nature from the goal, not from how well it went.

Choose exactly one category:

- "web_research" — finding, gathering, or synthesizing information from the
  web or external sources.
- "customer_ops" — customer-facing operations: support requests, account
  actions, order handling, communications on a user's behalf.
- "coding" — writing, modifying, debugging, or reviewing code or software
  configuration.
- "data_analysis" — querying, transforming, computing over, or interpreting
  structured data.
- "scheduling_planning" — calendars, bookings, itineraries, task planning,
  or coordination.
- "content_generation" — producing prose, documents, summaries, or other
  creative/communicative artifacts as the deliverable.
- "retrieval_qa" — answering a question from a known corpus or knowledge
  base.
- "other" — none of the above fits.

Respond with JSON: {"task_category": "...", "confidence": <0.0-1.0>,
"reasoning": "<one sentence>"}.
"""
