import json

import pytest

from app.analysis import llm
from app.analysis.agent import judge
from app.analysis.config import AnalysisSettings
from tests.unit.test_agent_turns import delegating, session

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


async def test_invalid_span_id_is_fed_back_with_candidates(monkeypatch) -> None:
    seen = install(
        monkeypatch, [tool("read_turn", turn_index=0), answer([TURN_SPAN]), answer([LLM_SPAN])]
    )
    verdict = await judge.judge_turn(session(), 0, SETTINGS)
    feedback = seen[1]["input"][-1]["content"]
    last_llm = f"{4:016x}"
    assert TURN_SPAN in feedback and "omission" in feedback and f"{last_llm} (llm" in feedback
    assert verdict.failure_modes[0].span_ids == [LLM_SPAN] and verdict.uncertain is None


async def test_invalid_after_retry_drops_label_in_plain_words(monkeypatch) -> None:
    install(monkeypatch, [tool("read_turn", turn_index=0), answer([TURN_SPAN]), answer(["nope"])])
    verdict = await judge.judge_turn(session(), 0, SETTINGS)
    assert verdict.failure_modes == []
    assert verdict.uncertain == (
        "The judge could not point to the spans that show 'invention_of_information'; "
        "that label was dropped."
    )


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
    assert "without reading" in verdict.uncertain


async def test_step_limit_forces_indeterminate(monkeypatch) -> None:
    seen = install(monkeypatch, [tool("list_turns")] * 3 + [answer([LLM_SPAN], outcome="success")])
    verdict = await judge.judge_turn(session(), 0, SETTINGS)
    assert seen[-1]["agent"].model_settings.tool_choice == "none"
    assert verdict.outcome == "success" and "all 3 of its steps" in verdict.uncertain


async def test_context_overflow_degrades_like_the_step_limit(monkeypatch) -> None:
    outputs = [{"type": "function_call_output", "output": f"page {i}"} for i in range(4)]
    seen: list = []

    async def fake_run(agent, input, max_turns):
        seen.append(input)
        if len(seen) < 3:  # the run, then the first forced answer, overflow
            raise llm.ContextLimitExceeded([{"role": "user", "content": "go"}, *outputs], META)
        return llm.AgentRun(judge._Answer(**answer([LLM_SPAN])["answer"]), [], META)

    monkeypatch.setattr(llm, "run_agent", fake_run)
    verdict = await judge.judge_turn(session(), 0, SETTINGS)
    kept = [[i["output"] for i in call if i.get("type")] for call in seen[1:]]
    assert kept[0][2:] == ["page 2", "page 3"] and kept[1][3:] == ["page 3"]
    assert verdict.outcome == "failure" and "too large" in verdict.uncertain


async def test_opening_message_carries_the_previous_turn(monkeypatch) -> None:
    seen = install(monkeypatch, [tool("read_turn", turn_index=1), answer([], failure_modes=[])])
    await judge.judge_turn(session(), 1, SETTINGS)
    assert "Previous turn 0 (human):\nask: first ask" in seen[0]["input"]


async def test_read_past_the_end_does_not_count(monkeypatch) -> None:
    install(monkeypatch, [tool("read_turn", turn_index=0, offset=99), answer([LLM_SPAN])] * 2)
    verdict = await judge.judge_turn(session(), 0, SETTINGS)
    assert "without reading" in verdict.uncertain


async def test_malformed_retry_keeps_the_first_answer(monkeypatch) -> None:
    script = [tool("read_turn", turn_index=0), answer([TURN_SPAN, LLM_SPAN])]

    install(monkeypatch, script)
    scripted = llm.run_agent

    async def fake_run(agent, input, max_turns):
        if not script:
            raise llm.MalformedResponse("bad")
        return await scripted(agent, input, max_turns)

    monkeypatch.setattr(llm, "run_agent", fake_run)
    verdict = await judge.judge_turn(session(), 0, SETTINGS)
    assert verdict.failure_modes[0].span_ids == [LLM_SPAN] and verdict.uncertain is None


def test_round_budget_cuts_later_results() -> None:
    usage = judge._Usage(0, round_budget=10)
    assert judge._within_round_budget("x" * 8, usage) == "x" * 8
    assert judge._within_round_budget("y" * 8, usage) == "yy\n" + judge._ROUND_BUDGET_NOTE
    assert judge._within_round_budget("z", usage) == judge._ROUND_BUDGET_NOTE


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


async def test_subagent_judge_reads_and_cites_only_under_its_spawn_span(monkeypatch) -> None:
    outer, own_llm, nested_llm, main_llm = (f"{i:016x}" for i in (3, 4, 6, 2))

    def verdict(span_ids: list[str]) -> dict:
        body = answer(span_ids)["answer"]
        return {"answer": {k: body[k] for k in ("outcome", "summary", "failure_modes")}}

    # Reading the whole turn is not reading the subagent; the main agent's
    # span and the spawn span are outside it.
    seen = install(
        monkeypatch,
        [
            tool("read_turn", turn_index=0),
            verdict([main_llm, outer]),
            tool("read_turn", turn_index=0, under=outer),
            verdict([main_llm, own_llm, nested_llm]),
        ],
    )
    result, meta = await judge.judge_subagent_with_meta(delegating(), 0, outer, SETTINGS)
    feedback = seen[1]["input"][-1]["content"]
    assert f"read_turn(0, under='{outer}')" in feedback and "the subagent under" in feedback
    assert result.span_id == outer and result.failure_modes[0].span_ids == [own_llm, nested_llm]
    assert meta.llm_calls == 2
    assert "Brief (the spawn call's input)" in seen[0]["input"]


async def test_subagent_cut_short_or_unread_gets_no_verdict(monkeypatch) -> None:
    outer = f"{3:016x}"
    body = {"answer": {"outcome": "success", "summary": "s", "failure_modes": []}}
    install(monkeypatch, [tool("list_turns")] * 3 + [body])  # step limit, forced answer
    assert (await judge.judge_subagent_with_meta(delegating(), 0, outer, SETTINGS))[0] is None
    install(monkeypatch, [body, body])  # never read, even after the feedback
    assert (await judge.judge_subagent_with_meta(delegating(), 0, outer, SETTINGS))[0] is None


def test_turn_prompt_explains_subagent_verdict_rows() -> None:
    from app.analysis.prompts.agent import judge_turn

    assert "is a lead, not a" in judge_turn.build_v6(["other"])
