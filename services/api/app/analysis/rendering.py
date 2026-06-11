"""Trace renderer: normalized spans → chronological OpenAI-style messages.

Pure function of (trace, RENDERER_VERSION, config) — 1_analysis.md. Budget
mechanics in spec order: per-step content caps first (middle-out, per field),
then priority tiering — the first user message, all error spans, and the
final K steps are must-haves; remaining middle steps fill the budget
newest-first with explicit elision markers. The step skeleton (name, status,
ordering) of every rendered step survives capping; whole-step elision is
always marked.
"""

from dataclasses import dataclass

from app.analysis import content
from app.analysis.config import RendererConfig
from app.analysis.models import RenderedMessage, RenderedTrace
from app.analysis.trace_input import SpanInput, TraceInput

RENDERER_VERSION = "1"

_ROLE_BY_KIND = {"llm": "assistant", "tool": "tool"}
# Cap-shrink floor: after this many halvings, steps render skeleton-only.
_MAX_CAP_HALVINGS = 6


def _middle_out(text: str, cap: int) -> tuple[str, bool]:
    if len(text) <= cap:
        return text, False
    if cap < 48:
        # No room for the counted marker; a bare ellipsis still cues the cut.
        return text[: cap - 1] + "…", True
    keep = (cap - 32) // 2
    removed = len(text) - 2 * keep
    return f"{text[:keep]}…[{removed} chars truncated]…{text[-keep:]}", True


@dataclass
class _Step:
    index: int  # 1-based chronological position
    role: str
    skeleton: str
    input_text: str | None
    output_text: str | None
    summary: str | None
    is_error: bool

    def render(self, field_cap: int) -> tuple[str, bool]:
        """Step text at a given per-field cap; cap 0 = skeleton only."""
        lines = [self.skeleton]
        truncated = False
        if field_cap > 0:
            for label, text in (("input", self.input_text), ("output", self.output_text)):
                if text:
                    capped, cut = _middle_out(text, field_cap)
                    lines.append(f"{label}: {capped}")
                    truncated = truncated or cut
            if not self.input_text and not self.output_text and self.summary:
                lines.append(f"attrs: {self.summary}")
        else:
            truncated = bool(self.input_text or self.output_text or self.summary)
        return "\n".join(lines), truncated


def _build_step(span: SpanInput, index: int, total: int) -> _Step:
    is_error = span.status == "error"
    status = span.status + (f", {span.error_type}" if span.error_type else "")
    skeleton = f"[step {index}/{total}] {span.kind} {span.name} ({status}, {span.duration_ms}ms)"
    return _Step(
        index=index,
        role=_ROLE_BY_KIND.get(span.kind, "system"),
        skeleton=skeleton,
        input_text=content.input_text(span),
        output_text=content.output_text(span),
        summary=content.attribute_summary(span),
        is_error=is_error,
    )


def _header(trace: TraceInput) -> str:
    text = (
        f"Trace: {trace.name} | status: {trace.status} | "
        f"spans: {trace.span_count} ({trace.error_count} errors) | "
        f"duration: {trace.duration_ms}ms"
    )
    if trace.tool_names:
        text += f" | tools: {', '.join(trace.tool_names)}"
    return text


def _field_cap(step: _Step, config: RendererConfig, halvings: int) -> int:
    base = (
        config.conversation_cap_chars if step.role == "assistant" else config.tool_field_cap_chars
    )
    return base // (2**halvings) if halvings < _MAX_CAP_HALVINGS else 0


def _assemble(
    fixed: list[RenderedMessage], steps: list[_Step], rendered: dict[int, str]
) -> tuple[list[RenderedMessage], int]:
    """Final message list with elision markers, plus its total char count."""
    messages = list(fixed)
    elided_run: list[int] = []

    def flush() -> None:
        if elided_run:
            marker = f"[steps {elided_run[0]}-{elided_run[-1]} elided ({len(elided_run)} steps)]"
            messages.append(RenderedMessage(role="system", content=marker))
            elided_run.clear()

    for step in steps:
        if step.index in rendered:
            flush()
            messages.append(RenderedMessage(role=step.role, content=rendered[step.index]))
        else:
            elided_run.append(step.index)
    flush()
    return messages, sum(len(m.content) for m in messages)


def rendering_text(messages: list[RenderedMessage]) -> str:
    """The flat prompt-surface form of a rendering — what LLM analyzers
    (judge, critics) actually send."""
    return "\n\n".join(f"{m.role}: {m.content}" for m in messages)


def render_trace(trace: TraceInput, config: RendererConfig) -> RenderedTrace:
    total = len(trace.spans)
    steps = [_build_step(span, i + 1, total) for i, span in enumerate(trace.spans)]

    fixed: list[RenderedMessage] = [RenderedMessage(role="system", content=_header(trace))]
    truncated = False
    user_message = content.first_user_message(trace.spans)
    if user_message:
        capped, cut = _middle_out(user_message, config.conversation_cap_chars)
        truncated = truncated or cut
        fixed.append(RenderedMessage(role="user", content=capped))

    final_from = max(total - config.final_steps, 0)
    mandatory = {s.index for s in steps if s.is_error or s.index > final_from}

    # Per-step caps, halved until the must-haves (with their elision markers)
    # fit the budget; floor is skeleton-only. Halvings apply to every step so
    # one config renders one way — determinism over per-step cleverness.
    halvings = 0
    while True:
        rendered: dict[int, str] = {}
        for step in steps:
            if step.index in mandatory:
                text, cut = step.render(_field_cap(step, config, halvings))
                rendered[step.index] = text
                truncated = truncated or cut
        _, mandatory_total = _assemble(fixed, steps, rendered)
        if mandatory_total <= config.budget_chars or halvings >= _MAX_CAP_HALVINGS:
            break
        halvings += 1
        truncated = True

    # Fill the remaining budget with middle steps, newest-first. Marker cost
    # shifts as runs split, so this is an estimate the trim pass corrects.
    remaining = config.budget_chars - mandatory_total
    for step in sorted(steps, key=lambda s: -s.index):
        if step.index in mandatory:
            continue
        text, cut = step.render(_field_cap(step, config, halvings))
        if len(text) <= remaining:
            rendered[step.index] = text
            remaining -= len(text)
            truncated = truncated or cut

    # Trim until exactly within budget: lowest-priority rendered steps first —
    # optional middles before pre-final-K error spans, oldest first. The final
    # K steps and the fixed messages always stay — the budget floor: if those
    # alone exceed the budget (unreachable with sane configs; K skeletons are
    # a few hundred chars), the output runs over rather than dropping them.
    removable = sorted(
        (s for s in steps if s.index in rendered and s.index <= final_from),
        key=lambda s: (s.is_error, s.index),
    )
    while True:
        messages, total_chars = _assemble(fixed, steps, rendered)
        if total_chars <= config.budget_chars or not removable:
            break
        del rendered[removable.pop(0).index]
        truncated = True

    return RenderedTrace(
        messages=messages,
        rendering_truncated=truncated or len(rendered) < total,
        renderer_version=RENDERER_VERSION,
        step_count=len(rendered),
        elided_step_count=total - len(rendered),
    )
