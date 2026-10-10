"""人工评估模块（HumanEvaluator）。

评分项：视觉效果 / 功能完整度 / 代码质量 / 修改成本 / 业务需求符合度（均为 1~5 分）
结构化字段：error_type / error_severity / modified_files / modification_count /
modification_time / review_comment
对应文档：评估体系设计 17.1~17.2 + 对比文档 8.6
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.models.database import session_scope
from app.models.entities import HumanReview

logger = get_logger("webmind.evaluation.human")

DIMENSIONS = ("visual", "completeness", "code_quality", "modification_cost", "business_fit")
LABELS = {
    "visual": "视觉效果",
    "completeness": "功能完整度",
    "code_quality": "代码质量",
    "modification_cost": "修改成本",
    "business_fit": "业务需求符合度",
}


class HumanEvaluator:
    """人工评分的写入与聚合。"""

    def submit(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with session_scope() as session:
            review = HumanReview(
                task_id=task_id,
                reviewer=payload.get("reviewer", "engineer"),
                visual=int(payload.get("visual", 0)),
                completeness=int(payload.get("completeness", 0)),
                code_quality=int(payload.get("code_quality", 0)),
                modification_cost=int(payload.get("modification_cost", 0)),
                business_fit=int(payload.get("business_fit", 0)),
                error_type=payload.get("error_type", ""),
                error_severity=payload.get("error_severity", ""),
                modified_files=int(payload.get("modified_files", 0)),
                modification_count=int(payload.get("modification_count", 0)),
                modification_time=float(payload.get("modification_time", 0.0)),
                review_comment=payload.get("review_comment", ""),
            )
            session.add(review)
            session.flush()
            review_id = review.id
        logger.info("[%s] 人工评估提交成功，记录 #%s", task_id, review_id)
        return {"task_id": task_id, "review_id": review_id, **self.evaluate(task_id)}

    def latest(self, task_id: str) -> dict[str, Any] | None:
        with session_scope() as session:
            row = (
                session.execute(
                    select(HumanReview).where(HumanReview.task_id == task_id).order_by(HumanReview.id.desc())
                )
                .scalars()
                .first()
            )
            if not row:
                return None
            return {
                "task_id": row.task_id,
                "reviewer": row.reviewer,
                "visual": row.visual,
                "completeness": row.completeness,
                "code_quality": row.code_quality,
                "modification_cost": row.modification_cost,
                "business_fit": row.business_fit,
                "error_type": row.error_type,
                "error_severity": row.error_severity,
                "modified_files": row.modified_files,
                "modification_count": row.modification_count,
                "modification_time": row.modification_time,
                "review_comment": row.review_comment,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

    def evaluate(self, task_id: str) -> dict[str, Any]:
        """把 1~5 分人工评分折算为 0~100 分。"""
        review = self.latest(task_id)
        if not review:
            return {"score": None, "source": "none", "dimensions": {}}
        scored = {dim: int(review.get(dim) or 0) for dim in DIMENSIONS}
        scored = {k: v for k, v in scored.items() if v > 0}
        if not scored:
            return {"score": None, "source": "none", "dimensions": {}}
        score = round(sum(scored.values()) / len(scored) / 5 * 100, 2)
        return {
            "score": score,
            "source": "human",
            "dimensions": {LABELS[k]: v for k, v in scored.items()},
            "raw": scored,
            "error_type": review.get("error_type"),
            "error_severity": review.get("error_severity"),
        }
