# 19. Parallel Development Orchestration

更新时间：`2026-06-27`

## 目的

本文件用于把 SaaS 重构拆成可以由多个 Codex 窗口、多个终端和多个智能体并行推进的开发作战计划。目标是提高开发效率，同时避免多人同时改同一批文件导致冲突、返工和架构分叉。

当前执行顺序以 `docs/refactor-saas/DEVELOPMENT_PLAN.md` 为准：先完成 Writer-first Pi Agent vertical slice，再分批承接 SaaS 基座和其他模块。本文件只描述如何并行，不反转总纲顺序。

适用方式：

- 一个主控窗口负责拆任务、审查、集成和更新进度。
- 多个工作窗口分别负责独立泳道。
- 每个工作窗口使用独立 git worktree 或独立分支。
- 每个任务有明确输入文档、输出文件、验收标准和禁止触碰范围。

## 并行开发原则

### 一主多工

必须保留一个 **Coordinator / Integrator** 窗口。

职责：

- 维护任务看板。
- 分配任务。
- 审查 PR / patch。
- 解决跨模块接口冲突。
- 更新 `18-legacy-coverage-matrix.md`。
- 保证所有实现仍符合 `docs/refactor-saas/` 文档。

工作窗口不要各自重新设计架构。架构决策以本目录文档为准。

### 按边界并行，不按热情并行

可以并行：

- 前端 shell 和 Go API skeleton。
- Postgres schema 和 Python worker scaffold。
- LLM Facility UI 和 backend module binding API。
- 资产库 UI 和资产 API。
- Story Graph UI 和 graph worker。

不应并行：

- 两个窗口同时改同一 migration。
- 两个窗口同时改同一 API contract。
- 一个窗口改 schema，另一个窗口按旧 schema 写 service。
- 多个窗口同时重构 writer tool executor。

### 每个窗口都要有“只读上下文”和“可写范围”

每个任务分配时必须写清：

- 必读文档。
- 可修改目录。
- 不可修改目录。
- 预期输出。
- 验收命令。

### 先接口，后实现

多窗口并行时，必须先冻结共享契约：

- OpenAPI schema。
- DB migration。
- shared TypeScript types。
- workflow payload schema。
- Agent output schema。

否则前后端和 worker 会彼此追着改。

## 推荐窗口配置

每个窗口的完整身份卡和可复制启动提示词见：

- `docs/refactor-saas/20-agent-window-identities-and-prompts.md`
- `docs/refactor-saas/prompts/`

### Window 0：Coordinator / Integrator

人数：1

职责：

- 维护整体计划。
- 分配任务和处理依赖。
- 审查工作窗口结果。
- 合并分支。
- 跑集成测试。
- 更新文档和覆盖矩阵。

必读：

- `README.md`
- `AGENTS.md`
- `docs/refactor-saas/README.md`
- `docs/refactor-saas/17-migration-roadmap.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- 本文件。

可写：

- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/`
- 集成修复文件。

禁止：

- 在没有审查的情况下大规模改业务实现。

### Window 1：Infra / Dev Environment

职责：

- monorepo 目录骨架。
- Docker Compose。
- Postgres / Redis / Temporal / MinIO。
- 本地启动脚本。
- 环境变量模板。

可写：

```text
infra/
docker-compose.yml
.env.example
Makefile 或 justfile
apps/*/Dockerfile
```

必读：

- `01-target-architecture.md`
- `02-tech-stack.md`
- `16-deployment-and-ops.md`

首个验收：

- `docker compose up` 能启动基础依赖。
- Go API health、Next.js web、Python worker hello workflow 能互通。

### Window 2：Database / RLS / Migrations

职责：

- Postgres schema。
- tenant tables。
- project tables。
- RLS policy。
- migration framework。
- seed test fixtures。

可写：

```text
apps/api/internal/db/
apps/api/migrations/
packages/shared-contracts/db/
```

必读：

- `03-multi-tenant-saas.md`
- `14-data-model.md`
- `18-legacy-coverage-matrix.md`

首个验收：

- users / tenants / projects 表可迁移。
- RLS 测试证明跨租户无法读取。

