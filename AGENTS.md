# AGENTS.md

## 目的

这份文档给后续 AI coding agent 快速接手 `MiroFish-Novel` 使用，并明确 legacy 应用与当前 SaaS 重构的边界。

更新时间：`2026-07-13`

## SaaS 开发真相源

完整 SaaS 重构是当前活跃目标。判断范围和进度时只按以下顺序：

1. `docs/refactor-saas/DEVELOPMENT_PLAN.md`：范围、阶段顺序和最终完成定义。
2. `docs/refactor-saas/24-current-development-progress.md`：唯一当前进度、关键路径和验证新鲜度入口。
3. `tasks/refactor-saas-parallel-board.md`：活动任务、依赖和 next gate。
4. 当前 worktree、schema 和本轮实际测试输出：冲突时的最终事实。

不得使用历史 handoff、追加式日志、旧 subagent 计划或固定窗口 prompt 判断当前状态，也不得从 Phase 0 重新开始。

活跃 SaaS 代码位于 `apps/api`、`apps/web`、`apps/agent-runtime`、`apps/pi-agent-runtime` 和 `infra`。`backend/` 仅作 legacy 数据迁移和兼容参考；根目录旧 `frontend/` 已退役并删除，不得重建、运行、复制或用作视觉参考。

## 项目定位

`MiroFish-Novel` 是面向长篇小说创作的多智能体分析与写作平台。核心目标不是舆情分析，而是：

- 读取小说文本、设定、大纲、角色卡和自由素材
- 提取角色、组织、关系、伏笔、世界规则与叙事阶段
- 建立统一数据库中的故事图谱、档案库和资产库
- 通过单世界 worldline 做剧情推演、变量注入和角色互动
- 为 Writer Agent 提供可消费上下文，并产出正文、续写、审校和世界数据更新

主链：`上传小说 -> seed pipeline -> ontology / graph -> archives / assets -> worldline -> writer agent -> manuscript`。

## Legacy 后端状态（非 SaaS 进度）

- 后端已迁移到 `FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2`。
- 默认后端端口：`3888`。
- 统一数据库默认位于 `backend/data/mirofish.db`，由 `DATABASE_URL` 决定。
- Legacy 后端不再配套可运行前端，不是产品入口。
- 当前是活跃开发仓库，工作区可能存在未提交功能分支改动；先看 `git status --short` 再动手。

## SaaS 快速命令

```bash
# Go control plane
cd apps/api
go test ./...

# Next Web
cd apps/web
npm test
npm run typecheck
npm run build

# Python Agent Runtime
cd apps/agent-runtime
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider tests -q

# Pi Writer Runtime
cd apps/pi-agent-runtime
npm test
npm run typecheck
npm run build

# Local infrastructure
docker compose -f infra/docker-compose.yml up -d
```

所有会写数据库、对象存储或队列的 live/E2E 测试必须通过
`infra/scripts/run-live-test-stack.sh -- <command>` 运行；需要 API/Web 时使用
`--app`。禁止把任何 `*_LIVE_DATABASE_URL` 指向主 `mirofish` 数据库，也禁止
硬编码主 Compose 容器名。独立 runner 使用唯一 `mirofish_test_*` 数据库、
`mirofish.live_test=on` 标记和独立 volumes，退出时执行 `down -v`。

## Legacy 后端快速命令

```bash
# 后端
cd backend
APP_PORT=3888 uv run python run.py

# 无 uv 时
cd backend
APP_PORT=3888 .venv/bin/python run.py

# 后端测试，中文路径环境建议显式 UTF-8
cd backend
env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 .venv/bin/python -m pytest tests
```

## SaaS 目录责任

- `apps/api/`：Go control plane、HTTP/RBAC、workflow admission 和 read side。
- `apps/web/`：Next.js SaaS shell 与各工作台。
- `apps/agent-runtime/`：Python Seed/Graph/Worldline/Asset 领域 worker。
- `apps/pi-agent-runtime/`：Pi Writer Agent Runtime。
- `infra/`：Postgres baseline、Temporal/Redis/MinIO 和 compose。
- `docs/refactor-saas/`：SaaS scope、当前进度和领域契约。

