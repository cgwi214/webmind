"""需求理解评估模块（RequirementEvaluator）。

指标：页面覆盖率 / 字段覆盖率 / 功能覆盖率 / 交互覆盖率
对应文档：评估体系设计 7.1~7.3 + 对比文档 8.3
"""

from __future__ import annotations

import re
from typing import Any


class RequirementEvaluator:
    """评估需求解析结果与最终代码的一致性。"""

    def _text(self, files: dict[str, str]) -> str:
        return "\n".join(files.values())

    def page_coverage(self, requirement: dict, files: dict[str, str]) -> tuple[float, dict]:
        pages = requirement.get("pages") or []
        if not pages:
            return 0.0, {"expected": 0, "generated": 0}
        views = [p for p in files if p.startswith("src/views/") and p.endswith(".vue")]
        generated = len(views)
        expected = len(pages)
        return round(min(generated / expected, 1.0) * 100, 2), {
            "expected": expected,
            "generated": generated,
        }

    def field_coverage(self, requirement: dict, files: dict[str, str]) -> tuple[float, dict]:
        code = self._text(files)
        expected_fields: list[str] = []
        for page in requirement.get("pages") or []:
            for field in page.get("fields") or []:
                name = field.get("name") if isinstance(field, dict) else str(field)
                if name:
                    expected_fields.append(name)
        if not expected_fields:
            return 70.0, {"expected": 0, "hit": 0, "note": "需求未声明字段，按基线分计"}
        hit = sum(1 for field in expected_fields if field in code)
        return round(hit / len(expected_fields) * 100, 2), {
            "expected": len(expected_fields),
            "hit": hit,
        }

    def function_coverage(self, requirement: dict, files: dict[str, str]) -> tuple[float, dict]:
        code = self._text(files)
        # 右侧 token 必须与 codegen 实际生成的处理器名保持一致
        keyword_map = {
            "搜索": "handleSearch",
            "查询": "handleSearch",
            "新增": "新增",
            "创建": "新增",
            "编辑": "编辑",
            "修改": "编辑",
            "删除": "handleDelete",
            "导出": "导出",
            "导入": "导入",
            "上传": "upload",
            "登录": "submitForm",
            "提交": "submitForm",
            "保存": "save",
            "重置": "handleReset",
        }
        expected: list[str] = []
        for page in requirement.get("pages") or []:
            for func in page.get("functions") or []:
                if func in keyword_map:
                    expected.append(keyword_map[func])
        if not expected:
            # 页面未声明（或未命中）任何可识别功能，按基线分计，避免误判为 0
            return 70.0, {"expected": [], "hit": 0, "note": "需求未声明可识别功能，按基线分计"}
        hit = sum(1 for token in set(expected) if token in code)
        return round(hit / len(set(expected)) * 100, 2), {
            "expected": sorted(set(expected)),
            "hit": hit,
        }

    def interaction_coverage(self, requirement: dict, files: dict[str, str]) -> tuple[float, dict]:
        code = self._text(files)
        checks = {
            "事件绑定": bool(re.search(r"@click|@change|@submit", code)),
            "表单校验": "rules" in code,
            "分页交互": "el-pagination" in code,
            "弹窗交互": "el-dialog" in code,
        }
        hit = sum(1 for ok in checks.values() if ok)
        return round(hit / len(checks) * 100, 2), checks

    def evaluate(self, requirement: dict, files: dict[str, str]) -> dict[str, Any]:
        page_score, page_detail = self.page_coverage(requirement, files)
        field_score, field_detail = self.field_coverage(requirement, files)
        func_score, func_detail = self.function_coverage(requirement, files)
        inter_score, inter_detail = self.interaction_coverage(requirement, files)

        score = round(
            page_score * 0.35 + field_score * 0.25 + func_score * 0.25 + inter_score * 0.15, 2
        )
        return {
            "score": score,
            "page_coverage": page_score,
            "field_coverage": field_score,
            "function_coverage": func_score,
            "interaction_coverage": inter_score,
            "detail": {
                "page": page_detail,
                "field": field_detail,
                "function": func_detail,
                "interaction": inter_detail,
            },
        }