### Window 3：Go Control Plane Foundation

职责：

- Go API skeleton。
- auth middleware。
- tenant context。
- project API。
- workflow run API。
- standardized error response。

可写：

```text
apps/api/cmd/
apps/api/internal/auth/
apps/api/internal/tenant/
apps/api/internal/projects/
apps/api/internal/http/
apps/api/internal/workflows/
```

必读：

- `01-target-architecture.md`
- `03-multi-tenant-saas.md`
- `15-api-contracts.md`

首个验收：

- `GET /v1/me`。
- `GET /v1/tenants/{slug}/projects`。
- `GET /v1/projects/{projectId}/overview` 返回真实 DB 数据。

### Window 4：Next.js App Shell

职责：

- Next.js app scaffold。
- auth-aware app shell。
- tenant/project router。
- sidebar/topbar。
- project dashboard empty state。
- API client skeleton。

可写：

```text
apps/web/
packages/shared-contracts/types/
```

必读：

- `04-design-system-and-ui.md`
- `05-overview-dashboard.md`
- `15-api-contracts.md`

首个验收：

- 登录态 mock/dev provider 下能进入 tenant project list。
- 项目页显示真实 API overview。
- UI 不使用假业务数据伪装成功。

### Window 5：Temporal / Python Agent Runtime Foundation

职责：

- Python worker package。
- Temporal worker。
- AgentContext。
- trace event writer。
- LLM router interface。
- hello workflow。

可写：

```text
apps/agent-runtime/
packages/shared-contracts/workflows/
```

必读：

- `01-target-architecture.md`
- `13-agent-runtime.md`
- `12-llm-facility.md`

首个验收：

- Go 能启动 hello workflow。
- Python worker 执行 activity。
- workflow event 可被 Go API 查询。

### Window 6：LLM Facility

职责：

- channels / models / bindings API。
- module registry。
- model sync。
- activity logging。
- LLM Facility UI。

可写：

```text
apps/api/internal/llm/
apps/web/features/llm/
apps/agent-runtime/mirofish_agents/llm/
```

必读：

- `12-llm-facility.md`
- `13-agent-runtime.md`
- `15-api-contracts.md`

首个验收：

- 创建渠道。
- 同步模型。
- 绑定 `writer_orchestrator`。
- Python worker 缺绑定时明确失败。

### Window 7：Seed Pipeline Vertical Slice

职责：

- upload API。
- seed workflow。
- parse/segment/sequential reading activity scaffold。
- seed progress UI。
- structured canon writes 第一版。

可写：

```text
apps/api/internal/uploads/
apps/api/internal/seed/
apps/agent-runtime/mirofish_agents/seed/
apps/web/features/seed/
```

必读：

- `05-overview-dashboard.md`
- `06-seed-pipeline.md`
- `13-agent-runtime.md`

首个验收：

- 上传 TXT。
- 启动 seed workflow。
- 前端看到阶段进度。
- 至少写入项目、source file、segments、workflow events。

### Window 8：Asset Library

职责：

- asset schema/API。
- asset ingestion workflow。
- facets/search。
- asset list/detail UI。

可写：

```text
apps/api/internal/assets/
apps/agent-runtime/mirofish_agents/assets/
apps/web/features/assets/
```

必读：

- `08-asset-library.md`
- `14-data-model.md`
- `15-api-contracts.md`

首个验收：

- 手动创建 asset。
- 搜索 asset。
- 粘贴素材触发 ingestion workflow。
- candidate asset 可审阅。

### Window 9：Story Graph

职责：

- graph schema/API。
- graph build workflow。
- React Flow graph workspace。
- inspector。
- compose mode scaffold。

可写：

```text
apps/api/internal/graph/
apps/agent-runtime/mirofish_agents/graph/
apps/web/features/story-graph/
```

必读：

- `07-story-graph.md`
- `14-data-model.md`
- `15-api-contracts.md`

首个验收：

- 从 seed/canon mock fixture 或真实 seed 数据构建 graph snapshot。
- 前端能浏览节点/边。
- inspector 显示证据。

