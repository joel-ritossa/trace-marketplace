from datetime import datetime

from pydantic import BaseModel


class MeResponse(BaseModel):
    id: str
    email: str | None
    display_name: str | None
    created_at: datetime
