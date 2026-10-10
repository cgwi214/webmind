"""代码评估模块（CodeEvaluator）。

判断生成代码是否可以：安装 → 启动 → 编译 → 运行核心功能。
对应文档：评估体系设计 5.1~5.4 + 对比文档 8.1（Install/Build/Start/Runtime/Console/API/Test）
"""

from __future__ import annotations

import re
from typing import Any


class CodeEvaluator:
    """对生成工程做可用性评估，输出 0~100 分与 Hard Gate 判定。"""

    CORE_FEATURES = {
        "table": ["el-table", "el-table-column"],
        "form": ["<el-form", "submitForm"],
        "detail": ["el-descriptions"],
        "config": ["<el-form", "save"],
        "login": ["<el-form", "submitForm"],
        "dashboard": ["el-table"],
    }

    def evaluate(self, files: dict[str, str], meta: dict[str, Any] | None = None) -> dict[str, Any]:
        meta = meta or {}
        errors: list[str] = []
        warnings: list[str] = []

        # ---------- Install ----------
        package = files.get("package.json", "")
        install_success = bool(package) and '"dependencies"' in package
        if not install_success:
            errors.append("缺少 package.json 或依赖声明，无法安装")

        # ---------- Build ----------
        build_success = True
        for required in ("src/main.ts", "vite.config.ts", "tsconfig.json"):
            if required not in files:
                build_success = False
                errors.append(f"缺少构建必需文件 {required}")
        for rel_path, content in files.items():
            for imported in re.findall(r"from ['\"]@/([^'\"]+)['\"]", content):
                candidate = f"src/{imported}"
                if not any(
                    key == candidate or key.rsplit(".", 1)[0] == candidate for key in files
                ):
                    build_success = False
                    errors.append(f"{rel_path} 引用不存在模块 @/{imported}")

        # ---------- Start ----------
        start_success = bool(files.get("src/main.ts")) and bool(files.get("index.html"))
        if not start_success:
            errors.append("缺少入口文件（src/main.ts / index.html），工程无法启动")

        # ---------- Runtime / 核心功能 ----------
        runtime_success = True
        page_types = {p.get("type") for p in meta.get("pages", [])} or {"table"}
        for page_type in page_types:
            features = self.CORE_FEATURES.get(page_type, [])
            if features and not any(
                any(feature in content for feature in features)
                for content in files.values()
            ):
                runtime_success = False
                errors.append(f"核心功能缺失：{page_type} 页面未生成 {features} 相关实现")

        # ---------- Console / API 异常 ----------
        console_errors = sum(content.count("console.error") for content in files.values())
        api_errors = sum(len(re.findall(r"https?://[^\s'\"]+", content)) for content in files.values())
        if console_errors:
            warnings.append(f"存在 {console_errors} 处 console.error")
        if api_errors:
            warnings.append(f"存在 {api_errors} 处硬编码 URL，建议改为环境变量或接口配置")

        # ---------- 评分 ----------
        score = 100.0
        if not install_success:
            score -= 60
        if not build_success:
            score -= 30
        if not start_success:
            score -= 20
        if not runtime_success:
            score -= 25
        score -= min(console_errors * 3, 10)
        score = max(0.0, round(score, 2))

        return {
            "score": score,
            "install_success": install_success,
            "build_success": build_success,
            "start_success": start_success,
            "runtime_success": runtime_success,
            "console_error_count": console_errors,
            "api_error_count": api_errors,
            "errors": errors,
            "warnings": warnings,
        }
