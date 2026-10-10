"""WebMind 主编排（LangGraph StateGraph）。

需求解析 → 页面生成 → 代码审查 →（通过？多端适配 / 不过？回退自修复 ≤2 次 → 人工）
另外：需求置信度低 → 直接转人工澄清。

对应文档：WebMind项目详解.md 第 5 节
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.adapt_agent import adapt_agent
from app.agents.page_agent import page_agent
from app.agents.requirement_agent import requirement_agent
from app.agents.review_agent import review_agent
from app.core.config import settings
from app.core.logging import get_logger
from app.services import cache
from app.workflows.state import WebMindState

logger = get_logger("webmind.workflow")


async def human_node(state: WebMindState) -> dict[str, Any]:
    """人工介入节点：记录原因并等待工程师处理。"""
    task_id = state.get("task_id", "")
    reason = "需求置信度过低，需人工澄清" if state.get("status") == "needs_clarification" else "自动修复次数超限，转人工处理"
    logger.warning("[%s] %s", task_id, reason)
    cache.set_task_status(task_id, "human_required", "human", reason)
    return {
        "status": "human_required",
        "current_agent": "human",
        "human_intervention": True,
        "error": reason,
    }


async def repair_node(state: WebMindState) -> dict[str, Any]:
    """自修复计数节点：每次回退页面生成前累加重试次数。"""
    retry_count = int(state.get("retry_count", 0)) + 1
    logger.info("[%s] 审查未通过，第 %s 次自动修复", state.get("task_id", ""), retry_count)
    cache.set_task_status(state.get("task_id", ""), "repairing", "page", f"第 {retry_count} 次自修复")
    return {"retry_count": retry_count, "status": "repairing"}


def route_after_requirement(state: WebMindState) -> str:
    """置信度低 → 转人工澄清。"""
    if state.get("status") == "needs_clarification":
        return "human"
    return "page"


def route_after_review(state: WebMindState) -> str:
    """审查通过 → 多端适配；未通过且重试 < 2 → 自修复；否则转人工。"""
    review = state.get("review_result") or {}
    if review.get("pass"):
        return "adapt"
    if int(state.get("retry_count", 0)) < settings.MAX_SELF_REPAIR:
        return "repair"
    return "human"


def build_graph() -> Any:
    """构建并编译主编排图。"""
    graph = StateGraph(WebMindState)

    graph.add_node("requirement", requirement_agent)
    graph.add_node("page", page_agent)
    graph.add_node("review", review_agent)
    graph.add_node("adapt", adapt_agent)
    graph.add_node("repair", repair_node)
    graph.add_node("human", human_node)

    graph.add_edge(START, "requirement")
    graph.add_conditional_edges(
        "requirement",
        route_after_requirement,
        {"page": "page", "human": "human"},
    )
    graph.add_edge("page", "review")
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {"adapt": "adapt", "repair": "repair", "human": "human"},
    )
    graph.add_edge("repair", "page")
    graph.add_edge("adapt", END)
    graph.add_edge("human", END)

    checkpointer = MemorySaver() if settings.LANGGRAPH_CHECKPOINT else None
    return graph.compile(checkpointer=checkpointer)


_workflow: Any | None = None


def get_workflow() -> Any:
    global _workflow
    if _workflow is None:
        _workflow = build_graph()
    return _workflow


async def run_workflow(state: WebMindState) -> WebMindState:
    """执行主编排，返回最终状态。"""
    workflow = get_workflow()
    config = {"configurable": {"thread_id": state.get("task_id", "default")}}
    result = await workflow.ainvoke(state, config=config)
    return result