### Window 10：Worldline

职责：

- worldline session API。
- prepare workflow。
- variable injection。
- candidate event lifecycle。
- saved paths。
- worldline UI。

可写：

```text
apps/api/internal/worldline/
apps/agent-runtime/mirofish_agents/worldline/
apps/web/features/worldline/
```

必读：

- `09-worldline.md`
- `13-agent-runtime.md`
- `14-data-model.md`

首个验收：

- 从角色资产创建 prepare。
- 启动 session。
- 注入变量。
- 产生并保存 candidate event。

### Window 11：Character Console

职责：

- interaction session API。
- turn stream。
- first-person mode UI。
- interaction to chapter workflow。

可写：

```text
apps/api/internal/character_console/
apps/agent-runtime/mirofish_agents/character_console/
apps/web/features/character-console/
```

必读：

- `10-character-console.md`
- `09-worldline.md`
- `11-writer-workbench.md`

首个验收：

- 选择 worldline session 和角色。
- 记录互动 turn。
- 转换为 draft scene。

### Window 12：Writer Workbench

职责：

- chapter/scene/manuscript API。
- writer workflow。
- stream events。
- editor shell。
- reviewer/dedup scaffold。

可写：

```text
apps/api/internal/writer/
apps/agent-runtime/mirofish_agents/writer/
apps/web/features/writer/
```

必读：

- `11-writer-workbench.md`
- `13-agent-runtime.md`
- `14-data-model.md`

首个验收：

- 创建 chapter/scene。
- 启动 writer run。
- 前端收到 writer token stream。
- draft 可采用到 manuscript。

### Window 14：Pi Writer Runtime

职责：

- Node/TypeScript Pi Writer Runtime。
- `@earendil-works/pi-agent-core` 接入。
- LLM Facility adapter。
- Pi event -> workflow event 映射。
- Writer tool registry。
- draft persistence bridge。

可写：

```text
apps/pi-agent-runtime/
packages/shared-contracts/writer/
docs/refactor-saas/21-pi-writer-agent-runtime.md
```

必读：

- `DEVELOPMENT_PLAN.md`
- `21-pi-writer-agent-runtime.md`
- `11-writer-workbench.md`
- `12-llm-facility.md`
- `13-agent-runtime.md`
- `15-api-contracts.md`

首个验收：

- 使用 faux/test provider 跑通 Pi writer run。
- 输出 token stream。
- 至少执行一个 read tool。
- 保存 draft revision。

### Window 13：Migration / Legacy Import

职责：

- 旧 SQLite / artifacts 导入。
- legacy coverage tests。
- import report。
- 数据一致性验证。

可写：

```text
apps/api/internal/importer/
apps/agent-runtime/mirofish_agents/migration/
tools/migration/
tests/legacy/
```

必读：

- `14-data-model.md`
- `17-migration-roadmap.md`
- `18-legacy-coverage-matrix.md`
- `docs/database/database-source-of-truth-matrix.md`

首个验收：

- 导入一个旧项目 metadata。
- 导入旧 assets / entities / graph snapshot 子集。
- 生成 import report。

## 推荐开发波次

## Wave 0：冻结契约和工作方式

目标：

- 确认 `18-legacy-coverage-matrix.md` 是功能覆盖基线。
- 确认本文件是并行开发规则。
- 建立任务看板。
- 每个窗口开独立 worktree/branch。

并行度：低，Coordinator 主导。

输出：

- `tasks/refactor-saas-parallel-board.md`
- 初始 branch/worktree 列表。

## Wave 1：Writer-first Pi Agent 最小闭环

可并行窗口：

- Window 12 Writer Workbench。
- Window 14 Pi Writer Runtime。
- Window 6 LLM Facility。
- Window 3 Go Foundation 或当前 FastAPI compatibility bridge。

依赖：

- Coordinator 先冻结 writer run API、event schema、draft schema、tool schema。
- Pi Runtime 可以先用 faux/test provider 验证 stream，不等真实 LLM。
- LLM Facility 至少要能返回缺绑定错误，真实模型绑定可随后接入。

完成标准：

