# MiroFish-Novel

面向小说创作的多智能体分析与写作平台。上传小说全文，自动构建世界观图谱、角色档案与关系网络，在世界线中推演剧情走向，并通过多 Agent 协作流水线辅助创作。

## 功能概览

### 种子分析 — 从小说到结构化知识

上传小说文本（PDF / MD / TXT，最大 100 MB），平台通过四阶段 LLM 驱动管线完成深度解析：

| 阶段 | 说明 |
|------|------|
| **文本准备** | 智能分段，按 token 预算切分阅读单元 |
| **深度阅读** | LLM 逐段精读，维持跨段记忆，提取角色、关系、线索、世界观 |
| **全局整合** | 聚合所有阅读笔记，生成 seed_analysis + 故事本体 (ontology) |
| **角色构建** | 为重要角色并发生成结构化 Agent 档案（性格、语言、动机、知识边界） |

每个步骤的 LLM 调用（完整 prompt + response）均被记录，前端可逐步展开查看。

### 故事图谱

从种子分析数据构建力导向关系图谱（D3.js）。节点按重要性分层（protagonist / major / supporting / minor），边权重反映关系深度。工具栏式布局，图谱画布最大化；支持实体类型过滤、点击查看角色档案详情。

### 档案库

自动为角色、组织、关系生成结构化档案。按重要性层级使用不同模板深度：
- **protagonist / major**: 8 个维度（身份、动机、张力、关系、行为、状态、风险、隐私）
- **supporting**: 5 个维度
- **minor**: 3 个维度

档案支持搜索、筛选、重建索引，是世界线推演和写作流水线的核心数据来源。

### 世界线推演

基于单世界模型的剧情推演引擎（全部运行状态落在统一数据库）：
- 创建世界线会话，注入变量改变剧情走向
- 角色 Agent 可独立提出动作、参与对话
- 自动推演（auto-evolution）通过 SSE 实时流式输出
- 高价值推演结果进入 candidate 记忆层，需作者审核后升级为 canon

### 写作工作台

多 Agent 协作的创作辅助系统：
- **Agent 工具循环**: 写作 Agent 拥有 write_prose / compile_manuscript / set_scene_status 等工具，自主规划写作步骤
- **检索规划员**: 正式写作前由轻量 LLM 单次预演，输出 `<retrieval_plan>` 注入 orchestrator，作为最低检索基线
- **世界数据写入工具**: Agent 可通过 manage_entity / manage_thread / manage_world_rule / manage_relationship 增量维护世界设定
- **世界数据更新**: 散文提交后，可一键触发 Agent 分析并更新实体、伏笔、规则等世界数据
- **实体关联查询**: query_entity 返回角色关联伏笔线索 + 适用世界规则，一次调用获取完整上下文
- **大纲版本管理**: 大纲保存时自动快照（`outline_versions` 表），支持版本历史浏览、预览对比、标签标注、一键恢复
- **章节 / 场景管理**: 创建章节、拆分场景、设置 POV 角色、管理预设
- **手稿阅读**: TOC 导航 + 散文视图，手稿块统一以 `asset_type='manuscript_block'` 存放于资产表
- **记忆系统**: 短期记忆 (episodic) + 长期记忆 (canon / candidate / experiment) 分层管理
- **任务类型**: write_scene（场景写作）、continue（续写）、outline（章节大纲生成）

### 资产库（统一视图）

将角色档案、组织、关系、伏笔线索、世界规则、上传素材、手稿块等数据源以**只读**方式聚合为统一的「资产条目」视图，并通过可插拔的全文检索后端（SQLite FTS / LIKE / Postgres）支持跨 silo 搜索与 facets 过滤。配套的 Ingestion Agent 可将自由素材抽取为结构化资产，写作 Agent 可统一检索。

### LLM 设施面板

统一管理所有 LLM 渠道、模型与模块绑定（`llm_channels` / `llm_models` / `llm_module_bindings` 表）。支持多渠道配置、模块级别的模型指定、并发控制与活动追踪。

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+（前端构建需要）
- 至少一个 OpenAI 兼容的 LLM API

### 后端

```bash
cd backend
uv sync                              # 安装依赖
APP_PORT=3888 uv run python run.py    # 启动 FastAPI（uvicorn）
```

如果 `uv` 不可用：

```bash
cd backend
pip install -e .                     # 基于 pyproject.toml 安装
APP_PORT=3888 python3 run.py
```

启动时会自动执行 `alembic upgrade head`，把统一数据库升级到最新 schema。

### 前端

```bash
cd frontend
npm install
npm run dev                          # 开发服务器（http://localhost:3999，自动代理 /api 到后端 :3888）
npm run build                        # 生产构建（tsc -b && vite build）
npm run lint                         # 类型检查（tsc --noEmit）
npm run test                         # Vitest
```

### 配置

复制 `.env.example` 为 `.env` 并按需修改：

```bash
# LLM 配置通过前端"LLM 设施面板"统一管理，无需在此设置 API key
LLM_REQUEST_TIMEOUT_SECONDS=120

# App runtime
APP_HOST=0.0.0.0
APP_PORT=3888
APP_DEBUG=true

# Unified database（默认 SQLite，可切换至 Postgres）
# DATABASE_URL=sqlite:///./data/mirofish.db

# Zep（可选，仅在线图谱构建需要）
ZEP_API_KEY=your_zep_api_key_here
```

启动后访问 `http://localhost:3999`，在 LLM 设施面板中配置至少一个 LLM 渠道即可开始使用。

