from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

from app.analysis.models import TASK_CATEGORIES

DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ProfileResponse(BaseModel):
    id: str
    email: str | None
    display_name: str | None
    allow_private_llm_analysis: bool
    task_categories: list[str]
    created_at: datetime


class ProfileUpdateRequest(BaseModel):
    # Partial update: omitted fields are untouched.
    display_name: DisplayName | None = None
    allow_private_llm_analysis: bool | None = None
    # Owner task scope (3_api.md): global enum values, never "other"
    # (always implicitly allowed); deduplicated; [] = unscoped.
    task_categories: list[str] | None = None

    @field_validator("task_categories")
    @classmethod
    def _valid_categories(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unknown = [v for v in value if v not in TASK_CATEGORIES or v == "other"]
        if unknown:
            raise ValueError(f"unknown task categories {unknown}")
        return sorted(set(value))
