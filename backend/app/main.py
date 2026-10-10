"""WebMind FastAPI 入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import evaluation, health, task
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.models.database import init_db

setup_logging()
logger = get_logger("webmind.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s 启动完成：http://%s:%s/docs", settings.APP_NAME, settings.BACKEND_HOST, settings.BACKEND_PORT)
    yield
    logger.info("%s 已停止", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description="WebMind · 多 Agent 前端智能研发平台",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(task.router)
app.include_router(evaluation.router)
app.include_router(health.router)


@app.get("/")
def index():
    return {
        "service": settings.APP_NAME,
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
    }
