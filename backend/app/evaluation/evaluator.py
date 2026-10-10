"""评估调度器（EvaluationRunner）。

第一版文档的缺口已修正：
1. engineering_score 补齐并写入 evaluation_result
2. QualityEvaluator 真正接入调度器
3. 综合评分前先过 Hard Gate（安装 / 构建 / 启动 / 核心功能）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.evaluation.agent_evaluator import AgentEvaluator
from app.evaluation.code_evaluator import CodeEvaluator
from app.evaluation.human_evaluator import HumanEvaluator
from app.evaluation.quality_evaluator import QualityEvaluator
from app.evaluation.requirement_evaluator import RequirementEvaluator
from app.evaluation.visual_evaluator import VisualEvaluator
from app.models.database import session_scope
from app.models.entities import EvaluationResult, EvaluationTask
from app.services import doc_store, task_service

logger = get_logger("webmind.evaluation")


class EvaluationRunner:
    """六合一评估调度器。"""

    def __init__(self) -> None:
        self.code_evaluator = CodeEvaluator()
        self.visual_evaluator = VisualEvaluator()
        self.requirement_evaluator = RequirementEvaluator()
        self.agent_evaluator = AgentEvaluator()
        self.quality_evaluator = QualityEvaluator()
        self.human_evaluator = HumanEvaluator()

    # ---------------- 数据装载 ----------------
    def _load_run(self, task_id: str) -> dict[str, Any]:
        records = doc_store.find("task_runs", {"task_id": task_id}, limit=10)
        return records[-1] if records else {}

    def run(self, task_id: str) -> dict[str, Any]:
        task = task_service.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        bundle = task_service.get_code_files(task_id)
        files: dict[str, str] = bundle.get("files") or {}
        requirement = task.get("requirement_json") or {}
        run = self._load_run(task_id)
        timings = run.get("timings") or {}
        design_note = run.get("design_note", "")
        human_review = self.human_evaluator.latest(task_id)

        task_payload = {
            "status": task.get("status", ""),
            "retry_count": task.get("retry_count", 0),
            "self_repair_count": task.get("self_repair_count", 0),
            "human_intervention": task.get("human_intervention", False),
            "tokens": run.get("tokens") or {},
            "execution_time": timings and round(sum(timings.values()), 2) or 0,
        }

        # ---------------- 六个评估模块 ----------------
        code = self.code_evaluator.evaluate(files, requirement)
        visual = self.visual_evaluator.evaluate(files, design_note, human_review)
        requirement_eval = self.requirement_evaluator.evaluate(requirement, files)
        agent = self.agent_evaluator.evaluate(task_payload, timings)
        engineering = self.quality_evaluator.evaluate(files)
        human = self.human_evaluator.evaluate(task_id)

        # ---------------- Hard Gate ----------------
        # 与文档一致：安装 / 构建 / 启动 / 核心功能 任一失败即封顶
        hard_gate_passed = bool(
            code["install_success"]
            and code["build_success"]
            and code["start_success"]
            and code["runtime_success"]
        )
        weights = settings.weights
        total = round(
            code["score"] * weights["code"]
            + visual["score"] * weights["visual"]
            + requirement_eval["score"] * weights["requirement"]
            + agent["score"] * weights["agent"]
            + engineering["score"] * weights["engineering"],
            2,
        )
        if settings.EVAL_HARD_GATE and not hard_gate_passed:
            total = round(min(total, 40.0), 2)
            logger.warning("[%s] Hard Gate 未通过，总分封顶 40", task_id)

        result = {
            "task_id": task_id,
            "code_score": code["score"],
            "visual_score": visual["score"],
            "requirement_score": requirement_eval["score"],
            "agent_score": agent["score"],
            "engineering_score": engineering["score"],
            "human_score": human["score"],
            "total_score": total,
            "hard_gate_passed": hard_gate_passed,
            "install_success": code["install_success"],
            "build_success": code["build_success"],
            "runtime_success": code["runtime_success"],
            "execution_time": task_payload["execution_time"],
            "input_tokens": agent["input_tokens"],
            "output_tokens": agent["output_tokens"],
            "retry_count": agent["retry_count"],
            "self_repair_count": agent["self_repair_count"],
            "human_intervention": agent["human_intervention"],
            "cost_per_successful_task": agent["cost_per_successful_task"],
            "weights": weights,
            "detail": {
                "code": code,
                "visual": visual,
                "requirement": requirement_eval,
                "agent": agent,
                "engineering": engineering,
                "human": human,
            },
        }

        self._persist(result)
        doc_store.insert("evaluation_reports", {"task_id": task_id, "result": result})
        logger.info(
            "[%s] 评估完成：总分 %.2f（代码 %.1f / 视觉 %.1f / 需求 %.1f / Agent %.1f / 工程 %.1f）",
            task_id,
            total,
            code["score"],
            visual["score"],
            requirement_eval["score"],
            agent["score"],
            engineering["score"],
        )
        return result

    def _persist(self, result: dict[str, Any]) -> None:
        with session_scope() as session:
            row = EvaluationResult(
                task_id=result["task_id"],
                code_score=result["code_score"],
                visual_score=result["visual_score"],
                requirement_score=result["requirement_score"],
                agent_score=result["agent_score"],
                engineering_score=result["engineering_score"],
                human_score=result["human_score"] or 0.0,
                total_score=result["total_score"],
                hard_gate_passed=result["hard_gate_passed"],
                install_success=result["install_success"],
                build_success=result["build_success"],
                runtime_success=result["runtime_success"],
                execution_time=result["execution_time"],
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                retry_count=result["retry_count"],
                self_repair_count=result["self_repair_count"],
                human_intervention=result["human_intervention"],
                detail=result["detail"],
            )
            session.add(row)
            session.flush()
            result_id = row.id

            exists = session.execute(
                select(EvaluationTask).where(EvaluationTask.task_id == result["task_id"])
            ).scalar_one_or_none()
            if exists:
                exists.status = "done"
            else:
                session.add(
                    EvaluationTask(
                        task_id=result["task_id"], status="done", created_time=datetime.now()
                    )
                )
        result["result_id"] = result_id

    def latest(self, task_id: str) -> dict[str, Any] | None:
        with session_scope() as session:
            row = (
                session.execute(
                    select(EvaluationResult)
                    .where(EvaluationResult.task_id == task_id)
                    .order_by(EvaluationResult.id.desc())
                )
                .scalars()
                .first()
            )
            if not row:
                return None
            return {
                "task_id": row.task_id,
                "code_score": row.code_score,
                "visual_score": row.visual_score,
                "requirement_score": row.requirement_score,
                "agent_score": row.agent_score,
                "engineering_score": row.engineering_score,
                "human_score": row.human_score,
                "total_score": row.total_score,
                "hard_gate_passed": row.hard_gate_passed,
                "install_success": row.install_success,
                "build_success": row.build_success,
                "runtime_success": row.runtime_success,
                "execution_time": row.execution_time,
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "retry_count": row.retry_count,
                "self_repair_count": row.self_repair_count,
                "human_intervention": row.human_intervention,
                "detail": row.detail,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
