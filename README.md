# WebMind

**多 Agent 协作的前端智能研发平台** —— 用一段自然语言描述需求，自动完成「需求解析 → 页面生成 → 代码审查 → 多端适配 → 质量评估」全链路，产出可直接运行的前端工程。

WebMind 关注的不只是"能不能生成代码"，而是**生成出来的东西能不能交付**：每一份产物都要经过静态审查、多端适配和六维质量评估，跑不起来的产物一律判定为不合格。

---

## 目录

- [核心特性](#核心特性)
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [目录结构](#目录结构)
- [API 一览](#api-一览)
- [评估体系](#评估体系)
- [常见问题](#常见问题)

---

## 核心特性

| 能力 | 说明 |
|---|---|
| **需求解析** | 支持自然语言与 Markdown PRD 两种输入，输出结构化的页面模型（页面 / 字段 / 功能点 / 组件选型），并给出置信度；置信度低于阈值时自动转人工澄清，而不是硬着头皮往下走 |
| **页面生成** | 基于**组件白名单**确定性生成 Vue 3 工程 —— 页面、路由、mock 数据、构建配置一次产出。白名单外的组件会被拦截并回退重写，从机制上杜绝"幻觉组件" |
| **代码审查 + 自修复** | 对生成产物做静态审查，发现问题自动回退重写，最多 2 轮；仍不通过则转人工，不把问题留到下游 |
| **多端适配** | 同一份页面模型可产出 **Web 版**与 **uni-app 小程序版**（通过条件编译指令区分平台差异） |
| **六维质量评估** | 代码可用性 / 页面还原度 / 需求理解 / Agent 执行 / 工程规范 / 人工评分，加权得出综合分；配合 Hard Gate 做"一票否决" |
| **基准回归** | 内置评测数据集，按复杂度分层跑批，与历史运行逐指标对比，直接回答"**这个版本到底有没有变好**" |
| **可视化工作台** | 任务创建、执行进度、产物预览与下载、评估看板、基准回归，全部在浏览器里完成 |

---

## 系统架构

主编排（Orchestration）负责业务流转与状态管理，各 Agent 只专注自己的职责：

```text
需求输入 · 自然语言 / Markdown PRD
        │
        ▼
需求解析 Agent
        ├──[置信度不足]──▶ 人工澄清
        ▼
页面生成 Agent
        │
        ▼
代码审查 Agent
        ├──[不通过]──▶ 回退修复（最多 2 轮）──▶ 回到「页面生成 Agent」
        ▼
多端适配 Agent
        │
        ▼
工程产物 · Web + uni-app 小程序
        │
        ▼
六维质量评估
        │
        ▼
基准回归 / 看板
```

编排层基于 LangGraph 的 `StateGraph` 实现：节点即 Agent，边即流转规则，审查结果通过**条件路由**决定是回到生成、进入适配，还是转交人工。状态由 Checkpointer 持久化，任务中断后可恢复。

---

## 技术栈

| 层次 | 选型 |
|---|---|
| **语言** | Python 3.11+（后端）、TypeScript 5（前端） |
| **后端框架** | FastAPI · Pydantic v2 · Uvicorn |
| **Agent 编排** | LangGraph（StateGraph / 条件路由 / Checkpointer）· LangChain Core |
| **模型接入** | OpenAI 兼容的 HTTP 接口 —— 可对接 OpenAI、DeepSeek、Moonshot、本地 vLLM / Ollama 等任意兼容服务 |
| **前端框架** | Vue 3（Composition API）· Vite 5 · Element Plus · Vue Router 4 · Axios |
| **关系型存储** | MySQL 8（SQLAlchemy 2 + PyMySQL） |
| **文档型存储** | MongoDB 7（PyMongo） |
| **缓存 / 状态** | Redis 7 |
| **部署** | Docker · Docker Compose · Nginx |

### 关于依赖

三个存储组件与模型服务都是**可插拔**的：未配置时自动降级到等价的本地实现 —— MySQL → SQLite、MongoDB → 本地 JSON、Redis → 进程内缓存、模型服务 → 内置规则引擎。

这意味着 `git clone` 之后**不装任何外部服务也能直接跑起来**，先把流程走通，再按需接入真实基础设施。生产部署则通过 `docker-compose.yml` 一键拉起完整依赖。

---

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
cp .env.example .env

cd deploy
docker compose up -d --build
```

启动完成后：

| 服务 | 地址 |
|---|---|
| 前端工作台 | http://localhost:8080 |
| 后端接口文档 | http://localhost:8000/docs |

MySQL、MongoDB、Redis 会一并启动，后端自动使用它们（无需额外配置）。

### 方式二：本地开发

**后端**

```bash
cd backend

# 创建虚拟环境（推荐，避免污染全局环境）
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python start.py
```

后端启动后：http://127.0.0.1:8000/docs

**前端**

```bash
cd frontend
npm install
npm run dev
```

前端启动后：http://127.0.0.1:5173（开发服务器已配置 `/api` 代理到后端 8000 端口）

> 本地开发无需启动任何数据库。不配置 `.env` 也能运行 —— 所有外部依赖都会自动降级。

### 冒烟测试

后端启动后，可一键验证全链路是否正常：

```bash
cd backend
python smoke_test.py
```

脚本会依次走完「健康检查 → 创建任务 → 等待执行 → 查看产物 → 质量评估 → 人工评分 → 确认合并 → 查看报告」，并打印每一步的结果。

---

## 配置说明

所有配置通过项目根目录的 `.env` 管理（可从 `.env.example` 复制）。常用项：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OPENAI_API_KEY` | 空 | 模型服务凭据；留空则使用内置规则引擎 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | 任何 OpenAI 兼容服务的地址 |
| `MODEL_NAME` | `gpt-4.1` | 调用的模型名 |
| `VISION_MODEL` | 空 | 可选，多模态模型名；配置后视觉评估切换到模型打分通道 |
| `DB_BACKEND` | `auto` | `auto` / `mysql` / `sqlite` |
| `DOC_STORE_BACKEND` | `auto` | `auto` / `mongo` / `json` |
| `CACHE_BACKEND` | `auto` | `auto` / `redis` / `memory` |
| `MAX_SELF_REPAIR` | `2` | 审查不通过时的最大自修复轮数 |
| `EVAL_HARD_GATE` | `true` | 是否启用 Hard Gate 一票否决 |
| `EVALUATION_DATASET_DIR` | `./evaluation_dataset` | 评测数据集目录 |

`auto` 表示启动时探测，可用则用、不可用则降级。想固定某一种后端时显式指定即可。

---

## 目录结构

```
WebMind/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── agents/             # 四个 Agent：需求解析 / 页面生成 / 代码审查 / 多端适配
│   │   ├── workflows/          # LangGraph 主编排图与状态定义
│   │   ├── evaluation/         # 六维评估模块 + 基准回归
│   │   ├── rag/                # 组件知识库检索
│   │   ├── services/           # 代码生成、模型调用、存储、任务调度
│   │   ├── api/                # HTTP 接口
│   │   └── core/               # 配置与日志
│   ├── requirements.txt
│   ├── start.py                # 后端启动入口
│   ├── run_benchmark.py        # 基准回归命令行
│   └── smoke_test.py           # 端到端冒烟测试
├── frontend/                   # Vue 3 工作台
│   └── src/views/              # 任务创建 / 任务列表 / 任务详情 / 评估看板 / 基准回归
├── knowledge/
│   └── component_docs/         # 组件知识库（生成时的白名单来源）
├── evaluation_dataset/         # 评测数据集：PRD 样本 / 设计说明 / 期望产物
├── deploy/                     # Dockerfile、docker-compose、Nginx、MySQL 初始化
└── .env.example
```

---

## API 一览

后端完整交互式文档见 `/docs`（Swagger UI）。

**任务**

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/task/create` | 创建生成任务 |
| `POST` | `/api/task/upload` | 上传 PRD 文件创建任务 |
| `GET` | `/api/task/list` | 任务列表 |
| `GET` | `/api/task/{task_id}` | 任务详情与执行状态 |
| `GET` | `/api/task/{task_id}/files` | 产物文件列表 |
| `GET` | `/api/task/{task_id}/download` | 打包下载产物 |
| `POST` | `/api/task/{task_id}/confirm` | 确认合并（记录修正类型） |

**评估**

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/evaluation/run/{task_id}` | 触发六维评估 |
| `GET` | `/api/evaluation/result/{task_id}` | 查询评估结果 |
| `POST` | `/api/evaluation/human/{task_id}` | 提交人工评分 |
| `GET` | `/api/evaluation/dashboard` | 聚合看板指标 |
| `GET` | `/api/evaluation/report` | 生成评估报告 |
| `POST` | `/api/evaluation/benchmark/run` | 跑一次基准回归 |
| `GET` | `/api/evaluation/benchmark/latest` | 最近一次基准结果 |
| `GET` | `/api/evaluation/benchmark/runs` | 基准回归历史 |

**系统**

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 健康检查（含各组件的降级状态） |
| `GET` | `/api/projects` | 产品线列表 |

---

## 评估体系

综合分由六个维度加权得出：

| 维度 | 权重 | 关注点 |
|---|---|---|
| 代码可用性 | 30% | 依赖安装、构建、启动、核心功能是否真的可用 |
| 页面还原度 | 25% | 生成结构与设计说明的一致性 |
| 需求理解 | 20% | 页面 / 字段 / 功能点的覆盖率 |
| Agent 执行 | 15% | 各阶段执行情况与自修复轮数 |
| 工程规范 | 10% | 目录结构、命名、依赖、重复与死代码、TS / Lint 配置 |
| 人工评分 | — | 工程师 1~5 分打分，与自动结果按 7:3 融合 |

**Hard Gate（一票否决）**：依赖安装、构建、启动、核心功能四项中任意一项失败，综合分直接封顶 —— 一个跑不起来的工程，界面再漂亮也没有意义。

**基准回归**则解决另一个问题：单次评估只能说明"这一单得了多少分"，而基准回归把一批样本（按 Level 1/2/3 分层）跑一遍并留存结果，下次运行自动与历史对比，给出"较上次提升 / 持平 / 下降"以及各维度的具体差值。它回答的是"**这条产线有没有在变好**"。

---

## 常见问题

**Q：一定要配模型 API 吗？**
不一定。没有配置凭据时会使用内置规则引擎完成解析与选型，全链路依然可以走通，方便先了解产品形态；接入真实模型后，需求理解的灵活度会明显提升。

**Q：一定要装 MySQL / MongoDB / Redis 吗？**
不需要。三者都是可选的，缺失时自动降级到本地实现，数据落在 `data/` 目录下。想体验完整形态用 Docker Compose 即可。

**Q：生成的前端工程能直接跑吗？**
可以。产物是一个完整的 Vite + Vue 3 工程，包含 `package.json`、构建配置、路由与 mock 数据，`npm install && npm run dev` 即可启动；多端产物则是标准的 uni-app 工程结构。

**Q：接口数据是假的吗？**
页面里的接口调用默认生成 mock 实现 —— 这是有意的设计：WebMind 负责把页面骨架和交互逻辑做出来，真实接口由工程师按团队规范接入。接口调用规范见 `knowledge/component_docs/api-docs.md`。
