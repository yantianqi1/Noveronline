# 04 API 接口规范与联调方案

## 1. 文档目标与现状边界

本方案只讨论 API 边界，不改写业务实现代码。目标是为后续 `DDD 模块化单体 + durable workflow + CQRS` 架构提供稳定的接口层规范，并保证重构期间前端不停服。

当前仓库的真实现状如下：

- 后端仍是单 Flask 应用，蓝图按 `project / novel / worldline / llm / archive` 暴露。
- 前端直接依赖这些端点，调用集中在 `frontend/src/api/*.js`。
- 目前已经存在 SSE 端点：
  - `POST /api/novel/draft/generate`
  - `POST /api/novel/draft/revise`
  - `POST /api/worldline/session/<session_id>/auto-evolve/stream`
- 当前大多数接口返回包络为：

```json
{
  "success": true,
  "data": {}
}
```

或失败时：

```json
{
  "success": false,
  "error": "message"
}
```

这个现状可以继续兼容，但不应该继续作为目标契约。

---

## 2. 目标 API 总体原则

### 2.1 总体风格

- 主体使用 REST。
- 长时任务统一建模为 `operation` 资源。
- 流式进度与生成过程统一走 SSE。
- 只有明确需要双向实时交互的场景才使用 WebSocket，例如导演台实时协作、多人共编、Agent 对话长连接。
- 所有破坏性变更统一进入 `/api/v2`，旧 `/api/*` 通过兼容层保留。

### 2.2 领域边界

目标 API 不再按旧代码文件名切，而是按稳定业务资源切：

- `workspace`：项目、原稿、导入任务、产物入口
- `chapter-context`：章节上下文包
- `worldline`：prepare、session、timeline、candidate/canon event、agent 视图
- `draft`：生成、修订、定稿、审校报告
- `archive`：档案库、记忆审查
- `llm`：渠道、模型、模块绑定、活动观测
- `operation`：所有异步工作流统一状态资源

---

## 3. URL 与资源命名规范

### 3.1 基础路径

- 规范新接口统一为 `/api/v2/...`
- 旧接口继续保留在 `/api/...`
- 路径一律使用小写加短横线或复数名词，不使用动词式大杂烩路径

正确示例：

- `/api/v2/workspaces`
- `/api/v2/workspaces/{workspace_id}/ingests`
- `/api/v2/worldlines/sessions/{session_id}/events`
- `/api/v2/archives/{archive_id}/memories`

不再扩张的旧式路径示例：

- `/api/novel/chapter-context`
- `/api/worldline/session/create`
- `/api/project/seed/extract`

### 3.2 资源标识

- 所有主资源主键统一命名为 `{resource}_id`
- 路径参数使用业务稳定 ID，不使用临时文件名
- 查询参数一律使用 snake_case 或统一 camelCase 二选一，目标架构建议统一 `snake_case`
- 前端 DTO 可以 camelCase，但边界转换必须在 typed client/BFF 中完成，不进入领域服务

### 3.3 资源操作约定

- `POST /resources`：创建资源或发起命令
- `GET /resources/{id}`：读取资源详情
- `GET /resources`：读取资源列表
- `PATCH /resources/{id}`：局部更新
- `DELETE /resources/{id}`：删除
- 对于本质是“动作”的命令，不直接塞进查询资源路径里，优先显式建命令子资源

示例：

- 不推荐：`POST /worldlines/session/<id>/events/adopt`
- 推荐：`POST /api/v2/worldlines/sessions/{session_id}/event-adoptions`

如果必须保留动作语义，可在兼容层继续支持旧路径，但 canonical API 不再增加这种形式。

---

## 4. 命令接口 vs 查询接口

### 4.1 分离原则

目标架构虽然外部仍是 REST，但内部按 CQRS 设计：

- 命令接口负责改变状态，调用 workflow / aggregate
- 查询接口只返回 projection，不触发副作用

### 4.2 命令接口规则

