"""Behavior-summary generator: a gist + step walkthrough of what the agent
did (1_analysis.md behavior-summary section).

Not a label analyzer — the output is free-form descriptive prose for the
trace-detail Analysis section and the review resolve view. One sampled call,
no voting: a malformed response fails open (None — no row, no summary)
rather than retrying toward a guess. Unlike listing copy it is machine-owned
display text, never owner-editable, so every analysis rewrite regenerates it.

Privacy: nothing here logs; the rendering and raw output exist only in
memory. The summary derives from trace content by design — it is shown
exactly where the trace itself is visible (owner or listed).
"""

from pydantic import BaseModel

from app.analysis import llm
from app.analysis.config import AnalysisSettings, RendererConfig
from app.analysis.models import MetricCall, SummaryResult
from app.analysis.prompts import summary
from app.analysis.rendering import render_trace, rendering_text
from app.analysis.trace_input import TraceInput

SUMMARY_VERSION = "1"

# Display bounds, not owner-input bounds (nothing here is editable): keep the
# gist a glance and each bullet one line-ish, whatever the model returns.
_MAX_GIST_CHARS = 500
_MAX_STEPS = 10
_MAX_STEP_CHARS = 300


class _SummaryDraft(BaseModel):
    gist: str
    steps: list[str]


def normalize_steps(raw: list[str]) -> list[str]:
    """Trim, drop empties, clamp length and count — model output never
    bypasses the display bounds."""
    out: list[str] = []
    for step in raw:
        cleaned = step.strip()
        if not cleaned:
            continue
        out.append(cleaned[:_MAX_STEP_CHARS])
        if len(out) == _MAX_STEPS:
            break
    return out


async def run_summary(trace: TraceInput, settings: AnalysisSettings) -> SummaryResult | None:
    if not llm.llm_configured(settings.judge_model):
        return None  # keyless: inapplicable, no fake output
    rendered = render_trace(trace, RendererConfig.from_settings(settings))
    messages = [
        {"role": "system", "content": summary.V1},
        {"role": "user", "content": rendering_text(rendered.messages)},
    ]
    try:
        parsed, meta = await llm.complete(
            settings.judge_model, messages, _SummaryDraft, llm.SAMPLING_TEMPERATURE
        )
    except llm.MalformedResponse:
        return None
    gist = parsed.gist.strip()[:_MAX_GIST_CHARS] or None
    steps = normalize_steps(parsed.steps)
    if gist is None and not steps:
        return None
    return SummaryResult(gist=gist, steps=steps, calls=[MetricCall(**meta.model_dump())])
