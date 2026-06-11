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
