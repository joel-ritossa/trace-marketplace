"""Agent judge entry points (9_session-analysis.md Agent).

    judge_turn(trace, turn_index, settings) -> TurnVerdict
    judge_turn_with_meta(trace, turn_index, settings) -> tuple[TurnVerdict, AgentMeta]
    judge_subagent_with_meta(trace, turn_index, span_id, settings)
        -> tuple[SubagentVerdict | None, AgentMeta]
    roll_up(trace, verdicts, settings) -> SessionVerdict
    roll_up_with_meta(trace, verdicts, settings) -> tuple[SessionVerdict, AgentMeta]

Pure async over the trace; every model call goes through
`llm.run_agent` (OpenAI Agents SDK). Provider errors propagate as
`llm.PermanentAnalysisError` or transient exceptions; unparseable output
raises `llm.MalformedResponse`. Every contract violation degrades the
verdict and sets `uncertain`; so does running out of steps or context,
which forces a verdict from what the agent read.

A subagent is judged by the same agent scoped to its spawn span. Both
judges take `verdicts` (by spawn span id): the subagents already judged,
which their tools show as one row each.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from agents import Agent, AgentHooks, FunctionTool, ModelSettings
from pydantic import BaseModel, Field

from app.analysis import content, llm
from app.analysis.agent import tools
from app.analysis.agent.models import (
    AGENT_FAILURE_MODES,
    AgentMeta,
    FailureLabel,
    SessionVerdict,
    SubagentVerdict,
    TurnVerdict,
    merge_labels,
)
from app.analysis.agent.turns import TurnView, split, subagents
from app.analysis.config import AnalysisSettings, RendererConfig
from app.analysis.models import TASK_CATEGORIES, Outcome
from app.analysis.prompts.agent import judge_subagent as subagent_prompt
from app.analysis.prompts.agent import judge_turn as judge_prompt
from app.analysis.prompts.agent import roll_up as roll_up_prompt
from app.analysis.rendering import middle_out
from app.analysis.trace_input import TraceInput

AGENT_VERSION = "7"

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
    uncertain: str | None = Field(
        description=(
            "null unless you could not determine this turn's outcome or labels with "
            "confidence and a human should look; then one plain sentence why. Caveats "
            "about the agent's work go in summary or a failure-mode reason."
        )
    )


class _SubagentAnswer(BaseModel):
    outcome: Outcome
    summary: str
    failure_modes: list[_Label]


@dataclass
class _Usage:
    turn_index: int
    # Tool output chars returned in the current round (one model turn).
    round_budget: int
    # The spawn span a subagent's judge must read under; None for a turn.
    under: str | None = None
    read: bool = False
    tool_calls: int = 0
    round_chars: int = 0


class _NewRound(AgentHooks):
    def __init__(self, usage: _Usage) -> None:
        self.usage = usage

    async def on_llm_start(self, context, agent, system_prompt, input_items) -> None:
        self.usage.round_chars = 0


# A round's combined tool output: room for this many full reads of an llm
# span (input and output at the conversation cap) before later results are
# cut, so one round cannot flood the context.
_ROUND_FULL_READS = 4
_ROUND_BUDGET_NOTE = "(output budget reached for this round; request fewer spans per round)"


async def judge_turn(trace: TraceInput, turn_index: int, settings: AnalysisSettings) -> TurnVerdict:
    return (await judge_turn_with_meta(trace, turn_index, settings))[0]


async def roll_up(
    trace: TraceInput, verdicts: list[TurnVerdict], settings: AnalysisSettings
) -> SessionVerdict:
    return (await roll_up_with_meta(trace, verdicts, settings))[0]


async def judge_turn_with_meta(
    trace: TraceInput,
    turn_index: int,
    settings: AnalysisSettings,
    verdicts: Mapping[str, SubagentVerdict] | None = None,
) -> tuple[TurnVerdict, AgentMeta]:
    turns = split(trace)
    turn = _find(turns, turn_index)
    allowed = allowed_categories(trace)
    indices = ", ".join(str(t.index) for t in turns)
    prompt = (
        f"Judge turn {turn_index} ({turn.origin}). "
        f"The session has {len(turns)} turns (indices {indices}). "
        f"Start with {_read_call(turn)}. {_budget(settings)}"
        + _previous_turn(turns, turn, RendererConfig.from_settings(settings))
    )
    answer, read, cut_short, meta = await _judge(
        Agent(
            name="turn_judge",
            instructions=judge_prompt.build_v6(allowed),
            model=settings.judge_model,
            output_type=_Answer,
        ),
        prompt,
        trace,
        turns,
        turn,
        settings,
        verdicts,
        allowed,
    )
    if answer is None:
        answer = _Answer(
            outcome="indeterminate",
            summary="No verdict: the judge could not finish reading this turn.",
            task_categories=["other"],
            failure_modes=[],
            uncertain=None,
        )
    return _verdict(answer, turn, read, allowed, cut_short), meta


async def judge_subagent_with_meta(
    trace: TraceInput,
    turn_index: int,
    span_id: str,
    settings: AnalysisSettings,
    verdicts: Mapping[str, SubagentVerdict] | None = None,
) -> tuple[SubagentVerdict | None, AgentMeta]:
    """Judge one linked subagent against its brief: the turn judge scoped to
    the spawn span `span_id`. No verdict (None) when the judge never read
    the subagent or its run was cut short: a subagent verdict has no
    `uncertain` to say so, and it would hide the spans from the turn judge."""
    turns = split(trace)
    view = next((v for v in subagents(trace, _find(turns, turn_index)) if v.under == span_id), None)
    if view is None:
        raise ValueError(f"turn {turn_index} has no linked subagent {span_id!r}")
    cap = RendererConfig.from_settings(settings).tool_field_cap_chars
    brief, returned = (
        middle_out(text, cap)[0] if text else "(not recorded)"
        for text in (view.ask, content.output_text(view.span))
    )
    page = tools.READ_TURN_PAGE_SPANS
    prompt = (
        f"Judge the subagent spawned by span {span_id} in turn {turn_index}. "
        f"It has {len(view.spans)} spans: {_read_call(view)} shows {page} per page "
        f"(offset 0, {page}, {2 * page}, ...). Request its pages together in your first round. "
        f"Budget: {settings.agent_max_steps} model turns; each round of tool calls is one, and "
        "so is your answer. Every round re-sends all you have read, so use few: put "
        "independent calls in the same round and answer as soon as you can judge."
        f"\n\nBrief (the spawn call's input):\n{brief}"
        f"\n\nWhat the spawn call returned to its parent:\n{returned}"
    )
    answer, read, cut_short, meta = await _judge(
        Agent(
            name="subagent_judge",
            instructions=subagent_prompt.V2,
            model=settings.judge_model,
            output_type=_SubagentAnswer,
        ),
        prompt,
        trace,
        turns,
        view,
        settings,
        verdicts,
        None,
    )
    if answer is None or not read or cut_short:
        return None, meta
    verdict = SubagentVerdict(
        span_id=span_id,
        outcome=answer.outcome,
        summary=answer.summary,
        failure_modes=merge_labels(_labels(answer, view, [])),
    )
    return verdict, meta


async def _judge(
    agent: Agent,
    prompt: str,
    trace: TraceInput,
    turns: list[TurnView],
    scope: TurnView,
    settings: AnalysisSettings,
    verdicts: Mapping[str, SubagentVerdict] | None,
    allowed: frozenset[str] | None,
) -> tuple[Any | None, bool, str | None, AgentMeta]:
    """The judge run shared by turns and subagents: `agent` gets the tools,
    contract violations are fed back once, and a run cut short by the step
    bound or the context window is forced to answer from what it read.
    Returns the answer (None when even the forced one failed), whether the
    scope was read, why the run was cut short, and what it cost."""
    config = RendererConfig.from_settings(settings)
    usage = _Usage(scope.index, _ROUND_FULL_READS * 2 * config.conversation_cap_chars, scope.under)
    agent = agent.clone(
        hooks=_NewRound(usage), tools=_function_tools(trace, turns, config, usage, verdicts)
    )
    steps = settings.agent_max_steps
    metas: list[llm.CallMeta] = []
    cut_short: str | None = None
    try:
        run = await llm.run_agent(agent, prompt, steps)
        metas.append(run.meta)
        answer = run.output
        errors = _check(answer, scope, usage.read, allowed)
        if errors:
            feedback = "Your answer has problems; fix them:\n" + "\n".join(f"- {e}" for e in errors)
            history = run.history + [{"role": "user", "content": feedback}]
            try:
                run = await llm.run_agent(agent, history, steps)
            except llm.MalformedResponse:
                pass  # keep the first answer; the verdict drops what violates
            else:
                metas.append(run.meta)
                answer = run.output
    except llm.RunCutShort as exc:
        metas.append(exc.meta)
        history = exc.history
        if isinstance(exc, llm.ContextLimitExceeded):
            cut_short = "The turn is too large for the judge to read in full"
            history = _drop_old_outputs(history) or history
        else:
            cut_short = f"The judge used all {steps} of its steps before finishing"
        cut_short += "; the verdict is from what it read."
        answer, meta = await _forced_answer(agent, history)
        metas.extend(meta)
    return answer, usage.read, cut_short, _meta(settings, metas, usage.tool_calls)


def _find(turns: list[TurnView], turn_index: int) -> TurnView:
    turn = next((t for t in turns if t.index == turn_index), None)
    if turn is None:
        raise ValueError(f"trace has no turn {turn_index}")
    return turn


def _read_call(scope: TurnView) -> str:
    """The read_turn call that opens the judged scope."""
    under = f", under={scope.under!r}" if scope.under else ""
    return f"read_turn({scope.index}{under})"


def _budget(settings: AnalysisSettings) -> str:
    return (
        f"Budget: {settings.agent_max_steps} model turns; each round of "
        "tool calls is one, and so is your answer. Put independent calls in the same round "
        "(several read_span calls or read_turn pages at once), and answer as soon as you "
        "can judge, but on a large turn use the budget to check the middle too."
    )


async def roll_up_with_meta(
    trace: TraceInput, verdicts: list[TurnVerdict], settings: AnalysisSettings
) -> tuple[SessionVerdict, AgentMeta]:
    turns = split(trace)
    asks = {t.index: t.ask for t in turns}
    origins = {t.index: t.origin for t in turns}
    blocks = []
    for v in sorted(verdicts, key=lambda v: v.turn_index):
        modes = ", ".join(label.value for label in v.failure_modes) or "none"
        blocks.append(
            # 1-based, as users see turns.
            f"Turn {v.turn_index + 1} ({origins.get(v.turn_index, 'human')}) | "
            f"ask: {tools.preview(asks.get(v.turn_index))}\n"
            f"outcome: {v.outcome} | failure modes: {modes}\nsummary: {v.summary}"
        )
    agent = Agent(
        name="session_roll_up",
        instructions=roll_up_prompt.V3,
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
    trace: TraceInput,
    turns: list[TurnView],
    config: RendererConfig,
    usage: _Usage,
    verdicts: Mapping[str, SubagentVerdict] | None,
) -> list[FunctionTool]:
    def make(spec: dict[str, Any]) -> FunctionTool:
        async def invoke(_ctx: Any, arguments: str) -> str:
            usage.tool_calls += 1
            result = tools.run(spec["name"], arguments, trace, turns, config, verdicts)
            if (
                spec["name"] == "read_turn"
                and _reads(arguments, usage)
                and not result.startswith("error:")
            ):
                usage.read = True
            return _within_round_budget(result, usage)

        return FunctionTool(
            name=spec["name"],
            description=spec["description"],
            params_json_schema=spec["parameters"],
            on_invoke_tool=invoke,
            strict_json_schema=False,
        )

    return [make(spec) for spec in tools.SPECS]


async def _forced_answer(agent: Agent, history: list[Any]) -> tuple[Any | None, list[llm.CallMeta]]:
    """One tool-less answer from what the agent has read, dropping older
    tool outputs while the conversation overflows the context window; None
    if even that fails."""
    final = agent.clone(model_settings=ModelSettings(tool_choice="none"))
    nudge = {"role": "user", "content": "Out of budget. Answer now from what you have read."}
    while True:
        try:
            run = await llm.run_agent(final, history + [nudge], 1)
            return run.output, [run.meta]
        except llm.ContextLimitExceeded:
            shorter = _drop_old_outputs(history)
            if shorter is None:
                break
            history = shorter
        except (llm.StepLimitExceeded, llm.MalformedResponse):
            break
    return None, []


_DROPPED_OUTPUT = "(output dropped to fit the context window)"


def _drop_old_outputs(history: list[Any]) -> list[Any] | None:
    """Replace the older half of the remaining tool outputs; None when
    there is nothing left to drop."""
    outputs = [
        i
        for i, item in enumerate(history)
        if isinstance(item, dict)
        and item.get("type") == "function_call_output"
        and item.get("output") != _DROPPED_OUTPUT
    ]
    if not outputs:
        return None
    drop = set(outputs[: (len(outputs) + 1) // 2])
    return [
        {**item, "output": _DROPPED_OUTPUT} if i in drop else item for i, item in enumerate(history)
    ]


def _previous_turn(turns: list[TurnView], turn: TurnView, config: RendererConfig) -> str:
    """The turn before, for free: what it asked and how the agent answered."""
    earlier = [t for t in turns if t.index < turn.index]
    if not earlier:
        return ""
    prev = earlier[-1]
    ask = middle_out(prev.ask, config.conversation_cap_chars)[0] if prev.ask else "(not recorded)"
    final = tools.final_message(prev, config) or "(none)"
    return (
        f"\n\nPrevious turn {prev.index} ({prev.origin}):\nask: {ask}\n"
        f"agent's final message: {final}"
    )


def _check(answer: Any, turn: TurnView, read: bool, allowed: frozenset[str] | None) -> list[str]:
    """Contract violations, phrased as feedback for the model. `turn` is the
    judged scope; `allowed` is None for a subagent (no task categories)."""
    errors = []
    if not read:
        errors.append(f"you never read it: call {_read_call(turn)} before answering")
    if allowed is not None:
        if not answer.task_categories:
            errors.append("give at least one task category")
        for category in answer.task_categories:
            if category not in allowed:
                errors.append(f"task category {category!r} is not in the allowed list")
    citable = _citable(turn)
    for label in answer.failure_modes:
        if label.value not in AGENT_FAILURE_MODES:
            errors.append(f"failure mode {label.value!r} is not in the allowed list")
        bad = [i for i in label.span_ids if i not in citable]
        if bad or not label.span_ids:
            cited = f"cites {bad}, which are not" if bad else "cites no span_ids; it needs"
            errors.append(
                f"failure mode {label.value!r} {cited} llm or tool spans of {_name(turn)}. "
                f"{_citation_hint(turn)}"
            )
    return errors


def _name(scope: TurnView) -> str:
    return f"the subagent under {scope.under}" if scope.under else f"turn {scope.index}"


def _citation_hint(turn: TurnView) -> str:
    """Which ids are acceptable, with a few real candidates."""
    spans = [s for s in turn.spans if s.kind in _CITABLE_KINDS]
    if not spans:
        return f"There are no llm or tool spans in {_name(turn)}: remove this failure mode."
    last_llm = [s for s in spans if s.kind == "llm"][-1:]
    picks = list({s.source_span_id: s for s in last_llm + spans[-2:]}.values())
    examples = ", ".join(
        f"{s.source_span_id} ({s.kind} {tools.preview(s.tool_name or s.name)[:40]})" for s in picks
    )
    outside = "the spawn span or spans outside it" if turn.under else "another turn's spans"
    return (
        f"Cite ids of llm or tool rows from {_read_call(turn)} (nested subagent rows "
        f"count; never the turn span or {outside}). For an omission, cite the llm "
        "span where the agent gave its final answer or declared done, or its last step. "
        f"Valid ids at the end of {_name(turn)}: {examples}. "
        "Remove the label if nothing shows it."
    )


def _verdict(
    answer: _Answer, turn: TurnView, read: bool, allowed: frozenset[str], cut_short: str | None
) -> TurnVerdict:
    """Build the verdict, dropping whatever still violates the contract;
    each drop adds a plain sentence to `uncertain`."""
    notes = [cut_short] if cut_short else []
    if not read:
        notes.append("The judge answered without reading this turn.")
    labels = _labels(answer, turn, notes)
    categories = [c for c in dict.fromkeys(answer.task_categories) if c in allowed]
    if not categories:
        notes.append("The judge gave no allowed task category; it is set to 'other'.")
    uncertain = " ".join(([answer.uncertain] if answer.uncertain else []) + notes) or None
    return TurnVerdict(
        turn_index=turn.index,
        outcome=answer.outcome,
        summary=answer.summary,
        task_categories=categories or ["other"],
        failure_modes=labels,
        uncertain=uncertain,
    )


def _labels(answer: Any, turn: TurnView, notes: list[str]) -> list[FailureLabel]:
    """The answer's failure modes that hold up: ids outside the judged scope
    are dropped, and so is a label left with none or with an unknown value
    (each drop noted in plain words)."""
    citable = _citable(turn)
    labels = []
    for label in answer.failure_modes:
        ids = [i for i in label.span_ids if i in citable]
        if label.value not in AGENT_FAILURE_MODES:
            notes.append(f"The judge used an unknown failure mode '{label.value}'; it was dropped.")
        elif not ids:
            notes.append(
                f"The judge could not point to the spans that show '{label.value}'; "
                "that label was dropped."
            )
        else:
            labels.append(FailureLabel(value=label.value, span_ids=ids, reason=label.reason))
    return labels


def _citable(turn: TurnView) -> set[str]:
    return {s.source_span_id for s in turn.spans if s.kind in _CITABLE_KINDS}


def _within_round_budget(result: str, usage: _Usage) -> str:
    left = usage.round_budget - usage.round_chars
    usage.round_chars += len(result)
    if len(result) <= left:
        return result
    return (result[: max(left, 0)] + "\n" if left > 0 else "") + _ROUND_BUDGET_NOTE


def _reads(arguments: str, usage: _Usage) -> bool:
    """Whether a read_turn call opens what is being judged: the turn, or
    for a subagent's judge the spawn span."""
    try:
        args = json.loads(arguments or "{}")
        return int(args.get("turn_index")) == usage.turn_index and (
            usage.under is None or args.get("under") == usage.under
        )
    except (ValueError, TypeError, AttributeError):
        return False


def _meta(settings: AnalysisSettings, metas: list[llm.CallMeta], tool_calls: int) -> AgentMeta:
    folded = llm.fold_meta(metas) if metas else llm.CallMeta(latency_ms=0, llm_calls=0)
    return AgentMeta(model=settings.judge_model, tool_calls=tool_calls, **folded.model_dump())
