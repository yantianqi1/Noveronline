# AGENTS.md

## 目的

这份文档给后续 AI coding agent 快速接手 `MiroFish-Novel` 使用。它应与 `README.md`、`CLAUDE.md` 和 `docs/database/database-source-of-truth-matrix.md` 保持一致。

更新时间：`2026-04-25`

## 项目定位

`MiroFish-Novel` 是面向长篇小说创作的多智能体分析与写作平台。核心目标不是舆情分析，而是：

- 读取小说文本、设定、大纲、角色卡和自由素材
- 提取角色、组织、关系、伏笔、世界规则与叙事阶段
- 建立统一数据库中的故事图谱、档案库和资产库
- 通过单世界 worldline 做剧情推演、变量注入和角色互动
- 为 Writer Agent 提供可消费上下文，并产出正文、续写、审校和世界数据更新

主链：`上传小说 -> seed pipeline -> ontology / graph -> archives / assets -> worldline -> writer agent -> manuscript`。

## 当前状态

- 后端已迁移到 `FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2`。
- 前端已迁移到 `React 19 + TypeScript + Vite 6 + React Router 7`。
- 默认后端端口：`3888`；默认前端端口：`3999`。
- 统一数据库默认位于 `backend/data/mirofish.db`，由 `DATABASE_URL` 决定。
- LLM 渠道、模型、模块绑定都通过前端 LLM 设施面板写入统一数据库。
- 当前是活跃开发仓库，工作区可能存在未提交功能分支改动；先看 `git status --short` 再动手。

## 快速命令

```bash
# 后端
cd backend
APP_PORT=3888 uv run python run.py

# 无 uv 时
cd backend
APP_PORT=3888 .venv/bin/python run.py

# 前端
cd frontend
npm run dev

# 后端测试，中文路径环境建议显式 UTF-8
cd backend
env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 .venv/bin/python -m pytest tests

# 前端检查
cd frontend
npm run lint
npm run build
npm run test
```

## 目录责任

- `backend/app/api_fastapi/`：FastAPI 路由，统一挂载 `/api`。
- `backend/app/services/`：业务服务，包括 seed、graph、archive、assets、worldline、writer agent。
- `backend/app/repositories/`：数据库访问层；新增业务读写优先新增或扩展 repository。
- `backend/app/tables/`：SQLAlchemy 表定义；schema 变更必须通过 Alembic revision。
- `backend/app/schemas/`：Pydantic 请求 / 响应 schema。
- `backend/app/utils/llm_client.py`：OpenAI-compatible LLM 客户端与 JSON 调用工具。
- `frontend/src/pages/`：路由页面，核心页面包括 `overview`、`asset-library`、`story-graph`、`worldline`、`writer`、`llm-facility`。
- `frontend/src/api/`：TypeScript API 客户端和 SSE 客户端。
- `frontend/src/stores/`：Zustand 状态。
- `docs/`：设计、迁移和交接文档。

## 关键产品事实

### Seed Pipeline

上传 TXT / MD / PDF 后执行智能分段、顺序精读、全局聚合、ontology 生成、角色 Agent 档案生成。进度由 `SeedTaskProgressTracker` 与任务表追踪，步骤 trace 会记录 prompt 和 response。

### Story Graph / Archives / Assets

故事图谱写入统一 `graph_*` 表。档案库、实体、关系、伏笔、世界规则、手稿块、自由素材统一进入资产视图，供检索和 Writer Agent 使用。

### Worldline

当前产品语义是单世界 `current_world`。旧多分支接口不再扩展；遇到 `/branches`、`/comparison` 语义时要谨慎，不要恢复旧模型。

### Writer Agent

Writer 工作台覆盖书籍计划、章节、场景、续写、正文生成、手稿编译、审校、去重约束和世界数据更新。`writer_reviewer` 是独立 LLM 审校模块，不是规则硬编码评分。

### LLM Facility

所有 LLM 调用必须通过模块绑定。不要新增旧式单组环境变量 fallback。模块未绑定应显式失败或在 UI 中明确提示。

## 开发硬约束

- 不添加 mock 成功、静默 fallback、吞错、隐式降级或伪数据路径。
- 不为“跑通”新增随意边界、上限、硬截断；必要限制必须显式、可配置、可解释。
- 不把 API Key、用户小说原文、数据库、上传产物或 LLM trace 泄露到 git。
- 不直接拼接用户输入到 SQL 或 shell；数据库访问使用参数化查询和 repository。
- 不在新代码中引入 Twitter / Reddit / 舆情分析等上游旧项目语义。
- 不直接编辑已应用 Alembic revision；schema 变化新增 revision。
- 后端单测建议加 60 秒超时，避免卡死。

## 质量基线

- 函数保持短小，超过约 50 行优先拆分。
- 文件按职责拆分，避免继续堆大文件。
- 优先依赖注入，业务逻辑不要硬编码具体外部实现。
- 参数过多时使用 options / config 对象。
- 默认不可变，不修改入参或全局状态。
- 修改超过约 50 行代码后，应完整重启前后端验证。

## 接手顺序

1. 读 `README.md`、本文件和 `CLAUDE.md`。
2. 运行 `git status --short`，确认是否有用户未提交改动。
3. 若涉及数据源，读 `docs/database/database-source-of-truth-matrix.md`。
4. 若涉及 API，查 `docs/fastapi-route-manifest.md` 和对应 `api_fastapi` 路由。
5. 若涉及 Writer，优先读 `backend/app/services/writer_agent/` 与 `frontend/src/pages/writer/`。
6. 若涉及 Worldline，优先读 `backend/app/services/worldline_*`、`backend/app/services/agents/worldline/` 与 `frontend/src/pages/worldline/`。

## 开源维护约定

- PR 必须说明动机、实现范围、验证方式和潜在破坏性。
- issue 里不要粘贴私有 API Key、完整小说原文或敏感日志。
- 新功能文档优先落在 `docs/`，用户入口文档更新 `README.md`。
- Agent 专用接手信息更新本文件；Claude Code 专用导航更新 `CLAUDE.md`。
