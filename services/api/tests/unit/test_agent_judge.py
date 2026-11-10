import json

import pytest

from app.analysis import llm
from app.analysis.agent import judge
from app.analysis.config import AnalysisSettings
from tests.unit.test_agent_turns import session

LLM_SPAN = f"{2:016x}"
SUB_TOOL_SPAN = f"{5:016x}"
TURN_SPAN = f"{1:016x}"
META = llm.CallMeta(latency_ms=10, input_tokens=100, output_tokens=20)


def tool(name: str, **args) -> dict:
    return {"tool": name, "args": args}


def answer(span_ids: list[str], **overrides) -> dict:
    body = {
        "outcome": "failure",
        "summary": "asked X, agent fabricated Y",
        "task_categories": ["coding"],
        "failure_modes": [
            {"value": "invention_of_information", "span_ids": span_ids, "reason": "made it up"}
        ],
        "uncertain": None,
        **overrides,
    }
    return {"answer": body}


def install(monkeypatch, script: list[dict]) -> list[dict]:
    """Scripted llm.run_agent: each entry is the model's next turn — a tool
    call (run for real against the agent's tools) or the final answer."""
    seen: list[dict] = []

    async def fake_run(agent, input, max_turns):
        seen.append({"agent": agent, "input": input})
        history = list(input) if isinstance(input, list) else [{"role": "user", "content": input}]
        for _ in range(max_turns):
            step = script.pop(0)
            if "tool" in step:
                fn = next(t for t in agent.tools if t.name == step["tool"])
                result = await fn.on_invoke_tool(None, json.dumps(step["args"]))
                history.append({"tool": step["tool"], "result": result})
                continue
            output = agent.output_type.model_validate(step["answer"])
            return llm.AgentRun(output, history, META)
        raise llm.StepLimitExceeded(history, META)

    monkeypatch.setattr(llm, "run_agent", fake_run)
    return seen


SETTINGS = AnalysisSettings(judge_model="gpt-test", agent_max_steps=3)


async def test_happy_path_with_meta(monkeypatch) -> None:
    install(monkeypatch, [tool("read_turn", turn_index=0), answer([LLM_SPAN, SUB_TOOL_SPAN])])
    verdict, meta = await judge.judge_turn_with_meta(session(), 0, SETTINGS)
    assert verdict.outcome == "failure" and verdict.uncertain is None
    assert verdict.failure_modes[0].span_ids == [LLM_SPAN, SUB_TOOL_SPAN]
    assert (meta.llm_calls, meta.tool_calls, meta.input_tokens) == (1, 1, 100)


async def test_invalid_span_id_is_fed_back_and_fixed(monkeypatch) -> None:
    seen = install(
        monkeypatch, [tool("read_turn", turn_index=0), answer([TURN_SPAN]), answer([LLM_SPAN])]
    )
    verdict = await judge.judge_turn(session(), 0, SETTINGS)
    assert TURN_SPAN in seen[1]["input"][-1]["content"]
    assert verdict.failure_modes[0].span_ids == [LLM_SPAN] and verdict.uncertain is None


async def test_invalid_after_retry_drops_label_and_sets_uncertain(monkeypatch) -> None:
    install(monkeypatch, [tool("read_turn", turn_index=0), answer([TURN_SPAN]), answer(["nope"])])
    verdict = await judge.judge_turn(session(), 0, SETTINGS)
    assert verdict.failure_modes == [] and verdict.uncertain


async def test_answer_without_reading_the_turn_is_a_violation(monkeypatch) -> None:
    seen = install(
        monkeypatch, [answer([LLM_SPAN]), tool("read_turn", turn_index=0), answer([LLM_SPAN])]
    )
    verdict = await judge.judge_turn(session(), 0, SETTINGS)
    assert "read_turn(0)" in seen[1]["input"][-1]["content"]
    assert verdict.uncertain is None


async def test_reading_another_turn_does_not_count(monkeypatch) -> None:
    install(monkeypatch, [tool("read_turn", turn_index=1), answer([LLM_SPAN]), answer([LLM_SPAN])])
    verdict = await judge.judge_turn(session(), 0, SETTINGS)
    assert "never read the turn" in verdict.uncertain


async def test_step_limit_forces_indeterminate(monkeypatch) -> None:
    seen = install(monkeypatch, [tool("list_turns")] * 3 + [answer([LLM_SPAN], outcome="success")])
    verdict = await judge.judge_turn(session(), 0, SETTINGS)
    assert seen[-1]["agent"].model_settings.tool_choice == "none"
    assert verdict.outcome == "indeterminate" and "step limit" in verdict.uncertain


async def test_owner_scope_constrains_categories(monkeypatch) -> None:
    trace = session().model_copy(update={"owner_task_categories": ["debugging"]})
    install(monkeypatch, [tool("read_turn", turn_index=0), answer([LLM_SPAN]), answer([LLM_SPAN])])
    verdict = await judge.judge_turn(trace, 0, SETTINGS)
    assert verdict.task_categories == ["other"] and verdict.uncertain


async def test_roll_up(monkeypatch) -> None:
    session_answer = {
        "goal": "g",
        "outcome": "partial",
        "summary": "s",
        "tags": ["t"],
        "description": "d",
    }
    install(monkeypatch, [{"answer": session_answer}])
    verdict, meta = await judge.roll_up_with_meta(session(), [], SETTINGS)
    assert verdict.outcome == "partial" and meta.tool_calls == 0


async def test_malformed_output_propagates(monkeypatch) -> None:
    async def fake_run(agent, input, max_turns):
        raise llm.MalformedResponse("bad")

    monkeypatch.setattr(llm, "run_agent", fake_run)
    with pytest.raises(llm.MalformedResponse):
        await judge.judge_turn(session(), 0, SETTINGS)
