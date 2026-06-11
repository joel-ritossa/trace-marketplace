import asyncpg
from fastapi import APIRouter

from app.auth import AuthUser, CurrentUser
from app.clients import db
from app.errors import ApiError
from app.queries import profiles
from app.schemas.profile import ProfileResponse, ProfileUpdateRequest

router = APIRouter(prefix="/profile")


def _response(user: AuthUser, row: asyncpg.Record) -> ProfileResponse:
    return ProfileResponse(
        id=user.id,
        email=user.email,
        display_name=row["display_name"],
        allow_private_llm_analysis=row["allow_private_llm_analysis"],
        task_categories=list(row["task_categories"]),
        created_at=row["created_at"],
    )


@router.get("", response_model=ProfileResponse)
async def get_profile(user: CurrentUser) -> ProfileResponse:
    row = await profiles.get_profile(db.pool(), user.id)
    if row is None:
        raise ApiError("profile_not_found", "Profile not found.", status=404)
    return _response(user, row)


@router.patch("", response_model=ProfileResponse)
async def update_profile(body: ProfileUpdateRequest, user: CurrentUser) -> ProfileResponse:
    row = await profiles.update_profile(
        db.pool(),
        user.id,
        display_name=body.display_name,
        allow_private_llm_analysis=body.allow_private_llm_analysis,
        task_categories=body.task_categories,
    )
    if row is None:
        raise ApiError("profile_not_found", "Profile not found.", status=404)
    return _response(user, row)
