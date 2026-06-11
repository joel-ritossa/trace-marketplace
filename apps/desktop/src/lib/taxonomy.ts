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

// Flat, canonical group order, "other" last (the resolve select needs no
// group structure; the web settings page owns the grouped picker).
export const TASK_CATEGORIES: string[] = [
  "coding",
  "debugging",
  "code_review",
  "testing_qa",
  "devops_infra",
  "ci_cd",
  "database_admin",
  "security_engineering",
  "ml_engineering",
  "data_analysis",
  "data_engineering",
  "data_visualization",
  "reporting_bi",
  "financial_analysis",
  "web_research",
  "web_automation",
  "web_scraping",
  "market_research",
  "competitive_analysis",
  "academic_research",
  "retrieval_qa",
  "summarization",
  "translation",
  "content_generation",
  "technical_writing",
  "copywriting",
  "editing_proofreading",
  "social_media",
  "customer_ops",
  "customer_support",
  "sales_outreach",
  "crm_ops",
  "hr_recruiting",
  "legal_review",
  "compliance",
  "procurement",
  "invoicing_billing",
  "scheduling_planning",
  "email_management",
  "travel_planning",
  "task_management",
  "personal_assistant",
  "monitoring_alerting",
  "incident_response",
  "file_management",
  "document_processing",
  "education_tutoring",
  "design_assets",
  "game_playing",
  "other",
];

export function humanize(value: string): string {
  return value.replaceAll("_", " ");
}
