"""任务接口：创建任务、查询状态、查看/下载代码、确认合并反馈。"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services import task_service

router = APIRouter(prefix="/api/task", tags=["task"])


class TaskCreateRequest(BaseModel):
    prd: str = Field(..., description="需求文本（PRD 内容）")
    title: str = ""
    project_id: int | None = None
    target_platforms: list[str] = Field(default_factory=lambda: ["web"])
    design_note: str = ""
    owner: str = "admin"


class ConfirmRequest(BaseModel):
    correction_type: str = "无需修正"
    reviewer: str = "engineer"
    comment: str = ""
    modified_files: int = 0
    modification_count: int = 0
    modification_time: float = 0.0
    human_scores: dict[str, int] = Field(default_factory=dict)


@router.post("/create")
async def create(request: TaskCreateRequest):
    """创建任务并异步执行主编排。"""
    if not request.prd.strip():
        raise HTTPException(status_code=400, detail="PRD 内容不能为空")
    return task_service.create_task(
        prd=request.prd,
        title=request.title,
        project_id=request.project_id,
        target_platforms=request.target_platforms,
        design_note=request.design_note,
        owner=request.owner,
    )


@router.post("/upload")
async def upload(
    prd: str = Form(""),
    title: str = Form(""),
    target_platforms: str = Form("web"),
    design_note: str = Form(""),
    prd_file: UploadFile | None = File(None),
    design_file: UploadFile | None = File(None),
):
    """上传 PRD / UI 设计稿文件后创建任务。"""
    prd_file_path = ""
    design_file_path = ""
    upload_dir = settings.upload_dir

    if prd_file is not None:
        target = upload_dir / f"{prd_file.filename}"
        with target.open("wb") as buffer:
            shutil.copyfileobj(prd_file.file, buffer)
        prd_file_path = str(target)
        if not prd and target.suffix.lower() in {".md", ".txt", ".markdown"}:
            prd = target.read_text(encoding="utf-8", errors="ignore")

    if design_file is not None:
        target = upload_dir / f"{design_file.filename}"
        with target.open("wb") as buffer:
            shutil.copyfileobj(design_file.file, buffer)
        design_file_path = str(target)

    if not prd.strip():
        raise HTTPException(status_code=400, detail="PRD 内容为空，请填写文本或上传 .md/.txt 文件")

    platforms = [p.strip() for p in target_platforms.split(",") if p.strip()] or ["web"]
    return task_service.create_task(
        prd=prd,
        title=title,
        target_platforms=platforms,
        design_note=design_note,
        prd_file=prd_file_path,
        design_file=design_file_path,
    )


@router.get("/list")
async def list_tasks(status: str | None = None, limit: int = 50):
    return {"items": task_service.list_tasks(status=status, limit=limit), "queue": task_service.cache.queue_snapshot()}


@router.get("/{task_id}")
async def get_task(task_id: str):
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/{task_id}/files")
async def get_files(task_id: str, version: int | None = None):
    files = task_service.get_code_files(task_id, version)
    if not files:
        raise HTTPException(status_code=404, detail="尚无生成结果或任务仍在执行")
    return files


@router.get("/{task_id}/download")
async def download(task_id: str):
    zip_path = task_service.get_zip_path(task_id)
    if not zip_path or not Path(zip_path).exists():
        raise HTTPException(status_code=404, detail="代码包尚未生成")
    return FileResponse(zip_path, filename=Path(zip_path).name, media_type="application/zip")


@router.post("/{task_id}/confirm")
async def confirm(task_id: str, request: ConfirmRequest):
    """工程师确认合并 + 填写修正原因（离线迭代原料）。"""
    return task_service.confirm_merge(
        task_id=task_id,
        correction_type=request.correction_type,
        reviewer=request.reviewer,
        comment=request.comment,
        modified_files=request.modified_files,
        modification_count=request.modification_count,
        modification_time=request.modification_time,
        human_scores=request.human_scores,
    )
