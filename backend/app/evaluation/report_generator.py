"""评估报告生成（自动报告 + 周度聚合分析 + 反馈闭环建议）。

对应文档：评估体系设计 18 / 19 节
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.models.database import session_scope
from app.models.entities import EvaluationResult
from app.services.task_service import feedback_stats

logger = get_logger("webmind.evaluation.report")


class ReportGenerator:
    """生成评估报告：全局指标 + 错误分布 + 优化建议。"""

    def aggregate(self) -> dict[str, Any]:
        with session_scope() as session:
            rows = session.execute(select(EvaluationResult)).scalars().all()
        if not rows:
            return {"total_tasks": 0, "message": "暂无评估结果"}

        def avg(values: list[float]) -> float:
            return round(sum(values) / len(values), 2)

        total = len(rows)
        build_success = sum(1 for r in rows if r.build_success)
        runtime_success = sum(1 for r in rows if r.runtime_success)

        return {
            "total_tasks": total,
            "code_success_rate": round(build_success / total * 100, 2),
            "runtime_success_rate": round(runtime_success / total * 100, 2),
            "avg_code_score": avg([r.code_score for r in rows]),
            "avg_visual_score": avg([r.visual_score for r in rows]),
            "avg_requirement_score": avg([r.requirement_score for r in rows]),
            "avg_agent_score": avg([r.agent_score for r in rows]),
            "avg_engineering_score": avg([r.engineering_score for r in rows]),
            "avg_total_score": avg([r.total_score for r in rows]),
            "avg_execution_time": avg([r.execution_time or 0 for r in rows]),
            "avg_total_tokens": avg([(r.input_tokens or 0) + (r.output_tokens or 0) for r in rows]),
            "self_repair_tasks": sum(1 for r in rows if (r.self_repair_count or 0) > 0),
            "human_intervention_tasks": sum(1 for r in rows if r.human_intervention),
            "generated_at": datetime.now().isoformat(),
        }

    def error_analysis(self) -> dict[str, Any]:
        """错误类型分布 → 驱动 Prompt / Agent / RAG 优化。"""
        with session_scope() as session:
            rows = session.execute(select(EvaluationResult)).scalars().all()

        buckets = {
            "组件使用问题": 0,
            "需求理解偏差": 0,
            "工程规范问题": 0,
            "代码可运行性": 0,
            "视觉还原偏差": 0,
        }
        for row in rows:
            detail = row.detail or {}
            if (detail.get("code") or {}).get("errors"):
                buckets["代码可运行性"] += len(detail["code"]["errors"])
            if (detail.get("engineering") or {}).get("issues"):
                buckets["工程规范问题"] += len(detail["engineering"]["issues"])
            req_detail = (detail.get("requirement") or {}).get("detail", {})
            if req_detail.get("field", {}).get("hit", 1) == 0:
                buckets["需求理解偏差"] += 1
            if (row.visual_score or 100) < 70:
                buckets["视觉还原偏差"] += 1
            if (detail.get("visual") or {}).get("detail", {}).get("misses"):
                buckets["组件使用问题"] += len(detail["visual"]["detail"]["misses"])

        total = sum(buckets.values()) or 1
        return {
            "distribution": buckets,
            "ratio": {k: round(v / total, 4) for k, v in buckets.items()},
            "top_issue": max(buckets, key=buckets.get),
        }

    def suggestions(self) -> list[str]:
        """按高频错误给出优化建议（评估 → 优化闭环）。"""
        analysis = self.error_analysis()
        top = analysis["top_issue"]
        mapping = {
            "组件使用问题": "增强组件 RAG 文档、收紧组件白名单、在 Prompt 中补充组件示例",
            "需求理解偏差": "优化需求解析 Prompt、补充字段抽取规则、提高低置信度转人工阈值",
            "工程规范问题": "更新代码模板中的目录结构与命名规范、补充 ESLint/Prettier 配置",
            "代码可运行性": "开启 RUN_REAL_BUILD 做真实构建验证、修正依赖版本与引入路径",
            "视觉还原偏差": "补充设计稿结构化描述、提高视觉评估权重校准样本量",
        }
        suggestions = [f"高频问题：{top} → {mapping.get(top, '持续观察')}"]
        stats = feedback_stats()
        if stats["total"]:
            top_feedback = max(stats["distribution"], key=stats["distribution"].get)
            suggestions.append(f"工程师修正原因 Top1：{top_feedback} → 纳入下周 Prompt 迭代")
        return suggestions

    def markdown(self) -> str:
        """生成 Markdown 版评估报告。"""
        agg = self.aggregate()
        analysis = self.error_analysis()
        if agg.get("total_tasks", 0) == 0:
            return "# WebMind Evaluation Report\n\n暂无评估结果。\n"

        lines = [
            "# WebMind Evaluation Report",
            "",
            f"- 生成时间：{agg['generated_at']}",
            f"- 任务数量：{agg['total_tasks']}",
            "",
            "## 核心指标",
            "",
            f"- 构建成功率：{agg['code_success_rate']}%",
            f"- 运行成功率：{agg['runtime_success_rate']}%",
            f"- 平均视觉评分：{agg['avg_visual_score']}（百分制）",
            f"- 需求覆盖率：{agg['avg_requirement_score']}%",
            f"- 平均综合得分：{agg['avg_total_score']}",
            f"- 平均生成耗时：{agg['avg_execution_time']} 秒",
            f"- 平均 Token 消耗：{agg['avg_total_tokens']}",
            f"- 触发自修复任务数：{agg['self_repair_tasks']}",
            f"- 转人工任务数：{agg['human_intervention_tasks']}",
            "",
            "## 分项得分",
            "",
            f"- 代码可用性：{agg['avg_code_score']}",
            f"- 页面还原度：{agg['avg_visual_score']}",
            f"- 需求理解：{agg['avg_requirement_score']}",
            f"- Agent 执行：{agg['avg_agent_score']}",
            f"- 工程规范：{agg['avg_engineering_score']}",
            "",
            "## 错误分布",
            "",
        ]
        for key, value in analysis["distribution"].items():
            lines.append(f"- {key}：{value}（占比 {analysis['ratio'][key] * 100:.1f}%）")
        lines += ["", "## 优化建议", ""]
        lines += [f"- {item}" for item in self.suggestions()]
        lines.append("")
        return "\n".join(lines)

    def save(self) -> str:
        content = self.markdown()
        path = settings.evaluation_output_dir / f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        path.write_text(content, encoding="utf-8")
        logger.info("评估报告已生成: %s", path)
        return str(path)
