from fastapi import APIRouter

from app.auth import CurrentUser
from app.clients import db
from app.errors import ApiError
from app.queries import profiles
from app.schemas.profile import MeResponse

router = APIRouter()


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser) -> MeResponse:
    row = await profiles.get_profile(db.pool(), user.id)
    if row is None:
        raise ApiError("profile_not_found", "Profile not found.", status=404)
    return MeResponse(
        id=user.id,
        email=user.email,
        display_name=row["display_name"],
        created_at=row["created_at"],
    )
