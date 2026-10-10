"""Agent 公共工具：计时、Token 累计、状态写入。"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from app.core.logging import get_logger
from app.services import cache
from app.services.llm import TokenUsage

logger = get_logger("webmind.agent")


@contextmanager
def stage(name: str, state: dict[str, Any]) -> Iterator[None]:
    """记录单个 Agent 阶段耗时并写入 Redis/内存状态。"""
    start = time.time()
    task_id = state.get("task_id", "")
    if task_id:
        cache.set_task_status(task_id, state.get("status", "running"), name)
    try:
        yield
    finally:
        cost = round(time.time() - start, 3)
        timings = dict(state.get("timings") or {})
        timings[name] = timings.get(name, 0) + cost
        state["timings"] = timings
        logger.info("[%s] %s 阶段耗时 %.2fs", task_id or "-", name, cost)


def usage_from(state: dict[str, Any]) -> TokenUsage:
    """从 state 恢复 TokenUsage，保证跨 Agent 累计。"""
    usage = TokenUsage()
    tokens = state.get("tokens") or {}
    usage.add(int(tokens.get("input_tokens", 0)), int(tokens.get("output_tokens", 0)))
    return usage


def bump_self_repair(state: dict[str, Any]) -> int:
    count = int(state.get("self_repair_count", 0)) + 1
    state["self_repair_count"] = count
    return count


class Timer:
    """轻量计时器，供副编排子任务统计耗时。"""

    def __init__(self) -> None:
        self.records: dict[str, float] = {}

    def run(self, name: str, fn: Callable[[], Any]) -> Any:
        start = time.time()
        try:
            return fn()
        finally:
            self.records[name] = round(time.time() - start, 3)