- 写作台能启动 writer run。
- Pi Runtime 能执行 agent loop。
- 前端能看到 token stream 和 tool event。
- draft 能保存并采用到 manuscript。
- LLM 未绑定时显式失败。

## Wave 2：写作台工具接入知识层

可并行窗口：

- Window 8 Asset Library。
- Window 9 Story Graph。
- Window 10 Worldline。
- Window 12 Writer Workbench。
- Window 14 Pi Writer Runtime。

依赖：

- Writer tool result schema 已冻结。
- Asset / Graph / Worldline 可以先提供最小 read API 或 fixture import，但 UI 不能展示假成功。

完成标准：

- Writer 能引用资产。
- Writer 能引用图谱邻居。
- Writer 能引用 worldline saved path。
- 工具结果能进入 trace 和右侧面板。

## Wave 3：SaaS 基座承接 Writer vertical slice

可并行窗口：

- Window 1 Infra。
- Window 2 DB/RLS。
- Window 3 Go Foundation。
- Window 4 Next.js App Shell。
- Window 5 Python Agent Runtime Foundation。
- Window 14 Pi Writer Runtime。

依赖：

- Phase 1 Writer/Pi 契约已验证。
- Window 2 先产出 users/tenants/projects/workflow/writer 最小 schema。

完成标准：

- 本地全栈可启动。
- 可以登录/选择 tenant/project。
- Go 能启动 Pi writer workflow。
- Python worker hello workflow 保留。
- 前端能订阅 workflow events。

## Wave 4：Seed / Assets / Graph 结构化迁移

可并行窗口：

- Window 7 Seed Pipeline。
- Window 8 Asset Library。
- Window 9 Story Graph。
- Window 13 Legacy Import。

依赖：

- SaaS schema 和 workflow_runs 可用。
- LLM Facility 至少完成 module binding。

完成标准：

- TXT 上传 -> seed run -> structured canon rows。
- seed 结果进入资产库。
- 图谱能从 canon 表构建。
- Writer tools 从新表读取上下文。

## Wave 5：Worldline / Character Console / Writer 完整化

目标：

```text
上传小说
  -> seed
  -> 资产/图谱
  -> worldline
  -> character console
  -> writer
  -> manuscript
```

工作：

- Worldline saved path 接入 Writer。
- Character interaction 转章节草稿。
- Reviewer / dedup / forbidden lexicon / one-click actions。
- 跨模块联调。
- 权限审计。
- 旧功能覆盖矩阵更新。
- 性能和并发测试。

并行度：中等，Coordinator 控制集成顺序。

## Wave 6：生产化

可并行：

- Billing / usage。
- Monitoring。
- Backup。
- Rate limit。
- Admin support tools。
- Security review。

依赖：

- 核心闭环已跑通。

## Branch / Worktree 策略

每个窗口使用独立分支：

```text
codex/saas-pi-writer-runtime
codex/saas-writer-workbench
codex/saas-llm-facility
codex/saas-infra
codex/saas-db-rls
codex/saas-go-foundation
codex/saas-web-shell
codex/saas-agent-runtime
codex/saas-seed
codex/saas-assets
codex/saas-story-graph
codex/saas-worldline
codex/saas-character-console
codex/saas-legacy-import
```

推荐 worktree：

```bash
git worktree add ../Noveronline-saas-infra -b codex/saas-infra
git worktree add ../Noveronline-saas-db -b codex/saas-db-rls
git worktree add ../Noveronline-saas-api -b codex/saas-go-foundation
git worktree add ../Noveronline-saas-web -b codex/saas-web-shell
git worktree add ../Noveronline-saas-agent -b codex/saas-agent-runtime
```

注意：

- 当前主工作区已有大量未提交前端改动。创建 worktree 前必须由 Coordinator 判断是否从当前 HEAD、当前工作区快照或新基线分支开始。
- 不要在同一工作区打开多个窗口同时改文件。
- 不要让两个窗口同时编辑同一 migration 文件。

## 每个工作窗口的标准启动 Prompt

给新 Codex 窗口的通用 prompt：

