"""FROZEN CONTRACT — analyzer result models (B0, 1_analysis.md).

These models are the seam between the analysis stream (B-slices) and the
platform stream (A-slices): analyzers return them, the worker persists them
into `analyzer_results.output` / promotes fields into `trace_analysis`
(2_data-model.md). Field names and types are frozen at B0 close; change is
additive or goes through a spec amendment recorded in the buildlog.
"""

from typing import Any, Literal

from pydantic import BaseModel

Outcome = Literal["success", "failure", "indeterminate"]
# Per-field provenance on trace_analysis columns (2_data-model.md). No result
# model carries it yet — A2's worker stamps it at persistence; part of the
# frozen contract vocabulary, not dead code.
Provenance = Literal["machine", "human_confirmed", "human"]
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

# Family 3 catalog, locked at B3 (buildlog stage-2/B3): the default-on set
# and the only valid `metric_scores` keys — the B3→A4 contract surface.
# Critics yield booleans, the RAGAS-backed pair yields 0–1 floats.
METRICS = (
    "hallucination",
    "helpfulness",
    "harmfulness",
    "coherence",
    "relevancy",
    "faithfulness",
    "goal_accuracy",
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
        "devops_infra": "Deploys, infrastructure-as-code, cloud or system operations",
        "ci_cd": "Build pipelines and release automation",
        "database_admin": "Schema, migration, and query administration",
        "security_engineering": "Vulnerability analysis, hardening, secrets handling",
        "ml_engineering": "Training, evaluating, or deploying ML models",
    },
    "Data": {
        "data_analysis": "Querying, transforming, computing over, or interpreting structured data",
        "data_engineering": "Data pipelines, ETL, ingestion",
        "data_visualization": "Charts or dashboards as the deliverable",
        "reporting_bi": "Recurring business reporting and BI",
        "financial_analysis": "Financial modeling or accounting analysis",
    },
    "Web & research": {
        "web_research": "Finding, gathering, or synthesizing information from the open web",
        "web_automation": "Performing actions or transactions on web applications",
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
    """Family 1 output. All catalog fields nullable — analyzers fail open;
    null means "no opinion", never a guess. Which fields get promoted into
    `trace_analysis` columns is B1's hit-rate-gated call."""

    has_retry_loop: bool | None = None
    loop_kind: LoopKind | None = None
    recovered_from_error: bool | None = None
    truncation_suspected: bool | None = None
    llm_call_count: int | None = None
    tool_call_count: int | None = None
    # Stored for routing auditability; never promoted, never user-facing,
    # never in the judge prompt. False means "no opinion", not "success".
    failure_suspected: bool = False


class JudgeVote(BaseModel):
    """One sampled run of one composed call — the stored audit artifact.
    Values are labels + reasoning snippets, never trace content.

    Self-report + per-call cost fields added in B2 (additive; each vote is
    exactly one LLM call, so the audit artifact carries what it cost)."""

    call: Literal["outcome", "failure_mode", "category"]
    value: str
    reasoning: str | None = None
    # Self-reported confidence; the fold uses it only at N=1 (vote share is
    # meaningless there). Null on malformed votes.
    confidence: float | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class JudgeVerdict(BaseModel):
    """Family 2 output: the three composed calls' labels with per-field
    confidence (vote share), plus the recorded votes."""

    outcome: Outcome | None = None
    outcome_confidence: float | None = None
    failure_mode: str | None = None
    failure_mode_confidence: float | None = None
    task_category: str | None = None
    task_category_confidence: float | None = None
    reasoning: str | None = None
    votes: list[JudgeVote] = []
    rendering_truncated: bool = False


class MetricCall(BaseModel):
    """One LLM call made while computing a metric — the cost audit artifact
    (JudgeVote's metadata shape without vote semantics; added in B3,
    additive)."""

    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class MetricResult(BaseModel):
    """Family 3 output, one per applicable metric. Inapplicable metrics
    produce no result at all — never a garbage score."""

    metric: str
    value: float | bool
    reason: str | None = None
    calls: list[MetricCall] = []


class ListingResult(BaseModel):
    """Listing-copy generator output (additive, post-B0): free-form
    marketplace copy — tags + description — never labels. No closed
    vocabulary, no confidence, no routing; the worker fill-if-empty
    writes it into the owner-editable `traces` columns."""

    description: str | None = None
    tags: list[str] = []
    calls: list[MetricCall] = []


class SummaryResult(BaseModel):
    """Behavior-summary output (additive, post-B0): a gist + step
    walkthrough of what the agent did — descriptive prose, never a label.
    No confidence, no routing, no promoted columns; it lives in its
    `analyzer_results` row and the analysis endpoint reads it from there."""

    gist: str | None = None
    steps: list[str] = []
    calls: list[MetricCall] = []


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
    """Envelope mirroring `analyzer_results` columns 1:1. The runner dumps
    these; A2's worker persists them verbatim. `output` is the result
    model's dump (jsonb-shaped); the registry's result model re-validates."""

    analyzer: str
    analyzer_version: str
    model_id: str | None = None
    confidence: float | None = None
    output: dict[str, Any]
