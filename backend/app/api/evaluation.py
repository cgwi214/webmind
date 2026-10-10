"""评估体系接口：执行评估、查询结果、人工评分、报告、反馈统计与基准回归。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.evaluation.benchmark import BenchmarkRunner
from app.evaluation.evaluator import EvaluationRunner
from app.evaluation.human_evaluator import HumanEvaluator
from app.evaluation.report_generator import ReportGenerator
from app.services.task_service import feedback_stats

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


class HumanReviewRequest(BaseModel):
    reviewer: str = "engineer"
    visual: int = Field(0, ge=0, le=5)
    completeness: int = Field(0, ge=0, le=5)
    code_quality: int = Field(0, ge=0, le=5)
    modification_cost: int = Field(0, ge=0, le=5)
    business_fit: int = Field(0, ge=0, le=5)
    error_type: str = ""
    error_severity: str = ""
    modified_files: int = 0
    modification_count: int = 0
    modification_time: float = 0.0
    review_comment: str = ""


class BenchmarkRequest(BaseModel):
    sample_ids: list[str] = Field(default_factory=list, description="只跑指定样本 id；为空则全量")
    tag: str = Field("", description="本次运行标签，如 prompt-v2 / agent-v3")


@router.post("/run/{task_id}")
async def run_evaluation(task_id: str):
    """对指定任务执行六模块评估。"""
    try:
        return EvaluationRunner().run(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/result/{task_id}")
async def get_result(task_id: str):
    result = EvaluationRunner().latest(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="尚无评估结果，请先执行 /run/{task_id}")
    return result


@router.post("/human/{task_id}")
async def submit_human_review(task_id: str, request: HumanReviewRequest):
    """提交人工评估（1~5 分）。"""
    return HumanEvaluator().submit(task_id, request.model_dump())


@router.get("/human/{task_id}")
async def get_human_review(task_id: str):
    review = HumanEvaluator().latest(task_id)
    if not review:
        raise HTTPException(status_code=404, detail="暂无人工评估")
    return review


@router.get("/dashboard")
async def dashboard():
    """评估看板：全局聚合 + 错误分布 + 优化建议 + 修正原因分布。"""
    generator = ReportGenerator()
    return {
        "aggregate": generator.aggregate(),
        "error_analysis": generator.error_analysis(),
        "suggestions": generator.suggestions(),
        "feedback": feedback_stats(),
    }


@router.get("/report")
async def report(save: bool = False):
    """生成 Markdown 评估报告。"""
    generator = ReportGenerator()
    content = generator.markdown()
    payload = {"content": content}
    if save:
        payload["path"] = generator.save()
    return payload


# ------------------------------------------------------------------ 基准回归
@router.post("/benchmark/run")
async def run_benchmark(request: BenchmarkRequest):
    """在评估数据集上跑一轮基准回归（逐样本跑通主编排 + 六模块评估 + 回归对比）。"""
    try:
        return await BenchmarkRunner().run(
            sample_ids=request.sample_ids or None, tag=request.tag
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/benchmark/latest")
async def benchmark_latest():
    """最近一次基准回归结果。"""
    data = BenchmarkRunner().latest()
    if not data:
        raise HTTPException(status_code=404, detail="尚无基准回归结果，请先执行 /benchmark/run")
    return data


@router.get("/benchmark/runs")
async def benchmark_runs(limit: int = 20):
    """基准回归历史（用于观察"新版本有没有变好"）。"""
    return {"items": BenchmarkRunner().history(limit=limit)}
