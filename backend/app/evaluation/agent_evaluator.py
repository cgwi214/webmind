"""Agent 执行质量评估模块（AgentEvaluator）。

指标：成功率 / 执行时间 / Token / Retry / 自修复次数 / 人工介入 / 单次成功成本
对应文档：评估体系设计 8.1~8.2 + 对比文档 8.4
"""

from __future__ import annotations

from typing import Any

# 单价（元 / 千 token），用于估算单次成功任务成本
INPUT_PRICE_PER_K = 0.01
OUTPUT_PRICE_PER_K = 0.03


class AgentEvaluator:
    """评估 Agent 执行效率与稳定性。"""

    def evaluate(self, task_row: dict[str, Any], timings: dict[str, float] | None = None) -> dict[str, Any]:
        timings = timings or {}
        status = task_row.get("status", "")
        success = status in ("delivered", "confirmed")

        execution_time = round(sum(timings.values()), 2) if timings else float(
            task_row.get("execution_time") or 0
        )
        tokens = task_row.get("tokens") or {}
        input_tokens = int(tokens.get("input_tokens", 0))
        output_tokens = int(tokens.get("output_tokens", 0))

        retry_count = int(task_row.get("retry_count", 0))
        self_repair_count = int(task_row.get("self_repair_count", 0))
        human_intervention = bool(task_row.get("human_intervention", False))

        # 成功率（单任务视角：成功=100，失败=0）
        success_score = 100.0 if success else 0.0
        # 效率分：10 分钟内满分，超时线性衰减
        time_score = max(0.0, 100 - max(0.0, execution_time - 600) / 60 * 5)
        # 成本分：消耗越高分越低
        token_score = max(0.0, 100 - (input_tokens + output_tokens) / 1000 * 5)
        # 稳定性分：重试、自修复、人工介入均扣分
        stability_score = max(
            0.0, 100 - retry_count * 15 - self_repair_count * 10 - (30 if human_intervention else 0)
        )

        score = round(
            success_score * 0.4 + time_score * 0.2 + token_score * 0.15 + stability_score * 0.25, 2
        )

        cost = round(
            input_tokens / 1000 * INPUT_PRICE_PER_K + output_tokens / 1000 * OUTPUT_PRICE_PER_K, 4
        )

        return {
            "score": score,
            "success": success,
            "success_rate": 1.0 if success else 0.0,
            "execution_time": execution_time,
            "stage_timings": timings,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "retry_count": retry_count,
            "self_repair_count": self_repair_count,
            "human_intervention": human_intervention,
            "cost_per_task": cost,
            "cost_per_successful_task": cost if success else None,
            "detail": {
                "success_score": success_score,
                "time_score": round(time_score, 2),
                "token_score": round(token_score, 2),
                "stability_score": round(stability_score, 2),
            },
        }
