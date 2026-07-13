# 21. Pi Writer Agent Runtime

更新时间：`2026-07-13`

## 模块定位

Pi Writer Agent Runtime 是 SaaS 重构的第一条可运行创作闭环。它把写作台前端、writer run API、LLM Facility、MiroFish 小说上下文工具和 `earendil-works/pi` 的 Agent SDK 连接起来。

目标不是从零开发一个新的 writer agent loop，而是使用 Pi 的通用 agent 基座承载 MiroFish 的小说写作能力：

- `@earendil-works/pi-agent-core`：状态化 agent、tool calling、事件流、并行/串行工具执行、`beforeToolCall` / `afterToolCall`。
- `@earendil-works/pi-ai`：多 provider LLM API、OpenAI-compatible、stream、usage/cost。

Pi 只替代 Writer Agent 的通用执行循环和 provider 抽象。小说领域知识、权限、数据库、LLM 模块绑定、trace、workflow、draft/manuscript 仍由 MiroFish 自己掌控。

## 为什么使用 Pi

旧重构文档默认会在 Python Agent Runtime 中重建 writer orchestrator、tool loop、stream、trace、LLM routing。现在调整为：

- Writer Agent loop 使用 Pi SDK。
- Seed / Graph / Asset ingestion / Worldline 第一阶段继续保留 Python 领域逻辑。
- 后续再评估 Character Console 和 Worldline 是否也迁到 Pi。

收益：

- 更快获得稳定的 tool-calling loop。
- 复用 Pi 的 streaming event、state management、tool execution mode。
- 减少自研 provider compatibility 和 tool loop 细节。
- 让团队先验证“用户写作台 -> 后端 agent -> draft”的产品价值。

代价：

- Pi 是 TypeScript / Node SDK，需要新增 Node worker。
- Pi 不内置 MiroFish 的租户权限、RLS、审计和业务工具。
- Pi 默认 auth 可走环境变量，但本项目禁止旧式环境变量 LLM fallback，需要适配 LLM Facility。
- Pi 默认没有权限沙箱，工具执行必须由 MiroFish wrapper 严格控制。

## 范围

### 第一阶段必须做

- 写作台触发 writer run。
- 后端创建 run 并启动 Pi Writer Runtime。
- Pi Runtime 通过 LLM Facility 解析模块绑定。
- Pi Runtime 执行最小 writer tools。
- 前端收到流式正文和工具事件。
- 草稿保存为 draft revision。
- 用户可采用 draft 到 manuscript。
- 错误、trace、usage 可查询。

### 第一阶段不做

- 不迁移所有 seed/graph/worldline 逻辑到 Pi。
- 不实现完整计费系统。
- 不实现完整协作编辑。
- 不让 Pi 直接访问数据库裸连接并绕过 tenant context。
- 不使用 `pi-coding-agent` CLI 作为产品后端。
- 不让 Pi 从环境变量读取生产 LLM API Key。

## Runtime 拓扑

### 最小闭环拓扑

```text
Writer Workbench UI
  -> writer run API
  -> workflow_runs / writer_runs
  -> Pi Writer Runtime (Node/TS)
  -> LLM Facility adapter
  -> pi-agent-core Agent
  -> MiroFish writer tools
  -> workflow_events / agent_trace_events
  -> drafts / manuscript_blocks
```

### SaaS 目标拓扑

```text
apps/web
  -> apps/api (Go Control Plane)
  -> Temporal WriterRunWorkflow
  -> apps/pi-agent-runtime
  -> Postgres / Object Storage / LLM provider
```

### 兼容期拓扑

如果 SaaS 基座尚未完成，可以先使用当前前端/后端作为桥：

```text
apps/web/app/(app)/[tenantSlug]/projects/[projectId]/writer
  -> backend FastAPI compatibility endpoint
  -> Node Pi Writer Runtime process
  -> current unified DB / services
```

兼容期 endpoint 必须尽量贴近未来 `/v1/projects/{projectId}/writer-runs` 语义。兼容桥是过渡，不是长期真相源。

## 包与运行环境

推荐新增：

```text
apps/pi-agent-runtime/
  package.json
  tsconfig.json
  src/
    worker.ts
    runtime/pi-writer-agent.ts
    runtime/pi-model-adapter.ts
    runtime/pi-event-mapper.ts
    tools/
      index.ts
      query-project-context.ts
      query-chapter-scene.ts
      query-assets.ts
      query-manuscript-context.ts
      save-draft-revision.ts
    contracts/
      writer-run.ts
      writer-events.ts
```

