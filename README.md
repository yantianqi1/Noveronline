# MiroFish-Novel

MiroFish-Novel 是一个面向长篇小说创作的多智能体分析与写作平台。它把上传的小说、设定、大纲和素材转化为可检索的世界知识，生成角色 / 组织 / 关系 / 世界规则档案，并通过单世界 worldline 推演与 Writer Agent 工作台辅助作者完成续写、场景写作和审校。

> 当前状态：活跃开发中，已具备本地离线运行、统一数据库、种子分析、故事图谱、资产库、worldline 与写作工作台等主链能力；仍不建议直接作为生产级 SaaS 暴露到公网。

## 核心能力

- **种子分析**：上传 TXT / MD / PDF 后执行智能分段、顺序精读、全局聚合、故事本体生成和角色 Agent 档案生成。
- **故事图谱**：基于阅读笔记和 seed analysis 构建角色、组织、关系、事件、世界规则图谱，并写入统一数据库。
- **统一资产库**：以统一视图聚合素材、档案、伏笔、规则、关系、手稿块，并支持全文检索与 facets 过滤。
- **档案与记忆**：维护角色 / 组织 / 关系档案，区分 `canon`、`candidate`、`experiment` 记忆层级。
- **单世界 Worldline**：创建推演会话、准备角色 dossier、变量注入、自动演化、角色动作与对话，旧多分支接口已废弃。
- **Writer Agent**：支持书籍计划、章节 / 场景管理、续写、场景写作、手稿编译、世界数据更新、审校反馈与去重约束。
- **LLM 设施面板**：统一管理 OpenAI 兼容渠道、模型同步、模块绑定、并发限制与调用活动追踪。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11+ / FastAPI / Uvicorn / SQLAlchemy 2.0 / Alembic / Pydantic v2 |
| 前端 | React 19 / TypeScript / Vite 6 / React Router 7 / TanStack Query / Zustand / Tailwind CSS 4 / D3.js |
| LLM | OpenAI-compatible Chat Completions API，经 LLM 设施面板统一配置 |
| 存储 | SQLite 默认，Postgres-ready；schema 由 Alembic 管理 |

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- npm 9+
- 一个 OpenAI 兼容的 LLM API 渠道

### 1. 配置环境变量

```bash
cp .env.example .env
```

常用配置：

```bash
APP_HOST=0.0.0.0
APP_PORT=3888
APP_DEBUG=true
LLM_REQUEST_TIMEOUT_SECONDS=120
# DATABASE_URL=sqlite:///./data/mirofish.db
```

LLM API Key 不需要写入 `.env`，请在启动后进入前端「LLM 设施面板」配置渠道、模型和模块绑定。

### 2. 启动后端

推荐使用仓库内虚拟环境或 `uv`：

```bash
cd backend
uv sync
APP_PORT=3888 uv run python run.py
```

如果本机没有 `uv`：

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e .
APP_PORT=3888 .venv/bin/python run.py
```

后端启动时会自动执行 `alembic upgrade head`。API 文档地址：`http://localhost:3888/docs`。

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：`http://localhost:3999`。Vite 会把 `/api` 代理到 `http://127.0.0.1:3888`。

## 常用命令

```bash
# 后端测试
cd backend
env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 .venv/bin/python -m pytest tests

# 前端检查
cd frontend
npm run lint
npm run build
npm run test

# 数据库迁移
cd backend
uv run alembic upgrade head
uv run alembic revision -m "add_new_table"
uv run alembic downgrade -1
```

## 项目结构

```text
backend/
  app/
    api_fastapi/      FastAPI 路由，统一挂载在 /api
    services/         种子分析、图谱、资产、worldline、writer agent 等业务逻辑
    repositories/     数据访问层；服务应通过 repository 访问数据库
    tables/           SQLAlchemy 表定义，共享 metadata
    schemas/          Pydantic 请求 / 响应模型
    models/           轻量领域模型和运行时管理器
    middleware/       API Key 鉴权与异常处理
    utils/            LLM client、JSON 解析、文件解析、日志工具
  alembic/            数据库迁移
  tests/              后端测试

frontend/
  src/
    pages/            overview、assets、story-graph、worldline、writer 等页面
    components/       共享业务组件与 ui primitives
    api/              TypeScript API 客户端和 SSE 客户端
    stores/           Zustand 状态
    hooks/            React hooks
    lib/              工具函数
    types/            TypeScript 类型

docs/
  database/           数据库真相源矩阵
  plans/              设计和迁移计划
  superpowers/specs/  功能规格文档
```

## 核心约定

- **统一数据库优先**：默认数据库为 `backend/data/mirofish.db`；新增持久化能力必须经过 Alembic 迁移。
- **Repository 优先**：业务服务不直接拼 SQL；通过 `backend/app/repositories/` 访问数据。
- **LLM 模块绑定优先**：所有 LLM 调用走 `llm_channels`、`llm_models`、`llm_module_bindings`，未绑定模块应显式失败。
- **单世界 worldline**：当前产品语义是 `current_world` 单世界推进；旧 `/branches` 和 `/comparison` 风格接口不再扩展。
- **无静默兜底**：不要为了“跑通”加入 mock 成功、吞错、隐式降级或伪数据路径。
- **小说领域语言**：避免从上游 MiroFish 继承舆情、社媒、Twitter / Reddit 指标等不匹配抽象。

## 文档入口

- `AGENTS.md`：给 AI coding agent 的项目交接与开发约束。
- `CLAUDE.md`：给 Claude Code 的仓库导航、命令和架构说明。
- `docs/CODEX_HANDOFF_GUIDE.md`：更细的 Codex 接手指南。
- `docs/database/database-source-of-truth-matrix.md`：各业务域 DB / legacy JSON 真相源状态。
- `docs/fastapi-route-manifest.md`：FastAPI 路由清单。
- `docs/agent-data-schema-reference.md`：Agent 数据结构、prompt 和参数参考。

## 贡献

欢迎 issue、discussion 和 PR。提交前请阅读：

- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`

本仓库包含本地运行数据目录、LLM 调用日志和上传产物的忽略规则；请不要提交 API Key、用户小说原文、私有数据库或生成过程中的敏感数据。

## License

本项目以 `AGPL-3.0-only` 协议开源，详见 `LICENSE`。
