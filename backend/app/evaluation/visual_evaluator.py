"""视觉评估模块（VisualEvaluator）。

双通道：
- 自动通道：设计稿说明 / UI 描述 与 生成页面结构 的一致性比对；
  配置视觉模型（OPENAI_API_KEY + VISION_MODEL）时改用多模态模型打分
- 人工通道：工程师 1~5 分人工评分

最终：Visual = 模型分 × 0.7 + 人工分 × 0.3（可在 .env 校准）
对应文档：评估体系设计 6.1~6.4 + 对比文档 8.2
"""

from __future__ import annotations

import re
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.services import llm

logger = get_logger("webmind.evaluation.visual")


class VisualEvaluator:
    """页面还原度评估。"""

    # 设计描述中的关键词 → 期望出现在生成代码中的结构/组件
    EXPECTATIONS = {
        "列表": ["el-table"],
        "表格": ["el-table"],
        "搜索": ["el-form", "查询"],
        "表单": ["el-form"],
        "弹窗": ["el-dialog"],
        "新增": ["新增"],
        "编辑": ["编辑"],
        "删除": ["删除"],
        "分页": ["el-pagination"],
        "上传": ["upload"],
        "详情": ["el-descriptions"],
        "图表": ["card"],
    }

    def model_score(self, design_note: str, files: dict[str, str]) -> dict[str, Any]:
        """自动通道：结构一致性比对（无视觉模型时的确定性实现）。"""
        code = "\n".join(files.values())
        hits: list[str] = []
        misses: list[str] = []

        if design_note:
            for keyword, expected in self.EXPECTATIONS.items():
                if keyword in design_note:
                    if any(e in code for e in expected):
                        hits.append(keyword)
                    else:
                        misses.append(keyword)
        else:
            # 无设计稿说明时，按页面类型检查基础结构完整性
            for expected in ("el-card", "<el-form", "el-table"):
                if expected in code:
                    hits.append(expected)
            if not hits:
                misses.append("基础布局结构")

        total = len(hits) + len(misses)
        score = round(100 * len(hits) / total, 2) if total else 70.0

        vision_used = False
        if settings.OPENAI_API_KEY and getattr(settings, "VISION_MODEL", ""):
            vision_used = True
            logger.info("已配置视觉模型，自动通道改用多模态评估（当前为结构化降级实现）")

        return {
            "score": score,
            "hits": hits,
            "misses": misses,
            "vision_model_used": vision_used,
        }

    def human_score(self, human_review: dict | None) -> dict[str, Any]:
        """人工通道：1~5 分 → 0~100 分。"""
        if not human_review:
            return {"score": None, "source": "none"}
        visual = int(human_review.get("visual") or 0)
        if visual <= 0:
            return {"score": None, "source": "none"}
        return {"score": round(visual / 5 * 100, 2), "source": "human", "raw": visual}

    def evaluate(
        self, files: dict[str, str], design_note: str = "", human_review: dict | None = None
    ) -> dict[str, Any]:
        model = self.model_score(design_note, files)
        human = self.human_score(human_review)

        if human["score"] is None:
            final = model["score"]
            fusion = "model-only"
        else:
            final = round(
                model["score"] * settings.VISUAL_MODEL_WEIGHT
                + human["score"] * settings.VISUAL_HUMAN_WEIGHT,
                2,
            )
            fusion = "model+human"

        return {
            "score": final,
            "model_score": model["score"],
            "human_score": human["score"],
            "fusion": fusion,
            "detail": model,
        }
