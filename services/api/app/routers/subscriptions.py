import asyncpg
from fastapi import APIRouter, Query, Response

from app.auth import CurrentUser
from app.clients import db
from app.errors import ApiError
from app.queries import subscriptions as subscriptions_q
from app.queries import traces as traces_q
from app.schemas.subscription import (
    SeenResponse,
    Subscription,
    SubscriptionCreateRequest,
    SubscriptionFeedItem,
    SubscriptionFeedResponse,
    SubscriptionListResponse,
    SubscriptionPatchRequest,
    validate_anchor_pair,
)
from app.schemas.trace import TraceFilterQuery

router = APIRouter(prefix="/subscriptions")


@router.post("", response_model=Subscription, status_code=201)
async def create_subscription(body: SubscriptionCreateRequest, user: CurrentUser) -> Subscription:
    if body.similar_to_trace_id is not None:
        await _anchor_visible_or_422(body.similar_to_trace_id, user)
    row = await subscriptions_q.create(
        db.pool(),
        user.id,
        name=body.name,
        query=body.query.stored(),
        similar_to_trace_id=body.similar_to_trace_id,
        similarity_threshold=body.similarity_threshold,
    )
    # Re-read for the joined shape (anchor trace name).
    refreshed = await subscriptions_q.get_owned(db.pool(), str(row["id"]), user.id)
    if refreshed is None:  # deleted between the insert and the re-read
        raise ApiError("not_found", "Subscription not found.", status=404)
    return await _subscription(refreshed, last_match_at=None)


@router.get("", response_model=SubscriptionListResponse)
async def list_subscriptions(user: CurrentUser) -> SubscriptionListResponse:
    rows = await subscriptions_q.list_for_owner(db.pool(), user.id)
    return SubscriptionListResponse(
        subscriptions=[await _subscription(r, last_match_at=r["last_match_at"]) for r in rows]
    )


@router.patch("/{subscription_id}", response_model=Subscription)
async def update_subscription(
    subscription_id: str, body: SubscriptionPatchRequest, user: CurrentUser
) -> Subscription:
    fields = body.model_fields_set
    if not fields:
        raise ApiError("invalid_request", "Provide name, query, and/or anchor.", status=422)
    kwargs: dict = {}
    if "name" in fields:
        if body.name is None:
            raise ApiError("invalid_request", "name cannot be null.", status=422)
        kwargs["name"] = body.name
    if "query" in fields:
        if body.query is None:
            raise ApiError("invalid_request", "query cannot be null.", status=422)
        kwargs["query"] = body.query.stored()
    anchor_fields = {"similar_to_trace_id", "similarity_threshold"} & fields
    if anchor_fields:
        try:
            validate_anchor_pair(body.similar_to_trace_id, body.similarity_threshold)
        except ValueError as exc:
            raise ApiError("invalid_request", str(exc), status=422) from exc
        if body.similar_to_trace_id is None:
            kwargs["anchor"] = None
        else:
            await _anchor_visible_or_422(body.similar_to_trace_id, user)
            kwargs["anchor"] = (body.similar_to_trace_id, body.similarity_threshold)
    # The predicate floor against the effective row: a patch may not leave
    # the subscription with neither filters nor anchor (mirrors create).
    current = await _owned_or_404(subscription_id, user)
    effective_query = kwargs.get("query", current["query"])
    effective_anchor = (
        kwargs["anchor"] if "anchor" in kwargs else subscriptions_q.anchor_of(current)
    )
    if not effective_query and effective_anchor is None:
        raise ApiError(
            "invalid_request",
            "Subscription needs at least one filter predicate or a behavior anchor.",
            status=422,
        )
    row = await _update_or_404(subscription_id, user, **kwargs)
    refreshed = await subscriptions_q.get_owned(db.pool(), str(row["id"]), user.id)
    if refreshed is None:  # deleted between the update and the re-read
        raise ApiError("not_found", "Subscription not found.", status=404)
    return await _subscription(refreshed, last_match_at=refreshed["last_match_at"])


