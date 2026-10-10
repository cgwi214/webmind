"""工程质量评估模块（QualityEvaluator / EngineeringEvaluator）。

检查：ESLint 规则、TypeScript 类型、Prettier 格式、目录结构、命名规范、
依赖质量、重复代码、无效代码。
对应文档：评估体系设计 9.1~9.2 + 对比文档 8.5（必须接入 EvaluationRunner）
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any


class QualityEvaluator:
    """工程规范质量评估，输出 0~100 分与逐项结论。"""

    REQUIRED_DIRS = ("src/views", "src/mock", "src/router")
    ALLOWED_DEPS = {
        "vue",
        "vue-router",
        "element-plus",
        "@element-plus/icons-vue",
        "axios",
        "vite",
        "@vitejs/plugin-vue",
        "typescript",
        "vue-tsc",
        "eslint",
        "prettier",
    }

    def _eslint_check(self, files: dict[str, str]) -> tuple[float, list[str]]:
        issues: list[str] = []
        for rel_path, content in files.items():
            if rel_path.endswith((".vue", ".ts")):
                if "\t" in content:
                    issues.append(f"{rel_path}: 使用 Tab 缩进（Prettier/ESLint 规范为 2 空格）")
                if re.search(r"\bvar\s+\w+", content):
                    issues.append(f"{rel_path}: 使用 var 声明变量")
                if "console.log" in content:
                    issues.append(f"{rel_path}: 遗留 console.log")
                if re.search(r";\s*$", content, flags=re.M) and rel_path.endswith(".ts"):
                    issues.append(f"{rel_path}: 行尾分号（本项目约定不使用分号）")
        score = max(0.0, 100 - len(issues) * 8)
        return round(score, 2), issues

    def _typescript_check(self, files: dict[str, str]) -> tuple[float, list[str]]:
        issues: list[str] = []
        tsconfig = files.get("tsconfig.json", "")
        # 两侧都去掉空白再比对，否则 `"strict": true` 永远匹配不上
        if '"strict":true' not in tsconfig.replace(" ", "").replace("\n", "").replace("\t", ""):
            issues.append("tsconfig.json 未开启 strict 模式")
        for rel_path, content in files.items():
            if rel_path.endswith((".vue", ".ts")):
                if ": any" in content or "<any>" in content:
                    issues.append(f"{rel_path}: 存在 any 类型")
                if re.search(r"as unknown as", content):
                    issues.append(f"{rel_path}: 存在双重类型断言")
        score = max(0.0, 100 - len(issues) * 10)
        return round(score, 2), issues

    def _structure_check(self, files: dict[str, str]) -> tuple[float, list[str]]:
        issues: list[str] = []
        for required in self.REQUIRED_DIRS:
            if not any(key.startswith(required) for key in files):
                issues.append(f"缺少规范目录 {required}")
        if "README.md" not in files:
            issues.append("缺少 README.md")
        score = max(0.0, 100 - len(issues) * 15)
        return round(score, 2), issues

    def _naming_check(self, files: dict[str, str]) -> tuple[float, list[str]]:
        issues: list[str] = []
        for rel_path in files:
            if rel_path.startswith("src/views/") and rel_path.endswith(".vue"):
                name = Path(rel_path).stem
                if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", name):
                    issues.append(f"视图命名应为 PascalCase: {name}")
            if rel_path.startswith("src/mock/") and rel_path.endswith(".ts"):
                name = Path(rel_path).stem
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
                    issues.append(f"mock 文件命名不规范: {name}")
        score = max(0.0, 100 - len(issues) * 12)
        return round(score, 2), issues

    def _dependency_check(self, files: dict[str, str]) -> tuple[float, list[str]]:
        issues: list[str] = []
        package = files.get("package.json", "")
        # 只解析 dependencies / devDependencies 区块，避免把 version / name 等字段当成依赖
        deps: set[str] = set()
        for section in ("dependencies", "devDependencies"):
            block = re.search(rf'"{section}"\s*:\s*\{{(.*?)\}}', package, flags=re.S)
            if block:
                deps |= set(re.findall(r'"([^"]+)"\s*:', block.group(1)))
        unknown = {d for d in deps if d not in self.ALLOWED_DEPS}
        if unknown:
            issues.append(f"依赖不在白名单: {', '.join(sorted(unknown))}")
        if '"vue"' not in package:
            issues.append("缺少核心依赖 vue")
        score = max(0.0, 100 - len(issues) * 20)
        return round(score, 2), issues

    def _duplicate_check(self, files: dict[str, str]) -> tuple[float, list[str]]:
        issues: list[str] = []
        blocks: Counter[str] = Counter()
        for rel_path, content in files.items():
            if not rel_path.endswith((".vue", ".ts")):
                continue
            for line in content.splitlines():
                stripped = line.strip()
                if len(stripped) > 40:
                    blocks[stripped] += 1
        duplicated = [line for line, count in blocks.items() if count > 2]
        if duplicated:
            issues.append(f"存在 {len(duplicated)} 处重复代码块（>2 次出现）")
        score = max(0.0, 100 - len(duplicated) * 5)
        return round(score, 2), issues

    def _dead_code_check(self, files: dict[str, str]) -> tuple[float, list[str]]:
        issues: list[str] = []
        for rel_path, content in files.items():
            if rel_path.endswith((".vue", ".ts")):
                for match in re.finditer(r"(export\s+)?(?:const|function)\s+([A-Za-z_]\w*)", content):
                    # 导出声明是模块对外 API，可能被其他文件引用，不算死代码
                    if match.group(1):
                        continue
                    name = match.group(2)
                    if len(content.split(name)) <= 2:
                        issues.append(f"{rel_path}: 疑似未使用的声明 {name}")
        score = max(0.0, 100 - len(issues) * 6)
        return round(score, 2), issues

    def evaluate(self, files: dict[str, str]) -> dict[str, Any]:
        eslint_score, eslint_issues = self._eslint_check(files)
        ts_score, ts_issues = self._typescript_check(files)
        structure_score, structure_issues = self._structure_check(files)
        naming_score, naming_issues = self._naming_check(files)
        dependency_score, dependency_issues = self._dependency_check(files)
        duplicate_score, duplicate_issues = self._duplicate_check(files)
        dead_score, dead_issues = self._dead_code_check(files)

        score = round(
            (
                eslint_score
                + ts_score
                + structure_score
                + naming_score
                + dependency_score
                + duplicate_score
                + dead_score
            )
            / 7,
            2,
        )
        return {
            "score": score,
            "checks": {
                "eslint": {"score": eslint_score, "issues": eslint_issues},
                "typescript": {"score": ts_score, "issues": ts_issues},
                "prettier": {"score": eslint_score, "issues": [i for i in eslint_issues if "缩进" in i]},
                "project_structure": {"score": structure_score, "issues": structure_issues},
                "naming_convention": {"score": naming_score, "issues": naming_issues},
                "dependency_quality": {"score": dependency_score, "issues": dependency_issues},
                "duplicate_code": {"score": duplicate_score, "issues": duplicate_issues},
                "dead_code": {"score": dead_score, "issues": dead_issues},
            },
            "issues": (
                eslint_issues
                + ts_issues
                + structure_issues
                + naming_issues
                + dependency_issues
                + duplicate_issues
                + dead_issues
            ),
        }
