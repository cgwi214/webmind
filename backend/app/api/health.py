"""健康检查：展示各后端组件的实际运行后端（真实服务 / 降级实现）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.models.database import active_backend
from app.rag.retriever import get_retriever
from app.services import cache, doc_store, llm as llm_service

router = APIRouter(tags=["system"])


@router.get("/api/health")
async def health():
    try:
        retriever = get_retriever()
        whitelist = sorted(retriever.whitelist())
    except Exception:  # noqa: BLE001
        whitelist = []

    return {
        "service": settings.APP_NAME,
        "status": "running",
        "env": settings.ENV,
        "backends": {
            "database": active_backend(),
            "doc_store": "mongo" if doc_store.get_doc_store().__class__.__name__ == "MongoDocStore" else "memory",
            "cache": cache.cache_backend_name(),
        },
        "llm": {
            "provider": settings.LLM_PROVIDER,
            "model": settings.MODEL_NAME,
            "mock_mode": llm_service.mock_mode(),
        },
        "rag": {"components": len(whitelist), "whitelist_sample": whitelist[:8]},
        "max_self_repair": settings.MAX_SELF_REPAIR,
    }


@router.get("/api/projects")
async def projects():
    from sqlalchemy import select

    from app.models.database import session_scope
    from app.models.entities import Project

    with session_scope() as session:
        rows = session.execute(select(Project)).scalars().all()
        return [
            {"id": p.id, "name": p.name, "code": p.code, "description": p.description} for p in rows
        ]