- 只允许 `POST / PUT / PATCH / DELETE`
- 必须支持 `X-Trace-Id`
- 对“可能重复提交”的创建型命令必须支持 `Idempotency-Key`
- 长时命令默认返回 `202 Accepted` + `operation`
- 短时命令可返回 `200/201`
- 命令响应不返回“拼出来的大而全页面数据”，只返回必要资源标识、状态和链接

### 4.3 查询接口规则

- 只允许 `GET`
- 不得触发任务启动、状态变更、缓存重建
- 必须支持过滤、排序、分页
- 时间线、事件流、审计视图优先使用 cursor 分页

---

## 5. 统一请求与响应规范

### 5.1 请求头

所有新接口统一支持：

- `Content-Type: application/json`
- `Accept: application/json`
- `X-Trace-Id: <uuid>`：客户端可传；服务端必须回传
- `Idempotency-Key: <uuid>`：创建 session、draft、operation 时必填
- `If-Match: "<etag>"`：需要乐观锁的更新型接口使用
- `X-Client-Version: <app-version>`：前端版本观测

### 5.2 成功响应包络

新接口统一：

```json
{
  "data": {},
  "meta": {
    "trace_id": "01HT...",
    "version": "v2"
  },
  "links": {
    "self": "/api/v2/..."
  }
}
```

列表响应：

```json
{
  "data": [],
  "meta": {
    "trace_id": "01HT...",
    "pagination": {
      "next_cursor": "evt_123",
      "has_more": true
    }
  }
}
```

旧兼容接口仍可输出 `{ success, data }`，但由兼容层转换，不要求新应用服务继续原样返回。

### 5.3 错误模型

目标错误模型：

```json
{
  "error": {
    "code": "WORLDLINE_SESSION_NOT_FOUND",
    "message": "worldline session not found",
    "details": {
      "session_id": "ws_123"
    },
    "retryable": false
  },
  "meta": {
    "trace_id": "01HT...",
    "version": "v2"
  }
}
```

约束：

- `code` 必填，稳定可枚举
- `message` 面向开发者，不用拼接 traceback
- `details` 只放结构化字段，不放大段异常文本
- `traceback` 只进日志，不回 API
- `retryable` 用于前端决定是否展示重试

建议错误码分层：

- `WORKSPACE_*`
- `INGEST_*`
- `WORLDLINE_*`
- `DRAFT_*`
- `ARCHIVE_*`
- `LLM_*`
- `OPERATION_*`
- `VALIDATION_*`

### 5.4 幂等性

以下接口必须支持 `Idempotency-Key`：

- 创建 workspace ingest
- 创建 worldline preparation
- 创建 worldline session
- 创建 draft generation / revision
- finalize draft
- LLM 渠道创建与模型同步任务

实现要求：

- 服务端保存 `idempotency_key + request_hash + response_snapshot`
- 同 key 同 payload 重试返回同一结果
- 同 key 不同 payload 直接 `409 CONFLICT`

### 5.5 分页、过滤、排序

统一规范：

- 时间线和事件流：`?limit=50&cursor=evt_123`
- 列表筛选：`?status=active&layer=candidate&entity_type=character`
- 排序：`?sort=-created_at` 或 `?sort=created_at`

规则：

- `limit` 默认值由领域定义，但必须有上限，例如 `100`
- cursor 分页优先，offset 仅保留在兼容层或低规模后台配置页
- 多值过滤使用逗号分隔仅保留在兼容层；canonical API 优先重复 query key 或数组语义

---

## 6. SSE / WebSocket / Async Job Status 统一规范

### 6.1 总原则

当前仓库已经把 draft generate/revise 和 worldline auto-evolve 做成 SSE。目标架构必须把这三种东西统一成一套模型：

- 命令创建 `operation`
- `GET /api/v2/operations/{operation_id}` 查询状态
- `GET /api/v2/operations/{operation_id}/events` 查询事件历史
- `GET /api/v2/operations/{operation_id}/stream` 订阅 SSE

也就是说，SSE 只是 `operation` 的一种观察方式，不再让每个业务接口自行发明一套流式协议。

