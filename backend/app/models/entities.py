"""MySQL / SQLite 数据模型：用户、权限、项目、任务、评估记录。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(32), default="engineer")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tasks: Mapped[list["Task"]] = relationship(back_populates="owner")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    can_write: Mapped[bool] = mapped_column(Boolean, default=False)


class Project(Base):
    """产品线 / 项目归属。"""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tasks: Mapped[list["Task"]] = relationship(back_populates="project")


class Task(Base):
    """任务主记录：状态流转与当前 Agent。"""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    title: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    current_agent: Mapped[str] = mapped_column(String(32), default="")

    prd_text: Mapped[str] = mapped_column(Text, default="")
    prd_file: Mapped[str] = mapped_column(String(512), default="")
    design_file: Mapped[str] = mapped_column(String(512), default="")
    target_platforms: Mapped[str] = mapped_column(String(128), default="web")

    requirement_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    review_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    self_repair_count: Mapped[int] = mapped_column(Integer, default=0)
    human_intervention: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    output_dir: Mapped[str] = mapped_column(String(512), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped["Project | None"] = relationship(back_populates="tasks")
    owner: Mapped["User | None"] = relationship(back_populates="tasks")


class EvaluationTask(Base):
    """评估任务（evaluation_task）。"""

    __tablename__ = "evaluation_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EvaluationResult(Base):
    """评估汇总结果（evaluation_result）。

    对比文档指出第一版缺少 engineering_score，此处已补齐并接入工程评估器。
    """

    __tablename__ = "evaluation_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    code_score: Mapped[float] = mapped_column(Float, default=0.0)
    visual_score: Mapped[float] = mapped_column(Float, default=0.0)
    requirement_score: Mapped[float] = mapped_column(Float, default=0.0)
    agent_score: Mapped[float] = mapped_column(Float, default=0.0)
    engineering_score: Mapped[float] = mapped_column(Float, default=0.0)
    human_score: Mapped[float] = mapped_column(Float, default=0.0)
    total_score: Mapped[float] = mapped_column(Float, default=0.0)

    hard_gate_passed: Mapped[bool] = mapped_column(Boolean, default=True)
    install_success: Mapped[bool] = mapped_column(Boolean, default=False)
    build_success: Mapped[bool] = mapped_column(Boolean, default=False)
    runtime_success: Mapped[bool] = mapped_column(Boolean, default=False)

    execution_time: Mapped[float] = mapped_column(Float, default=0.0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    self_repair_count: Mapped[int] = mapped_column(Integer, default=0)
    human_intervention: Mapped[bool] = mapped_column(Boolean, default=False)

    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class HumanReview(Base):
    """人工评估记录（1~5 分 + 结构化字段）。"""

    __tablename__ = "human_review"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    reviewer: Mapped[str] = mapped_column(String(64), default="")

    visual: Mapped[int] = mapped_column(Integer, default=0)
    completeness: Mapped[int] = mapped_column(Integer, default=0)
    code_quality: Mapped[int] = mapped_column(Integer, default=0)
    modification_cost: Mapped[int] = mapped_column(Integer, default=0)
    business_fit: Mapped[int] = mapped_column(Integer, default=0)

    error_type: Mapped[str] = mapped_column(String(64), default="")
    error_severity: Mapped[str] = mapped_column(String(32), default="")
    modified_files: Mapped[int] = mapped_column(Integer, default=0)
    modification_count: Mapped[int] = mapped_column(Integer, default=0)
    modification_time: Mapped[float] = mapped_column(Float, default=0.0)
    review_comment: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
