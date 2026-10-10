"""需求解析 Agent（Requirement Agent）。

输入：PRD 文本 / UI 设计说明
输出：结构化需求 JSON（页面 / 组件 / 字段 / 功能）+ 置信度

约束：Function Calling 风格的 JSON Schema + Pydantic 校验；
置信度低于阈值 → 主编排转人工澄清。
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from app.agents.base import stage, usage_from
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.requirement import RequirementSpec
from app.services import cache, doc_store, llm
from app.services.codegen import detect_type

logger = get_logger("webmind.agent.requirement")

SYSTEM_PROMPT = """你是 WebMind 平台的需求解析 Agent，服务于企业前端研发团队。
任务：把产品需求文档（PRD）解析成结构化需求清单，供后续页面生成 Agent 使用。

必须严格输出如下 JSON 结构（不要输出任何解释文字）：
{
  "project_name": "项目名称",
  "pages": [
    {
      "name": "页面名称",
      "type": "table | form | detail | config | login | dashboard",
      "description": "页面用途一句话",
      "fields": [
        {"name": "字段英文名", "label": "字段中文名", "type": "string | number | date | enum | boolean | text", "required": true, "options": ["枚举值"]}
      ],
      "components": ["el-table"],
      "functions": ["搜索", "新增"],
      "apis": ["/api/xxx/list"],
      "priority": 1
    }
  ],
  "confidence": 0.85,
  "notes": "需求歧义点说明"
}

