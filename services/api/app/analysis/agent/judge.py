"""Agent judge entry points (9_session-analysis.md Agent).

    judge_turn(trace, turn_index, settings) -> TurnVerdict
    judge_turn_with_meta(trace, turn_index, settings) -> tuple[TurnVerdict, AgentMeta]
    roll_up(trace, verdicts, settings) -> SessionVerdict
    roll_up_with_meta(trace, verdicts, settings) -> tuple[SessionVerdict, AgentMeta]

Pure async over the trace; every model call goes through
`llm.run_agent` (OpenAI Agents SDK). Provider errors propagate as
`llm.PermanentAnalysisError` or transient exceptions; unparseable output
raises `llm.MalformedResponse`. Every contract violation degrades the
verdict and sets `uncertain`.
"""

import json
from dataclasses import dataclass
from typing import Any

from agents import Agent, FunctionTool, ModelSettings
from pydantic import BaseModel

from app.analysis import llm
from app.analysis.agent import tools
from app.analysis.agent.models import (
    AGENT_FAILURE_MODES,
    AgentMeta,
    FailureLabel,
    SessionVerdict,
    TurnVerdict,
)
from app.analysis.agent.turns import TurnView, split
from app.analysis.config import AnalysisSettings, RendererConfig
from app.analysis.models import TASK_CATEGORIES, Outcome
from app.analysis.prompts.agent import judge_turn as judge_prompt
from app.analysis.prompts.agent import roll_up as roll_up_prompt
from app.analysis.trace_input import TraceInput

AGENT_VERSION = "2"

_CITABLE_KINDS = ("llm", "tool")


class _Label(BaseModel):
    value: str
    span_ids: list[str]
    reason: str


class _Answer(BaseModel):
    """Looser than TurnVerdict: violations come back as feedback, not as
    schema errors."""

    outcome: Outcome
    summary: str
    task_categories: list[str]
    failure_modes: list[_Label]
    uncertain: str | None


@dataclass
class _Usage:
    turn_index: int
    read: bool = False
    tool_calls: int = 0


async def judge_turn(trace: TraceInput, turn_index: int, settings: AnalysisSettings) -> TurnVerdict:
    return (await judge_turn_with_meta(trace, turn_index, settings))[0]


async def roll_up(
    trace: TraceInput, verdicts: list[TurnVerdict], settings: AnalysisSettings
) -> SessionVerdict:
    return (await roll_up_with_meta(trace, verdicts, settings))[0]


async def judge_turn_with_meta(
    trace: TraceInput, turn_index: int, settings: AnalysisSettings
) -> tuple[TurnVerdict, AgentMeta]:
    turns = split(trace)
    turn = next((t for t in turns if t.index == turn_index), None)
    if turn is None:
        raise ValueError(f"trace has no turn {turn_index}")
    allowed = allowed_categories(trace)
    usage = _Usage(turn_index)
    agent = Agent(
        name="turn_judge",
        instructions=judge_prompt.build_v1(allowed),
        model=settings.judge_model,
        tools=_function_tools(trace, turns, RendererConfig.from_settings(settings), usage),
        output_type=_Answer,
    )
    steps = settings.agent_max_steps
    indices = ", ".join(str(t.index) for t in turns)
    prompt = (
        f"Judge turn {turn_index}. The session has {len(turns)} turns (indices {indices}). "
        f"Start with read_turn({turn_index}). You have at most {steps} model turns in total "
        "(each round of tool calls is one, and so is your answer): batch independent "
        "calls into one round and answer before the budget runs out."
    )
    metas: list[llm.CallMeta] = []
    notes: list[str] = []
    forced = False
    try:
        run = await llm.run_agent(agent, prompt, steps)
        metas.append(run.meta)
        answer = run.output
        errors = _check(answer, turn, usage.read, allowed)
        if errors:
            feedback = "Your answer has problems; fix them:\n" + "\n".join(f"- {e}" for e in errors)
            history = run.history + [{"role": "user", "content": feedback}]
            run = await llm.run_agent(agent, history, steps)
            metas.append(run.meta)
            answer = run.output
            errors = _check(answer, turn, usage.read, allowed)
    except llm.StepLimitExceeded as exc:
        metas.append(exc.meta)
        forced = True
        notes.append(f"step limit reached ({steps} model turns)")
        answer, meta = await _forced_answer(agent, exc.history)
        metas.extend(meta)
        errors = _check(answer, turn, usage.read, allowed)
    if errors:
        notes.append("unresolved after retry: " + "; ".join(errors))
    verdict = _verdict(answer, turn, allowed, forced, notes)
    return verdict, _meta(settings, metas, usage.tool_calls)