## 测试

```bash
cd backend
PYTHONPATH=$(pwd) pytest tests/                            # 全部测试
PYTHONPATH=$(pwd) pytest tests/test_worldline_engine.py    # 单文件
PYTHONPATH=$(pwd) pytest tests/test_xxx.py::test_func      # 单测试
```

Alembic 迁移操作：

```bash
cd backend
uv run alembic upgrade head                      # 升级到最新 schema
uv run alembic revision -m "add_foo_table"       # 新建迁移
uv run alembic downgrade -1                      # 回滚一版
```

## 项目结构

```
backend/
  app/
    api_fastapi/      # FastAPI 路由（挂载在 /api 前缀下）
    services/         # 核心业务逻辑
      agents/         #   Agent 子系统（memory / registry / worldline）
      assets/         #   资产与统一视图、Ingestion Agent、风格抽取
      writer_agent/   #   写作工作台服务（扁平模块布局）
    repositories/     # 单一职责的 DB 仓库（每个域一个）
      search_backends/#   可插拔全文检索后端
    schemas/          # Pydantic 请求/响应模式
    tables/           # SQLAlchemy 表定义（共享 metadata）
    models/           # 轻量领域数据类（Project / Task / Worldline）
    middleware/       # API-Key Auth + 异常处理
    database.py       # 引擎工厂、alembic 驱动的 init_db
    dependencies.py   # FastAPI 依赖注入
    config.py         # Pydantic Settings + legacy Config
    main.py           # FastAPI app factory
    utils/            # LLM client、文件解析、日志等
  alembic/            # 数据库迁移版本
  alembic.ini
  tests/              # 后端测试
frontend/
  src/
    pages/            # 路由页面（每页一个文件夹 + page.tsx）
    components/       # 共享组件（含 shadcn/ui primitives）
    api/              # 后端 API 客户端（TypeScript）
    stores/           # Zustand 状态存储
    hooks/            # React hooks
    lib/              # 工具函数
    types/            # TypeScript 类型
    router.tsx        # React Router 7 路由表
docs/
  database/database-source-of-truth-matrix.md  # 统一库真相源矩阵
  agent-data-schema-reference.md               # Agent 数据结构与提示词参考
  plans/                                       # 迁移与开发计划
  superpowers/specs/                           # 功能规格文档
data/
  mirofish.db        # 默认统一数据库文件（由 DATABASE_URL 决定）
```

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11+ / FastAPI / Uvicorn / SQLAlchemy 2.0 / Alembic / Pydantic v2 |
| 前端 | React 19 / TypeScript / Vite 6 / TanStack Query / Zustand / React Router 7 / Tailwind CSS 4 / shadcn/ui + Base UI + Radix / D3.js v7 |
| LLM | OpenAI 兼容 API（通过设施面板统一管理） |
| 持久化 | 统一 SQLite/Postgres 数据库（alembic 管理 schema）+ FTS 全文索引 |

## 核心概念

| 概念 | 说明 |
|------|------|
| **种子分析 (Seed)** | 上传小说后的四阶段 LLM 深度解析流程 |
| **故事本体 (Ontology)** | 从小说中提取的实体类型、关系类型与叙事轴定义 |
| **档案 (Archive)** | 角色/组织/关系的结构化描述，按重要性分层 |
| **世界线 (Worldline)** | 基于单世界模型的剧情推演空间（状态全部落库） |
| **Agent 档案** | 角色转化为可交互 Agent 所需的性格、语言、动机等数据 |
| **记忆层级** | canon（已确认）/ candidate（待审核）/ experiment（实验性） |
| **实体关联 (Entity Associations)** | 伏笔线索与世界规则自动关联到实体，查询时一并返回 |
| **大纲版本 (Outline Versions)** | 大纲保存时自动快照，支持历史浏览、预览、恢复 |
| **Chapter Context Pack** | 写作时的统一上下文（must_know / should_know / warnings） |
| **统一数据库 (Unified DB)** | 单一 SQLite/Postgres 库承载几乎全部持久化状态；schema 由 alembic 管理 |
| **Project Artifacts 表** | `project_artifacts` 作为旧 JSON 产物的 DB 镜像，种子/图谱/小说运行时读已切换至此表 |
| **Repository 层** | `app/repositories/` 下的每域仓库；服务必须通过仓库访问数据库 |

## 开发参考

- [Agent 数据结构与提示词参考](./docs/agent-data-schema-reference.md) — 所有 Agent 的数据 schema、LLM 提示词、参数配置
- [数据库真相源矩阵](./docs/database/database-source-of-truth-matrix.md) — 每个业务域的 DB vs legacy JSON 状态
- [数据库统一化迁移计划](./docs/plans/2026-04-14-database-unification-migration-plan.md) — Phase C–H 总计划
- [剩余阶段实施指南](./docs/plans/2026-04-17-remaining-phases-implementation-guide.md) — Phase D4/D11/E/F/G/H 详细指南
- [FastAPI 路由清单](./docs/fastapi-route-manifest.md) — 当前 REST 端点
- [种子管线重设计](./docs/superpowers/specs/2026-04-03-seed-pipeline-redesign.md)
- [写作 Agent 设计](./docs/superpowers/specs/2026-04-02-novel-writer-agent-design.md)
- [手稿阅读模式设计](./docs/superpowers/specs/2026-04-04-manuscript-reading-mode-design.md)
- [大纲版本管理设计](./docs/superpowers/specs/2026-04-05-outline-versioning-design.md)

## License

Private repository.
