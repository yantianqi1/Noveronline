# 05. Overview Dashboard

更新时间：`2026-07-13`

## 模块定位

总览是作者进入项目后的第一屏。它不应该是装饰性首页，而应该回答四个问题：

1. 这个项目现在处于什么阶段？
2. 有哪些数据已经准备好？
3. 哪些 Agent/任务正在运行或失败？
4. 作者下一步最应该做什么？

旧总览页面包含：

- HeroPanel
- RecentProjects
- SeedUploadPanel
- SeedAnalysisPanel
- TaskFocusCard
- InlineWorkflowStream
- SeedTaskTimeline
- SeedStepTracePanel
- RetryFailedSegmentsBanner

新总览必须覆盖这些功能，并把它们组织成 SaaS 项目仪表盘。

## 用户故事

### 新作者首次进入

作者登录后创建项目，进入总览。页面应显示：

- 项目名称和空状态。
- `从一个想法开始` 和 `上传已有文本` 两条入口。
- 支持 TXT / MD / PDF。
- LLM 设施未配置时的清晰提示。
- Seed Pipeline 预计会生成哪些数据。

### Planned: 空项目双入口

完整契约见 [28. Zero-start Writer and Manuscript Asset Distillation](./28-zero-start-writer-and-manuscript-asset-distillation.md)。该旅程尚未实现，不得据此把现有 Overview 空状态标记为完成。

- 主入口 `从一个想法开始` 使用紧凑 bootstrap 表单创建最小 book plan、第一章、第一场景和人工正文起始 block，然后深链 Writer；不调用 LLM，不要求 source file 或 Seed。
- 次入口 `上传已有文本` 继续使用现有 Upload -> Seed 流程。
- 空项目不展示会误导作者的全量健康统计面板；先呈现一个主动作和一个次动作。直接打开空 Writer 时复用同一 bootstrap，不要求返回 Overview。
- 移动端保持正文/下一动作优先，表单控件和按钮触控区域不小于 44px，异步错误使用可恢复的就地反馈。

### 作者上传小说

作者拖拽文件并点击开始分析：

- 文件先上传到对象存储。
- Go 创建 `SeedPipelineWorkflow`。
- 页面立即进入任务流状态。
- 进度以阶段、百分比、消息和 trace 表达。
- 断线刷新后可以恢复同一个任务视图。

### 作者继续失败任务

如果 seed 失败：

- 显示失败阶段。
- 显示错误摘要。
- 提供 `查看 trace`、`断点续传`、`重新开始`。
- 不把失败伪装为完成。

### 老用户回到项目

页面应显示：

- 最近 seed/graph/writer/worldline 任务。
- 数据就绪度。
- 最近章节/手稿。
- 未处理候选资产/候选事件/审校问题。
- 一键进入下一模块。

## 页面结构

### Desktop Layout

```text
Project Health Header
  project title / status / active workflow / quick actions

Readiness Strip
  seed / graph / assets / worldline / writer / llm

Main Grid
  Left  : Next Action + Upload / Continue
  Center: Workflow Stream / Recent Activity
  Right : Project Data Snapshot / Alerts

Lower Sections
  Recent projects or sibling projects
  Seed analysis summary
  Trace drawer on demand
```

### Mobile Layout

```text
Project Health
Next Action
Workflow Stream
Upload / Continue
Data Snapshot
Recent Activity
```

移动端不展示复杂多栏。任务进度和下一步动作优先。

## 核心组件

### ProjectHealthHeader

显示：

- 项目名。
- 所属租户。
- 最近更新时间。
- 项目状态：`empty | analyzing | ready | writing | blocked | archived`。
- 当前 active workflow。
- LLM 配置状态。
- 快捷按钮：上传、构图、写作、设置。

数据来源：

