"""FROZEN CONTRACT — HIL routing reasons (B0, 1_analysis.md HIL Routing).

The reason *model* is frozen here; the pure routing function
`(signals, verdict) -> list[RoutingReason]` lands in B2. The plain-language
message is what `review_items.context` records and the review UI shows.
"""

from typing import Literal

from pydantic import BaseModel

RoutingReasonCode = Literal[
    "signals_judge_disagreement",
    "outcome_indeterminate",
    "low_outcome_confidence",
    "low_task_category_confidence",
]


class RoutingReason(BaseModel):
    model_config = {"frozen": True}

    code: RoutingReasonCode
    message: str
