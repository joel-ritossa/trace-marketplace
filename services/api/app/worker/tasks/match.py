import logging

from app import obs
from app.clients import db
from app.queries import notifications as notifications_q
from app.queries import subscriptions as subscriptions_q
from app.schemas.trace import TraceFilterQuery
from app.worker.broker import broker

logger = logging.getLogger(__name__)


@broker.task()
async def match_trace(trace_id: str) -> None:
    """Evaluate every subscription against one trace (3_api.md: event-driven
    matching, fired when a trace becomes listed, when analyze_trace
    completes on a listed trace, or when a review resolve relabels a
    listed trace).

    Deliberately no retry/DLQ (A4 decision 6): trace-scoped dead letters
    derive the UI's analysis-failed state, and a matching hiccup must never
    read as a failed analysis. Idempotent (unique match pair) and re-fired
    by every trigger event — a lost run costs a notification, not
    correctness.
    """
    obs.bind(trace_id=trace_id)
    pool = db.pool()
    trace = await pool.fetchrow(
        "select id from traces where id = $1 and visibility = 'listed'", trace_id
    )
    if trace is None:  # unlisted or deleted since the trigger; nothing to match
        return

    matched = 0
    for sub in await subscriptions_q.fetch_all(pool):
        # Stored queries validated at write time against the same model —
        # parsing here cannot fail (3_api.md conventions). The behavior
        # anchor ANDs in; the embedding stage runs before the match kick,
        # so an embeddable trace has its vector by now.
        filters = TraceFilterQuery.model_validate(sub["query"])
        anchor = subscriptions_q.anchor_of(sub)
        if not await subscriptions_q.matches_trace(pool, filters, trace_id, anchor):
            continue
        # Ledger row and digest commit together: a first match can never be
        # recorded (permanently deduped) without its notification.
        async with pool.acquire() as conn, conn.transaction():
            if await subscriptions_q.record_match(conn, str(sub["id"]), trace_id):
                matched += 1
                await notifications_q.subscription_match_upsert(
                    conn,
                    user_id=str(sub["owner_id"]),
                    subscription_id=str(sub["id"]),
                    name=sub["name"],
                    trace_id=trace_id,
                )
    if matched:
        logger.info("match_trace: trace %s newly matched %d subscription(s)", trace_id, matched)
