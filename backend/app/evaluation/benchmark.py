"""评估基准回归（Benchmark / Regression）。

对应文档：
- 《WebMind 项目评估体系设计》第 16 节：评估数据集（prd / design / expected_output / result）
- 《WebMind 评估体系两版对比与选型建议》第 11 节：Benchmark Matrix
  （任务类型 × 复杂度 × Agent 版本 × Prompt 版本 × 模型版本）

职责：
1. 读取 ``evaluation_dataset/manifest.json`` 登记的样本；
2. 逐条跑通「提交任务 → 主编排 → 六模块评估」；
3. 按复杂度分层（Level 1/2/3）聚合指标；
4. 与上一次运行做回归对比，回答"新版本到底有没有变好"；
5. 结果落 ``evaluation_dataset/result/``（JSON + Markdown）并写入文档库。

与 ``EvaluationRunner`` 的分工：EvaluationRunner 管"这一单多少分"，
BenchmarkRunner 管"这条生产线有没有在变好"。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.evaluation.evaluator import EvaluationRunner
from app.services import doc_store, llm as llm_service
from app.services import task_service

logger = get_logger("webmind.evaluation.benchmark")

LEVEL_LABELS = {
    "level1": "Level 1 简单",
    "level2": "Level 2 中等",
    "level3": "Level 3 复杂",
}
LEVEL_ORDER = ("level1", "level2", "level3")

# 回归对比的核心指标
REGRESSION_METRICS = (
    "avg_total_score",
    "avg_code_score",
    "avg_visual_score",
    "avg_requirement_score",
    "avg_agent_score",
    "avg_engineering_score",
    "hard_gate_pass_rate",
)


class BenchmarkRunner:
    """基准回归调度器。"""

    def __init__(self, dataset_dir: Path | None = None) -> None:
        self.dataset_dir = Path(dataset_dir) if dataset_dir else settings.evaluation_dataset_dir
        self.result_dir = self.dataset_dir / "result"
        self.result_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ 数据集
    def manifest(self) -> list[dict[str, Any]]:
        """读取数据集清单；无 manifest.json 时按 prd/ 目录自动推断。"""
        manifest_path = self.dataset_dir / "manifest.json"
        if manifest_path.exists():
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data.get("samples", [])
            if isinstance(data, list):
                return data

        samples: list[dict[str, Any]] = []
        prd_dir = self.dataset_dir / "prd"
        for prd in sorted(prd_dir.glob("*.md")) if prd_dir.exists() else []:
            level = next((key for key in LEVEL_ORDER if key in prd.stem), "level2")
            samples.append({"id": prd.stem, "level": level, "prd": f"prd/{prd.name}"})
        return samples

    def _read(self, rel: str) -> str:
        if not rel:
            return ""
        path = self.dataset_dir / rel
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _expected(self, sample: dict[str, Any]) -> dict[str, Any]:
        rel = sample.get("expected_output", "")
        if not rel:
            return {}
        path = self.dataset_dir / rel
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------- 期望覆盖率
    @staticmethod
    def _coverage(actual: list[str], expected: list[str]) -> float:
        """expected 中有多少出现在 actual 里（百分比）。"""
        if not expected:
            return 100.0
        actual_set = set(actual)
        hit = sum(1 for item in expected if item in actual_set)
        return round(hit / len(expected) * 100, 2)

    def _expected_coverage(self, requirement: dict[str, Any], expected: dict[str, Any]) -> dict[str, float]:
        """用 expected_output 反查需求解析的页面 / 字段 / 功能覆盖率。"""
        pages: list[str] = []
        fields: list[str] = []
        functions: list[str] = []
        for page in requirement.get("pages") or []:
            if isinstance(page, dict):
                if page.get("name"):
                    pages.append(str(page["name"]))
                for field in page.get("fields") or []:
                    if isinstance(field, dict):
                        fields.append(str(field.get("label") or field.get("name") or ""))
                    else:
                        fields.append(str(field))
                for func in page.get("functions") or []:
                    functions.append(str(func))
        return {
            "page": self._coverage(pages, expected.get("pages", [])),
            "field": self._coverage(fields, expected.get("fields", [])),
            "function": self._coverage(functions, expected.get("functions", [])),
        }

    # ------------------------------------------------------------------ 执行
    async def run(self, sample_ids: list[str] | None = None, tag: str = "") -> dict[str, Any]:
        """跑一遍基准回归，返回并落盘结果。"""
        samples = self.manifest()
        if sample_ids:
            wanted = set(sample_ids)
            samples = [s for s in samples if s.get("id") in wanted]
        if not samples:
            raise ValueError("评估数据集为空：请在 evaluation_dataset/manifest.json 中登记样本")

        runner = EvaluationRunner()
        records: list[dict[str, Any]] = []
        for sample in samples:
            sample_id = sample.get("id") or "sample"
            logger.info("[benchmark] 执行样本 %s（%s）", sample_id, sample.get("level", "level2"))
            task_id = await task_service.run_task_now(
                prd=self._read(sample.get("prd", "")),
                title=sample.get("title") or sample_id,
                project_id=sample.get("project_id"),
                target_platforms=sample.get("target_platforms") or ["web"],
                design_note=self._read(sample.get("design", "")) or sample.get("design_note", ""),
                owner="benchmark",
            )
            task = task_service.get_task(task_id) or {}
            evaluation = runner.run(task_id)
            coverage = self._expected_coverage(
                task.get("requirement_json") or {}, self._expected(sample)
            )
            records.append(
                {
                    "id": sample_id,
                    "level": sample.get("level", "level2"),
                    "title": sample.get("title", sample_id),
                    "task_id": task_id,
                    "status": task.get("status", ""),
                    "total_score": evaluation["total_score"],
                    "code_score": evaluation["code_score"],
                    "visual_score": evaluation["visual_score"],
                    "requirement_score": evaluation["requirement_score"],
                    "agent_score": evaluation["agent_score"],
                    "engineering_score": evaluation["engineering_score"],
                    "hard_gate_passed": evaluation["hard_gate_passed"],
                    "self_repair_count": evaluation["self_repair_count"],
                    "human_intervention": evaluation["human_intervention"],
                    "expected_coverage": coverage,
                }
            )

        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        summary = self._summarize(records)
        previous = self.latest()
        payload = {
            "run_id": run_id,
            "tag": tag,
            "generated_at": datetime.now().isoformat(),
            "dataset_dir": str(self.dataset_dir),
            "llm_mock_mode": llm_service.mock_mode(),
            "model_name": settings.MODEL_NAME,
            "summary": summary,
            "records": records,
            "regression": self._regression(summary, previous),
        }
        self._persist(payload)
        return payload

    # ------------------------------------------------------------------ 聚合
    @staticmethod
    def _avg(values: list[float]) -> float:
        clean = [v for v in values if v is not None]
        return round(sum(clean) / len(clean), 2) if clean else 0.0

    def _block(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {"samples": 0}
        count = len(rows)
        return {
            "samples": count,
            "avg_total_score": self._avg([r["total_score"] for r in rows]),
            "avg_code_score": self._avg([r["code_score"] for r in rows]),
            "avg_visual_score": self._avg([r["visual_score"] for r in rows]),
            "avg_requirement_score": self._avg([r["requirement_score"] for r in rows]),
            "avg_agent_score": self._avg([r["agent_score"] for r in rows]),
            "avg_engineering_score": self._avg([r["engineering_score"] for r in rows]),
            "avg_expected_coverage": self._avg(
                [
                    sum((r.get("expected_coverage") or {}).values()) / 3
                    for r in rows
                    if r.get("expected_coverage")
                ]
            ),
            "hard_gate_pass_rate": round(
                sum(1 for r in rows if r["hard_gate_passed"]) / count * 100, 2
            ),
            "self_repair_rate": round(
                sum(1 for r in rows if (r.get("self_repair_count") or 0) > 0) / count * 100, 2
            ),
            "human_intervention_rate": round(
                sum(1 for r in rows if r.get("human_intervention")) / count * 100, 2
            ),
        }

    def _summarize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        by_level: dict[str, Any] = {}
        for level in LEVEL_ORDER:
            rows = [r for r in records if r.get("level") == level]
            if rows:
                by_level[level] = {"label": LEVEL_LABELS.get(level, level), **self._block(rows)}
        return {"overall": self._block(records), "by_level": by_level}

    def _regression(self, summary: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
        """与上一次运行对比，回答"新版有没有变好"。"""
        if not previous:
            return {"baseline": True, "message": "首次运行，无历史基线可比"}
        prev_overall = (previous.get("summary") or {}).get("overall", {})
        cur_overall = summary["overall"]
        delta = {
            metric: round(cur_overall.get(metric, 0) - prev_overall.get(metric, 0), 2)
            for metric in REGRESSION_METRICS
        }
        total_delta = delta["avg_total_score"]
        comparable = prev_overall.get("samples") == cur_overall.get("samples")
        if not comparable:
            verdict = "样本集不同，仅供参考"
        elif total_delta > 0.01:
            verdict = "较上次提升"
        elif total_delta < -0.01:
            verdict = "较上次下降"
        else:
            verdict = "与上次持平"
        return {
            "baseline": False,
            "previous_run": previous.get("run_id"),
            "previous_samples": prev_overall.get("samples"),
            "current_samples": cur_overall.get("samples"),
            "comparable": comparable,
            "delta": delta,
            "total_delta": total_delta,
            "verdict": verdict,
        }

    # ------------------------------------------------------------------ 落盘
    def _persist(self, payload: dict[str, Any]) -> None:
        run_id = payload["run_id"]
        json_path = self.result_dir / f"benchmark-{run_id}.json"
        md_path = self.result_dir / f"benchmark-{run_id}.md"
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        md_path.write_text(self._markdown(payload), encoding="utf-8")
        doc_store.insert("benchmark_runs", payload)
        payload["json_path"] = str(json_path)
        payload["markdown_path"] = str(md_path)
        logger.info("[benchmark] 回归结果已落盘：%s", json_path)

    def _run_files(self) -> list[Path]:
        return sorted(self.result_dir.glob("benchmark-*.json"))

    def latest(self) -> dict[str, Any] | None:
        files = self._run_files()
        if not files:
            return None
        return json.loads(files[-1].read_text(encoding="utf-8"))

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in self._run_files()[-limit:]:
            data = json.loads(path.read_text(encoding="utf-8"))
            items.append(
                {
                    "run_id": data.get("run_id"),
                    "tag": data.get("tag", ""),
                    "generated_at": data.get("generated_at"),
                    "overall": (data.get("summary") or {}).get("overall", {}),
                    "regression": data.get("regression", {}),
                }
            )
        return items

    def _markdown(self, payload: dict[str, Any]) -> str:
        overall = payload["summary"]["overall"]
        regression = payload.get("regression", {})
        lines = [
            "# WebMind Benchmark Report（基准回归）",
            "",
            f"- 运行编号：{payload['run_id']}",
            f"- 生成时间：{payload['generated_at']}",
            f"- 标签：{payload.get('tag') or '-'}",
            f"- 样本数：{overall.get('samples', 0)}",
            f"- 模型：{payload.get('model_name')}（{'本地启发式' if payload.get('llm_mock_mode') else '真实模型'}）",
            "",
            "## 总体指标",
            "",
            f"- 平均综合分：{overall.get('avg_total_score')}",
            f"- Hard Gate 通过率：{overall.get('hard_gate_pass_rate')}%",
            f"- 平均代码可用性：{overall.get('avg_code_score')}",
            f"- 平均页面还原度：{overall.get('avg_visual_score')}",
            f"- 平均需求理解：{overall.get('avg_requirement_score')}",
            f"- 平均 Agent 执行：{overall.get('avg_agent_score')}",
            f"- 平均工程规范：{overall.get('avg_engineering_score')}",
            f"- 期望覆盖率（对照 expected_output）：{overall.get('avg_expected_coverage')}%",
            f"- 触发自修复比例：{overall.get('self_repair_rate')}%",
            f"- 转人工比例：{overall.get('human_intervention_rate')}%",
            "",
        ]

        by_level = payload["summary"].get("by_level") or {}
        if by_level:
            lines += ["## 分层指标", "", "| 复杂度 | 样本数 | 平均综合分 | Hard Gate 通过率 | 期望覆盖率 |", "|---|---|---|---|---|"]
            for level in LEVEL_ORDER:
                block = by_level.get(level)
                if not block:
                    continue
                lines.append(
                    f"| {block.get('label', level)} | {block['samples']} | "
                    f"{block['avg_total_score']} | {block['hard_gate_pass_rate']}% | "
                    f"{block['avg_expected_coverage']}% |"
                )
            lines.append("")

        lines += [
            "## 样本明细",
            "",
            "| 样本 | 复杂度 | 状态 | 综合分 | 代码 | 视觉 | 需求 | Agent | 工程 | Hard Gate |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for record in payload["records"]:
            lines.append(
                f"| {record['title']} | {LEVEL_LABELS.get(record['level'], record['level'])} | "
                f"{record['status']} | {record['total_score']} | {record['code_score']} | "
                f"{record['visual_score']} | {record['requirement_score']} | "
                f"{record['agent_score']} | {record['engineering_score']} | "
                f"{'通过' if record['hard_gate_passed'] else '未通过'} |"
            )
        lines.append("")

        lines += ["## 回归对比", ""]
        if regression.get("baseline"):
            lines.append(f"- {regression.get('message')}")
        else:
            lines.append(f"- 对比基线：{regression.get('previous_run')}")
            lines.append(
                f"- 样本数：本次 {regression.get('current_samples')} / 基线 {regression.get('previous_samples')}"
            )
            if not regression.get("comparable", True):
                lines.append("- 注意：两次运行样本集不同，差值仅供参考")
            lines.append(f"- 结论：{regression.get('verdict')}（综合分 {regression.get('total_delta'):+}）")
            delta = regression.get("delta") or {}
            for metric, value in delta.items():
                lines.append(f"  - {metric}：{value:+}")
        lines.append("")
        return "\n".join(lines)
