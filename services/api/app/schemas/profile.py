from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ProfileResponse(BaseModel):
    id: str
    email: str | None
    display_name: str | None
    allow_private_llm_analysis: bool
    created_at: datetime


class ProfileUpdateRequest(BaseModel):
    # Partial update: omitted fields are untouched.
    display_name: DisplayName | None = None
    allow_private_llm_analysis: bool | None = None
