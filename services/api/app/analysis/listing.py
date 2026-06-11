"""Listing-copy generator: tags + description for the marketplace listing
(1_analysis.md listing-copy section).

Not a label analyzer — the output is free-form, non-deterministic copy for
the owner-editable `traces.tags` / `traces.description` columns, generated
only when the owner left them empty (the worker enforces fill-if-empty).
One sampled call, no voting: a regeneration would produce different copy,
so a malformed response fails open (None — no row, no copy) rather than
retrying toward a guess.

Privacy: nothing here logs; the rendering and raw output exist only in
memory. The copy itself derives from trace content by design — it is the
owner-consented listing surface.
"""

import re

from pydantic import BaseModel

from app.analysis import llm
from app.analysis.config import AnalysisSettings, RendererConfig
from app.analysis.models import ListingResult, MetricCall
from app.analysis.prompts import listing
from app.analysis.rendering import render_trace, rendering_text
from app.analysis.trace_input import TraceInput

LISTING_VERSION = "1"

# Generated copy obeys the same bounds the PATCH endpoint enforces on owner
# input (schemas/trace.py: Tag ≤ 80 chars, description ≤ 2000, ≤ 20 tags —
# the prompt asks for 3-6; cap there).
_MAX_TAGS = 6
_MAX_TAG_CHARS = 80
_MAX_DESCRIPTION_CHARS = 2000


class _ListingDraft(BaseModel):
    description: str
    tags: list[str]


def normalize_tags(raw: list[str]) -> list[str]:
    """Lowercase kebab-case, order-preserving dedupe, drop empties and
    oversize, cap count — model output never bypasses the owner-input
    bounds."""
    seen: set[str] = set()
    out: list[str] = []
    for tag in raw:
        cleaned = re.sub(r"[\s_]+", "-", tag.strip().lower()).strip("-")
        if not cleaned or len(cleaned) > _MAX_TAG_CHARS or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
        if len(out) == _MAX_TAGS:
            break
    return out


async def run_listing(trace: TraceInput, settings: AnalysisSettings) -> ListingResult | None:
    if not llm.llm_configured(settings.judge_model):
        return None  # keyless: inapplicable, no fake output
    rendered = render_trace(trace, RendererConfig.from_settings(settings))
    messages = [
        {"role": "system", "content": listing.V1},
        {"role": "user", "content": rendering_text(rendered.messages)},
    ]
    try:
        parsed, meta = await llm.complete(
            settings.judge_model, messages, _ListingDraft, llm.SAMPLING_TEMPERATURE
        )
    except llm.MalformedResponse:
        return None
    tags = normalize_tags(parsed.tags)
    description = parsed.description.strip()[:_MAX_DESCRIPTION_CHARS] or None
    if not tags and description is None:
        return None
    return ListingResult(
        description=description, tags=tags, calls=[MetricCall(**meta.model_dump())]
    )
