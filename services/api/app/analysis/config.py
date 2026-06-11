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

    # Outcome judge (1_analysis.md Family 2 / HIL routing). One model for
    # all three composed calls — analyzer_results.model_id is one column on
    # the judge's one row. Consensus is strict (share must exceed it) and
    # bounded ≥ 0.5 so at most one label can ever clear it;
    # confidence_threshold is the single routing knob for both the outcome
    # and task_category triggers. Misconfiguration fails at settings load,
    # not mid-analysis.
    judge_model: str = "openai/gpt-5-mini"
    judge_votes: int = Field(3, ge=1)
    judge_consensus: float = Field(0.5, ge=0.5, lt=1)
    confidence_threshold: float = 0.7


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
