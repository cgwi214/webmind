"""代码审查 Agent（Code Review Agent）。

内嵌副编排：静态检查 ∥ 运行验证 ∥ 规范比对 → 汇总审查报告。
对应文档：WebMind项目详解.md 4.3
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.agents.base import stage
from app.core.config import settings
from app.core.logging import get_logger
from app.rag.retriever import get_retriever
from app.services import cache, doc_store

logger = get_logger("webmind.agent.review")

_ISSUE = dict[str, Any]


def _issue(source: str, message: str, severity: str = "error", file: str = "") -> _ISSUE:
    return {"source": source, "file": file, "message": message, "severity": severity}


# ===================== 副编排子任务 =====================


async def _static_check(files: dict[str, str]) -> dict:
    """静态检查：组件白名单、命名、TS 用法、调试残留。"""
    await asyncio.sleep(0)
    errors: list[_ISSUE] = []
    warnings: list[_ISSUE] = []
    whitelist = get_retriever().whitelist()

    for rel_path, content in files.items():
        if rel_path.endswith(".vue"):
            component_name = Path(rel_path).stem
            if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", component_name):
                errors.append(_issue("static", f"组件命名应为 PascalCase: {component_name}", "error", rel_path))
            if "<script setup" not in content or 'lang="ts"' not in content:
                errors.append(_issue("static", "缺少 <script setup lang=\"ts\"> 声明", "error", rel_path))
            # 注意：<template #header> 等具名插槽也以 </template> 收尾，需一并计入开标签
            opened = len(re.findall(r"<template[\s>]", content))
            closed = content.count("</template>")
            if opened != closed:
                errors.append(
                    _issue("static", f"template 标签未闭合（开 {opened} / 闭 {closed}）", "error", rel_path)
                )
            for component in get_retriever().validate_components(content):
                errors.append(_issue("static", f"使用了组件白名单外的组件: {component}", "error", rel_path))
            if "console.log" in content:
                warnings.append(_issue("static", "存在 console.log 调试输出", "warning", rel_path))
            if re.search(r"\bvar\s+\w+", content):
                warnings.append(_issue("static", "使用了 var，建议 const/let", "warning", rel_path))
            if ": any" in content:
                warnings.append(_issue("static", "存在 any 类型，建议补充类型定义", "warning", rel_path))
        if rel_path.endswith(".ts"):
            if re.search(r"\bvar\s+\w+", content):
                warnings.append(_issue("static", "使用了 var，建议 const/let", "warning", rel_path))

    score = max(0.0, 100 - len(errors) * 15 - len(warnings) * 3)
    return {"errors": errors, "warnings": warnings, "score": round(score, 2), "whitelist_size": len(whitelist)}


async def _build_check(files: dict[str, str], output_dir: str | None) -> dict:
    """运行验证：默认做可构建性分析；开启 RUN_REAL_BUILD 时真实执行 npm build。"""
    errors: list[_ISSUE] = []
    warnings: list[_ISSUE] = []

    if "package.json" not in files:
        errors.append(_issue("build", "缺少 package.json", "error"))
    else:
        for script in ("dev", "build", "lint"):
            if f'"{script}"' not in files["package.json"]:
                errors.append(_issue("build", f"package.json 缺少 {script} 脚本", "error"))

    if "src/main.ts" not in files:
        errors.append(_issue("build", "缺少入口文件 src/main.ts", "error"))
    if "src/router/index.ts" not in files:
        warnings.append(_issue("build", "缺少路由文件 src/router/index.ts", "warning"))

    # 依赖引用是否都能在生成结果中找到
    for rel_path, content in files.items():
        for imported in re.findall(r"from ['\"]@/([^'\"]+)['\"]", content):
            candidate = f"src/{imported}"
            if not any(
                key == candidate or key.startswith(candidate + ".") or key.rsplit(".", 1)[0] == candidate
                for key in files
            ):
                errors.append(_issue("build", f"引用了不存在的模块 @/{imported}", "error", rel_path))

    real_build_ran = False
    if getattr(settings, "RUN_REAL_BUILD", False) and output_dir and shutil.which("npm"):
        real_build_ran = True
        try:
            subprocess.run(
                ["npm", "install", "--silent"],
                cwd=output_dir,
                timeout=900,
                check=False,
                shell=True,
            )
            proc = subprocess.run(
                ["npm", "run", "build"],
                cwd=output_dir,
                timeout=900,
                check=False,
                shell=True,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                tail = (proc.stdout or "")[-800:] + (proc.stderr or "")[-800:]
                errors.append(_issue("build", f"npm run build 失败: {tail}", "error"))
        except (subprocess.TimeoutExpired, OSError) as exc:
            errors.append(_issue("build", f"构建执行异常: {exc}", "error"))

    score = max(0.0, 100 - len(errors) * 25 - len(warnings) * 5)
    return {
        "errors": errors,
        "warnings": warnings,
        "score": round(score, 2),
        "install_success": "package.json" in files,
        "build_success": not errors,
        "real_build_ran": real_build_ran,
    }


async def _convention_check(files: dict[str, str]) -> dict:
    """规范比对：目录结构、路由注册、文件命名、缩进。"""
    await asyncio.sleep(0)
    errors: list[_ISSUE] = []
    warnings: list[_ISSUE] = []

    for required in ("src/views", "src/router/index.ts", "src/main.ts"):
        if not any(key.startswith(required) for key in files):
            errors.append(_issue("convention", f"缺少规范目录/文件: {required}", "error"))

    router = files.get("src/router/index.ts", "")
    views = [Path(p).stem for p in files if p.startswith("src/views/") and p.endswith(".vue")]
    for view in views:
        if view not in router and view != "Login":
            errors.append(_issue("convention", f"路由未注册组件: {view}", "error"))
    for registered in re.findall(r"import\('@/views/([A-Za-z0-9]+)\.vue'\)", router):
        if registered not in views:
            errors.append(_issue("convention", f"路由引用了不存在的视图: {registered}", "error"))

    for rel_path, content in files.items():
        if rel_path.endswith((".vue", ".ts")):
            if "\t" in content:
                warnings.append(_issue("convention", "存在 Tab 缩进，建议使用 2 空格", "warning", rel_path))

    score = max(0.0, 100 - len(errors) * 12 - len(warnings) * 2)
    return {"errors": errors, "warnings": warnings, "score": round(score, 2)}


# ===================== 主节点 =====================


async def review_agent(state: dict[str, Any]) -> dict[str, Any]:
    """代码审查节点：并行三项检查 → 汇总报告。"""
    task_id = state.get("task_id", "")
    files = state.get("code_files") or {}

    with stage("review", state):
        static_task = asyncio.create_task(_static_check(files))
        build_task = asyncio.create_task(_build_check(files, state.get("output_dir")))
        convention_task = asyncio.create_task(_convention_check(files))
        static, build, convention = await asyncio.gather(static_task, build_task, convention_task)

        errors = static["errors"] + build["errors"] + convention["errors"]
        warnings = static["warnings"] + build["warnings"] + convention["warnings"]
        passed = not errors

        review_result = {
            "pass": passed,
            "errors": errors,
            "warnings": warnings,
            "checks": {
                "static": static,
                "build": build,
                "convention": convention,
            },
            "score": round((static["score"] + build["score"] + convention["score"]) / 3, 2),
            "retry_count": int(state.get("retry_count", 0)),
        }

        doc_store.insert("review_reports", {"task_id": task_id, "review": review_result})
        logger.info(
            "[%s] 代码审查完成：pass=%s，错误 %s 条，警告 %s 条",
            task_id,
            passed,
            len(errors),
            len(warnings),
        )
        if task_id:
            cache.set_task_status(
                task_id,
                "reviewed" if passed else "repairing",
                "review",
                f"{'通过' if passed else f'{len(errors)} 项错误'}",
            )

    return {
        "review_result": review_result,
        "current_agent": "review",
        "status": "reviewed" if review_result["pass"] else "repairing",
        "timings": state.get("timings", {}),
    }
