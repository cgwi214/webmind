"""多端适配 Agent（Multi Platform Agent）。

将 Web（Vue3 + Element Plus）页面机械翻译为 uni-app（小程序 / H5）。
对应文档：WebMind完整开发指导.md 第 13 节 / 项目详解.md 4.4
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.agents.base import stage
from app.core.config import settings
from app.core.logging import get_logger
from app.services import cache, doc_store

logger = get_logger("webmind.agent.adapt")

# Web → uni-app 标签映射
_TAG_MAP = {
    "div": "view",
    "span": "text",
    "p": "text",
    "img": "image",
    "ul": "view",
    "li": "view",
    "section": "view",
    "header": "view",
    "footer": "view",
    "h1": "text",
    "h2": "text",
    "h3": "text",
    "a": "navigator",
    "button": "button",
    "input": "input",
    "textarea": "textarea",
}

# Element Plus → uni-app 近似映射（复杂组件需人工微调）
_EL_MAP = {
    "el-card": "view",
    "el-form": "view",
    "el-form-item": "view",
    "el-table": "view",
    "el-table-column": "view",
    "el-row": "view",
    "el-col": "view",
    "el-container": "view",
    "el-aside": "view",
    "el-main": "view",
    "el-menu": "view",
    "el-menu-item": "view",
    "el-descriptions": "view",
    "el-descriptions-item": "view",
    "el-button": "button",
    "el-input": "input",
    "el-select": "picker",
    "el-date-picker": "picker",
    "el-switch": "switch",
    "el-dialog": "view",
    "el-pagination": "view",
}


def transform_vue_to_uniapp(code: str) -> str:
    """Vue3 单文件组件 → uni-app 页面。"""
    result = code

    # Element Plus 组件 → uni-app 近似组件
    for el_tag, uni_tag in _EL_MAP.items():
        result = re.sub(rf"<{el_tag}(\s|>|/>)", rf"<{uni_tag}\1", result)
        result = result.replace(f"</{el_tag}>", f"</{uni_tag}>")

    # 基础 HTML 标签 → uni-app 内置组件
    for html_tag, uni_tag in _TAG_MAP.items():
        result = re.sub(rf"<{html_tag}(\s|>|/>)", rf"<{uni_tag}\1", result)
        result = result.replace(f"</{html_tag}>", f"</{uni_tag}>")

    # 网络请求：axios → uni.request
    result = result.replace("import axios from 'axios'", "import { request } from '@/utils/request'")
    result = result.replace("axios.get(", "request.get(").replace("axios.post(", "request.post(")

    # Element Plus 消息提示 → uni 原生提示
    result = re.sub(r"ElMessage\.success\(([^)]*)\)", r"uni.showToast({ title: \1, icon: 'success' })", result)
    result = re.sub(r"ElMessage\.error\(([^)]*)\)", r"uni.showToast({ title: \1, icon: 'none' })", result)
    result = re.sub(r"ElMessageBox\.confirm\(([^,)]*)[^)]*\)", r"uni.showModal({ content: \1 })", result)
    result = re.sub(r"import \{[^}]*\} from 'element-plus'", "", result)

    # 移除 scoped 样式中的 Web 专属单位（小程序不支持部分 CSS 选择器）
    result = re.sub(r"<style scoped>", "<style>", result)

    # 条件编译提示
    # 注意：根 template 的开标签是文件里第一个裸 `<template>`（插槽写作 `<template #header>`，
    # 不含子串 "<template>"），但根 template 的闭标签是**最后一个** `</template>` ——
    # 插槽的闭标签同样是 `</template>`，若取首个会把 #endif 插进卡片内部，导致条件编译不配对。
    if "<template>" in result:
        result = result.replace(
            "<template>",
            "<!-- 由 WebMind 多端适配 Agent 自动生成，平台差异部分需人工微调 -->\n"
            "<!-- #ifdef MP-WEIXIN || H5 -->\n<template>",
            1,
        )
    close_tag = "</template>"
    last_close = result.rfind(close_tag)
    if last_close != -1:
        insert_at = last_close + len(close_tag)
        result = result[:insert_at] + "\n<!-- #endif -->" + result[insert_at:]
    return result


def _pages_json(views: list[str]) -> str:
    pages = [
        {
            "path": f"pages/{view}/index" if view != "Login" else "pages/login/index",
            "style": {"navigationBarTitleText": view},
        }
        for view in views
    ]
    return json.dumps(
        {"pages": pages, "globalStyle": {"navigationBarTextStyle": "black", "navigationBarBackgroundColor": "#ffffff"}},
        ensure_ascii=False,
        indent=2,
    )


_REQUEST_TS = """// 由 WebMind 多端适配 Agent 生成的请求封装（uni.request）
type Method = 'GET' | 'POST' | 'PUT' | 'DELETE'

