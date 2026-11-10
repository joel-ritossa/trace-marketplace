"""FROZEN CONTRACT — analyzer result models (B0, 1_analysis.md).

These models are the seam between the analysis stream (B-slices) and the
platform stream (A-slices): analyzers return them, the worker persists them
into `analyzer_results.output` / promotes fields into `trace_analysis`
(2_data-model.md). Field names and types are frozen at B0 close; change is
additive or goes through a spec amendment recorded in the buildlog.
"""

from typing import Any, Literal

from pydantic import BaseModel

Outcome = Literal["success", "partial", "failure", "indeterminate"]
# Who set a turn's labels (9_session-analysis.md): human turns are never
# re-judged or overwritten.
Provenance = Literal["machine", "human"]
LoopKind = Literal["exact_repeat", "cycle", "stagnation"]

# failure_mode / task_category are text with app-level validation, no Literal:
# the taxonomies evolve additively without a contract break (1_analysis.md
# derived-field principles). These sets are the validators.
FAILURE_MODES = frozenset(
    {
        "plan_adherence_failure",
        "invention_of_information",
        "invalid_invocation",
        "tool_output_misinterpretation",
        "intent_plan_misalignment",
        "underspecified_intent",
        "intent_not_supported",
        "guardrails_triggered",
        "system_failure",
        "inconclusive",
    }
)

# Expanded at task-scope (buildlog stage-2/task-scope) from the 8 values
# locked at B2 — a strict superset, so existing labels stay valid. The
# canonical source for values, display groups, and the one-liners the
# category prompt and resolve forms show; web/desktop taxonomy files mirror
# it. Additions are additive text values, no contract break.
TASK_CATEGORY_GROUPS: dict[str, dict[str, str]] = {
    "Software engineering": {
        "coding": "Writing or modifying application code as the deliverable",
        "debugging": "Diagnosing and fixing defects or unexpected behavior",
        "code_review": "Reviewing code changes for correctness and quality",
        "testing_qa": "Writing or running tests; quality assurance",
        "devops_infra": "Cloud resources, hosts, secrets, networking, infrastructure-as-code",
        "ci_cd": "CI checks, merge queues, build and release pipelines",
        "database_admin": "Schema, migration, and query administration",
        "security_engineering": "Vulnerability analysis, hardening, secrets handling",
        "ml_engineering": "Training, evaluating, or deploying ML models",
    },
    "Data": {
        "data_analysis": "Querying, transforming, computing over, or interpreting structured data",
        "data_engineering": "Data pipelines, ETL, ingestion",
        "data_visualization": "Charts or dashboards as the deliverable",
        "reporting_bi": "Recurring business reporting and BI",
        "financial_analysis": "Financial modeling, accounting, or cloud/LLM spend analysis",
    },
    "Web & research": {
        "web_research": "Finding, gathering, or synthesizing information from the open web",
        "web_automation": "Driving a browser UI to act on web apps (not gh/CLI actions)",
        "web_scraping": "Programmatic extraction of data from websites",
        "market_research": "Researching markets, products, or pricing",
        "competitive_analysis": "Monitoring or analyzing competitors",
        "academic_research": "Literature search, papers, citation work",
    },
    "Knowledge & QA": {
        "retrieval_qa": "Answering questions from a known corpus or knowledge base",
        "summarization": "Condensing documents, threads, or transcripts",
        "translation": "Translating between natural languages",
    },
    "Content": {
        "content_generation": "Producing prose or creative artifacts as the deliverable",
        "technical_writing": "Documentation, specs, guides",
        "copywriting": "Marketing or promotional copy",
        "editing_proofreading": "Revising or correcting existing text",
        "social_media": "Posts, threads, community content",
    },
    "Business operations": {
        "customer_ops": (
            "Customer-facing operations: account actions, order handling, acting on a user's behalf"
        ),
        "customer_support": "Support requests, triage, troubleshooting for customers",
        "sales_outreach": "Prospecting, outreach, follow-ups",
        "crm_ops": "CRM record upkeep and workflows",
        "hr_recruiting": "Sourcing, screening, HR workflows",
        "legal_review": "Contract or policy review",
        "compliance": "Regulatory checks and audits",
        "procurement": "Vendor and purchasing workflows",
        "invoicing_billing": "Billing, invoices, payments administration",
    },
    "Personal & coordination": {
        "scheduling_planning": "Calendars, bookings, itineraries, coordination",
        "email_management": "Inbox triage and drafting",
        "travel_planning": "Trip itineraries and travel bookings",
        "task_management": "Todo and project tracker upkeep",
        "personal_assistant": "General life admin and errands",
    },
    "Operations & monitoring": {
        "monitoring_alerting": "Watching systems or metrics; handling alerts",
        "incident_response": "Diagnosing and mitigating live incidents",
        "file_management": "Organizing files, drives, archives",
        "document_processing": "Extracting or structuring data from documents (OCR, forms)",
    },
    "Specialized": {
        "education_tutoring": "Teaching, explaining, grading",
        "design_assets": "Generating or editing images and design assets",
        "game_playing": "Games, puzzles, or simulated environments",
    },
    "Other": {
        "other": "None of the above fits",
    },
}
TASK_CATEGORY_DESCRIPTIONS: dict[str, str] = {
    value: description
    for group in TASK_CATEGORY_GROUPS.values()
    for value, description in group.items()
}
TASK_CATEGORIES = frozenset(TASK_CATEGORY_DESCRIPTIONS)


class SignalsResult(BaseModel):
    """Family 1 output, per turn (stored on `turn_analysis.signals`) and
    combined per session (`trace_analysis` columns). All fields nullable —
    null means "no opinion", never a guess."""

    has_retry_loop: bool | None = None
    loop_kind: LoopKind | None = None
    recovered_from_error: bool | None = None
    truncation_suspected: bool | None = None
    llm_call_count: int | None = None
    tool_call_count: int | None = None


class RenderedMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class RenderedTrace(BaseModel):
    """Renderer output: chronological OpenAI-style message list serving the
    judge and family 3. Deterministic for a fixed (trace, version, config)."""

    messages: list[RenderedMessage]
    rendering_truncated: bool
    renderer_version: str
    step_count: int
    elided_step_count: int

    @property
    def total_chars(self) -> int:
        return sum(len(m.content) for m in self.messages)


class AnalyzerRun(BaseModel):
    """Envelope mirroring `analyzer_results` columns 1:1: one audit row per
    analysis run (model, usage, tool-call counts)."""

    analyzer: str
    analyzer_version: str
    model_id: str | None = None
    output: dict[str, Any]
