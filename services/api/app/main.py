from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.clients import db, redis, storage
from app.config import settings
from app.errors import register_error_handlers
from app.middleware.rate_limit import RateLimitMiddleware
from app.routers import dev, health, me, uploads
from app.worker.broker import broker


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
# headers for the browser.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.web_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

v1 = APIRouter(prefix="/v1")
v1.include_router(health.router)
v1.include_router(me.router)
v1.include_router(uploads.router)
if settings.dev_routes:
    v1.include_router(dev.router)
app.include_router(v1)