依赖：

```text
@earendil-works/pi-agent-core
@earendil-works/pi-ai
typebox
```

Pi 当前 npm 包要求 Node `>=22.19.0`。Infra 文档和 Dockerfile 必须同步这个版本要求。

## Writer Run 输入契约

```json
{
  "tenant_id": "ten_...",
  "project_id": "proj_...",
  "run_id": "run_...",
  "requested_by": "usr_...",
  "mode": "draft",
  "chapter_id": "chap_...",
  "scene_id": "scene_...",
  "instruction": "写下一场雨夜谈判，保持压迫感",
  "selected_asset_ids": [],
  "worldline_path_ids": [],
  "options": {
    "module_key": "writer_composer",
    "thinking_level": "medium",
    "tool_execution": "parallel",
    "target_words": 1800,
    "review_after_write": false
  }
}
```

规则：

- `tenant_id` 不从用户 body 信任；由 Go/FastAPI 边界解析并注入。
- `module_key` 默认为 `writer_composer`，复杂 tool loop 可使用 `writer_orchestrator`。
- `run_id` 是 trace、workflow events、draft revision 的关联键。
- `worldline_path_ids` 只能作为 reference，不能自动写 canon。

## Pi Agent 初始化

Pi Agent 初始化必须由 MiroFish runtime 包装：

```typescript
const agent = new Agent({
  initialState: {
    systemPrompt,
    model,
    thinkingLevel,
    tools,
    messages,
  },
  transformContext,
  getApiKey,
  beforeToolCall,
  afterToolCall,
  toolExecution,
  sessionId: runId,
});
```

其中：

- `systemPrompt` 来自 Writer prompt builder，不直接硬编码到 worker 入口。
- `model` 来自 LLM Facility adapter。
- `tools` 只能来自 MiroFish tool registry。
- `messages` 可从 chapter/scene/draft history 构建。
- `transformContext` 负责上下文裁剪、摘要注入和 token 控制。
- `getApiKey` 只能返回 LLM Facility 解密后的本次调用 key。
- `beforeToolCall` 做权限、tenant/project/run 校验。
- `afterToolCall` 写 trace、usage、审计补充字段。

## LLM Facility Adapter

Pi 的 provider/auth 能力必须被包在 MiroFish 模块绑定后面。

输入：

```text
tenant_id
project_id
module_key
run_id
```

输出：

```text
Pi Model
provider id
base_url
api_key for this request
model capability
cost metadata
concurrency lease
```

实现要求：

- 读取 `llm_module_bindings`，优先级为 project > tenant > platform default。
- 未绑定时抛出 `LLM_MODULE_UNBOUND`。
- 不读取 `OPENAI_API_KEY` 等环境变量作为业务 fallback。
- API Key 不写日志、不返回前端。
- 每次调用写 `llm_activity` 和 `usage_events`。
- 并发控制需要跨 worker 生效，可通过 Redis、Postgres lock 或 Go admission control。

Pi 接入方式：

1. 使用 `@earendil-works/pi-ai` 的 custom provider / custom model。
2. 或直接调用对应 API implementation 并显式传入 `apiKey`。

推荐第一阶段使用 custom provider，避免绕过 Pi 的 usage 和 model abstraction。

## Writer Tool Registry

### 最小工具

| Tool | 类型 | 职责 |
|---|---|---|
| `query_project_context` | read | 读取项目基础设定、语言、类型、当前状态 |
| `query_chapter_scene` | read | 读取目标章节、场景、大纲和 POV |
| `query_assets` | read | 检索资产库中的角色、规则、素材、风格 |
| `query_manuscript_context` | read | 读取前文、已采用 manuscript blocks、续写上下文 |
| `save_draft_revision` | write | 保存本次生成结果为 draft revision |

### 第二阶段工具

| Tool | 类型 | 来源文档 |
|---|---|---|
| `query_character_profile` | read | `08-asset-library.md`, `06-seed-pipeline.md` |
| `query_world_rules` | read | `06-seed-pipeline.md`, `08-asset-library.md` |
| `query_graph_neighbors` | read | `07-story-graph.md` |
| `query_worldline_paths` | read | `09-worldline.md` |
| `propose_scene_outline` | proposal | `11-writer-workbench.md` |
| `propose_rewrite_span` | proposal | `11-writer-workbench.md` |
| `run_reviewer` | workflow | `11-writer-workbench.md`, `12-llm-facility.md` |