const BASE_URL = 'https://example.com'

export const request = <T = unknown>(url: string, method: Method = 'GET', data?: unknown): Promise<T> => {
  return new Promise((resolve, reject) => {
    uni.request({
      url: BASE_URL + url,
      method,
      data,
      success: (res) => resolve(res.data as T),
      fail: (err) => reject(err),
    })
  })
}

export default request
"""

_UNI_MAIN = """import { createSSRApp } from 'vue'
import App from './App.vue'

export function createApp() {
  const app = createSSRApp(App)
  return { app }
}
"""


async def adapt_agent(state: dict[str, Any]) -> dict[str, Any]:
    """多端适配节点：Web 代码 → uni-app 多端代码。"""
    task_id = state.get("task_id", "")
    files: dict[str, str] = dict(state.get("code_files") or {})
    targets: list[str] = state.get("target_platforms") or ["web"]

    with stage("adapt", state):
        uniapp_files: dict[str, str] = {}
        views: list[str] = []

        for rel_path, content in files.items():
            if rel_path.startswith("src/views/") and rel_path.endswith(".vue"):
                name = Path(rel_path).stem
                views.append(name)
                uniapp_files[f"src/pages/{name}/index.vue"] = transform_vue_to_uniapp(content)
            elif rel_path.startswith("src/mock/"):
                uniapp_files[rel_path] = content

        uniapp_files["src/pages.json"] = _pages_json(views)
        uniapp_files["src/utils/request.ts"] = _REQUEST_TS
        uniapp_files["src/main.ts"] = _UNI_MAIN
        uniapp_files["src/App.vue"] = (
            "<script setup lang=\"ts\">\n// uni-app 入口（由 WebMind 生成）\n</script>\n\n"
            "<template>\n  <view class=\"app\">\n    <slot />\n  </view>\n</template>\n"
        )
        uniapp_files["README.uniapp.md"] = (
            "# uni-app 多端产物\n\n"
            "由 WebMind 多端适配 Agent 从 Vue3 + Element Plus 页面机械翻译而来。\n\n"
            "## 已知需人工微调\n"
            "- Element Plus 复杂组件（表格 / 表单 / 弹窗）已降级为 view + 基础组件\n"
            "- 样式类名与布局需按小程序规范复核\n"
            "- 真实接口需替换 src/utils/request.ts 中的 BASE_URL\n"
        )

        # 落盘
        output_root = settings.code_output_dir / task_id / "uniapp"
        for rel_path, content in uniapp_files.items():
            target = output_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        doc_store.insert(
            "code_versions",
            {
                "task_id": task_id,
                "version": f"uniapp-{len(views)}pages",
                "platform": "uniapp",
                "files": {k: len(v) for k, v in uniapp_files.items()},
                "output_dir": str(output_root),
            },
        )

        final_output = {
            "web": next(
                (p for p in files if p.startswith("src/views/")), ""
            ),
            "web_files": sorted(files.keys()),
            "uniapp_files": sorted(uniapp_files.keys()),
            "targets": targets,
            "output_dir": str(settings.code_output_dir / task_id),
            "uniapp_output_dir": str(output_root),
        }

        logger.info("[%s] 多端适配完成：%s 个页面", task_id, len(views))
        if task_id:
            cache.set_task_status(task_id, "delivered", "adapt", f"多端适配完成 {len(views)} 个页面")

    return {
        "uniapp_code": uniapp_files,
        "final_output": final_output,
        "status": "delivered",
        "current_agent": "adapt",
        "timings": state.get("timings", {}),
    }