@router.delete("/{subscription_id}", status_code=204)
async def delete_subscription(subscription_id: str, user: CurrentUser) -> Response:
    try:
        deleted = await subscriptions_q.delete_owned(db.pool(), subscription_id, user.id)
    except asyncpg.DataError:  # not a UUID
        deleted = False
    if not deleted:
        raise ApiError("not_found", "Subscription not found.", status=404)
    return Response(status_code=204)


@router.get("/{subscription_id}/results", response_model=SubscriptionFeedResponse)
async def subscription_results(
    subscription_id: str,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> SubscriptionFeedResponse:
    """The stored query executed live against listed traces (backfill for
    free), each card annotated new_since_last_seen (3_api.md)."""
    sub = await _owned_or_404(subscription_id, user)
    filters = TraceFilterQuery.model_validate(sub["query"])
    rows, total, excluded = await traces_q.list_visible(
        db.pool(),
        user.id,
        scope="marketplace",
        filters=filters,
        sort="created_at",
        limit=limit,
        offset=offset,
        anchor=subscriptions_q.anchor_of(sub),
    )
    # Local import: routers.traces owns the row→card mapping; importing the
    # helper (not duplicating it) keeps one source of truth per concept.
    from app.routers.traces import list_item

    new_ids = await subscriptions_q.new_match_ids(
        db.pool(), str(sub["id"]), [str(r["id"]) for r in rows]
    )
    return SubscriptionFeedResponse(
        traces=[
            SubscriptionFeedItem(
                **list_item(r).model_dump(),
                new_since_last_seen=str(r["id"]) in new_ids,
            )
            for r in rows
        ],
        total=total,
        excluded_unanalyzed=excluded,
    )


@router.post("/{subscription_id}/seen", response_model=SeenResponse)
async def mark_seen(subscription_id: str, user: CurrentUser) -> SeenResponse:
    await _owned_or_404(subscription_id, user)
    row = await subscriptions_q.mark_seen(db.pool(), subscription_id, user.id)
    if row is None:  # deleted out from under us
        raise ApiError("not_found", "Subscription not found.", status=404)
    return SeenResponse(last_seen_at=row["last_seen_at"])


async def _subscription(row: asyncpg.Record, *, last_match_at) -> Subscription:
    filters = TraceFilterQuery.model_validate(row["query"])
    anchor = subscriptions_q.anchor_of(row)
    return Subscription(
        subscription_id=str(row["id"]),
        name=row["name"],
        query=row["query"],
        similar_to_trace_id=(
            str(row["similar_to_trace_id"]) if row["similar_to_trace_id"] is not None else None
        ),
        similarity_threshold=row["similarity_threshold"],
        similar_to_name=row["similar_to_name"] if "similar_to_name" in row.keys() else None,
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
        match_count=await subscriptions_q.live_match_count(db.pool(), filters, anchor),
        last_match_at=last_match_at,
    )


async def _anchor_visible_or_422(trace_id: str, user: CurrentUser) -> None:
    """The anchor must be visible to the subscriber at write time (own or
    listed) — 422, not 404: the subscription is the malformed thing."""
    try:
        row = await traces_q.get_visible(db.pool(), trace_id, user.id)
    except asyncpg.DataError:  # not a UUID
        row = None
    if row is None:
        raise ApiError("invalid_request", "similar_to_trace_id is not a visible trace.", status=422)


async def _owned_or_404(subscription_id: str, user: CurrentUser) -> asyncpg.Record:
    try:
        row = await subscriptions_q.get_owned(db.pool(), subscription_id, user.id)
    except asyncpg.DataError:  # not a UUID
        row = None
    if row is None:
        # 404-not-403: invisible objects are indistinguishable from absent.
        raise ApiError("not_found", "Subscription not found.", status=404)
    return row


async def _update_or_404(subscription_id: str, user: CurrentUser, **kwargs) -> asyncpg.Record:
    try:
        row = await subscriptions_q.update_owned(db.pool(), subscription_id, user.id, **kwargs)
    except asyncpg.DataError:
        row = None
    if row is None:
        raise ApiError("not_found", "Subscription not found.", status=404)
    return row
