"""基准回归命令行入口。

用法：
    python run_benchmark.py                          # 全量样本
    python run_benchmark.py --tag prompt-v2          # 打标签，便于回归对比
    python run_benchmark.py --samples level1_login,level1_list

结果同时落 evaluation_dataset/result/（JSON + Markdown）。
"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.evaluation.benchmark import BenchmarkRunner
from app.models.database import init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="WebMind 基准回归（Benchmark / Regression）")
    parser.add_argument("--tag", default="", help="本次运行标签，如 prompt-v2 / agent-v3")
    parser.add_argument("--samples", default="", help="只跑指定样本 id，逗号分隔；默认全量")
    args = parser.parse_args()

    # 命令行独立运行不会经过 FastAPI 的 lifespan，需自行建表，
    # 否则在全新环境（还没有 data/webmind.db）下会报 no such table。
    init_db()

    sample_ids = [item.strip() for item in args.samples.split(",") if item.strip()] or None
    payload = asyncio.run(BenchmarkRunner().run(sample_ids=sample_ids, tag=args.tag))

    print("== benchmark ==")
    print(json.dumps({"run_id": payload["run_id"], **payload["summary"]["overall"]}, ensure_ascii=False, indent=2))
    print("regression:", json.dumps(payload["regression"], ensure_ascii=False))
    print("json:", payload.get("json_path"))
    print("md:  ", payload.get("markdown_path"))


if __name__ == "__main__":
    main()
