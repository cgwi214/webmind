"""任务服务：创建任务、驱动 LangGraph 执行、状态查询、交付与反馈闭环。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.models.database import session_scope
from app.models.entities import Task
from app.services import cache, doc_store
from app.workflows.graph import run_workflow
from app.workflows.state import initial_state

logger = get_logger("webmind.task")

_background_tasks: set[asyncio.Task] = set()


def create_task(
    prd: str,
    title: str = "",
    project_id: int | None = None,
    target_platforms: list[str] | None = None,
    design_note: str = "",
    prd_file: str = "",
    design_file: str = "",
    owner: str = "admin",
) -> dict[str, Any]:
    """创建任务：写 MySQL → 入 Redis 队列 → 异步执行 LangGraph。"""
    task_id = uuid.uuid4().hex[:16]
    platforms = target_platforms or ["web"]

    with session_scope() as session:
        owner_id = None
        from app.models.entities import User

        user = session.execute(select(User).where(User.username == owner)).scalar_one_or_none()
        if user:
            owner_id = user.id
        task = Task(
            task_id=task_id,
            project_id=project_id,
            owner_id=owner_id,
            title=title or (prd.strip().splitlines()[0][:50] if prd.strip() else "未命名需求"),
            status="queued",
            current_agent="",
            prd_text=prd,
            prd_file=prd_file,
            design_file=design_file,
            target_platforms=",".join(platforms),
        )
        session.add(task)
        session.flush()
        task_pk = task.id

    cache.enqueue(task_id)
    cache.set_task_status(task_id, "queued", "", "任务已入队")
    logger.info("[%s] 任务创建成功，产品线=%s，目标端=%s", task_id, project_id, platforms)

    # 异步执行主编排
    loop = asyncio.get_event_loop()
    job = loop.create_task(
        _execute_task(task_id, task_pk, prd, design_note, platforms, project_id)
    )
    _background_tasks.add(job)
    job.add_done_callback(_background_tasks.discard)

    return {
        "task_id": task_id,
        "status": "queued",
        "title": title or "未命名需求",
        "target_platforms": platforms,
    }


async def run_task_now(
    prd: str,
    title: str = "",
    project_id: int | None = None,
    target_platforms: list[str] | None = None,
    design_note: str = "",
    owner: str = "benchmark",
) -> str:
    """同步创建并等待一条任务跑完，返回 task_id。

    与 ``create_task`` 的区别：不把主编排放进后台事件循环，而是直接 ``await``，
    便于基准回归（Benchmark）等需要"跑完再评估"的场景按顺序取结果。
    """
    task_id = uuid.uuid4().hex[:16]
    platforms = target_platforms or ["web"]

    with session_scope() as session:
        owner_id = None
        from app.models.entities import User

        user = session.execute(select(User).where(User.username == owner)).scalar_one_or_none()
        if user:
            owner_id = user.id
        task = Task(
            task_id=task_id,
            project_id=project_id,
            owner_id=owner_id,
            title=title or (prd.strip().splitlines()[0][:50] if prd.strip() else "未命名需求"),
            status="queued",
            current_agent="",
            prd_text=prd,
            target_platforms=",".join(platforms),
        )
        session.add(task)
        session.flush()
        task_pk = task.id

    cache.enqueue(task_id)
    cache.set_task_status(task_id, "queued", "", "基准回归任务已入队")
    logger.info("[%s] 基准回归任务创建，目标端=%s", task_id, platforms)

    await _execute_task(task_id, task_pk, prd, design_note, platforms, project_id)
    return task_id


async def _execute_task(
    task_id: str,
    task_pk: int,
    prd: str,
    design_note: str,
    platforms: list[str],
    project_id: int | None,
) -> None:
    """执行主编排并把结果写回数据库。"""
    try:
        state = initial_state(
            task_id=task_id,
            prd=prd,
            design_note=design_note,
            target_platforms=platforms,
            project_id=project_id,
        )
        cache.set_task_status(task_id, "parsing", "requirement", "开始需求解析")
        result = await run_workflow(state)

        status = result.get("status", "delivered")
        # 运行记录：供评估体系统计耗时 / Token / 重试
        doc_store.insert(
            "task_runs",
            {
                "task_id": task_id,
                "status": status,
                "timings": result.get("timings", {}),
                "tokens": result.get("tokens", {}),
                "design_note": design_note,
                "target_platforms": platforms,
                "model_mode": result.get("model_mode", "heuristic"),
                "created_at": datetime.now().isoformat(),
            },
        )
        with session_scope() as session:
            task = session.get(Task, task_pk)
            if task:
                task.status = status
                task.current_agent = result.get("current_agent", "")
                task.requirement_json = result.get("requirement_json")
                task.review_summary = result.get("review_result")
                task.retry_count = int(result.get("retry_count", 0))
                task.self_repair_count = int(result.get("self_repair_count", 0))
                task.human_intervention = bool(result.get("human_intervention", False))
                task.confidence = float(result.get("confidence", 0.0))
                task.output_dir = result.get("output_dir", "")
                task.finished_at = datetime.now()
        cache.dequeue(task_id)
        cache.set_task_status(task_id, status, result.get("current_agent", ""), "任务结束")
        logger.info("[%s] 任务执行完成，状态=%s", task_id, status)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] 任务执行失败: %s", task_id, exc)
        with session_scope() as session:
            task = session.get(Task, task_pk)
            if task:
                task.status = "failed"
                task.error_message = str(exc)
                task.finished_at = datetime.now()
        cache.dequeue(task_id)
        cache.set_task_status(task_id, "failed", "", str(exc))


def list_tasks(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with session_scope() as session:
        stmt = select(Task).order_by(Task.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(Task.status == status)
        rows = session.execute(stmt).scalars().all()
        return [_task_to_dict(task) for task in rows]


def get_task(task_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        task = session.execute(select(Task).where(Task.task_id == task_id)).scalar_one_or_none()
        if not task:
            return None
        return _task_to_dict(task)


def _task_to_dict(task: Task) -> dict[str, Any]:
    live = cache.get_task_status(task.task_id) or {}
    return {
        "task_id": task.task_id,
        "title": task.title,
        "project_id": task.project_id,
        "status": live.get("status") or task.status,
        "current_agent": live.get("current_agent") or task.current_agent,
        "message": live.get("message", ""),
        "confidence": task.confidence,
        "retry_count": task.retry_count,
        "self_repair_count": task.self_repair_count,
        "human_intervention": task.human_intervention,
        "target_platforms": (task.target_platforms or "web").split(","),
        "requirement_json": task.requirement_json,
        "review_summary": task.review_summary,
        "output_dir": task.output_dir,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "agent_states": cache.get_agent_states(task.task_id),
    }


def get_code_files(task_id: str, version: int | None = None) -> dict[str, Any]:
    """读取某次生成的代码文件（默认最新版本）。"""
    versions = doc_store.find("code_versions", {"task_id": task_id}, limit=100)
    # 多端适配产物（uni-app）单独存放，不参与 Web 版本迭代
    versions = [
        v
        for v in versions
        if isinstance(v.get("version"), int) and v.get("platform") != "uniapp"
    ]
    if not versions:
        return {}
    record = versions[-1] if version is None else next(
        (v for v in versions if v.get("version") == version), versions[-1]
    )
    output_dir = Path(record.get("output_dir", ""))
    files: dict[str, str] = {}
    if output_dir.exists():
        for path in sorted(output_dir.rglob("*")):
            if path.is_file() and path.suffix in {".vue", ".ts", ".json", ".md", ".html"}:
                files[path.relative_to(output_dir).as_posix()] = path.read_text(encoding="utf-8")
    return {
        "version": record.get("version"),
        "output_dir": record.get("output_dir"),
        "zip_path": record.get("zip_path"),
        "files": files,
        "versions": [v.get("version") for v in versions],
    }


def get_zip_path(task_id: str) -> Path | None:
    zips = sorted((settings.code_output_dir / task_id).glob("*.zip")) if (settings.code_output_dir / task_id).exists() else []
    return zips[-1] if zips else None


def confirm_merge(
    task_id: str,
    correction_type: str = "无需修正",
    reviewer: str = "engineer",
    comment: str = "",
    modified_files: int = 0,
    modification_count: int = 0,
    modification_time: float = 0.0,
    human_scores: dict[str, int] | None = None,
) -> dict[str, Any]:
    """工程师确认合并：写修正记录（离线迭代原料）并关闭任务。"""
    doc_store.insert(
        "feedback_records",
        {
            "task_id": task_id,
            "correction_type": correction_type,
            "reviewer": reviewer,
            "comment": comment,
            "modified_files": modified_files,
            "modification_count": modification_count,
            "modification_time": modification_time,
            "human_scores": human_scores or {},
            "created_at": datetime.now().isoformat(),
        },
    )
    with session_scope() as session:
        task = session.execute(select(Task).where(Task.task_id == task_id)).scalar_one_or_none()
        if task:
            task.status = "confirmed"
            task.finished_at = datetime.now()
    cache.set_task_status(task_id, "confirmed", "", "工程师已确认合并")
    logger.info("[%s] 工程师确认合并，修正类型=%s", task_id, correction_type)
    return {"task_id": task_id, "status": "confirmed", "correction_type": correction_type}


def feedback_stats() -> dict[str, Any]:
    """修正原因分布（评估体系的数据消费端）。"""
    records = doc_store.find("feedback_records", limit=1000)
    distribution: dict[str, int] = {}
    for record in records:
        key = record.get("correction_type") or "未填写"
        distribution[key] = distribution.get(key, 0) + 1
    total = sum(distribution.values()) or 1
    return {
        "total": sum(distribution.values()),
        "distribution": distribution,
        "ratio": {k: round(v / total, 4) for k, v in distribution.items()},
    }