### 6.2 Async Job Status 规范

长时命令返回：

```json
{
  "data": {
    "operation_id": "op_123",
    "status": "accepted",
    "resource_type": "draft",
    "resource_id": "dr_456"
  },
  "links": {
    "self": "/api/v2/operations/op_123",
    "stream": "/api/v2/operations/op_123/stream",
    "events": "/api/v2/operations/op_123/events",
    "resource": "/api/v2/drafts/dr_456"
  }
}
```

`operation.status` 枚举统一为：

- `accepted`
- `running`
- `waiting`
- `completed`
- `failed`
- `cancelled`

### 6.3 SSE 规范

SSE 统一格式：

```text
id: 17
event: progress
data: {"operation_id":"op_123","step":"writer.generate","progress":62}

```

必须支持的事件类型：

- `operation.started`
- `progress`
- `artifact.ready`
- `warning`
- `heartbeat`
- `operation.completed`
- `operation.failed`

规则：

- 每个事件都必须带 `operation_id`
- 最后一条必须是 `operation.completed` 或 `operation.failed`
- 不允许只用 `type=done` 这类弱语义作为 canonical 规范
- SSE 响应头统一：
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-cache`
  - `X-Accel-Buffering: no`
- 允许 `Last-Event-ID` 恢复订阅，但必须以 operation event log 为前提

### 6.4 WebSocket 规范

WebSocket 只用于真正需要双向实时交互的场景：

- 导演台实时协同
- 多人共编草稿
- 实时 Agent chat room

WebSocket 消息包络：

```json
{
  "type": "agent.message.send",
  "trace_id": "01HT...",
  "seq": 18,
  "ts": "2026-04-11T15:30:00Z",
  "data": {}
}
```

规则：

- WebSocket 不承载工作流长任务状态主通道
- 长任务状态仍以 `operation + SSE` 为主
- WebSocket 只传交互事件，不替代查询接口

---

## 7. 版本管理规范

### 7.1 版本策略

- 所有破坏性变更进入 `/api/v2`
- `/api/*` 视为 legacy compatibility surface
- 非破坏性字段新增可直接在 `v2` 内进行
- 同一路径上的响应删除字段、字段改名、状态码语义变化，都必须升版本

### 7.2 生命周期

- `v1`：旧 Flask 蓝图接口，经兼容层继续暴露
- `v2`：canonical API，只允许新功能进入
- 文档中必须标明每个旧接口的状态：
  - `stable`
  - `compatibility-only`
  - `deprecated`
  - `removed`

---

## 8. 前后端契约管理建议

### 8.1 契约源

- REST 使用 `OpenAPI 3.1`
- SSE / WebSocket 使用 `AsyncAPI` 或最少维护独立事件 schema 文档
- 所有 schema 进入仓库版本控制，不允许靠 wiki 手工维护

### 8.2 客户端生成

- 前端不再手写大面积 `fetch("/api/...")`
- 通过 OpenAPI 生成 typed client
- BFF 内部同样使用 schema 校验 DTO
- 边界校验使用 `Zod` 或 `Pydantic` 双端对应

### 8.3 变更控制

- PR 必须同时包含：
  - schema 变更
  - handler 变更
  - consumer 变更
  - contract test
- 对 SSE 事件名、字段变更同样执行破坏性审查

### 8.4 测试要求

- 后端：consumer-driven contract tests
- 前端：mock server 基于 OpenAPI schema 自动生成
- 集成层：对关键链路做录制式回放测试
- 灰度前必须跑通 writer/worldline/archive/llm 四条关键接口回归

---

## 9. 核心接口优先重构清单

以下接口按“先立 canonical v2，再做兼容映射”的顺序规划。

### 9.1 Project / Workspace Ingest

当前主要接口：

- `POST /api/project/seed/extract`
- `GET /api/project/task/{task_id}`
- `GET /api/project/{project_id}`
- `GET /api/project/list`
- `DELETE /api/project/{project_id}`

目标接口：

| 优先级 | 当前接口 | 目标接口 | 类型 | 说明 |
|---|---|---|---|---|
| P0 | `POST /api/project/seed/extract` | `POST /api/v2/workspaces/{workspace_id}/ingests` | Command | 上传原稿并发起导入工作流，返回 `operation` |
| P0 | `GET /api/project/task/{task_id}` | `GET /api/v2/operations/{operation_id}` | Query | 统一任务状态模型 |
| P1 | `GET /api/project/{project_id}` | `GET /api/v2/workspaces/{workspace_id}` | Query | workspace 聚合详情 |
| P1 | `GET /api/project/list` | `GET /api/v2/workspaces` | Query | workspace 列表 |
| P1 | `DELETE /api/project/{project_id}` | `DELETE /api/v2/workspaces/{workspace_id}` | Command | 删除 workspace |

建议补全：

- `POST /api/v2/workspaces`
- `GET /api/v2/workspaces/{workspace_id}/ingests/{ingest_id}`
- `GET /api/v2/workspaces/{workspace_id}/artifacts`

### 9.2 Chapter Context

当前主要接口：

- `GET /api/novel/chapter-context/options`
- `POST /api/novel/chapter-context`

目标接口：

| 优先级 | 当前接口 | 目标接口 | 类型 | 说明 |
|---|---|---|---|---|
| P0 | `GET /api/novel/chapter-context/options?project_id=...` | `GET /api/v2/workspaces/{workspace_id}/chapter-context-options` | Query | 返回 scope、POV、章节、worldline 可选项 |
| P0 | `POST /api/novel/chapter-context` | `POST /api/v2/workspaces/{workspace_id}/chapter-contexts` | Command | 构建 context pack，可短时同步也可返回 operation |
| P1 | 无 | `GET /api/v2/workspaces/{workspace_id}/chapter-contexts/{context_id}` | Query | 读取已生成 context pack |

请求建议：

- `scope` 统一枚举：`project_chapter`、`worldline_session`
- 不再混杂旧 `branch_id` 语义，改为 `session_id`
- 上下文条目必须返回稳定 `entry_id`

### 9.3 Worldline Prepare / Session / Step / Events

当前主要接口：

- `POST /api/worldline/session/prepare`
- `GET /api/worldline/session/prepare/{prepare_id}`
- `GET /api/worldline/session/prepare/{prepare_id}/agents`
- `POST /api/worldline/session/prepare/{prepare_id}/start`
- `POST /api/worldline/session/create`
- `GET /api/worldline/session/{session_id}`
- `POST /api/worldline/session/{session_id}/step`
- `POST /api/worldline/session/{session_id}/inject-variable`
- `GET /api/worldline/session/{session_id}/timeline`
- `GET /api/worldline/session/{session_id}/events/candidates`
- `GET /api/worldline/session/{session_id}/events/canon`
- `POST /api/worldline/session/{session_id}/events/adopt`
- `POST /api/worldline/session/{session_id}/events/{event_id}/edit`
- `POST /api/worldline/session/{session_id}/auto-evolve/stream`

目标接口：

| 优先级 | 当前接口 | 目标接口 | 类型 | 说明 |
|---|---|---|---|---|
| P0 | `POST /api/worldline/session/prepare` | `POST /api/v2/worldlines/preparations` | Command | 预备 worldline，会生成 `operation` |
| P0 | `GET /api/worldline/session/prepare/{prepare_id}` | `GET /api/v2/worldlines/preparations/{preparation_id}` | Query | 读取 prepare 状态与摘要 |
| P0 | `GET /api/worldline/session/prepare/{prepare_id}/agents` | `GET /api/v2/worldlines/preparations/{preparation_id}/agents` | Query | 读取 prepare 产出的角色阵容 |
| P0 | `POST /api/worldline/session/prepare/{prepare_id}/start` | `POST /api/v2/worldlines/preparations/{preparation_id}/session-starts` | Command | 从 prepare 启动 session |
| P0 | `POST /api/worldline/session/create` | `POST /api/v2/worldlines/sessions` | Command | 直接创建 session |
| P0 | `GET /api/worldline/session/{session_id}` | `GET /api/v2/worldlines/sessions/{session_id}` | Query | 读取单世界 session |
| P0 | `POST /api/worldline/session/{session_id}/step` | `POST /api/v2/worldlines/sessions/{session_id}/steps` | Command | 推进一步，可同步或返回 operation |
| P0 | `GET /api/worldline/session/{session_id}/timeline` | `GET /api/v2/worldlines/sessions/{session_id}/timeline` | Query | cursor 分页时间线 |
| P0 | `GET /api/worldline/session/{session_id}/events/candidates` | `GET /api/v2/worldlines/sessions/{session_id}/events?status=candidate` | Query | 查询 candidate |
| P0 | `GET /api/worldline/session/{session_id}/events/canon` | `GET /api/v2/worldlines/sessions/{session_id}/events?status=canon` | Query | 查询 canon |
| P1 | `POST /api/worldline/session/{session_id}/inject-variable` | `POST /api/v2/worldlines/sessions/{session_id}/variables` | Command | 变量注入 |
| P1 | `POST /api/worldline/session/{session_id}/events/adopt` | `POST /api/v2/worldlines/sessions/{session_id}/event-adoptions` | Command | adopt/reject candidate 事件 |
| P1 | `POST /api/worldline/session/{session_id}/events/{event_id}/edit` | `PATCH /api/v2/worldlines/sessions/{session_id}/events/{event_id}` | Command | 编辑 candidate/canon 事件 |
| P1 | `POST /api/worldline/session/{session_id}/auto-evolve/stream` | `POST /api/v2/worldlines/sessions/{session_id}/auto-evolutions` + `GET /api/v2/operations/{id}/stream` | Command + SSE | 不再直接把业务命令绑定到裸 SSE 端点 |

明确约束：

- 新 worldline API 不再暴露 `branch` 语义
- 旧 `/branches`、`/comparison` 继续返回 `410`
- `branch_id` 在兼容层被忽略或映射为 `current_world`

### 9.4 Draft Generate / Revise / Finalize

当前主要接口：

- `POST /api/novel/draft/generate` `SSE`
- `POST /api/novel/draft/revise` `SSE`
- `POST /api/novel/draft/finalize`
- `GET /api/novel/reviewer-rules`
- `PUT /api/novel/reviewer-rules`

目标接口：

| 优先级 | 当前接口 | 目标接口 | 类型 | 说明 |
|---|---|---|---|---|
| P0 | `POST /api/novel/draft/generate` | `POST /api/v2/drafts` | Command | 创建 draft generation operation |
| P0 | `POST /api/novel/draft/revise` | `POST /api/v2/drafts/{draft_id}/revisions` | Command | 创建 revision operation |
| P0 | `POST /api/novel/draft/finalize` | `POST /api/v2/drafts/{draft_id}/finalizations` | Command | 回写章节卡与正文 |
| P1 | `GET /api/novel/reviewer-rules` | `GET /api/v2/workspaces/{workspace_id}/reviewer-rules` | Query | 审校规则读取 |
| P1 | `PUT /api/novel/reviewer-rules` | `PUT /api/v2/workspaces/{workspace_id}/reviewer-rules` | Command | 审校规则更新 |
| P0 | SSE 内嵌在业务接口 | `GET /api/v2/operations/{operation_id}/stream` | SSE | 统一 draft 流式事件 |

Draft 领域建议补资源：

- `GET /api/v2/drafts/{draft_id}`
- `GET /api/v2/drafts/{draft_id}/artifacts`
- `GET /api/v2/drafts/{draft_id}/review-report`

### 9.5 Archive Library / Memory Review

当前主要接口：

- `GET /api/archive/library`
- `GET /api/archive/library/{archive_id}`
- `GET /api/archive/library/{archive_id}/memory`
- `GET /api/archive/library/{archive_id}/memory/timeline`
- `POST /api/archive/library/{archive_id}/memory/{memory_id}/adopt`
- `POST /api/archive/library/{archive_id}/memory/{memory_id}/reject`
- `POST /api/archive/library/reindex`

目标接口：

| 优先级 | 当前接口 | 目标接口 | 类型 | 说明 |
|---|---|---|---|---|
| P0 | `GET /api/archive/library` | `GET /api/v2/archives` | Query | 档案列表 |
| P0 | `GET /api/archive/library/{archive_id}` | `GET /api/v2/archives/{archive_id}` | Query | 档案详情 |
| P0 | `GET /api/archive/library/{archive_id}/memory` | `GET /api/v2/archives/{archive_id}/memories` | Query | 记忆列表 |
| P0 | `GET /api/archive/library/{archive_id}/memory/timeline` | `GET /api/v2/archives/{archive_id}/memory-timeline` | Query | 记忆时间线 |
| P0 | `POST /api/archive/library/{archive_id}/memory/{memory_id}/adopt` | `POST /api/v2/archives/{archive_id}/memory-reviews` | Command | 审核决定 |
| P0 | `POST /api/archive/library/{archive_id}/memory/{memory_id}/reject` | `POST /api/v2/archives/{archive_id}/memory-reviews` | Command | 审核决定 |
| P1 | `POST /api/archive/library/reindex` | `POST /api/v2/archives/reindex-jobs` | Command | 后台重建索引 |

`memory-review` 命令体建议：

```json
{
  "memory_id": "mem_123",
  "decision": "adopt",
  "reason": "canon confirmed"
}
```

### 9.6 LLM Settings / Module Bindings

当前主要接口：

- `GET /api/llm/settings`
- `POST /api/llm/channels`
- `PATCH /api/llm/channels/{channel_key}`
- `DELETE /api/llm/channels/{channel_key}`
- `POST /api/llm/channels/{channel_key}/sync-models`
- `PUT /api/llm/module-bindings/{module_key}`
- `DELETE /api/llm/module-bindings/{module_key}`
- `GET /api/llm/activity`

目标接口：

| 优先级 | 当前接口 | 目标接口 | 类型 | 说明 |
|---|---|---|---|---|
| P0 | `GET /api/llm/settings` | `GET /api/v2/llm/settings` | Query | 全局快照 |
| P0 | `POST /api/llm/channels` | `POST /api/v2/llm/channels` | Command | 创建渠道 |
| P0 | `PATCH /api/llm/channels/{channel_key}` | `PATCH /api/v2/llm/channels/{channel_key}` | Command | 修改渠道 |
| P0 | `DELETE /api/llm/channels/{channel_key}` | `DELETE /api/v2/llm/channels/{channel_key}` | Command | 删除渠道 |
| P0 | `POST /api/llm/channels/{channel_key}/sync-models` | `POST /api/v2/llm/channels/{channel_key}/model-sync-jobs` | Command | 变成异步 operation |
| P0 | `PUT /api/llm/module-bindings/{module_key}` | `PUT /api/v2/llm/module-bindings/{module_key}` | Command | 模块绑定 |
| P0 | `DELETE /api/llm/module-bindings/{module_key}` | `DELETE /api/v2/llm/module-bindings/{module_key}` | Command | 模块解绑 |
| P1 | `GET /api/llm/activity` | `GET /api/v2/llm/activity` | Query | 运行态观测 |

---

## 10. 重构过渡方案：前端/客户端不停服

### 10.1 结论

必须采用一层 **Edge BFF / Compatibility Gateway**。这不是可选项。

原因很直接：

- 当前前端已经直接依赖旧 Flask 端点和旧响应包络。
- 如果新服务直接替换旧路径，前端会因为字段、状态码、SSE 事件格式变化而断掉。
- 这个项目有 SSE 工作流，不适合让前端同时理解两套流式协议。

因此建议：

- 统一入口仍然保持 `/api/*`
- 网关同时代理：
  - legacy Flask handlers
  - new canonical `/api/v2/*`
- BFF 负责协议适配、DTO 映射、灰度切换、追踪打点

在单机 Docker 部署下，BFF 与新后端服务可以共同运行于同一 compose 中，不增加部署复杂度本质，只增加边界清晰度。

### 10.2 过渡期拓扑

```text
Frontend
  |
  v
Edge BFF / Compatibility Gateway
  |----------------------> Legacy Flask API (/api/project, /api/novel, /api/worldline, /api/archive, /api/llm)
  |
  |----------------------> New Application API (/api/v2/...)
  |
  |----------------------> Operation Stream Adapter (SSE)
```

### 10.3 BFF/Gateway 职责

- 维持旧路径可用
- 统一追加 `X-Trace-Id`
- 把新 v2 响应转换成旧前端可消费的数据结构
- 对 SSE 事件做 event name / payload shape 适配
- 做灰度路由和快速回滚
- 记录旧接口调用量，作为下线路径依据

### 10.4 兼容策略

#### 策略 A：旧接口兼容壳

保留旧路径，但 handler 不再直接实现业务，改为：

- 调用 v2 canonical API
- 把返回值转换成旧结构
- 对旧字段做兼容填充

示例：

- 旧：`POST /api/novel/draft/generate` 直接输出 SSE
- 过渡：兼容层内部先 `POST /api/v2/drafts` 创建 operation，再把 `/api/v2/operations/{id}/stream` 转写成旧前端接受的 `data: {"type":"..."}` 事件流

#### 策略 B：双路由

同一业务同时保留：

- `/api/...` 旧路由
- `/api/v2/...` 新路由

要求：

- 新功能只加到 `/api/v2/...`
- 旧路由只做适配，不再引入新领域逻辑

#### 策略 C：灰度切换

按以下维度逐步切：

- 按页面：先切 `writer`，再切 `worldline`
- 按接口组：先只切查询，再切命令
- 按工作区：内部测试 workspace 先切
- 按用户：管理员/测试账号先切

灰度控制建议：

- header：`X-Api-Profile: v2`
- 或 cookie / feature flag
- 或前端配置表按页面开关

### 10.5 推荐切换顺序

1. 先接入 BFF/Gateway，但所有流量仍走旧 Flask
2. 先把查询接口接到 v2，命令接口继续走旧实现
3. 再切 archive / llm 这类状态清晰的资源接口
4. 再切 chapter-context
5. 再切 worldline prepare / session query
6. 最后切 draft generate/revise 和 worldline auto-evolve 这两类流式命令

原因：

- 查询最容易做等价验证
- LLM 流式接口最脆弱，必须最后迁

### 10.6 SSE 过渡细则

过渡期 SSE 处理必须统一经过网关，不能让前端直接连两个后端流。

网关职责：

- 将 v2 `operation.*` 事件转换为旧前端可用事件：
  - `operation.started` -> `start`
  - `progress` -> `progress`
  - `artifact.ready` -> `partial`
  - `operation.completed` -> `done`
  - `operation.failed` -> `error`
- 补齐旧字段名，例如当前前端依赖 `type`
- 保持 `data:` 分块格式不变

限制：

- 旧前端只消费兼容事件
- 新前端只消费 canonical v2 事件
- 不做“一条流里混两套语义”

### 10.7 前端联调策略

#### 阶段一：兼容联调

- 现有 `frontend/src/api/*.js` 不大改
- 只把 base URL 指到 BFF
- 通过网关兼容旧结构

#### 阶段二：双客户端并存

- 保留 `legacyApiClient`
- 新增 `v2ApiClient`
- 页面按 feature flag 切换

#### 阶段三：页面级完全迁移

- `writer` 页面改用 `v2ApiClient`
- `worldline` 页面改用 `v2ApiClient`
- 兼容 client 仅为未迁移页面保留

#### 阶段四：移除旧前端调用

- `frontend/src/api/*.js` 中旧接口全部标记 deprecated
- 删除旧 DTO 拼装逻辑

### 10.8 数据一致性与双写

本方案不推荐让前端双写，也不推荐同一个命令同时打到新旧两个后端。

允许的双轨方式只有：

- 查询双读比对
- 命令单写

原因：

- worldline、draft、memory review 都是高语义命令
- 双写极易制造状态分叉

正确做法：

- 命令只打一处
- 兼容层做协议转换
- 通过回放测试和灰度验证行为一致性

---

## 11. 旧接口兼容映射建议

以下旧接口建议最早进入兼容层，理由是它们已经被前端直接消费且位于核心链路上：

| 旧接口 | 新接口 | 兼容策略 |
|---|---|---|
| `POST /api/project/seed/extract` | `POST /api/v2/workspaces/{workspace_id}/ingests` | 兼容层处理 multipart，转成 ingest command |
| `GET /api/project/task/{task_id}` | `GET /api/v2/operations/{operation_id}` | task_id 映射 operation_id |
| `GET /api/novel/chapter-context/options` | `GET /api/v2/workspaces/{workspace_id}/chapter-context-options` | query 映射 |
| `POST /api/novel/chapter-context` | `POST /api/v2/workspaces/{workspace_id}/chapter-contexts` | payload 转换 |
| `POST /api/worldline/session/prepare` | `POST /api/v2/worldlines/preparations` | command 映射 |
| `POST /api/worldline/session/create` | `POST /api/v2/worldlines/sessions` | command 映射 |
| `POST /api/worldline/session/{session_id}/step` | `POST /api/v2/worldlines/sessions/{session_id}/steps` | command 映射 |
| `GET /api/worldline/session/{session_id}/events/candidates` | `GET /api/v2/worldlines/sessions/{session_id}/events?status=candidate` | query 映射 |
| `POST /api/novel/draft/generate` | `POST /api/v2/drafts` + `GET /api/v2/operations/{id}/stream` | SSE 适配 |
| `POST /api/novel/draft/revise` | `POST /api/v2/drafts/{draft_id}/revisions` + `GET /api/v2/operations/{id}/stream` | SSE 适配 |
| `POST /api/novel/draft/finalize` | `POST /api/v2/drafts/{draft_id}/finalizations` | command 映射 |
| `GET /api/archive/library` | `GET /api/v2/archives` | list 适配 |
| `GET /api/archive/library/{archive_id}/memory` | `GET /api/v2/archives/{archive_id}/memories` | list 适配 |
| `POST /api/archive/library/{archive_id}/memory/{memory_id}/adopt` | `POST /api/v2/archives/{archive_id}/memory-reviews` | command 适配 |
| `GET /api/llm/settings` | `GET /api/v2/llm/settings` | snapshot 适配 |
| `PUT /api/llm/module-bindings/{module_key}` | `PUT /api/v2/llm/module-bindings/{module_key}` | direct pass-through |

---

## 12. 联调完成判定标准

满足以下条件才能认为 API 重构联调合格：

- 旧前端在不改页面行为的前提下，经 BFF 仍能完成：
  - 上传与导入
  - chapter context 构建
  - worldline prepare / create / step / candidate events
  - draft generate / revise / finalize
  - archive memory review
  - llm settings / bindings
- 所有关键接口都能回传统一 `trace_id`
- SSE 在网络抖动下能正确结束并产出最终事件
- 旧接口和新接口有明确迁移状态标识
- 前后端联调不再依赖人工对字段含义的口头同步，而是以 schema 为准

---

## 13. 最终结论

这个项目的 API 重构不应该是“把 Flask 路径换个名字”，而是要做三件事：

1. 用 `/api/v2 + operation + SSE` 建立统一协议层。
2. 用 BFF/Compatibility Gateway 把旧前端保护起来，避免停服。
3. 把现有 `project / novel / worldline / archive / llm` 的散乱接口，收口成稳定资源与稳定事件模型。

如果不先做这层接口收口，后面的 durable workflow、CQRS projection、前端 typed client 都会继续建立在漂移中的边界上，最后只会得到一套更复杂但同样不稳定的系统。
