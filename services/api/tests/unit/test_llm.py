"""The LLM client seam: structured-output parsing, the one parse-retry,
permanent-vs-transient error classification, call metadata — litellm faked,
no network."""

import json
import os
from types import SimpleNamespace

import litellm
import pytest
from pydantic import BaseModel

from app.analysis import llm


class Vote(BaseModel):
    value: str
    confidence: float


def response(content: str, prompt_tokens: int = 7, completion_tokens: int = 3):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


GOOD = json.dumps({"value": "success", "confidence": 0.9})
MESSAGES = [{"role": "user", "content": "judge this"}]


def install(monkeypatch, results: list) -> list:
    """Queue acompletion results (exceptions raise); returns the call log."""
    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        item = results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    return calls


async def test_parses_structured_output_with_meta(monkeypatch) -> None:
    install(monkeypatch, [response(GOOD)])
    monkeypatch.setattr(litellm, "completion_cost", lambda r: 0.0012)
    parsed, meta = await llm.complete("openai/test", MESSAGES, Vote, temperature=0.7)
    assert parsed == Vote(value="success", confidence=0.9)
    assert (meta.input_tokens, meta.output_tokens, meta.cost_usd) == (7, 3, 0.0012)
    assert meta.latency_ms >= 0


async def test_unpriced_model_cost_is_null(monkeypatch) -> None:
    install(monkeypatch, [response(GOOD)])
    _, meta = await llm.complete("openai/test", MESSAGES, Vote, temperature=0.7)
    assert meta.cost_usd is None  # completion_cost raises on the fake response


async def test_one_parse_retry_then_success(monkeypatch) -> None:
    calls = install(monkeypatch, [response("not json"), response(GOOD)])
    parsed, meta = await llm.complete("openai/test", MESSAGES, Vote, temperature=0.7)
    assert parsed.value == "success"
    assert len(calls) == 2
    # The retried vote cost two calls; the meta carries both.
    assert (meta.input_tokens, meta.output_tokens) == (14, 6)


async def test_malformed_after_retry_raises_with_meta(monkeypatch) -> None:
    calls = install(monkeypatch, [response("not json"), response('{"wrong": 1}')])
    with pytest.raises(llm.MalformedResponse) as exc_info:
        await llm.complete("openai/test", MESSAGES, Vote, temperature=0.7)
    assert len(calls) == 2
    assert exc_info.value.meta.input_tokens == 14  # both attempts' cost auditable


async def test_permanent_provider_error_is_classified(monkeypatch) -> None:
    error = litellm.AuthenticationError(message="bad key", llm_provider="openai", model="test")
    install(monkeypatch, [error])
    with pytest.raises(llm.PermanentAnalysisError):
        await llm.complete("openai/test", MESSAGES, Vote, temperature=0.7)


async def test_transient_provider_error_propagates(monkeypatch) -> None:
    error = litellm.RateLimitError(message="slow down", llm_provider="openai", model="test")
    install(monkeypatch, [error])
    with pytest.raises(litellm.RateLimitError):
        await llm.complete("openai/test", MESSAGES, Vote, temperature=0.7)


def test_fold_meta_none_propagates_only_when_all_missing() -> None:
    folded = llm._fold_meta(
        [
            llm.CallMeta(latency_ms=10, input_tokens=7, cost_usd=None),
            llm.CallMeta(latency_ms=5, input_tokens=None, cost_usd=None),
        ]
    )
    assert (folded.latency_ms, folded.input_tokens, folded.cost_usd) == (15, 7, None)


def test_env_bootstrap_exports_only_provider_keys(monkeypatch, tmp_path) -> None:
    (tmp_path / ".env").write_text(
        "TESTPROV_API_KEY=sk-test\nTESTPROV_API_BASE=https://x\nDATABASE_URL=postgres://x\n"
    )
    monkeypatch.setattr(llm, "env_files", lambda: (str(tmp_path / ".env"),))
    monkeypatch.setattr(llm, "_env_loaded", False)
    for key in ("TESTPROV_API_KEY", "TESTPROV_API_BASE", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    try:
        llm._load_env_files()
        assert os.environ.get("TESTPROV_API_KEY") == "sk-test"
        assert os.environ.get("TESTPROV_API_BASE") == "https://x"
        assert "DATABASE_URL" not in os.environ
    finally:
        os.environ.pop("TESTPROV_API_KEY", None)
        os.environ.pop("TESTPROV_API_BASE", None)


def test_llm_configured_follows_validate_environment(monkeypatch) -> None:
    monkeypatch.setattr(
        litellm, "validate_environment", lambda model: {"keys_in_environment": True}
    )
    assert llm.llm_configured("openai/test") is True
    monkeypatch.setattr(
        litellm,
        "validate_environment",
        lambda model: {"keys_in_environment": False, "missing_keys": ["OPENAI_API_KEY"]},
    )
    assert llm.llm_configured("openai/test") is False