### 工具执行规则

- Read tools 可并行。
- Write tools 必须串行。
- Proposal tools 默认不写 canon。
- 所有工具参数用 schema 校验。
- 每个工具必须接收 runtime context，不从全局状态猜项目。
- `beforeToolCall` 必须检查权限和 tool allowlist。
- `save_draft_revision` 必须幂等，重复调用不能产生脏数据。

### Writer 查询生命周期门（规划中）

本契约来自 [28. Zero-start Writer and Manuscript Asset Distillation](./28-zero-start-writer-and-manuscript-asset-distillation.md)，是 Pi 工具读侧的待实现加固，不表示当前所有 query tool 已通过该 gate 验收。

- `query_assets` 在 `beforeToolCall` 授权后仍必须由 server-side reader 强制 tenant/project、`enabled = true` 和 lifecycle allowlist；不信任模型传入的 lifecycle 过滤器。
- `query_assets` allowlist 为 `seed | canon | material`。`candidate | draft | simulation | manuscript | archived` 在该工具中全部拒绝；simulation 和 manuscript 分别通过经过验证的 worldline reference 与 `query_manuscript_context` 专用工具读取。
- `query_character_profile` 和 `query_world_rules` 保持 typed canon reader，不从未采用 candidate assets 建立隐式 fallback；它们仍必须强制 tenant/project 和各自 canon/evidence 真相源。
- manuscript 反哺产生的资产在审阅前是 `candidate + disabled`；即使模型知道 candidate id，query gate 也必须拒绝。只有人工采用为 `canon` 或 `material` 并启用后才可被后续 Writer run 消费。
- 生命周期拒绝必须写 sanitized tool event/trace 元数据，不回显 candidate body、正文、prompt 或凭证。
- Pi Runtime 只保存 draft revision，不调用资产采用、canon 更新或 manuscript asset distillation 写入；这些动作由独立的用户/API/workflow 边界执行。

## Event 映射

Pi event 必须映射成产品事件和 trace 事件。

| Pi event | workflow event | trace event |
|---|---|---|
| `agent_start` | `writer.run.started` | `agent_started` |
| `turn_start` | `writer.turn.started` | `turn_started` |
| `message_update` text delta | `writer.token` | `llm_text_delta` |
| `tool_execution_start` | `writer.tool.started` | `tool_call` |
| `tool_execution_update` | `writer.tool.progress` | `tool_progress` |
| `tool_execution_end` | `writer.tool.completed` | `tool_result` |
| `message_end` assistant | `writer.message.completed` | `assistant_message` |
| `agent_end` | `writer.run.completed` | `agent_completed` |
| error/abort | `writer.run.failed` / `writer.run.cancelled` | `error` |

SSE 对前端暴露 workflow event，不直接暴露 Pi 内部 event 原型。这样以后替换 runtime 也不会破坏前端契约。

## Draft 保存

Pi 生成正文后必须保存到：

```text
drafts
draft_events
workflow_runs
workflow_events
agent_traces
agent_trace_events
llm_activity
```

如果当前兼容期还没有新表，允许写入旧 writer draft/chapter 表，但必须生成迁移报告或兼容标记，避免长期混淆真相源。

采用正文时：

- draft -> manuscript 是独立 API。
- 采用动作写 audit log。
- 采用后可触发 dedup/reviewer/index workflow。
- Agent 自己不能默认把 draft 提交为 manuscript。

## 错误处理

错误格式遵循 `15-api-contracts.md`：

```json
{
  "error": {
    "code": "LLM_MODULE_UNBOUND",
    "message": "writer_composer 模块未绑定",
    "details": {},
    "request_id": "req_..."
  }
}
```

关键错误：

- `LLM_MODULE_UNBOUND`
- `LLM_PROVIDER_ERROR`
- `SCHEMA_VALIDATION_FAILED`
- `TOOL_PERMISSION_DENIED`
- `TOOL_EXECUTION_FAILED`
- `WRITER_CONTEXT_EMPTY`
- `WORKFLOW_CANCELLED`
- `WORKER_UNAVAILABLE`

禁止：

- LLM 失败后返回 mock 正文。
- 上下文为空时生成“泛化成功”。
- 工具失败被吞掉。
- JSON 解析失败变成空对象继续落库。

