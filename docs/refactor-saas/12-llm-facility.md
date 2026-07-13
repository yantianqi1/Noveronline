# 12. LLM Facility

更新时间：`2026-07-13`

## 模块定位

LLM Facility 管理所有 OpenAI-compatible 渠道、模型、模块绑定、并发、活动追踪、用量和成本。旧系统已经要求所有 LLM 调用必须通过模块绑定；SaaS 版本必须继续强化这个原则。

## 旧功能覆盖

旧能力：

- list settings。
- create/update/delete channel。
- sync models。
- update/delete module binding。
- get activity。
- LLM activity indicator。
- 模块注册表。
- 并发控制。
- writer presets/global presets 部分关联。

新系统必须覆盖并扩展：

- 租户级渠道。
- 平台级渠道。
- 用户自带 Key 或平台托管模型。
- 用量统计。
- 成本估算。
- 模块绑定健康检查。
- 配额限制。

## 配置层级

### Platform Channel

平台管理员配置，租户使用平台额度。

字段：

- provider。
- base_url。
- encrypted_api_key。
- allowed_models。
- cost table。
- enabled。

### Tenant Channel

租户自带渠道。

字段：

- tenant_id。
- name。
- base_url。
- encrypted_api_key。
- max_concurrency。
- enabled。

### Module Binding

模块绑定可以在两个层级：

- tenant default。
- project override。

优先级：

```text
project binding
> tenant binding
> platform default binding
> missing -> explicit error
```

不允许旧式环境变量 fallback。

`settings_json.max_concurrency` 可作为 module-specific concurrency 上限。Pi Writer Runtime 在 provider 调用前会先按 `llm_channels.max_concurrency` 抢占 `llm_channel` slot；当 module binding settings 配置了正整数 `max_concurrency` 时，还会额外抢占 `llm_module` / `module_key` slot。module slot 抢占失败必须释放已取得的 channel slot，并以 `LLM_CONCURRENCY_LIMITED` 显式失败。

## 模块列表

必须覆盖当前注册表：

### Seed / Graph

- `story_ontology`
- `local_block_facts`
- `contextual_block_analysis`
- `anchor_point_summary`
- `entity_resolution`
- `novel_chapter_summarizer`
- `sequential_reading`
- `character_agent_profile`
- `graph_bond_generator`

### Archive / Assets

- `narrative_archives`
- `asset_ingestion`
- `style_extractor`

### Worldline

- `parallel_world_config`
- `worldline_agent_prepare`
- `worldline_agent_dialogue`
- `worldline_character_proposal`
- `worldline_director`
- `worldline_agent_action`
- `worldline_goal_evaluator`

### Writer

- `writer_retrieval_planner`
- `writer_orchestrator`
- `writer_composer`
- `writer_dedup_extractor`
- `writer_reviewer`

### Planned: Writer Asset Distiller

`writer_asset_distiller` 是 [28. Zero-start Writer and Manuscript Asset Distillation](./28-zero-start-writer-and-manuscript-asset-distillation.md) 规划的新模块，当前未进入已实现注册表，不能据此宣称 binding、worker 或 live provider 已闭合。

- module group 归入 Writer/Assets 后处理，要求 JSON capability，不使用旧环境变量 fallback。
- 输入正文只由 worker 通过 app-role/RLS 私下读取；Temporal input/history、公开 Activity、usage、event 和错误不保存正文、evidence、prompt 或 provider body。
- module unbound、capability 不足、quota denied 或 provider failure 只令蒸馏 workflow 失败，不回滚已保存 manuscript，也不写 partial candidate。
- 手动蒸馏由用户动作构成处理授权；`after_adoption | chapter_complete` 自动模式还要求项目 owner/admin 显式确认正文会发送到当前绑定 provider。Channel 自身的 external HTTPS opt-in 和 encrypted credential 约束继续生效。

## 数据模型

```text
llm_channels
  tenant_id nullable for platform
  channel_id
  name
  provider
  base_url
  encrypted_api_key
  max_concurrency
  enabled
  last_sync_at
  last_sync_status

llm_models
  tenant_id nullable
  channel_id
  model_id
  owned_by
  context_window
  supports_tools
  supports_json
  input_cost
  output_cost
  raw_payload_json

llm_module_bindings
  tenant_id
  project_id nullable
  module_key
  channel_id
  model_id
  settings_json
  updated_by
  updated_at

llm_activity
  tenant_id
  project_id nullable
  run_id nullable
  module_key
  channel_id
  model_id
  status
  prompt_tokens
  completion_tokens
  latency_ms
  cost_estimate
  error
  created_at
```

API Key 必须加密，不以明文写数据库。

## UI 设计

位置：

- 租户设置：`Settings -> LLM Facility`。
- 项目设置：`Project Settings -> LLM Overrides`。
- 顶栏：LLM Activity Indicator。

