# 01. Target Architecture

更新时间：`2026-06-27`

## 架构目标

目标架构必须同时满足两类需求：

1. 公网 SaaS 控制面：多用户、高并发、权限、租户隔离、计费、审计、实时任务状态。
2. 小说 Agent 能力：长文本分析、图谱构建、资产入库、世界线推演、角色互动、写作和审校。

因此推荐混合架构：

```text
Browser
  |
  | HTTPS
  v
Next.js App
  |
  | typed API / SSE / WebSocket
  v
Go Control Plane
  |
  | SQL / object URLs / workflow commands
  v
Postgres + pgvector ---- Redis ---- S3/R2/MinIO
  |
  | workflow state
  v
Temporal Cluster
  |
  | activities
  v
Python Agent Workers
```

## 服务边界

### Next.js App

职责：

- 登录、注册、组织选择和项目选择。
- 作者工作台所有页面。
- 服务端加载基础页面数据。
- 客户端订阅任务进度和 Agent trace。
- UI 状态、布局偏好、当前项目上下文。

不负责：

- 不直接访问数据库。
- 不保存 LLM API Key。
- 不在浏览器中执行长任务。

### Go Control Plane

职责：

- Auth session 校验。
- Tenant context 解析。
- RBAC / ABAC 权限判断。
- Project / Asset / Graph / Worldline / Writer API。
- 上传签名、文件登记、对象存储元数据。
- 任务创建、取消、状态查询。
- SSE / WebSocket 推送。
- LLM 渠道、模型、绑定、用量和审计。
- Billing / quota / rate limit。

Go 是公网入口的主后端。它必须是无状态可横向扩展服务。

### Temporal Workflows

职责：

- 管理长任务生命周期。
- 记录任务状态和可恢复进度。
- 执行重试、超时、取消、补偿。
- 串联 Go activities 和 Python activities。
- 支持人类审阅点，例如采用候选事件、确认档案入库。

典型 workflow：

- `SeedPipelineWorkflow`
- `StoryGraphBuildWorkflow`
- `AssetIngestionWorkflow`
- `StyleExtractionWorkflow`
- `WorldlinePrepareWorkflow`
- `WorldlineAutoEvolutionWorkflow`
- `CharacterInteractionToChapterWorkflow`
- `WriterRunWorkflow`
- `ReviewerWorkflow`
- `PiAnalysisRunWorkflow`
- `ProjectImportWorkflow`

### Python Agent Workers

职责：

- LLM prompt 构造、调用、JSON 修复和 schema 校验。
- 长文本解析、分段、精读、聚合。
- story ontology、entity resolution、archive generation。
- graph build 的语义构图和证据处理。
- asset ingestion Agent。
- worldline agent prepare、director、角色提案、目标判定。
- writer 相关的旧 Python 领域逻辑迁移辅助、reviewer/dedup 兼容实现，以及暂未迁到 Pi 的内部活动。

Python worker 不直接暴露公网。它通过 Temporal task queue 接收任务。

### Pi Writer Runtime

职责：

- 第一阶段 Writer Agent loop。
- `@earendil-works/pi-agent-core` 状态化 agent 和 tool calling。
- `@earendil-works/pi-ai` provider/model 抽象，但必须通过 LLM Facility adapter 获取模块绑定和 API key。
- writer token stream、tool event、draft revision 保存。
- writer tools 的权限、trace 和 event wrapper。

Pi Runtime 当前以三个独立 worker 进程部署（同一 build，不同 Temporal task queue）：

- `pi-agent-runtime`（`writer-streaming`）：Writer Agent loop。
- `pi-agent-runtime-analysis`（`analysis-streaming`）：候选式故事分析（见下）。
- `pi-agent-runtime-worldline-cast`（`worldline-cast-streaming`）：Worldline Cast Planner 目标驱动选角。

**候选式故事分析（`PiAnalysisRunWorkflow`）。** 它是与 Seed pipeline 并行的**候选路径**，不替代 Seed：模型经 agent loop 读源分段、写 workspace 笔记与候选 JSON，产出落 `analysis_candidates`（非 canon、`candidate` 状态），再由 Go `SQLAnalysisAssetImporter` 投影进资产库（`source_kind = pi_analysis`）。它覆盖「阅读理解 → 人物/关系/世界规则/时间线候选」这一段；story ontology、entity resolution、agent profile、index_assets 等 canon 阶段仍只在 Python Seed pipeline。模块绑定使用 `analysis_planner` / `analysis_worker` 两个 LLM module key。

Pi Writer Runtime 是 Node/TypeScript worker，不直接暴露公网。它通过 writer run API 或 Temporal workflow 接收任务，并且不能绕过 tenant/project/run context。

### Postgres

职责：

- 统一业务真相源。
- 所有核心表包含 `tenant_id`。
- RLS 强制隔离。
- 事务、约束、索引和审计基础。
- pgvector 承载语义检索 embedding。

### Redis

职责：

- 短期缓存。
- rate limit 计数。
- realtime fanout 辅助。
- 非关键临时状态。

Redis 不是核心业务真相源。

### Object Storage

职责：

- 用户上传原文。
- PDF/TXT/MD 原始文件。
- 解析后长文本文件。
- 导出 manuscript。
- 大型 trace 附件。
- 可选图谱快照导出。

数据库只存 object key、hash、mime、size、owner 和访问策略。

## 关键请求链路

### 登录后的页面加载

```text
Browser -> Next.js route
Next.js -> Go /me
Go -> Auth provider/session store
Go -> Postgres tenants/projects
Next.js renders shell
Browser subscribes task/activity streams
```

页面必须先拿到：