```text
你正在参与 MiroFish-Novel SaaS 重构的并行开发。

先阅读：
- AGENTS.md
- docs/refactor-saas/README.md
- docs/refactor-saas/DEVELOPMENT_PLAN.md
- docs/refactor-saas/19-parallel-development-orchestration.md
- 你负责模块对应的 docs/refactor-saas/*.md
- docs/refactor-saas/18-legacy-coverage-matrix.md

你的窗口角色是：[填写 Window 名称]
可修改目录：[填写]
禁止修改目录：[填写]
目标：[填写具体任务]
验收：[填写命令和预期结果]

工作规则：
- 先运行 git status --short。
- 不要改用户已有未提交改动，除非任务明确要求。
- 不要新增 mock 成功、静默 fallback、伪数据路径。
- 所有 LLM 调用必须走 LLM Facility 模块绑定。
- 所有 SaaS 数据必须带 tenant/project 上下文。
- 完成后更新对应文档或覆盖矩阵状态说明。
```

## 任务交接模板

每个工作窗口完成后提交：

```markdown
## Status

DONE / DONE_WITH_CONCERNS / BLOCKED

## Scope

- Branch:
- Worktree:
- Files changed:

## What Changed

- ...

## Verification

- Command:
- Result:

## Contract Changes

- API:
- DB:
- Workflow payload:
- Shared types:

## Risks / Follow-ups

- ...
```

## 冲突控制

### 高冲突文件

以下文件只能由 Coordinator 或单一指定窗口修改：

```text
docs/refactor-saas/DEVELOPMENT_PLAN.md
docs/refactor-saas/18-legacy-coverage-matrix.md
docs/refactor-saas/19-parallel-development-orchestration.md
docs/refactor-saas/21-pi-writer-agent-runtime.md
packages/shared-contracts/*
apps/api/migrations/*
docker-compose.yml
.env.example
```

### Contract Freeze

每个 wave 开始前冻结：

- DB migration version。
- API request/response。
- workflow payload。
- event schema。

变更流程：

1. 提出 contract change。
2. Coordinator 审核。
3. 更新 shared contracts。
4. 通知相关窗口 rebase。

## 进度看板建议

创建：

```text
tasks/refactor-saas-parallel-board.md
```

字段：

```markdown
| ID | Wave | Window | Task | Owner Window | Branch | Status | Depends On | Verification |
```

状态：

- `ready`
- `in_progress`
- `blocked`
- `review`
- `verified`
- `merged`

## 推荐首批任务

### P0-001：建立并行看板

窗口：Coordinator

输出：

- `tasks/refactor-saas-parallel-board.md`

### P0-002：确定 worktree 基线

窗口：Coordinator

输出：

- 当前未提交改动处理策略。
- 是否创建 `codex/saas-mainline` 基线分支。

### P1-001：Writer run contract freeze

窗口：Coordinator / Writer / Pi Writer Runtime

输出：

- writer run request/response。
- writer event schema。
- draft persistence schema。
- writer tool result schema。

### P1-002：Pi Writer Runtime skeleton

窗口：Pi Writer Runtime

输出：

- `apps/pi-agent-runtime`。
- Pi SDK dependency。
- faux/test provider run。
- token stream event mapper。

### P1-003：LLM Facility adapter

窗口：LLM Facility / Pi Writer Runtime

输出：

- module binding lookup。
- missing binding error。
- custom Pi provider/model adapter。

### P1-004：Writer Workbench stream UI

窗口：Writer Workbench

输出：

- run button。
- token stream。
- tool trace rail。
- draft preview。

### P1-005：Draft save/adopt

窗口：Writer Workbench / API / Pi Writer Runtime

输出：

- save draft revision。
- adopt draft to manuscript。
- audit/trace events。

## 何时适合真正多窗口开工

必须满足：

- 当前文档已审阅。
- 基线分支已确定。
- `tasks/refactor-saas-parallel-board.md` 已创建。
- Phase 1 Writer/Pi/API/LLM 可写范围已锁定。
- Coordinator 准备接收和审查多个分支。

如果这些没准备好就开很多窗口，会变快一小时，返工三天。