async def roll_up_with_meta(
    trace: TraceInput, verdicts: list[TurnVerdict], settings: AnalysisSettings
) -> tuple[SessionVerdict, AgentMeta]:
    asks = {t.index: t.ask for t in split(trace)}
    blocks = []
    for v in sorted(verdicts, key=lambda v: v.turn_index):
        modes = ", ".join(label.value for label in v.failure_modes) or "none"
        blocks.append(
            f"turn {v.turn_index} | ask: {tools.preview(asks.get(v.turn_index))}\n"
            f"outcome: {v.outcome} | failure modes: {modes}\nsummary: {v.summary}"
        )
    agent = Agent(
        name="session_roll_up",
        instructions=roll_up_prompt.V1,
        model=settings.judge_model,
        output_type=SessionVerdict,
    )
    run = await llm.run_agent(agent, "\n\n".join(blocks), 1)
    return run.output, _meta(settings, [run.meta], 0)


def allowed_categories(trace: TraceInput) -> frozenset[str]:
    """Owner task scope + "other"; unscoped means the full taxonomy."""
    scope = TASK_CATEGORIES & frozenset(trace.owner_task_categories or ())
    return scope | {"other"} if scope else TASK_CATEGORIES


def _function_tools(
    trace: TraceInput, turns: list[TurnView], config: RendererConfig, usage: _Usage
) -> list[FunctionTool]:
    def make(spec: dict[str, Any]) -> FunctionTool:
        async def invoke(_ctx: Any, arguments: str) -> str:
            usage.tool_calls += 1
            if spec["name"] == "read_turn" and _turn_arg(arguments) == usage.turn_index:
                usage.read = True
            return tools.run(spec["name"], arguments, trace, turns, config)

        return FunctionTool(
            name=spec["name"],
            description=spec["description"],
            params_json_schema=spec["parameters"],
            on_invoke_tool=invoke,
            strict_json_schema=False,
        )

    return [make(spec) for spec in tools.SPECS]


async def _forced_answer(agent: Agent, history: list[Any]) -> tuple[_Answer, list[llm.CallMeta]]:
    """One tool-less answer from what the agent has read; a plain
    placeholder if even that fails."""
    final = agent.clone(model_settings=ModelSettings(tool_choice="none"))
    nudge = {"role": "user", "content": "Step limit reached. Answer now from what you have read."}
    try:
        run = await llm.run_agent(final, history + [nudge], 1)
    except (llm.StepLimitExceeded, llm.MalformedResponse):
        placeholder = _Answer(
            outcome="indeterminate",
            summary="No verdict: the agent hit its step limit.",
            task_categories=["other"],
            failure_modes=[],
            uncertain=None,
        )
        return placeholder, []
    return run.output, [run.meta]


def _check(answer: _Answer, turn: TurnView, read: bool, allowed: frozenset[str]) -> list[str]:
    errors = []
    if not read:
        errors.append(f"you never read the turn: call read_turn({turn.index}) before answering")
    if not answer.task_categories:
        errors.append("give at least one task category")
    for category in answer.task_categories:
        if category not in allowed:
            errors.append(f"task category {category!r} is not in the allowed list")
    citable = _citable(turn)
    for label in answer.failure_modes:
        if label.value not in AGENT_FAILURE_MODES:
            errors.append(f"failure mode {label.value!r} is not in the allowed list")
        if not label.span_ids:
            errors.append(f"failure mode {label.value!r} cites no span_ids")
        bad = [i for i in label.span_ids if i not in citable]
        if bad:
            errors.append(
                f"failure mode {label.value!r} cites {bad}, which are not llm/tool spans "
                f"of turn {turn.index}"
            )
    return errors


def _verdict(
    answer: _Answer, turn: TurnView, allowed: frozenset[str], forced: bool, notes: list[str]
) -> TurnVerdict:
    """Build the verdict, dropping whatever still violates the contract."""
    citable = _citable(turn)
    labels = []
    for label in answer.failure_modes:
        ids = [i for i in label.span_ids if i in citable]
        if label.value in AGENT_FAILURE_MODES and ids:
            labels.append(FailureLabel(value=label.value, span_ids=ids, reason=label.reason))
    categories = [c for c in dict.fromkeys(answer.task_categories) if c in allowed] or ["other"]
    uncertain = "; ".join(([answer.uncertain] if answer.uncertain else []) + notes) or None
    return TurnVerdict(
        turn_index=turn.index,
        outcome="indeterminate" if forced else answer.outcome,
        summary=answer.summary,
        task_categories=categories,
        failure_modes=labels,
        uncertain=uncertain,
    )


def _citable(turn: TurnView) -> set[str]:
    return {s.source_span_id for s in turn.spans if s.kind in _CITABLE_KINDS}


def _turn_arg(arguments: str) -> int | None:
    try:
        return int(json.loads(arguments or "{}").get("turn_index"))
    except (ValueError, TypeError, AttributeError):
        return None


def _meta(settings: AnalysisSettings, metas: list[llm.CallMeta], tool_calls: int) -> AgentMeta:
    folded = llm.fold_meta(metas) if metas else llm.CallMeta(latency_ms=0, llm_calls=0)
    return AgentMeta(model=settings.judge_model, tool_calls=tool_calls, **folded.model_dump())