- `GET /v1/projects/{projectId}/overview`
- 当前 Go 增量聚合读侧：`GET /v1/projects/{projectId}/overview` 在配置 `DATABASE_URL` 时使用 app-role tenant context 聚合 `source_files`、`workflow_runs`、最新 `project_readiness_snapshots`、enabled `assets`、最新 `story_graph_snapshots` node/edge counts、`worldline_sessions` / `worldline_events`、`character_interaction_sessions`、`writer_runs`、`llm_activity`、`usage_events.usage_type = llm_tokens`、enabled LLM channel count、valid bound module count、核心创作 module missing count、enabled channel model-sync health counts（ok / failed / pending / latest sync at），以及 latest failed workflow public summary（run id / workflow type / error code / updated at），返回 project id、derived status、active workflow id/type/status、latest failed workflow summary、source/seed run counts、readiness counts、cross-module public counts、LLM configuration public counts、LLM model sync public counts 和 timestamp；无 DB 返回 `PROJECT_OVERVIEW_BACKEND_UNCONFIGURED`，普通 query/scan/rows failure 稳定为 `PROJECT_OVERVIEW_QUERY_FAILED`。该响应不返回 source object key、raw/parsed text、readiness report body、workflow error message、prompt/response、API key、encrypted credential、`credential_ref`、channel/model/provider/base URL 详情、draft 或 manuscript。Next `/overview` 已把该 aggregate contract 接入顶部 Project Health status pills 和 `Project health` panel；live provider connectivity call、cluster health、failure drilldown 和 live Seed E2E 仍 pending。
- 当前 readiness-specific 读侧：`GET /v1/projects/{projectId}/readiness` 可读取最新 `project_readiness_snapshots` public metadata；Next `/overview` 已把该读侧接入 Project readiness 面板，展示 snapshot id、run id、ready counts 和 timestamps，并在缺 DB/backend 时显示 `PROJECT_READINESS_BACKEND_UNCONFIGURED` 等显式错误。该路径不返回 readiness report body、raw text、prompt、API key、`credential_ref`、draft 或 manuscript。

### ReadinessStrip

指标：

| 指标 | 含义 |
|---|---|
| Seed | 是否完成基础分析 |
| Canon | entities / relationships / world rules 是否有数据 |
| Graph | 是否有可用图谱快照 |
| Assets | 资产数量和候选数量 |
| Worldline | 是否有 session / saved path |
| Writer | 是否有章节/场景/稿件 |
| LLM | 必需模块是否绑定 |

每个指标都有：

- status。
- count。
- helper text。
- click target。

### NextActionPanel

根据项目状态计算下一步：

| 状态 | 下一步 |
|---|---|
| 无上传 | 上传小说/设定 |
| 已上传未分析 | 开始 Seed Pipeline |
| seed 运行中 | 查看任务进度 |
| seed 失败 | 断点续传或重新开始 |
| seed 完成但无图谱 | 构建故事图谱 |
| 图谱完成但无资产审阅 | 审阅资产/档案 |
| 数据就绪 | 开始世界线或写作 |
| writer 草稿待审 | 查看审校结果 |

### UploadSurface

覆盖旧 `SeedUploadPanel`。

能力：

- 拖拽上传。
- 选择文件。
- 项目名/描述。
- 上传前校验。
- 文件 hash。
- 进度。
- 取消上传。

禁止：

- 上传失败后创建假项目。
- 解析空内容继续 seed。
- 前端保存用户原文到 localStorage。

### WorkflowStream

覆盖旧：

- InlineWorkflowStream
- SeedTaskTimeline
- TaskFocusCard
- RetryFailedSegmentsBanner

统一展示所有 workflow：

- seed。
- graph。
- asset ingestion。
- worldline prepare。
- writer。
- reviewer。

事件类型：

```text
workflow_started
stage_started
stage_progress
llm_call_started
llm_call_finished
artifact_written
candidate_generated
stage_failed
workflow_completed
workflow_cancelled
```

### SeedAnalysisSummary

覆盖旧 `SeedAnalysisPanel`。

显示 seed 完成后摘要：

- 角色数量。
- 组织/势力数量。
- 关系数量。
- 世界规则数量。
- 开放剧情线数量。
- 关键叙事阶段。
- 角色 Agent 档案就绪度。

不在总览展示所有详情，只提供跳转资产库/图谱。

### TraceDrawer

覆盖旧 `SeedStepTracePanel`，并升级为所有 workflow 通用。

显示：

- 阶段。
- prompt。
- response。
- model。
- latency。
- token usage。
- parsed JSON。
- error。

权限：

- viewer 默认可看摘要。
- editor/owner 可看完整 trace。
- 查看完整用户原文 trace 写 audit log。

## API 设计

### Overview

```http
GET /v1/projects/{projectId}/overview
```