- 当前用户。
- 当前租户。
- 可访问项目列表。
- 最近任务摘要。
- LLM 配置健康状态。

### 上传小说并启动 seed

```text
Browser selects file
  -> Go creates upload session
  -> Browser uploads to S3/R2 signed URL
  -> Go records file asset
  -> Go starts SeedPipelineWorkflow
  -> Temporal schedules Python activities
  -> Python parses and analyzes
  -> progress events persisted
  -> Browser receives realtime progress
```

设计要点：

- 上传和分析分离。
- 文件对象必须属于 tenant/project。
- 任务可取消。
- 解析失败是显式错误，不用空内容继续。
- 进度由 workflow events / task_runs 持久化，不靠内存。

### 构建故事图谱

```text
Browser clicks Build Graph
  -> Go validates project permission
  -> Go starts StoryGraphBuildWorkflow
  -> Python worker loads canon tables
  -> Python builds semantic graph snapshot
  -> Go graph API serves viewport-optimized graph
  -> React Flow renders clusters and details
```

设计要点：

- 图谱输入以 Postgres canon tables 为主。
- 旧 artifact 只作为迁移导入来源。
- 图谱前端不一次性渲染无限节点。
- 证据、节点、边、聚类和版本分开建模。

### 资产入库 Agent

```text
Browser submits raw material
  -> Go creates AssetIngestionWorkflow
  -> Python asset_ingestion Agent extracts schema
  -> result is candidate asset
  -> user reviews or auto-adopts by policy
  -> asset enters library and search index
```

设计要点：

- 入库结果必须符合标准资产 schema。
- 高风险资产类型默认进入 candidate。
- 用户可以修正字段后采用。
- 入库 trace 可审计。

### Writer Agent

```text
Browser starts writer run
  -> Go validates project/chapter/scene permission
  -> Temporal WriterRunWorkflow
  -> Python retrieval planner selects context
  -> Python orchestrator tool loop gathers data
  -> Python composer streams prose
  -> Go relays writer_token events
  -> draft saved as revision
  -> reviewer/dedup optional workflows run
```

设计要点：

- Writer run 是 workflow，不是单个 HTTP 请求。
- token stream 和最终草稿都要持久化。
- tool calls、prompt snapshots、model usage 都归档到 agent traces。
- 采用正文和更新世界数据是两个明确动作。

## 数据访问原则

### Tenant Context

所有请求进入 Go 后必须得到：

```text
subject_id
tenant_id
membership_role
project_scope
request_id
```

没有 tenant context 的业务请求必须拒绝。

### Worker Context

所有 Temporal workflow/activity 必须携带：

```text
tenant_id
project_id
run_id
actor_type = system | user | worker
actor_id
permission_snapshot
```

Worker 不能自己猜 tenant。

### RLS

Postgres 表默认启用 RLS。应用连接设置当前 tenant，例如：

```sql
SET app.current_tenant_id = '<tenant-id>';
```

策略按照 `tenant_id = current_setting('app.current_tenant_id')` 过滤。

服务级维护任务必须使用单独连接角色，并写入审计日志。

## 实时通信

推荐两层：

- SSE：任务进度、writer token、LLM activity、trace event。
- WebSocket：需要低延迟双向互动的角色控制、协作编辑、presence。

第一阶段可以用 SSE 覆盖大多数场景：

- seed progress
- graph build progress
- worldline auto-evolution
- writer run stream
- LLM activity

Character Console 如果需要“实时角色扮演感”，可以升级为 WebSocket。

## 模块结构建议

### Go 仓库结构

```text
apps/api/
  cmd/api/
  internal/auth/
  internal/tenant/
  internal/projects/
  internal/assets/
  internal/graph/
  internal/worldline/
  internal/writer/
  internal/llm/
  internal/workflows/
  internal/realtime/
  internal/billing/
  internal/audit/
  internal/db/
  internal/http/
```

### Python worker 结构

```text
apps/agent-runtime/
  mirofish_agents/
    seed/
    graph/
    assets/
    archives/
    worldline/
    character_console/
    writer/
    llm/
    traces/
    schemas/
    temporal/
```

### Next.js 结构

```text
apps/web/
  app/
    (marketing)/
    (auth)/
    (app)/
      [tenant]/
        projects/
        projects/[projectId]/
          overview/
          graph/
          assets/
          worldline/
          character-console/
          writer/
          settings/
  components/
  features/
  lib/api/
  lib/auth/
  lib/realtime/
```

## 兼容策略

### 不建议长期保留旧 FastAPI 公网面

旧 FastAPI 可以在迁移期作为内部 adapter 存在，但目标状态是：

- 公网只进 Next.js / Go。
- Python 只作为 worker。
- 旧 `/api/*` 语义迁移到 Go typed API。
- 旧 Pydantic schema 可作为 worker payload 起点，但不能成为公网 API 的长期真相源。

### 旧数据导入

旧 SQLite / project_artifacts / uploads 通过 `ProjectImportWorkflow` 导入：

1. 读取旧项目 metadata。
2. 上传原文和产物到 object storage。
3. 写入新 Postgres 项目、文件、artifact、entities、assets、worldline、writer 数据。
4. 生成迁移报告。
5. 用户确认后标记 legacy project imported。

## 架构验收

- Go API 可以水平扩容到多实例。
- Python worker 可以按 task queue 横向扩容。
- 任意一个 worker 崩溃后，Temporal 能恢复或标记失败。
- Postgres RLS 测试证明用户无法跨 tenant 读取。
- 同一租户内不同项目有项目级 RBAC。
- SSE 断线重连后可以从 last event id 恢复。
- Object storage 文件无法被猜 URL 直接访问。
