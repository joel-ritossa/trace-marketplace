"""LLM provider layer — the only place provider calls happen.

OpenAI only: agents run through the OpenAI Agents SDK (Responses API),
embeddings through the OpenAI SDK. Model names are plain OpenAI ids from
env vars. Because pydantic-settings loads `.env`/`.env.local` only for
declared fields, this module bootstraps `os.environ` from the same files
(`OPENAI_*` keys only, non-empty values, real-env-wins) so file-kept keys
reach the SDK in the runner and worker alike.

Privacy: the only log line is a provider error's class, status, type and
code (never its message or any content), and the Agents SDK's trace
export to OpenAI is disabled at import. Prompts and raw outputs exist only in memory; only
parsed results and call metadata (latency/tokens) leave the call site.
"""

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import openai
from agents import (
    Agent,
    MaxTurnsExceeded,
    ModelBehaviorError,
    RunContextWrapper,
    RunHooks,
    Runner,
    set_tracing_disabled,
)
from dotenv import dotenv_values
from pydantic import BaseModel

from app.env import env_files

set_tracing_disabled(True)
logger = logging.getLogger(__name__)

_env_loaded = False

_PERMANENT = (
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    openai.NotFoundError,
    openai.BadRequestError,  # context-window overflows split out in run_agent
    openai.UnprocessableEntityError,
)


def _load_env_files() -> None:
    """Export OPENAI_* keys from the env files into os.environ once,
    mirroring settings precedence: real env > .env.local > .env. Empty
    values count as unset."""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    # env_files() orders (.env, .env.local) with .env.local winning;
    # setdefault semantics need the winner first.
    for path in reversed(env_files()):
        for key, value in dotenv_values(path).items():
            if value and key.startswith("OPENAI_"):
                os.environ.setdefault(key, value)


def llm_configured(model: str) -> bool:
    """Whether an OpenAI key is available — the predicate behind
    `llm_skip_reason = 'not_configured'` (worker) and the runner's keyless
    skip. `model` is kept for call-site symmetry; every model is OpenAI."""
    _load_env_files()
    return bool(os.environ.get("OPENAI_API_KEY"))


class PermanentAnalysisError(Exception):
    """Provider failure retrying cannot fix (auth, bad request — not bad
    infra). Mirrors PermanentIngestError: the worker marks analysis failed
    immediately; anything else is transient and retried. `code` is the
    provider's error code (or type/class when it has none), safe to store."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


class MalformedResponse(Exception):
    """Model output that still violates its schema after the one retry."""


class CallMeta(BaseModel):
    latency_ms: int
    input_tokens: int | None = None
    # The part of input_tokens served from the provider's prompt cache.
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    llm_calls: int = 1


def fold_meta(metas: list[CallMeta]) -> CallMeta:
    """Sum metadata across calls; a token count stays null only when every
    call lacked it."""

    def total(values: list[int | None]) -> int | None:
        present = [v for v in values if v is not None]
        return sum(present) if present else None

    return CallMeta(
        latency_ms=sum(m.latency_ms for m in metas),
        input_tokens=total([m.input_tokens for m in metas]),
        cached_input_tokens=total([m.cached_input_tokens for m in metas]),
        output_tokens=total([m.output_tokens for m in metas]),
        llm_calls=sum(m.llm_calls for m in metas),
    )


@dataclass
class AgentRun:
    output: Any  # the agent's parsed output_type instance
    history: list[Any]  # input items to continue the conversation from
    meta: CallMeta


class RunCutShort(Exception):
    """The run stopped before answering; carries the conversation so far
    (input items to continue from) and what it cost."""

    def __init__(self, history: list[Any], meta: CallMeta):
        super().__init__(type(self).__name__)
        self.history = history
        self.meta = meta


class StepLimitExceeded(RunCutShort):
    """The run used up `max_turns`."""


class ContextLimitExceeded(RunCutShort):
    """A model call's input outgrew the model's context window; `history`
    is the input that overflowed."""


class _LastInput(RunHooks):
    """Remembers the latest model input and the run's usage: a provider
    error carries neither."""

    def __init__(self) -> None:
        self.input: list[Any] = []
        self.context: RunContextWrapper | None = None

    async def on_llm_start(self, context, agent, system_prompt, input_items) -> None:
        self.input, self.context = list(input_items), context


async def run_agent(agent: Agent, input: str | list[Any], max_turns: int) -> AgentRun:
    """One Agents SDK run. Permanent provider errors raise
    PermanentAnalysisError, unparseable output MalformedResponse, the turn
    bound StepLimitExceeded, a context-window overflow ContextLimitExceeded;
    everything else propagates as transient."""
    _load_env_files()
    started = time.perf_counter()
    last = _LastInput()
    try:
        result = await Runner.run(agent, input, max_turns=max_turns, hooks=last)
    except MaxTurnsExceeded as exc:
        data = exc.run_data
        if data is None:
            raise
        history = _as_list(data.input) + [item.to_input_item() for item in data.new_items]
        raise StepLimitExceeded(history, _meta(data.context_wrapper.usage, started)) from None
    except ModelBehaviorError as exc:
        raise MalformedResponse(str(exc)) from exc
    except _PERMANENT as exc:
        code = _log_provider_error(exc)
        if code == "context_length_exceeded":
            usage = last.context.usage if last.context else None
            history = last.input or _as_list(input)
            raise ContextLimitExceeded(history, _meta(usage, started)) from None
        raise PermanentAnalysisError(str(exc), code) from exc
    return AgentRun(
        result.final_output, result.to_input_list(), _meta(result.context_wrapper.usage, started)
    )


async def embed(model: str, text: str) -> tuple[list[float], CallMeta]:
    """One embedding call. Same error classification as `run_agent`; no
    parse-retry — an embedding response is never malformed-but-200."""
    _load_env_files()
    started = time.perf_counter()
    try:
        response = await openai.AsyncOpenAI().embeddings.create(model=model, input=[text])
    except _PERMANENT as exc:
        raise PermanentAnalysisError(str(exc), _log_provider_error(exc)) from exc
    meta = CallMeta(
        latency_ms=int((time.perf_counter() - started) * 1000),
        input_tokens=response.usage.prompt_tokens,
    )
    return list(response.data[0].embedding), meta


def _log_provider_error(exc: Exception) -> str:
    """Log a permanent provider error's metadata only; return its code."""
    status = getattr(exc, "status_code", None)
    kind = getattr(exc, "type", None)
    code = getattr(exc, "code", None)
    logger.warning(
        "provider error %s: status=%s type=%s code=%s", type(exc).__name__, status, kind, code
    )
    return str(code or kind or type(exc).__name__)


def _as_list(input: str | list[Any]) -> list[Any]:
    return [{"role": "user", "content": input}] if isinstance(input, str) else list(input)


def _meta(usage: Any, started: float) -> CallMeta:
    latency_ms = int((time.perf_counter() - started) * 1000)
    if usage is None:
        return CallMeta(latency_ms=latency_ms, llm_calls=0)
    return CallMeta(
        latency_ms=latency_ms,
        input_tokens=usage.input_tokens,
        cached_input_tokens=getattr(
            getattr(usage, "input_tokens_details", None), "cached_tokens", None
        ),
        output_tokens=usage.output_tokens,
        llm_calls=usage.requests,
    )
