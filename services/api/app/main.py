from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.clients import db, redis, storage
from app.config import settings
from app.errors import register_error_handlers
from app.middleware.correlation import CorrelationIdMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.obs import configure_logging
from app.routers import (
    api_keys,
    bulk,
    dev,
    health,
    notifications,
    profile,
    review_items,
    subscriptions,
    traces,
    uploads,
)
from app.worker.broker import broker

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.open_pool()
    await redis.open_client()
    await storage.open_client()
    await broker.startup()
    yield
    await broker.shutdown()
    await storage.close_client()
    await redis.close_client()
    await db.close_pool()


app = FastAPI(title="Trace Marketplace API", version="0.1.0", lifespan=lifespan)

# Middleware runs in reverse add order: CORS outermost so even 429s carry CORS
# headers for the browser; correlation wraps rate limiting so 429s are
# correlated too.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.web_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

v1 = APIRouter(prefix="/v1")
v1.include_router(health.router)
v1.include_router(profile.router)
v1.include_router(api_keys.router)
v1.include_router(uploads.router)
# Bulk's static /traces/* paths register before the dynamic /{trace_id} ones.
v1.include_router(bulk.router)
v1.include_router(traces.router)
v1.include_router(notifications.router)
v1.include_router(review_items.router)
v1.include_router(subscriptions.router)
if settings.dev_routes:
    v1.include_router(dev.router)
app.include_router(v1)