## 前端退役边界

- `apps/web/` 是唯一前端代码和唯一 Web 构建上下文。
- Writer 保持 **产物主导（manuscript-primary 原则）+ conversation-first IA**：主画布是连续稿件文档（章节内片段按序渲染，选中片段就地编辑），画布头可见视图切换（稿件 / 章节 / 审校 / 工具），Writer Agent 作为**常驻协作者**位于右侧 dock（连续 thread + 常驻 composer + 选区驱动调用），而非占据半屏。当前结构：`writer-agent-layout[data-layout="conversation-first"]` 包含 `writer-artifact-canvas`（主导主区）与 `writer-agent-dock`（常驻副区）。
- 旧蓝色 Vite UI、旧蓝色 Writer 长页截图、`writer-studio-grid`、折叠 composer 和深色 `writer-agent-rail` 均已退役，不得恢复或作为验收基线。
- `docs/plans/` 与 `docs/superpowers/` 中指向旧 `frontend/` 的内容只是历史记录，不是待执行任务。

## Legacy 后端目录责任

- `backend/app/api_fastapi/`：FastAPI 路由，统一挂载 `/api`。
- `backend/app/services/`：业务服务，包括 seed、graph、archive、assets、worldline、writer agent。
- `backend/app/repositories/`：数据库访问层；新增业务读写优先新增或扩展 repository。
- `backend/app/tables/`：SQLAlchemy 表定义；schema 变更必须通过 Alembic revision。
- `backend/app/schemas/`：Pydantic 请求 / 响应 schema。
- `backend/app/utils/llm_client.py`：OpenAI-compatible LLM 客户端与 JSON 调用工具。
- `docs/`：设计、迁移和交接文档。

## 关键产品事实

### Seed Pipeline

上传 TXT / MD / PDF 后执行智能分段、顺序精读、全局聚合、ontology 生成、角色 Agent 档案生成。进度由 `SeedTaskProgressTracker` 与任务表追踪，步骤 trace 会记录 prompt 和 response。

### Story Graph / Archives / Assets

故事图谱写入统一 `graph_*` 表。档案库、实体、关系、伏笔、世界规则、手稿块、自由素材统一进入资产视图，供检索和 Writer Agent 使用。

### Worldline

当前产品语义是单世界 `current_world`。旧多分支接口不再扩展；遇到 `/branches`、`/comparison` 语义时要谨慎，不要恢复旧模型。

### Writer Agent

Writer 工作台覆盖书籍计划、章节、场景、续写、正文生成、手稿编译、审校、去重约束和世界数据更新。当前产品交互是 Agent thread + artifact workspace，不是后台表单长页。`writer_reviewer` 是独立 LLM 审校模块，不是规则硬编码评分。

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
- 修改超过约 50 行代码后，应完整重启受影响的 SaaS API/Web 验证。

## 接手顺序

1. 运行 `git status --short`，确认用户和其他 agent 的未提交改动。
2. SaaS 任务先读 `DEVELOPMENT_PLAN.md`、`24-current-development-progress.md` 和活动任务板，从当前 next gate 继续。
3. 再读当前任务对应的领域文档、代码、schema 和测试；文档与代码冲突时以当前 worktree/测试为准并校准进度文档。
4. 涉及 legacy import/兼容时，才读 `docs/database/database-source-of-truth-matrix.md`、`docs/fastapi-route-manifest.md` 和 `backend/` 实现；不得因历史文档重建旧 `frontend/`。
5. 不创建新的 handoff/progress 副本；完成 milestone 时更新 `24-current-development-progress.md`，任务状态变化时更新活动任务板。

## 开源维护约定

- PR 必须说明动机、实现范围、验证方式和潜在破坏性。
- issue 里不要粘贴私有 API Key、完整小说原文或敏感日志。
- 新功能文档优先落在 `docs/`，用户入口文档更新 `README.md`。
- Agent 专用接手信息更新本文件；Claude Code 专用导航更新 `CLAUDE.md`。
