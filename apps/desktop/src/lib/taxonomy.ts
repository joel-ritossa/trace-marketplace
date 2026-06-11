// The closed label vocabularies (1_analysis.md), mirrored from
// services/api/app/analysis/models.py and the web's review/taxonomy.ts —
// keep in sync. Descriptions are the spec's one-liners.

import type { Outcome } from "./review";

export const OUTCOMES: { value: Outcome; description: string }[] = [
  { value: "success", description: "The agent accomplished what was asked." },
  { value: "failure", description: "The agent did not accomplish what was asked." },
  { value: "indeterminate", description: "This trace genuinely can’t be judged." },
];

export const FAILURE_MODES: { value: string; description: string }[] = [
  { value: "plan_adherence_failure", description: "Skips steps or adds unnecessary actions (incl. loops/repetition)" },
  { value: "invention_of_information", description: "Fabricates or omits ungrounded facts" },
  { value: "invalid_invocation", description: "Malformed tool call (wrong args/types/schema)" },
  { value: "tool_output_misinterpretation", description: "Incorrect reasoning about tool results" },
  { value: "intent_plan_misalignment", description: "Pursues wrong objective" },
  { value: "underspecified_intent", description: "Missing information to proceed" },
  { value: "intent_not_supported", description: "Action can’t be performed with available tools" },
  { value: "guardrails_triggered", description: "Blocked by safety/access policies" },
  { value: "system_failure", description: "Infra errors (timeouts, unreachable endpoints)" },
  { value: "inconclusive", description: "Failed, cause unattributable" },
];

export const TASK_CATEGORIES: string[] = [
  "web_research",
  "customer_ops",
  "coding",
  "data_analysis",
  "scheduling_planning",
  "content_generation",
  "retrieval_qa",
  "other",
];

export function humanize(value: string): string {
  return value.replaceAll("_", " ");
}
