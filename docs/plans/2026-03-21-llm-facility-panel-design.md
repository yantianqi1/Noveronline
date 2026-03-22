# LLM Facility Panel Design

**Goal:** 为项目增加一个全局设施面板，使用 SQLite 持久化 OpenAI 兼容渠道、模型缓存与“业务模块 -> 渠道 + 模型”绑定关系，并让后端所有 LLM 调用统一走这套可热更新配置。

**Recommended Approach:** 采用“SQLite 配置中心 + 模型缓存 + 统一 LLM 路由器”。不再从环境变量读取 `api_key / base_url / model`，而是让前端设施面板直接管理渠道、同步上游模型列表，再把每个业务模块绑定到一个明确的“渠道 + 模型”组合。业务服务不再自己决定默认模型，只通过路由器解析绑定结果。

## Why This Approach

- 当前仓库的 LLM 配置仍是单组全局环境变量，无法支持模块级差异化模型。
- 需求已经明确要求废弃环境变量方案，并把配置直接存入数据库。
- 项目目前没有正式数据库层，SQLite 是最小改动、最符合当前单机开发形态的选择。
- 引入模型缓存后，设施面板展示不会受上游接口波动影响；只有手动同步模型时才访问上游。
- 统一路由器可以避免各业务服务继续散落地读取配置，后续扩展新模块也更稳定。

## Scope

本轮只实现最小闭环：

- SQLite 持久化 LLM 渠道、模型缓存、模块绑定
- 设施面板支持新增、编辑、启停、删除渠道
- 面板支持从 OpenAI 兼容上游同步模型列表
- 面板支持配置每个业务模块绑定到“渠道 + 模型”
- 后端已有 LLM 业务模块改为走统一路由器
- 前端新增全局设施面板页面与导航入口

本轮不做：

- 非 OpenAI 兼容协议适配
- 渠道密钥加密存储
- 运行中任务强制切换模型
- 模型能力探测、价格探测、上下文窗口探测
- 多用户权限控制

## Module Registry

模块绑定采用固定业务模块键，不直接暴露类名。首批模块为：

- `story_ontology`：种子本体生成
- `local_block_facts`：块内局部事实提取
- `contextual_block_analysis`：带前情快照的剧情块分析
- `narrative_archives`：角色 / 势力档案生成
- `parallel_world_config`：平行世界配置生成

这些模块由后端代码注册，前端只消费后端返回的模块清单。

## Data Design

使用 SQLite 三张核心表：

### `llm_channels`

- `channel_key`
- `name`
- `base_url`
- `api_key`
- `is_enabled`
- `created_at`
- `updated_at`
- `last_sync_at`
- `last_sync_status`
- `last_sync_error`

说明：

- `channel_key` 使用稳定字符串主键，供 API 与绑定表引用。
- `api_key` 持久化保存，但 API 返回时只返回掩码字段，不回传明文。

### `llm_models`

- `channel_key`
- `model_id`
- `owned_by`
- `fetched_at`
- `raw_payload`

说明：

- 每次同步指定渠道时，覆盖该渠道的模型缓存。
- `raw_payload` 保留上游返回的原始字段，便于后续扩展展示。

### `llm_module_bindings`

- `module_key`
- `channel_key`
- `model_id`
- `updated_at`

说明：

- 每个业务模块只能绑定一个“渠道 + 模型”组合。
- 删除渠道时，同时删除引用该渠道的绑定，让模块进入未配置状态。

## Backend Design

后端新增三层：

### 1. SQLite 存储层

- 负责建表、连接、CRUD
- 提供渠道、模型缓存、模块绑定的读写接口

### 2. 设施服务层

- 校验渠道参数
- 调用 OpenAI 兼容 `models.list` 接口同步模型
- 组装设施面板所需快照数据
- 处理模块绑定更新

### 3. 统一 LLM 路由层

- 业务服务只传 `module_key`
- 路由层解析出 `channel + model`
- 再构造 `LLMClient`

### Existing Service Changes

以下服务改为通过模块键解析客户端：

- `StoryOntologyGenerator`
- `LocalBlockFactExtractor`
- `ContextualBlockAnalyzer`
- `NarrativeEntityArchivist`
- `ParallelWorldConfigGenerator`

如果 `use_llm=True` 且模块未绑定渠道模型，直接抛出显式错误，不做静默回退。

## API Design

新增蓝图：`/api/llm`

接口：

- `GET /api/llm/settings`
  返回模块注册表、渠道列表、模型缓存与当前绑定快照
- `POST /api/llm/channels`
  创建渠道
- `PATCH /api/llm/channels/<channel_key>`
  编辑渠道
- `DELETE /api/llm/channels/<channel_key>`
  删除渠道及其缓存模型、相关绑定
- `POST /api/llm/channels/<channel_key>/sync-models`
  从上游同步模型列表
- `PUT /api/llm/module-bindings/<module_key>`
  更新指定业务模块绑定

## Frontend Design

新增“全局设施面板”页面，分为三块：

### 渠道管理

- 新建渠道
- 编辑名称、`base_url`、`api_key`
- 启用 / 停用
- 删除渠道

### 模型同步

- 针对单个渠道点击“同步模型”
- 展示该渠道缓存下来的模型列表
- 显示上次同步状态、时间、错误信息

### 模块绑定

- 按业务模块展示中文名和说明
- 每行两个选择器：渠道、模型
- 模型列表随渠道切换而更新
- 保存后立即生效于后续新调用

## Error Handling

- 渠道未配置时，模块 LLM 调用直接报错，提示去设施面板配置。
- 渠道被禁用时，相关模块调用直接报错。
- 绑定的模型不在缓存列表时仍允许保存失败暴露，不自动改绑。
- 同步模型失败时保留旧缓存，并把错误记录到渠道同步状态里。

## Testing

后端测试覆盖：

- 渠道 CRUD
- 模型同步写入缓存
- 模块绑定快照读取
- LLM 路由器按模块解析正确渠道模型
- 业务服务在未配置绑定时显式报错

前端验证：

- 新增设施面板路由可构建
- 渠道与绑定页面交互状态正常
- 整体 `vite build` 通过
