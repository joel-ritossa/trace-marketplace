from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.config import settings
from app.errors import register_error_handlers
from app.routers import dev, health, me
from app.worker import broker


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.open_pool()
    await broker.startup()
    yield
    await broker.shutdown()
    await db.close_pool()


app = FastAPI(title="Trace Marketplace API", version="0.1.0", lifespan=lifespan)

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
if settings.dev_routes:
    v1.include_router(dev.router)
app.include_router(v1)
