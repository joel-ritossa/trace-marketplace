"""Analysis settings and config models.

Separate from the platform `Settings`: analysis runs offline (fixture-mode
runner, B-stream tests) with zero infrastructure env, so nothing here may
require DB/Redis/Supabase variables. All values are local-demo defaults,
overridable via `ANALYSIS_*` env vars documented in `.env.example`.
"""

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.env import env_files

# Budget env var speaks tokens (spec language); rendering counts chars. The
# ~4 chars/token heuristic is fine for a size/cost guard — no tokenizer dep.
CHARS_PER_TOKEN = 4


class AnalysisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="analysis_", env_file=env_files(), extra="ignore")

    render_budget_tokens: int = 15_000
    render_final_steps: int = 8
    render_tool_field_cap_chars: int = 2_000
    render_conversation_cap_chars: int = 8_000

    # Loop detection: exact-repeat / stagnation threshold (1_analysis.md,
    # N = 3 default). Cycle parameters are spec-fixed constants.
    loop_n: int = 3

    # Agent judge (9_session-analysis.md): one model for the per-turn agent
    # and the roll-up; tool rounds per turn before the verdict is forced and
    # marked indeterminate; turns judged concurrently per run.
    judge_model: str = "gpt-5-mini"
    agent_max_steps: int = Field(100, ge=1)
    turn_concurrency: int = Field(4, ge=1)

    # Similar behavior (docs/proposals/similar-behavior.md): one embedding
    # per trace over the roll-up text, truncated to this budget before the
    # call. Default leaves real headroom under the
    # model's 8192-token window: the ~4 chars/token heuristic undercounts
    # tokens for JSON-heavy tool content, and an over-window input is a
    # permanent (unretryable) failure. The vector dimension is fixed by the
    # trace_embeddings migration (1536); a model swap is a migration +
    # re-embed, not a config flip.
    embedding_model: str = "text-embedding-3-small"
    embedding_budget_tokens: int = Field(6_000, ge=100)


class RendererConfig(BaseModel):
    """Rendering tunables. Part of the renderer's determinism contract:
    a rendering is a pure function of (trace, renderer version, config)."""

    model_config = {"frozen": True}

    budget_chars: int
    final_steps: int
    tool_field_cap_chars: int
    conversation_cap_chars: int

    @classmethod
    def from_settings(cls, settings: AnalysisSettings) -> "RendererConfig":
        return cls(
            budget_chars=settings.render_budget_tokens * CHARS_PER_TOKEN,
            final_steps=settings.render_final_steps,
            tool_field_cap_chars=settings.render_tool_field_cap_chars,
            conversation_cap_chars=settings.render_conversation_cap_chars,
        )
