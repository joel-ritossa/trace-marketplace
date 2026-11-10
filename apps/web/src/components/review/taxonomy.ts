// The closed label vocabularies (9_session-analysis.md), mirrored from
// services/api/app/analysis/models.py and agent/models.py — keep in sync
// (they are plain strings in the OpenAPI schema). Descriptions are the
// spec's one-liners, shown in the relabel form.

import type { Outcome } from "@/lib/api/traces";

export const OUTCOMES: { value: Outcome; description: string }[] = [
  { value: "success", description: "The agent accomplished what was asked." },
  { value: "partial", description: "The agent accomplished some of what was asked." },
  { value: "failure", description: "The agent did not accomplish what was asked." },
  { value: "indeterminate", description: "This genuinely can’t be judged." },
];

// The agent's failure modes: models.py FAILURE_MODES minus "inconclusive"
// (agent/models.py AGENT_FAILURE_MODES) — an empty set says "none identified".
export const FAILURE_MODES: { value: string; description: string }[] = [
  { value: "plan_adherence_failure", description: "Skips steps or adds unnecessary actions (incl. loops/repetition)" },
  { value: "invention_of_information", description: "Fabricates or omits ungrounded facts" },
  {
    value: "invalid_invocation",
    description:
      "A malformed command or tool call (wrong flags or arguments, schema errors) that the agent did not correct",
  },
  { value: "tool_output_misinterpretation", description: "Incorrect reasoning about tool results" },
  { value: "intent_plan_misalignment", description: "Pursues wrong objective" },
  { value: "underspecified_intent", description: "Missing information to proceed" },
  { value: "intent_not_supported", description: "The environment or tools cannot do what was asked" },
  {
    value: "guardrails_triggered",
    description:
      "A safety or permission policy blocked the agent’s action (not an external check failing)",
  },
  { value: "system_failure", description: "Infrastructure errors that affected the result" },
];

// Display groups mirror models.py TASK_CATEGORY_GROUPS (1_analysis.md
// Taxonomies). "other" is the judge's permanent escape hatch — listed for
// filters/relabel, never offered in the task-scope picker.
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

// Groups as the filter and relabel pickers show them: the scope groups plus
// the escape hatch.
export const TASK_CATEGORY_PICKER_GROUPS: { label: string; values: string[] }[] = [
  ...TASK_CATEGORY_GROUPS,
  { label: "Other", values: ["other"] },
];

// One-liners per task category (models.py TASK_CATEGORY_GROUPS), shown as
// chip tooltips and in the relabel form.
export const TASK_CATEGORY_DESCRIPTIONS: Record<string, string> = {
  coding: "Writing or modifying application code as the deliverable",
  debugging: "Diagnosing and fixing defects or unexpected behavior",
  code_review: "Reviewing code changes for correctness and quality",
  testing_qa: "Writing or running tests; quality assurance",
  devops_infra: "Cloud resources, hosts, secrets, networking, infrastructure-as-code",
  ci_cd: "Pull requests, merges, CI checks, build and release pipelines",
  database_admin: "Schema, migration, and query administration",
  security_engineering: "Vulnerability analysis, hardening, secrets handling",
  ml_engineering: "Training, evaluating, or deploying ML models",
  data_analysis: "Querying, transforming, computing over, or interpreting structured data",
  data_engineering: "Data pipelines, ETL, ingestion",
  data_visualization: "Charts or dashboards as the deliverable",
  reporting_bi: "Recurring business reporting and BI",
  financial_analysis: "Financial modeling, accounting, or cloud/LLM spend analysis",
  web_research: "Finding, gathering, or synthesizing information from the open web",
  web_automation: "Driving a browser UI to act on web apps (not gh/CLI actions)",
  web_scraping: "Programmatic extraction of data from websites",
  market_research: "Researching markets, products, or pricing",
  competitive_analysis: "Monitoring or analyzing competitors",
  academic_research: "Literature search, papers, citation work",
  retrieval_qa: "Answering questions from a known corpus or knowledge base",
  summarization: "Condensing documents, threads, or transcripts",
  translation: "Translating between natural languages",
  content_generation: "Producing prose or creative artifacts as the deliverable",
  technical_writing: "Documentation, specs, guides",
  copywriting: "Marketing or promotional copy",
  editing_proofreading: "Revising or correcting existing text",
  social_media: "Posts, threads, community content",
  customer_ops:
    "Customer-facing operations: account actions, order handling, acting on a user’s behalf",
  customer_support: "Support requests, triage, troubleshooting for customers",
  sales_outreach: "Prospecting, outreach, follow-ups",
  crm_ops: "CRM record upkeep and workflows",
  hr_recruiting: "Sourcing, screening, HR workflows",
  legal_review: "Contract or policy review",
  compliance: "Regulatory checks and audits",
  procurement: "Vendor and purchasing workflows",
  invoicing_billing: "Billing, invoices, payments administration",
  scheduling_planning: "Calendars, bookings, itineraries, coordination",
  email_management: "Inbox triage and drafting",
  travel_planning: "Trip itineraries and travel bookings",
  task_management: "Todo and project tracker upkeep",
  personal_assistant: "General life admin and errands",
  monitoring_alerting: "Watching systems or metrics; handling alerts",
  incident_response: "Diagnosing and mitigating live incidents",
  file_management: "Organizing files, drives, archives",
  document_processing: "Extracting or structuring data from documents (OCR, forms)",
  education_tutoring: "Teaching, explaining, grading",
  design_assets: "Generating or editing images and design assets",
  game_playing: "Games, puzzles, or simulated environments",
  other: "None of the above fits",
};

const FAILURE_MODE_DESCRIPTIONS: Record<string, string> = Object.fromEntries(
  FAILURE_MODES.map((m) => [m.value, m.description]),
);

/** The one-liner for a label value, for tooltips. */
export function describe(value: string): string | undefined {
  return TASK_CATEGORY_DESCRIPTIONS[value] ?? FAILURE_MODE_DESCRIPTIONS[value];
}

// Display names that sentence-casing the value would get wrong.
const LABELS: Record<string, string> = {
  ci_cd: "CI/CD",
  testing_qa: "Testing & QA",
  ml_engineering: "ML engineering",
  crm_ops: "CRM ops",
  reporting_bi: "Reporting & BI",
  devops_infra: "DevOps & infra",
  retrieval_qa: "Retrieval QA",
  hr_recruiting: "HR & recruiting",
  editing_proofreading: "Editing & proofreading",
  scheduling_planning: "Scheduling & planning",
  monitoring_alerting: "Monitoring & alerting",
  invoicing_billing: "Invoicing & billing",
  education_tutoring: "Education & tutoring",
};

/** The one display name for every taxonomy value (outcomes, categories,
 *  failure modes) — chips, filters, settings, relabel. Sentence case. */
export function humanize(value: string): string {
  const label = LABELS[value] ?? value.replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}
