"""The LLM client seam: error classification, step-limit capture, env
bootstrap — Runner faked, no network."""

import os
from types import SimpleNamespace

import httpx
import openai
import pytest
from agents import Agent, MaxTurnsExceeded, Runner

from app.analysis import llm

AGENT = Agent(name="t", model="gpt-test")
USAGE = SimpleNamespace(input_tokens=7, output_tokens=3, requests=2)


def raising(exc: Exception):
    async def fake_run(*args, **kwargs):
        raise exc

    return fake_run


def api_error(cls: type[openai.APIStatusError], status: int) -> openai.APIStatusError:
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.test"))
    return cls("boom", response=response, body=None)


async def test_result_meta(monkeypatch) -> None:
    result = SimpleNamespace(
        final_output="ok",
        to_input_list=lambda: ["h"],
        context_wrapper=SimpleNamespace(usage=USAGE),
    )

    async def fake_run(*args, **kwargs):
        return result

    monkeypatch.setattr(Runner, "run", fake_run)
    run = await llm.run_agent(AGENT, "hi", 3)
    assert (run.output, run.history) == ("ok", ["h"])
    assert (run.meta.input_tokens, run.meta.output_tokens, run.meta.llm_calls) == (7, 3, 2)


async def test_permanent_provider_error_is_classified(monkeypatch) -> None:
    monkeypatch.setattr(Runner, "run", raising(api_error(openai.AuthenticationError, 401)))
    with pytest.raises(llm.PermanentAnalysisError):
        await llm.run_agent(AGENT, "hi", 3)


async def test_transient_provider_error_propagates(monkeypatch) -> None:
    monkeypatch.setattr(Runner, "run", raising(api_error(openai.RateLimitError, 429)))
    with pytest.raises(openai.RateLimitError):
        await llm.run_agent(AGENT, "hi", 3)


async def test_max_turns_becomes_step_limit_with_history(monkeypatch) -> None:
    exc = MaxTurnsExceeded("too many")
    exc.run_data = SimpleNamespace(
        input="hi",
        new_items=[SimpleNamespace(to_input_item=lambda: {"type": "function_call"})],
        context_wrapper=SimpleNamespace(usage=USAGE),
    )
    monkeypatch.setattr(Runner, "run", raising(exc))
    with pytest.raises(llm.StepLimitExceeded) as info:
        await llm.run_agent(AGENT, "hi", 3)
    assert info.value.history == [{"role": "user", "content": "hi"}, {"type": "function_call"}]
    assert info.value.meta.llm_calls == 2


def test_env_bootstrap_exports_only_openai_keys(monkeypatch, tmp_path) -> None:
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\nDATABASE_URL=postgres://x\n")
    monkeypatch.setattr(llm, "env_files", lambda: (str(tmp_path / ".env"),))
    monkeypatch.setattr(llm, "_env_loaded", False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    try:
        assert llm.llm_configured("gpt-test") is True
        assert "DATABASE_URL" not in os.environ
    finally:
        os.environ.pop("OPENAI_API_KEY", None)


def test_llm_configured_without_key(monkeypatch) -> None:
    monkeypatch.setattr(llm, "_env_loaded", True)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm.llm_configured("gpt-test") is False