约束：
1. components 只能从 Element Plus 组件库或公司组件库（wm- 前缀）中选择，不得虚构组件
2. confidence 反映需求描述的清晰度，信息不足时给低分
3. 不要编造 PRD 中不存在的字段或接口
"""

_FIELD_TYPE_HINTS = {
    "时间": "date",
    "日期": "date",
    "创建": "date",
    "数量": "number",
    "金额": "number",
    "价格": "number",
    "状态": "enum",
    "类型": "enum",
    "是否": "boolean",
    "备注": "text",
    "描述": "text",
}

# 本地启发式可识别的功能点关键字（命中即记入页面 functions）
_FUNCTION_HINTS = (
    "搜索",
    "查询",
    "新增",
    "创建",
    "编辑",
    "修改",
    "删除",
    "导出",
    "导入",
    "上传",
    "登录",
    "保存",
    "提交",
    "重置",
)


def _guess_field_type(name: str) -> str:
    for hint, ftype in _FIELD_TYPE_HINTS.items():
        if hint in name:
            return ftype
    return "string"


_MD_HEADING_RE = re.compile(r"^\s*#{1,6}\s*")
_NUMBERED_RE = re.compile(r"^\d+[\.、\)]\s*")
_BULLET_RE = re.compile(r"^[-*·]\s*")


def _clean_heading(line: str) -> str | None:
    """把一行识别为页面标题并返回清洗后的页面名；不是标题则返回 None。

    PRD 常见三种写法都要能认：Markdown 标题（``## 1. 用户列表页面``）、
    编号行（``1. 用户列表页面``）、以及裸标题（``用户列表页面``）。
    短横线项（``- 支持新增用户``）多为功能点而非页面，只有明确含"页面/模块"才当标题，
    否则会被误判成新页面、把功能点全部吃掉。
    """
    stripped = _MD_HEADING_RE.sub("", line).strip()

    if _NUMBERED_RE.match(stripped):
        raw = _NUMBERED_RE.sub("", stripped)
    elif _BULLET_RE.match(stripped):
        raw = _BULLET_RE.sub("", stripped)
        if not re.search(r"页面|模块|页$", raw) or len(raw) > 30:
            return None
    elif ("页面" in stripped or "模块" in stripped) and len(stripped) <= 40:
        raw = stripped
    else:
        return None

    name = re.split(r"[：:（(]", raw)[0].strip()
    name = re.sub(r"(页面|模块)$", "", name).strip()
    if not name or len(name) > 30:
        return None
    return name


def _heuristic_parse(prd: str) -> dict:
    """无 LLM 时的本地启发式解析，保证链路可跑通。"""
    lines = [line.strip() for line in prd.splitlines() if line.strip()]
    pages: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in lines:
        heading_name = _clean_heading(line)
        if heading_name is not None:
            current = {
                "name": heading_name,
                "type": detect_type(heading_name),
                "description": line,
                "fields": [],
                "components": [],
                "functions": [],
                "apis": [],
                "priority": len(pages) + 1,
            }
            pages.append(current)
            continue

        if current is None:
            continue

        is_function_line = "功能" in line or "操作" in line
        is_field_line = not is_function_line and any(
            sep in line for sep in ("字段", "：", ":", "，", "、")
        )

        # 功能点只在非字段行扫描，避免"最大登录次数""新增用户数"这类字段名被误判为功能
        if not is_field_line:
            for keyword in _FUNCTION_HINTS:
                if keyword in line and keyword not in current["functions"]:
                    current["functions"].append(keyword)

        # 字段只在"字段声明行"抽取；"功能/操作"行里的取值是功能点，不是字段
        if is_field_line:
            parts = re.split(r"[：:，,、/|]", line)
            for part in parts[1:]:
                token = part.strip()
                if 1 <= len(token) <= 12 and not token.isdigit() and not token.startswith("http"):
                    current["fields"].append(
                        {
                            "name": token,
                            "label": token,
                            "type": _guess_field_type(token),
                            "required": False,
                            "options": [],
                        }
                    )

        if re.search(r"/api/[A-Za-z0-9_\-/]+", line):
            current["apis"].extend(re.findall(r"/api/[A-Za-z0-9_\-/]+", line))

    if not pages:
        pages = [
            {
                "name": "需求页面",
                "type": "table",
                "description": (prd[:60] or "PRD 未提供结构化页面信息"),
                "fields": [],
                "components": [],
                "functions": [],
                "apis": [],
                "priority": 1,
            }
        ]

    # 置信度：页面数、字段数、功能点越少越不确定
    field_count = sum(len(p["fields"]) for p in pages)
    func_count = sum(len(p["functions"]) for p in pages)
    confidence = 0.45
    if len(pages) >= 1:
        confidence += 0.15
    if field_count >= 3:
        confidence += 0.15
    if func_count >= 2:
        confidence += 0.1
    if len(prd) > 200:
        confidence += 0.05
    confidence = round(min(confidence, 0.9), 2)

    return {
        "project_name": "WebMind 生成工程",
        "pages": pages,
        "confidence": confidence,
        "notes": "本地启发式解析（未配置 LLM），建议补充字段与接口说明以提高置信度",
    }


def _validate(data: dict | None) -> RequirementSpec | None:
    if not isinstance(data, dict) or not data.get("pages"):
        return None
    try:
        return RequirementSpec.model_validate(data)
    except ValidationError as exc:
        logger.warning("需求 JSON 校验失败: %s", exc)
        return None


async def requirement_agent(state: dict[str, Any]) -> dict[str, Any]:
    """需求解析节点：PRD → 结构化需求 JSON。"""
    task_id = state.get("task_id", "")
    prd = state.get("prd") or state.get("requirement") or ""
    usage = usage_from(state)

    with stage("requirement", state):
        spec: RequirementSpec | None = None
        mode = "heuristic"

        raw = llm.chat(SYSTEM_PROMPT, f"PRD 内容如下：\n{prd}", usage=usage)
        if raw:
            spec = _validate(llm.extract_json(raw))
            if spec is not None:
                mode = "llm"
        if spec is None:
            spec = _validate(_heuristic_parse(prd)) or RequirementSpec(
                pages=[{"name": "需求页面", "type": "table"}]
            )

        requirement_json = spec.model_dump()
        confidence = float(requirement_json.get("confidence") or 0.6)

        # 组件白名单兜底：模型可能给出不存在的组件
        from app.rag.retriever import get_retriever

        whitelist = get_retriever().whitelist()
        for page in requirement_json.get("pages", []):
            page["components"] = [c for c in page.get("components", []) if c in whitelist]

        doc_store.insert(
            "requirements",
            {
                "task_id": task_id,
                "prd": prd,
                "requirement": requirement_json,
                "confidence": confidence,
                "mode": mode,
            },
        )

        status = "needs_clarification" if confidence < settings.REQUIREMENT_CONFIDENCE_THRESHOLD else "parsed"
        logger.info(
            "[%s] 需求解析完成：%s 个页面，置信度 %.2f，模式=%s",
            task_id,
            len(requirement_json.get("pages", [])),
            confidence,
            mode,
        )
        if task_id:
            cache.set_task_status(
                task_id, status, "requirement", f"解析出 {len(requirement_json['pages'])} 个页面"
            )

    return {
        "requirement_json": requirement_json,
        "confidence": confidence,
        "status": "needs_clarification" if confidence < settings.REQUIREMENT_CONFIDENCE_THRESHOLD else "parsed",
        "current_agent": "requirement",
        "tokens": usage.as_dict(),
        "timings": state.get("timings", {}),
        "model_mode": mode,
    }
