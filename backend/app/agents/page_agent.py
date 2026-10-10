"""页面生成 Agent（Page Generate Agent）。

内嵌副编排：布局解析 ∥ 组件映射 → 合并 → 代码生成 → 组件白名单校验。
对应文档：WebMind项目详解.md 4.2 / 5 节（副编排并行化）
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.agents.base import bump_self_repair, stage, usage_from
from app.core.config import settings
from app.core.logging import get_logger
from app.rag.retriever import get_retriever
from app.services import cache, doc_store, llm
from app.services.codegen import detect_type, generate_project, to_identifier

logger = get_logger("webmind.agent.page")

SYSTEM_PROMPT = """你是 WebMind 的组件映射 Agent。
根据页面需求与检索到的组件文档，为每个页面选择最合适的组件。

严格输出 JSON：
{
  "pages": [
    {"name": "页面名称", "components": ["el-table", "el-form"], "reason": "一句话理由"}
  ]
}

约束：components 只能从给定组件白名单中选择，不得虚构。
"""


# ===================== 副编排子任务 =====================


async def _layout_parse(requirement_json: dict) -> dict:
    """子任务一：把页面需求拆成结构树（页头 / 搜索区 / 表格区 / 分页）。"""
    await asyncio.sleep(0)
    trees = {}
    for index, page in enumerate(requirement_json.get("pages", [])):
        page_type = page.get("type") or detect_type(page.get("name", ""))
        blocks = ["header"]
        if page_type in ("table", "dashboard"):
            blocks += ["search", "table", "pagination"]
        elif page_type in ("form", "config"):
            blocks += ["form", "actions"]
        elif page_type == "detail":
            blocks += ["descriptions"]
        else:
            blocks += ["form"]
        trees[to_identifier(page.get("name", ""), index)] = {
            "page": page.get("name"),
            "type": page_type,
            "blocks": blocks,
        }
    return trees


async def _component_mapping(requirement_json: dict, usage) -> dict:
    """子任务二：结合 RAG 组件文档为每个页面匹配组件（白名单内）。"""
    retriever = get_retriever()
    whitelist = retriever.whitelist()
    mapping: dict[str, list[str]] = {}

    pages = requirement_json.get("pages", [])
    query = " ".join(
        f'{p.get("name", "")} {p.get("type", "")} {" ".join(p.get("functions", []))}' for p in pages
    )
    rag_context = retriever.search(query or "列表页 表单", top_k=6)
    for page in pages:
        mapping[page.get("name", "")] = sorted(
            {chunk["component"] for chunk in rag_context if chunk["component"]}
        )

    # LLM 可用时，让模型基于检索结果做一次组件选择（仍受白名单约束）
    raw = llm.chat(
        SYSTEM_PROMPT,
        "组件白名单：\n"
        + ", ".join(sorted(whitelist))
        + "\n\n页面需求：\n"
        + json.dumps(pages, ensure_ascii=False)
        + "\n\nRAG 检索到的组件文档：\n"
        + json.dumps(rag_context, ensure_ascii=False),
        usage=usage,
    )
    if raw:
        data = llm.extract_json(raw)
        if isinstance(data, dict):
            for item in data.get("pages", []):
                name = item.get("name")
                if not name:
                    continue
                components = [c for c in item.get("components", []) if c in whitelist]
                if components:
                    mapping[name] = components
    return {"mapping": mapping, "rag_context": rag_context, "whitelist": sorted(whitelist)}


# ===================== 主节点 =====================


def _persist(task_id: str, files: dict[str, str], version: int) -> Path:
    output_dir = settings.code_output_dir / task_id / f"v{version}"
    for rel_path, content in files.items():
        target = output_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return output_dir


def _write_zip(task_id: str, output_dir: Path) -> str:
    """产出可下载 zip 包。"""
    import zipfile

    zip_path = settings.code_output_dir / task_id / f"{task_id}-v{output_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in output_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(output_dir))
    return str(zip_path)


async def page_agent(state: dict[str, Any]) -> dict[str, Any]:
    """页面生成节点：需求 JSON → Vue3 工程代码。"""
    task_id = state.get("task_id", "")
    requirement_json = state.get("requirement_json") or {}
    usage = usage_from(state)
    retriever = get_retriever()

    with stage("page", state):
        # ---------- 副编排：两个子任务并行 ----------
        layout_task = asyncio.create_task(_layout_parse(requirement_json))
        mapping_task = asyncio.create_task(_component_mapping(requirement_json, usage))
        layout_tree, mapping_result = await asyncio.gather(layout_task, mapping_task)

        rag_context = mapping_result["rag_context"]
        mapping = mapping_result["mapping"]
        for page in requirement_json.get("pages", []):
            if mapping.get(page.get("name")):
                page["components"] = mapping[page["name"]]

        # ---------- 代码生成 ----------
        project_name = requirement_json.get("project_name") or "WebMind 生成工程"
        files = generate_project(requirement_json, project_name)

        # ---------- 组件白名单校验（防幻觉） ----------
        invalid: list[str] = []
        for rel_path, content in files.items():
            if rel_path.endswith(".vue"):
                invalid.extend(retriever.validate_components(content))
        if invalid:
            logger.warning("[%s] 检测到白名单外组件 %s，执行回退重写", task_id, invalid)
            # 重写：将未知组件替换为受支持的基础组件
            for rel_path, content in list(files.items()):
                if rel_path.endswith(".vue"):
                    for component in set(invalid):
                        content = content.replace(f"<{component}", "<el-input").replace(
                            f"</{component}>", "</el-input>"
                        )
                    files[rel_path] = content

        # ---------- 版本与持久化 ----------
        previous = doc_store.find("code_versions", {"task_id": task_id}, limit=100)
        version = len(previous) + 1
        output_dir = _persist(task_id, files, version)
        zip_path = _write_zip(task_id, output_dir)

        doc_store.insert(
            "code_versions",
            {
                "task_id": task_id,
                "version": version,
                "files": {k: len(v) for k, v in files.items()},
                "output_dir": str(output_dir),
                "zip_path": zip_path,
                "main_code": next(iter(files.values()), ""),
                "rag_context": rag_context,
                "layout_tree": layout_tree,
                "component_mapping": mapping,
                "invalid_components": invalid,
            },
        )

        main_view = next((p for p in files if p.startswith("src/views/")), "")
        generated_code = files.get(main_view, "")

        repaired = False
        if state.get("review_result") and not state["review_result"].get("pass", True):
            bump_self_repair(state)
            repaired = True

        logger.info(
            "[%s] 页面生成完成：%s 个文件，版本 v%s，自修复=%s",
            task_id,
            len(files),
            version,
            repaired,
        )
        if task_id:
            cache.set_task_status(task_id, "generated", "page", f"生成 {len(files)} 个文件")

    return {
        "generated_code": generated_code,
        "code_files": files,
        "output_dir": str(output_dir),
        "zip_path": zip_path,
        "rag_context": rag_context,
        "layout_tree": layout_tree,
        "component_mapping": mapping,
        "status": "generated",
        "current_agent": "page",
        "tokens": usage.as_dict(),
        "timings": state.get("timings", {}),
        "self_repair_count": state.get("self_repair_count", 0),
    }
