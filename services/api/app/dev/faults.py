"""Dev-only fault injection for demoing the retry/DLQ paths.

POST /v1/uploads accepts an X-Fault header (honored only when dev_routes is
on); the spec is stashed in Redis keyed by upload and the matching task
trips on it. Plain specs target ingestion; an ``analyze:`` prefix targets
the analysis job of every trace in the upload (A2):

- ``transient:N`` — fail the first N attempts, then succeed (retry demo).
- ``exhaust``     — fail every attempt (dead-letter demo).
- ``permanent``   — raise the permanent error type (immediate-fail demo).

``analyze:verdict:<outcome>:<conf>[:<category>:<conf>]`` is the keyless
routing lever (A3 decision 9): the analysis job adopts a canned judge
verdict instead of calling the LLM, so routing → digest → queue → resolve
is exercisable on a stack with no provider key.
"""

import re

from app.analysis import JudgeVerdict, PermanentAnalysisError
from app.clients import redis
from app.config import settings
from app.importers.errors import PermanentIngestError

_SPEC_RE = re.compile(r"^(analyze:)?(permanent|exhaust|transient:\d+)$")
_CONF = r"(?:0(?:\.\d+)?|1(?:\.0+)?)"
_VERDICT_RE = re.compile(
    rf"^analyze:verdict:(success|failure|indeterminate):({_CONF})(?::([a-z_]+):({_CONF}))?$"
)
_TTL_SECONDS = 3600


def is_valid(spec: str) -> bool:
    return _SPEC_RE.match(spec) is not None or _VERDICT_RE.match(spec) is not None


async def arm(upload_id: str, spec: str) -> None:
    await redis.client().set(f"fault:{upload_id}", spec, ex=_TTL_SECONDS)


async def _armed_spec(upload_id: str) -> str | None:
    if not settings.dev_routes:
        return None
    raw = await redis.client().get(f"fault:{upload_id}")
    return raw.decode() if raw is not None else None


def _trip(spec: str, attempt: int, permanent_error: type[Exception]) -> None:
    if spec == "permanent":
        raise permanent_error("Fault injection: permanent failure.")
    if spec == "exhaust":
        raise RuntimeError("Fault injection: transient failure (exhaust).")
    failures = int(spec.split(":", 1)[1])
    if attempt <= failures:
        raise RuntimeError(f"Fault injection: transient failure (attempt {attempt}/{failures}).")


async def trip(upload_id: str, attempt: int) -> None:
    """Raise the armed ingest fault for this upload, if any. No-op outside dev."""
    spec = await _armed_spec(upload_id)
    if spec is None or spec.startswith("analyze:"):
        return
    _trip(spec, attempt, PermanentIngestError)


async def trip_analysis(upload_id: str, attempt: int) -> None:
    """Raise the armed analysis fault for this upload's traces, if any.
    Verdict specs don't trip — they substitute, via canned_verdict."""
    spec = await _armed_spec(upload_id)
    if spec is None or not spec.startswith("analyze:") or spec.startswith("analyze:verdict:"):
        return
    _trip(spec.removeprefix("analyze:"), attempt, PermanentAnalysisError)


async def canned_verdict(upload_id: str) -> JudgeVerdict | None:
    """The armed canned verdict for this upload's traces, if any. The worker
    treats it as the judge's output (marked `fault:canned` on the audit row)
    and runs the real routing math over it."""
    spec = await _armed_spec(upload_id)
    if spec is None:
        return None
    m = _VERDICT_RE.match(spec)
    if m is None:
        return None
    outcome, outcome_conf, category, category_conf = m.groups()
    return JudgeVerdict(
        outcome=outcome,  # type: ignore[arg-type]  # the regex enforces the ternary
        outcome_confidence=float(outcome_conf),
        failure_mode="inconclusive" if outcome == "failure" else None,
        failure_mode_confidence=float(outcome_conf) if outcome == "failure" else None,
        task_category=category,
        task_category_confidence=float(category_conf) if category_conf is not None else None,
        reasoning="Fault injection: canned verdict.",
    )