响应：

```json
{
  "project_id": "proj_...",
  "status": "ready",
  "source_file_count": 2,
  "seed_run_count": 3,
  "active_workflow_run_id": "run_...",
  "active_workflow_type": "seed_pipeline",
  "active_workflow_status": "running",
  "latest_failed_workflow_run_id": "run_failed_...",
  "latest_failed_workflow_type": "seed_pipeline",
  "latest_failed_workflow_error_code": "LLM_MODULE_UNBOUND",
  "latest_failed_workflow_updated_at": "...",
  "readiness_snapshot_id": "snap_...",
  "readiness_run_id": "run_...",
  "ready_asset_count": 310,
  "ready_entity_count": 42,
  "ready_relationship_count": 88,
  "ready_world_rule_count": 12,
  "asset_count": 310,
  "graph_node_count": 42,
  "graph_edge_count": 88,
  "worldline_session_count": 2,
  "worldline_event_count": 9,
  "character_interaction_count": 4,
  "writer_run_count": 8,
  "llm_activity_count": 21,
  "llm_token_count": 144000,
  "llm_sync_ok_channel_count": 1,
  "llm_sync_failed_channel_count": 1,
  "llm_sync_pending_channel_count": 0,
  "llm_latest_sync_at": "...",
  "updated_at": "..."
}
```

### Create Upload

```http
POST /v1/projects/{projectId}/uploads
```

请求：

```json
{
  "filename": "novel.txt",
  "content_type": "text/plain",
  "size_bytes": 1234567,
  "purpose": "seed_source"
}
```

响应：

```json
{
  "upload_id": "upl_...",
  "object_key": "tenants/.../uploads/...",
  "signed_url": "https://...",
  "expires_at": "..."
}
```

### Start Seed Workflow

```http
POST /v1/projects/{projectId}/workflows/seed
```

请求：

```json
{
  "upload_id": "upl_...",
  "options": {
    "language": "zh-CN",
    "analysis_depth": "standard",
    "generate_agent_profiles": true
  }
}
```

响应：

```json
{
  "run_id": "run_...",
  "workflow_type": "seed_pipeline",
  "status": "queued"
}
```

### Workflow Events

```http
GET /v1/workflow-runs/{runId}/events
Accept: text/event-stream
```

## 数据模型

当前实现不新增 `project_overview_snapshots` 表。`GET /v1/projects/{projectId}/overview` 是即时聚合 read side，真相源仍是各领域表：`source_files`、`workflow_runs`、`project_readiness_snapshots`、`assets`、`story_graph_snapshots`、`worldline_sessions`、`worldline_events`、`character_interaction_sessions`、`writer_runs`、`llm_activity`、`usage_events` 和 `llm_channels.last_sync_*`。latest failed workflow 只读取 `workflow_runs` 的 public run/type/error code/timestamp metadata，不读取或返回 `error_message`。LLM model sync health 只读取 enabled channel 的 `last_sync_status` / `last_sync_at` 并聚合 counts，不读取或返回 provider/base URL/API key/credential material，也不代表当前实时 provider connectivity。后续如要引入 materialized snapshot，必须继续只保存 public metadata/counts，并保持 raw text、prompt、credential、draft/manuscript 不入公开响应。

## 旧功能映射

| 旧功能 | 新设计 |
|---|---|
| RecentProjects | SaaS Project List + 项目内 recent activity |
| HeroPanel | ProjectHealthHeader，不做营销 hero |
| SeedUploadPanel | UploadSurface |
| InlineWorkflowStream | WorkflowStream |
| RetryFailedSegmentsBanner | Workflow error recovery |
| SeedTaskTimeline | Workflow stage timeline |
| SeedStepTracePanel | TraceDrawer |
| SeedAnalysisPanel | SeedAnalysisSummary + Asset/Graph deep links |
| delete project | Project settings / danger zone + audit |

## 验收清单

- 新项目空状态能引导上传。
- 上传大文件时页面可刷新并恢复任务。
- seed 任务进度可实时更新。
- seed 失败显示真实错误和恢复动作。
- seed 完成后展示数据就绪度。
- LLM 未绑定时阻止启动并指向设置。
- viewer 看不到危险操作。
- 不同用户进入同一路由看到各自 tenant 数据。
