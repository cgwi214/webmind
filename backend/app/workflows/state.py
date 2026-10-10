"""LangGraph 主编排状态定义。"""

from __future__ import annotations

from typing import Any, TypedDict


class WebMindState(TypedDict, total=False):
    """任务在多个 Agent 之间流转的共享状态。"""

    # 基础信息
    task_id: str
    prd: str
    design_note: str
    target_platforms: list[str]
    project_id: int | None

    # 需求解析
    requirement_json: dict
    confidence: float

    # 页面生成
    layout_tree: dict
    component_mapping: dict
    rag_context: list[dict]
    generated_code: str
    code_files: dict[str, str]
    output_dir: str
    zip_path: str

    # 代码审查
    review_result: dict
    retry_count: int
    self_repair_count: int
    human_intervention: bool

    # 多端适配与交付
    uniapp_code: dict[str, str]
    final_output: dict

    # 运行时
    status: str
    current_agent: str
    error: str
    tokens: dict
    timings: dict
    model_mode: str
    meta: dict[str, Any]


def initial_state(task_id: str, prd: str, **kwargs: Any) -> WebMindState:
    """构造初始状态。"""
    state: WebMindState = {
        "task_id": task_id,
        "prd": prd,
        "design_note": kwargs.get("design_note", ""),
        "target_platforms": kwargs.get("target_platforms") or ["web"],
        "project_id": kwargs.get("project_id"),
        "status": "queued",
        "current_agent": "",
        "retry_count": 0,
        "self_repair_count": 0,
        "human_intervention": False,
        "tokens": {},
        "timings": {},
    }
    state.update({k: v for k, v in kwargs.items() if k in WebMindState.__annotations__})
    return state