## Trace 与隐私

Pi trace 可能包含用户小说原文。

要求：

- 默认前端只展示摘要、工具名、状态、token、耗时。
- 完整 prompt/response 需要权限。
- 查看完整 trace 写 audit log。
- 平台管理员默认不能无审计查看明文。
- 大型 prompt/response 可存 object storage，DB 存引用。

## 与 Python Agent Runtime 的关系

第一阶段保留 Python Agent Runtime 作为：

- seed pipeline。
- graph build。
- asset ingestion。
- worldline prepare / director。
- legacy service extraction。

Pi Writer Runtime 只负责 writer agent loop。

后续评估顺序：

1. Reviewer / dedup：可优先迁到 Pi，因为与 writer run 接近。
2. Character Console：可迁到 Pi，因为是互动 agent。
3. Worldline interactive layer：可部分迁到 Pi，但 director/canon 写入仍需严格约束。
4. Seed/Graph/Asset ingestion：除非收益明确，否则继续 Python。

## API

目标 API：

```http
POST /v1/projects/{projectId}/writer-runs
GET /v1/writer-runs/{runId}
GET /v1/writer-runs/{runId}/events
POST /v1/writer-runs/{runId}/cancel
POST /v1/drafts/{draftId}/adoptions
```

兼容期 API 可以挂在旧后端，但语义必须对齐目标 API。

## 前端要求

写作台必须支持：

- 运行按钮。
- 运行中禁用/取消状态。
- token stream。
- tool call 折叠列表。
- trace drawer。
- 错误状态和重试入口。
- draft preview。
- adopt draft。

UI 细节遵循：

- `04-design-system-and-ui.md` 的写作台布局。
- `11-writer-workbench.md` 的 Draft Mode / Continue Mode / Right Rail。
- `28-zero-start-writer-and-manuscript-asset-distillation.md` 的双入口、候选资产 rail 和移动端 bottom Sheet 契约。
- 不在页面中放“这是 AI 功能说明”的大段说明文本。

## 测试与验收

### Unit

- LLM Facility adapter：缺绑定返回 `LLM_MODULE_UNBOUND`。
- Tool registry：未授权 tool 被 `beforeToolCall` 阻止。
- Event mapper：Pi event 正确映射 workflow event。
- Draft persistence：重复 save 不产生重复主稿。

### Integration

- 创建 writer run。
- 使用 faux/test provider 产生确定 token stream。
- `apps/pi-agent-runtime/src/llm/pi-ai-compose.live.test.ts` 提供 opt-in live/local provider smoke：只接受 resolved LLM Facility handoff env（`MIROFISH_PI_WRITER_LIVE_RESOLVED_*`），无 env 时 skip，partial env 时 fail fast，完整 env 时通过 Pi AI explicit-key adapter 调 OpenAI-compatible provider；该 harness 不新增 production fallback，也不在测试输出中打印 API key、prompt、raw provider response 或生成正文。
- 调用 read tools。
- 保存 draft。
- 前端读取 SSE events。

### Manual

- 在 LLM Facility 绑定 `writer_composer`。
- 在写作台选择章节/场景。
- 输入写作指令。
- 看到流式正文。
- 看到工具调用。
- 采用 draft 到 manuscript。

## 分阶段接入

### Stage 1：最小闭环

- Pi Writer Runtime。
- LLM adapter。
- 最小 tools。
- stream。
- draft save/adopt。

### Stage 2：上下文增强

- 资产库检索。
- 世界规则。
- 角色档案。
- 前文续写上下文。

### Stage 3：创作系统接入

- graph neighbors。
- worldline saved paths。
- character interaction drafts。

### Stage 4：质量链路

- reviewer。
- dedup extractor。
- forbidden lexicon。
- one-click actions。

### Stage 5：SaaS 硬化

- Temporal workflow。
- 多租户 RLS。
- usage/cost。
- trace privacy。
- concurrency。

## 验收清单

- 写作台能触发 Pi writer run。
- Pi Runtime 不使用 `pi-coding-agent` CLI。
- LLM 只通过模块绑定解析。
- 缺绑定显式失败。
- 工具调用全部带 tenant/project/run context。
- token stream 可见。
- draft 可保存和采用。
- trace 可查询。
- 失败不伪装成功。
- 后续资产、图谱、worldline 能作为 writer tools 分批接入。
