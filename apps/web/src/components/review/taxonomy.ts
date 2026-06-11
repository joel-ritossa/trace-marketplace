// The closed label vocabularies (1_analysis.md), mirrored from
// services/api/app/analysis/models.py — keep in sync. Descriptions are the
// spec's one-liners, shown in the resolve form.

import type { Outcome } from "@/lib/api/traces";

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

// Display groups mirror models.py TASK_CATEGORY_GROUPS (1_analysis.md
// Taxonomies). "other" is the judge's permanent escape hatch — listed for
// filters/resolve, never offered in the task-scope picker.
export const TASK_CATEGORY_GROUPS: { label: string; values: string[] }[] = [
  {
    label: "Software engineering",
    values: [
      "coding",
      "debugging",
      "code_review",
      "testing_qa",
      "devops_infra",
      "ci_cd",
      "database_admin",
      "security_engineering",
      "ml_engineering",
    ],
  },
  {
    label: "Data",
    values: [
      "data_analysis",
      "data_engineering",
      "data_visualization",
      "reporting_bi",
      "financial_analysis",
    ],
  },
  {
    label: "Web & research",
    values: [
      "web_research",
      "web_automation",
      "web_scraping",
      "market_research",
      "competitive_analysis",
      "academic_research",
    ],
  },
  { label: "Knowledge & QA", values: ["retrieval_qa", "summarization", "translation"] },
  {
    label: "Content",
    values: [
      "content_generation",
      "technical_writing",
      "copywriting",
      "editing_proofreading",
      "social_media",
    ],
  },
  {
    label: "Business operations",
    values: [
      "customer_ops",
      "customer_support",
      "sales_outreach",
      "crm_ops",
      "hr_recruiting",
      "legal_review",
      "compliance",
      "procurement",
      "invoicing_billing",
    ],
  },
  {
    label: "Personal & coordination",
    values: [
      "scheduling_planning",
      "email_management",
      "travel_planning",
      "task_management",
      "personal_assistant",
    ],
  },
  {
    label: "Operations & monitoring",
    values: ["monitoring_alerting", "incident_response", "file_management", "document_processing"],
  },
  { label: "Specialized", values: ["education_tutoring", "design_assets", "game_playing"] },
];

export const TASK_CATEGORIES: string[] = [
  ...TASK_CATEGORY_GROUPS.flatMap((group) => group.values),
  "other",
];

export function humanize(value: string): string {
  return value.replaceAll("_", " ");
}
