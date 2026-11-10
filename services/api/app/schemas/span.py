from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.analysis import Outcome
from app.analysis.agent.models import FailureLabel

# Mirrors the spans.kind / spans.status check constraints and the frontend
# types (apps/web/src/lib/api/traces.ts).
SpanKind = Literal["llm", "agent", "tool", "chain", "retriever", "embedding", "other"]
SpanStatus = Literal["ok", "error", "unset"]


class SpanListItem(BaseModel):
    """Tree-building fields only; attributes/events live on the per-span
    endpoint so list payloads stay bounded (3_api.md)."""

    span_id: str
    source_span_id: str
    source_parent_span_id: str | None
    name: str
    kind: SpanKind
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    status: SpanStatus
    status_message: str | None
    error_type: str | None
    provider: str | None
    model: str | None
    tool_name: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class SpanListResponse(BaseModel):
    spans: list[SpanListItem]
    total: int


class AgentVerdict(BaseModel):
    """A linked subagent's own verdict, judged against its brief
    (9_session-analysis.md Subagent verdicts)."""

    outcome: Outcome
    summary: str
    failure_modes: list[FailureLabel]


class AgentSpawn(BaseModel):
    """One subagent: the tool span that spawned it plus totals over its
    subtree (GET /v1/traces/{id}/agents)."""

    span_id: str
    # Nearest ancestor spawn; null when spawned by the main agent.
    parent_span_id: str | None
    turn_index: int | None
    # 0 = spawned by the main agent.
    depth: int
    description: str | None
    type: str | None
    model: str | None
    background: bool | None
    # Has a transcript: a subagent id and spans under the spawn.
    linked: bool
    status: Literal["ok", "error"]
    started_at: datetime
    # Latest end over the spawn span and everything under it.
    ended_at: datetime
    # Everything under the spawn, nested subagents included...
    span_count: int
    llm_calls: int
    tool_calls: int
    error_count: int
    input_tokens: int
    output_tokens: int
    # ...and only its own stream (nested subagents' subtrees excluded).
    own_span_count: int
    # Null when not judged (unlinked, analysis skipped or not run yet).
    verdict: AgentVerdict | None = None


class AgentsResponse(BaseModel):
    agents: list[AgentSpawn]


class SubagentSummary(BaseModel):
    count: int
    # Turns that spawned at least one subagent.
    turns: int
    max_depth: int


class SpanDetailResponse(SpanListItem):
    attributes: dict[str, Any]
    events: list[dict[str, Any]]