### LLM Facility 页面

Tabs：

- Channels。
- Models。
- Module Bindings。
- Activity。
- Usage。
- Security。

### Module Binding Matrix

用矩阵而不是散乱表单：

```text
Module Group | Module | Channel | Model | Health | Last Used | Actions
Seed         | sequential_reading | opcl | gpt-... | OK | ...
Writer       | writer_composer    | ...  | ...     | Missing | Bind
```

点击 module 显示：

- 说明。
- 示例 prompt。
- 示例 output。
- 推荐模型能力。
- 最近失败。

Project override 表单必须允许配置 module-specific `max_concurrency`，并写入 `llm_module_bindings.settings_json.max_concurrency`。该字段为空时不收紧 module concurrency；填写正整数时由 Pi Writer Runtime 在 provider 调用前用 `resource_locks` 生效。

## 用量与配额

每次 LLM 调用记录 usage event。

LLM Facility 的 Usage 读侧只聚合 `usage_events.usage_type = llm_tokens`。`usage_events` 是全局计费/审计用量表，后续可能同时承载 storage、workflow、import 等非 LLM 用量；这些非 LLM 事件不得出现在 `GET /v1/projects/{projectId}/llm/usage` 或 LLM Facility Usage 面板中。

配额检查发生在：

- workflow start。
- activity before call。
- streaming run ongoing check。

超过配额：

- 新任务拒绝。
- 运行中任务可配置软停或硬停。
- 用户看到可操作提示。

## 并发控制

层级：

- channel max concurrency。
- tenant max LLM concurrency。
- module-specific concurrency。
- workflow concurrency。

实现：

- Go control plane 做 admission。
- Python LLM router 做 worker 侧 semaphore。
- Redis、Postgres advisory lock 或 `resource_locks` slot 做跨 worker 限流。

## Trace 与隐私

LLM trace 可能包含用户小说原文。

规则：

- 默认 activity 只显示摘要。
- 完整 prompt/response 存 trace object 或 encrypted payload。
- 查看完整 trace 需要权限。
- 导出 trace 要审计。
- 平台管理员默认看不到明文，除非支持流程授权。
- LLM module binding、LLM channel create/update 和 trace export 的 JSON decode validation failure 也属于公开隐私边界：无效 JSON、unknown field 或类型错误只返回稳定 `VALIDATION_FAILED` message 和空 details，不回显 decoder 字符串、unknown field 名称、Go struct field 名称，或 `api_key` / prompt / `credential_ref` / draft / manuscript 等敏感词。
- LLM resolver、module binding store、catalog/settings reader、channel store、model syncer 和 telemetry reader 的错误 message 也必须视为不可信。Go HTTP 边界按 error code 输出固定 public message；不回显底层 driver/provider/store exception 文本，即使其中夹带 API key、prompt、`credential_ref`、draft 或 manuscript。

## API

```http
GET /v1/llm/settings
GET /v1/projects/{projectId}/llm/modules
GET /v1/projects/{projectId}/llm/channels
GET /v1/projects/{projectId}/llm/channels/{channelId}/models
GET /v1/projects/{projectId}/llm/module-bindings
GET /v1/projects/{projectId}/llm/module-bindings/{moduleKey}/resolution
POST /v1/llm/channels
PATCH /v1/llm/channels/{channelId}
DELETE /v1/llm/channels/{channelId}
POST /v1/llm/channels/{channelId}/sync-models
PUT /v1/projects/{projectId}/llm/module-bindings/{moduleKey}
DELETE /v1/projects/{projectId}/llm/module-bindings/{moduleKey}
GET /v1/projects/{projectId}/llm/activity?run_id={runId}&module_key={moduleKey}
GET /v1/projects/{projectId}/llm/usage?run_id={runId}&module_key={moduleKey}
GET /v1/projects/{projectId}/agent-traces/{traceId}/events
GET /v1/projects/{projectId}/agent-traces/{traceId}/events?include_full=true
POST /v1/projects/{projectId}/agent-traces/{traceId}/export
```

## 旧功能映射

| 旧功能 | 新功能 |
|---|---|
| `llm_channels` | tenant/platform channels |
| `llm_models` | model cache + capability metadata |
| `llm_module_bindings` | tenant/project binding matrix |
| `llm_activity_tracker` | llm_activity + usage_events |
| `llm_concurrency_service` | distributed quota/concurrency |
| `llm_router` | Python worker LLM router using binding API/cache |
| LlmActivityIndicator | realtime tenant activity indicator |

## 验收清单

- 没有绑定模块时 Agent 明确失败。
- 租户 A 看不到租户 B 渠道。
- API Key 不明文返回。
- 模型同步失败显示错误。
- writer_composer 可绑定强模型，writer_reviewer 可绑定独立模型。
- activity 能按项目/run/module 过滤。
- 用量统计能汇总到租户账单。
