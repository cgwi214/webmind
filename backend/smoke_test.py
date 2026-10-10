"""端到端冒烟测试：创建任务 → 等待执行 → 查看产物 → 跑评估 → 拿报告。"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BASE = os.environ.get("WEBMIND_BASE", "http://127.0.0.1:8000")

PRD = """用户管理后台需求

1. 用户列表页面
字段：用户名、手机号、状态、注册时间、所属部门
功能：支持按用户名搜索、新增用户、编辑用户、删除用户、分页展示

2. 用户新增表单页面
字段：用户名、手机号、邮箱、所属部门、备注
功能：提交、重置

3. 系统配置页面
字段：系统名称、是否开启注册、最大登录次数
功能：保存配置
"""


def call(method: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    print("== health ==")
    print(json.dumps(call("GET", "/api/health"), ensure_ascii=False, indent=2))

    print("== create task ==")
    created = call(
        "POST",
        "/api/task/create",
        {
            "prd": PRD,
            "title": "用户管理后台",
            "target_platforms": ["web", "mp-weixin"],
            "design_note": "列表页包含搜索区、表格、分页；表单页含新增弹窗；配置页为表单",
            "project_id": 1,
        },
    )
    task_id = created["task_id"]
    print(json.dumps(created, ensure_ascii=False))

    for _ in range(60):
        time.sleep(2)
        task = call("GET", f"/api/task/{task_id}")
        if task["status"] in ("delivered", "human_required", "failed", "confirmed"):
            break
    print("== task status ==")
    print(json.dumps({k: task[k] for k in ("status", "current_agent", "confidence", "retry_count", "self_repair_count")}, ensure_ascii=False))
    print("requirement pages:", [p["name"] for p in (task.get("requirement_json") or {}).get("pages", [])])

    print("== files ==")
    files = call("GET", f"/api/task/{task_id}/files")
    print("version:", files["version"], "files:", list(files["files"].keys())[:12])

    print("== evaluation ==")
    evaluation = call("POST", f"/api/evaluation/run/{task_id}")
    print(json.dumps({k: evaluation[k] for k in ("total_score", "code_score", "visual_score", "requirement_score", "agent_score", "engineering_score", "hard_gate_passed")}, ensure_ascii=False, indent=2))

    print("== human review ==")
    human = call(
        "POST",
        f"/api/evaluation/human/{task_id}",
        {"visual": 4, "completeness": 4, "code_quality": 4, "modification_cost": 3, "business_fit": 4, "error_type": "组件错误", "error_severity": "minor", "modified_files": 2, "modification_count": 5},
    )
    print(json.dumps(human, ensure_ascii=False))

    print("== confirm merge ==")
    print(json.dumps(call("POST", f"/api/task/{task_id}/confirm", {"correction_type": "组件错了", "comment": "替换了两个组件"}), ensure_ascii=False))

    print("== dashboard ==")
    dashboard = call("GET", "/api/evaluation/dashboard")
    print(json.dumps(dashboard["aggregate"], ensure_ascii=False, indent=2))
    print(json.dumps(dashboard["suggestions"], ensure_ascii=False, indent=2))

    print("== report (first 20 lines) ==")
    report = call("GET", "/api/evaluation/report?save=true")
    print("\n".join(report["content"].splitlines()[:20]))
    print("saved:", report.get("path"))


if __name__ == "__main__":
    main()
