"""LLM provider layer — the only place provider calls happen (1_analysis.md).

litellm routes every provider through one call shape; provider SDKs are
never imported. Keys use litellm's conventional env var names; because
pydantic-settings loads `.env`/`.env.local` only for declared fields, this
module bootstraps `os.environ` from the same files (provider-credential
keys only, non-empty values, real-env-wins) so file-kept keys reach
litellm in the runner and worker alike.

Privacy: nothing here logs. Prompts and raw outputs exist only in memory;
only parsed labels and call metadata (latency/tokens/cost) leave the call
site.
"""

import os
import time

from dotenv import dotenv_values
from pydantic import BaseModel, ValidationError

from app.env import env_files

# Spec requires temperature > 0 where self-consistency votes are sampled
# (judge, critics); not a knob. Models that reject the param (litellm drops
# it) sample at their default temperature, which is also > 0.
SAMPLING_TEMPERATURE = 0.7

_env_loaded = False

# Only provider credentials get exported — the rest of the env files
# (platform settings) stay out of os.environ and child processes. Covers
# litellm's conventional names (OPENAI_API_KEY, ANTHROPIC_API_KEY,
# OPENROUTER_API_BASE, …); exotic provider vars must be real env.
_EXPORTABLE_SUFFIXES = ("_API_KEY", "_API_BASE")


def _load_env_files() -> None:
    """Export provider keys from the env files into os.environ once,
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
            if value and key.endswith(_EXPORTABLE_SUFFIXES):
                os.environ.setdefault(key, value)


def llm_configured(model: str) -> bool:
    """Whether the provider key(s) for `model` are available — the predicate
    behind `llm_skip_reason = 'not_configured'` (worker) and the runner's
    keyless skip. litellm owns the provider→key map."""
    import litellm

    _load_env_files()
    return bool(litellm.validate_environment(model)["keys_in_environment"])


class PermanentAnalysisError(Exception):
    """Provider failure retrying cannot fix (auth, bad request, context
    window — not bad infra). Mirrors PermanentIngestError: the worker marks
    analysis failed immediately; anything else is transient and retried."""


class MalformedResponse(Exception):
    """Schema-invalid model output after the one parse-retry. Carries the
    call metadata so the vote's cost is still auditable; the judge degrades
    the vote per its fail-open rules rather than failing the run."""

    def __init__(self, meta: "CallMeta"):
        super().__init__("model response failed schema validation")
        self.meta = meta


class CallMeta(BaseModel):
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


def _fold_meta(metas: list[CallMeta]) -> CallMeta:
    """Sum metadata across attempts — a parse-retried vote cost two calls,
    and the audit artifact carries what the vote actually cost."""

    def total(values: list[int | float | None]) -> int | float | None:
        present = [v for v in values if v is not None]
        return sum(present) if present else None

    return CallMeta(
        latency_ms=sum(m.latency_ms for m in metas),
        input_tokens=total([m.input_tokens for m in metas]),
        output_tokens=total([m.output_tokens for m in metas]),
        cost_usd=total([m.cost_usd for m in metas]),
    )


_PARSE_RETRIES = 1


async def complete(
    model: str,
    messages: list[dict[str, str]],
    schema: type[BaseModel],
    temperature: float,
) -> tuple[BaseModel, CallMeta]:
    """One structured-output completion: json-schema response_format from
    the vote schema, parsed and validated. One parse-retry (malformed JSON
    is model noise, not infra), then MalformedResponse. Permanent provider
    errors raise PermanentAnalysisError; everything else propagates as
    transient."""
    import litellm

    _load_env_files()
    litellm.suppress_debug_info = True
    # Some models (OpenAI gpt-5/o-series) reject non-default temperature;
    # dropping the param there still samples (their default temp is 1 > 0).
    litellm.drop_params = True

    metas: list[CallMeta] = []
    for attempt in range(_PARSE_RETRIES + 1):
        started = time.perf_counter()
        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                response_format=schema,
                temperature=temperature,
            )
        except (
            litellm.AuthenticationError,
            litellm.PermissionDeniedError,
            litellm.NotFoundError,
            litellm.BadRequestError,  # includes ContextWindowExceededError
            litellm.UnprocessableEntityError,
        ) as exc:
            raise PermanentAnalysisError(str(exc)) from exc
        metas.append(_call_meta(response, started))
        content = response.choices[0].message.content
        try:
            return schema.model_validate_json(content or ""), _fold_meta(metas)
        except ValidationError:
            if attempt == _PARSE_RETRIES:
                raise MalformedResponse(_fold_meta(metas)) from None
    raise AssertionError("unreachable")


async def embed(model: str, text: str) -> tuple[list[float], CallMeta]:
    """One embedding call (similar-behavior proposal). Same error
    classification as `complete`: provider errors retrying cannot fix raise
    PermanentAnalysisError; everything else propagates as transient. No
    parse-retry — an embedding response is never malformed-but-200."""
    import litellm

    _load_env_files()
    litellm.suppress_debug_info = True

    started = time.perf_counter()
    try:
        response = await litellm.aembedding(model=model, input=[text])
    except (
        litellm.AuthenticationError,
        litellm.PermissionDeniedError,
        litellm.NotFoundError,
        litellm.BadRequestError,  # includes over-window inputs
        litellm.UnprocessableEntityError,
    ) as exc:
        raise PermanentAnalysisError(str(exc)) from exc
    return list(response.data[0]["embedding"]), _call_meta(response, started)


def _call_meta(response, started: float) -> CallMeta:
    import litellm

    usage = getattr(response, "usage", None)
    try:
        cost = litellm.completion_cost(response)
    except Exception:  # model missing from litellm's price map
        cost = None
    return CallMeta(
        latency_ms=int((time.perf_counter() - started) * 1000),
        input_tokens=getattr(usage, "prompt_tokens", None),
        output_tokens=getattr(usage, "completion_tokens", None),
        cost_usd=cost,
    )
