# SaaS Refactor Development Plan

更新时间：`2026-07-13`

## 目的

本文件是 `docs/refactor-saas/` 的开发总纲，只定义范围、阶段顺序和最终完成条件。当前进度、当前关键路径和验证新鲜度以 `24-current-development-progress.md` 为唯一入口；不得根据本文件从 Phase 0 重新开始已完成工作。

本计划采用 **Writer-first Pi Agent vertical slice**：

1. 先把用户可见的写作台和后端 Pi Agent 打通。
2. 再把资产库、故事图谱、worldline、角色控制等模块分批接入写作台工具。
3. 最后完成多租户 SaaS 底座、迁移、运维和旧架构清理。

这不是放弃 SaaS 重构，而是改变实施顺序：先让核心创作闭环可运行，再把底座和周边模块稳稳接上。

## /goal 执行入口

建议使用下面的目标描述启动完整开发：

```text
按照 docs/refactor-saas/DEVELOPMENT_PLAN.md 的范围和完成定义继续 MiroFish-Novel SaaS 重构。开始前必须读取 docs/refactor-saas/24-current-development-progress.md 和 tasks/refactor-saas-parallel-board.md，以当前 worktree、schema 和本轮测试为最终事实，从当前最高优先级未完成 next gate 继续，不得重做已完成 Phase 或使用历史 handoff/日志/固定 prompt 判断进度。不能新增 mock 成功、静默 fallback、伪数据路径或旧式环境变量 LLM fallback。
```

执行时必须遵守：

- 先运行 `git status --short`，当前仓库可能已有大量未提交改动。
- 不覆盖用户未提交改动。
- 每个阶段都要有可运行验收。
- LLM 调用必须走 LLM Facility 模块绑定。
- Agent 只能产生 candidate/draft，采用为 manuscript/canon 必须是用户动作或明确策略。
- 所有新 SaaS 数据路径必须具备 tenant/project/run 上下文。

## 文档地图

| 文档 | 职责 |
|---|---|
| `README.md` | 文档集入口和总体决策摘要 |
| `DEVELOPMENT_PLAN.md` | 开发总纲、阶段顺序、详细文档映射 |
| `00-product-vision-and-scope.md` | 产品范围、用户角色、成功标准 |
| `01-target-architecture.md` | 目标架构和服务边界 |
| `02-tech-stack.md` | 技术栈和选型理由 |
| `03-multi-tenant-saas.md` | 多租户、权限、隔离、配额 |
| `04-design-system-and-ui.md` | UI 信息架构和工作台设计规则 |
| `05-overview-dashboard.md` | 项目总览和 workflow 状态入口 |
| `06-seed-pipeline.md` | 上传、解析、seed pipeline 和结构化 canon |
| `07-story-graph.md` | 故事图谱、构建、浏览、证据、Compose |
| `08-asset-library.md` | 资产库、入库 Agent、搜索和档案记忆 |
| `09-worldline.md` | 单世界推演、候选事件和保存路径 |
| `10-character-console.md` | 第一人称角色互动和转章节草稿 |
| `11-writer-workbench.md` | 写作台、章节、场景、draft、review、manuscript |
| `12-llm-facility.md` | LLM 渠道、模型、模块绑定、用量和隐私 |
| `13-agent-runtime.md` | Agent Runtime 通用约束、trace、tool calling |
| `14-data-model.md` | Postgres 表、RLS、向量、旧表映射 |
| `15-api-contracts.md` | 公网 API、错误格式、SSE、兼容路线 |
| `16-deployment-and-ops.md` | 部署、监控、备份、安全和成本控制 |
| `17-migration-roadmap.md` | 目标迁移顺序和验收摘要，不记录当前进度 |
| `18-legacy-coverage-matrix.md` | 旧功能覆盖矩阵和状态推进规则 |
| `19-parallel-development-orchestration.md` | 不含固定任务的多 agent 并行规则 |
| `21-pi-writer-agent-runtime.md` | Pi Writer Agent 详细设计和阶段接入方案 |
| `24-current-development-progress.md` | 当前总进度、完成定义审计、验证新鲜度、关键风险和下一步队列 |
| `28-zero-start-writer-and-manuscript-asset-distillation.md` | 空项目从零创作、正文资产蒸馏和候选审阅的后续产品扩展方案 |

`28-zero-start-writer-and-manuscript-asset-distillation.md` 是已批准的后续产品设计，不属于当前 MAIN-100 / Phase 0-8 完成定义。只有活动任务板正式启用对应目标后，才能把其中的 planned contract 计入当前进度；仅完成文档设计不得改写 `24-current-development-progress.md` 的实现状态。

## 总体开发顺序

```text
Phase 0  文档、契约和基线冻结
Phase 1  Writer-first Pi Agent 最小闭环
Phase 2  写作台工具接入资产、图谱、worldline
Phase 3  SaaS 基座承接 Writer vertical slice
Phase 4  LLM Facility、trace、usage、权限硬化
Phase 5  Seed / Assets / Graph 结构化迁移
Phase 6  Worldline / Character Console 创作链闭环
Phase 7  Legacy import、覆盖矩阵验证和旧架构清理
Phase 8  Ops / Billing / Security / Production hardening
```

每个 phase 的产出必须能独立运行或被清晰标记为 blocked。不要把未完成能力包装成完成。

## Phase 0：文档、契约和基线冻结

目标：

- 确认当前未提交改动处理策略。
- 确认 Writer-first Pi Agent 是优先实现顺序。
- 冻结第一阶段 API、event、draft、tool、LLM module 契约。
- 让 `/goal` 后续执行有唯一入口。

详细文档和子章节：

| 步骤 | 必读文档 | 子章节 |
|---|---|---|
| 0.1 确认产品范围 | `00-product-vision-and-scope.md` | 核心主链、旧功能覆盖范围、新增 SaaS 范围、非目标 |
| 0.2 确认目标架构 | `01-target-architecture.md` | 服务边界、关键请求链路、数据访问原则、兼容策略 |
| 0.3 确认 Pi Writer 路线 | `21-pi-writer-agent-runtime.md` | 模块定位、为什么使用 Pi、阶段范围、边界 |
| 0.4 冻结旧功能覆盖 | `18-legacy-coverage-matrix.md` | 页面覆盖、API Group 覆盖、Writer 覆盖、覆盖验收规则 |
| 0.5 冻结并行规则 | `19-parallel-development-orchestration.md` | 并行开发原则、Branch / Worktree 策略、冲突控制 |

产出：

- `tasks/refactor-saas-parallel-board.md` 状态与本总纲一致。
- `17-migration-roadmap.md` 与本总纲一致。
- 第一阶段不再讨论“从零自研 writer agent loop”。

验收：

- `rg -n "Pi Writer|Writer-first|DEVELOPMENT_PLAN" docs/refactor-saas` 能找到总纲和详细文档引用。
- 没有文档仍把“先完整 SaaS 基座再 Writer”写成唯一首选路径。

## Phase 1：Writer-first Pi Agent 最小闭环

目标：

让用户在写作台触发一次真实 writer run，由后端 Pi Agent 执行，前端看到流式输出、工具调用和最终 draft，并能采用到 manuscript 或 draft revision。

第一阶段不追求完整 SaaS，不迁移所有模块。它只证明：

```text
Writer UI -> writer run API -> Pi Writer Runtime -> LLM Facility -> writer tools -> stream events -> draft persistence
```

详细文档和子章节：

| 步骤 | 必读文档 | 子章节 |
|---|---|---|
| 1.1 写作台交互入口 | `11-writer-workbench.md` | 页面布局、Draft Mode、Continue Mode、WriterRunWorkflow、API、验收清单 |
| 1.2 Pi Runtime 设计 | `21-pi-writer-agent-runtime.md` | Runtime 拓扑、Pi SDK 使用方式、Worker 边界、事件映射 |
| 1.3 writer run API | `15-api-contracts.md` | 错误格式、Writer、Workflows、Compatibility |
| 1.4 LLM 模块绑定 | `12-llm-facility.md` | 配置层级、模块列表、并发控制、Trace 与隐私 |
| 1.5 Agent trace | `13-agent-runtime.md` | Context、Trace 模型、Tool Calling、Streaming |
| 1.6 draft / manuscript 表 | `14-data-model.md` | Writer Tables、Workflow / Trace Tables、LLM Tables |
| 1.7 UI 设计约束 | `04-design-system-and-ui.md` | 写作台、Workflow Progress Surface、Agent Trace Drawer、交互原则 |

最小实现范围：

- `writer_run` 创建、查询、取消。
- Pi Writer Worker 可启动，使用 `@earendil-works/pi-agent-core`。
- LLM Facility adapter 从模块绑定解析 `writer_composer` 或 `writer_orchestrator`。
- 工具最小集：
  - `query_project_context`
  - `query_chapter_scene`
  - `query_assets`
  - `query_manuscript_context`
  - `save_draft_revision`
- SSE 事件最小集：
  - `writer.run.started`
  - `writer.token`
  - `writer.tool.started`
  - `writer.tool.completed`
  - `writer.draft.saved`
  - `writer.run.failed`
  - `writer.run.completed`
- 前端写作台显示 stream、工具 trace、错误状态和最终 draft。

验收：

- LLM 未绑定时 writer run 显式失败，并提示去 LLM Facility。
- 绑定可用模型后，写作台能生成真实 draft。
- 页面刷新后可重新加载 run 状态和已有 token/draft。
- 工具调用都带 `tenant_id/project_id/run_id`。
- 不使用 mock 正文、假成功或环境变量 fallback。

## Phase 2：写作台工具接入资产、图谱、worldline

目标：

把旧系统中最能提升写作质量的上下文分批接入 Pi Writer tools，而不是等待全部模块重构完成。

详细文档和子章节：

| 步骤 | 必读文档 | 子章节 |
|---|---|---|
| 2.1 资产库检索工具 | `08-asset-library.md` | 资产类型、标准资产格式、搜索、API、旧功能映射 |
| 2.2 图谱邻居工具 | `07-story-graph.md` | 构建输入、Inspector、羁绊/支线生成、API |
| 2.3 worldline path 引用 | `09-worldline.md` | Saved Path、Writer 引用、Event Adoption、API |
| 2.4 writer tool system | `11-writer-workbench.md` | Tool System、Right Rail、One-click Actions |
| 2.5 tool 权限和 trace | `13-agent-runtime.md` | Tool Calling、Human-in-the-loop、Trace 模型 |

接入顺序：

1. `query_assets`
2. `query_world_rules`
3. `query_character_profile`
4. `query_graph_neighbors`
5. `query_worldline_paths`
6. `propose_scene_outline`
7. `propose_rewrite_span`

验收：

- Writer 可以显式选择资产、图谱节点或 worldline saved path 作为引用。
- simulation 内容不会自动变 canon。
- proposal tools 默认只产生 candidate/draft。
- 右侧工具结果能显示证据、来源和可采用动作。

## Phase 3：SaaS 基座承接 Writer vertical slice

目标：

把 Phase 1/2 的 Writer-to-Pi 能力承接到目标 SaaS 架构中，而不是长期停留在兼容桥上。

详细文档和子章节：

| 步骤 | 必读文档 | 子章节 |
|---|---|---|
| 3.1 Infra skeleton | `16-deployment-and-ops.md` | Local Dev、服务、Object Storage、Observability |
| 3.2 App / API / worker 边界 | `01-target-architecture.md` | 服务边界、关键请求链路、实时通信、模块结构建议 |
| 3.3 技术栈锁定 | `02-tech-stack.md` | 推荐技术栈、为什么 Go + Python Hybrid、工作流层、Auth 选型 |
| 3.4 多租户底座 | `03-multi-tenant-saas.md` | 核心实体、权限模型、Tenant Context、数据隔离、并发模型 |
| 3.5 数据模型 | `14-data-model.md` | Core SaaS Tables、Writer Tables、Workflow / Trace Tables、RLS 测试要求 |
| 3.6 API 契约 | `15-api-contracts.md` | SaaS / Auth、Projects、Workflows、Writer、LLM |

产出：

- `apps/web`
- `apps/api`
- `apps/pi-agent-runtime` 或 `apps/agent-runtime-node`
- `apps/agent-runtime` 继续保留 Python worker
- `packages/shared-contracts`
- `infra/docker-compose`

验收：

- 登录/租户/项目最小链路可用。
- Go API 能启动 writer workflow。
- Pi Worker 能消费任务并写 workflow events。
- Python worker 仍可作为 seed/graph/worldline 的后续承接点。

## Phase 4：LLM Facility、trace、usage、权限硬化

目标：

把 Phase 1 的可运行链路提升为可审计、可计费、可恢复、可并发控制的生产级链路。

详细文档和子章节：

| 步骤 | 必读文档 | 子章节 |
|---|---|---|
| 4.1 LLM Facility | `12-llm-facility.md` | 数据模型、Module Binding Matrix、用量与配额、并发控制 |
| 4.2 Agent trace | `13-agent-runtime.md` | Context、LLM Router、Trace 模型、Schema Validation |
| 4.3 多租户权限 | `03-multi-tenant-saas.md` | 权限模型、RLS 规则、审计、多租户测试 |
| 4.4 部署与观测 | `16-deployment-and-ops.md` | Metrics、Logs、Tracing、Cost Control |
| 4.5 API 错误 | `15-api-contracts.md` | 错误格式、Workflows、LLM |

验收：

- 完整 prompt/response trace 有权限门控。
- `llm_activity` 和 `usage_events` 能按 tenant/project/run 查询。
- writer stream 断线后可恢复。
- channel/model/module 并发限制生效。
- API Key 不明文返回、不写日志。

## Phase 5：Seed / Assets / Graph 结构化迁移

目标：

将旧系统的数据生产和知识层逐步迁入 SaaS 主数据模型，为 Writer Pi tools 提供稳定上下文。

详细文档和子章节：

| 步骤 | 必读文档 | 子章节 |
|---|---|---|
| 5.1 Seed Pipeline | `06-seed-pipeline.md` | 目标流程、Workflow 设计、关键数据产物、断点续传、错误处理 |
| 5.2 Asset Library | `08-asset-library.md` | 生命周期、Asset Ingestion Agent、搜索、Archive Entity |
| 5.3 Story Graph | `07-story-graph.md` | 工作模式、图谱数据模型、Graph Build Workflow、大图处理 |
| 5.4 Data Model | `14-data-model.md` | Seed / Canon Tables、Asset Tables、Story Graph Tables、Search / Vector |
| 5.5 Coverage | `18-legacy-coverage-matrix.md` | Seed Pipeline 覆盖、Asset / Archive 覆盖、Story Graph 覆盖 |

验收：

- 上传 TXT/MD/PDF 可进入 seed workflow。
- seed 结果写入结构化 canon 表。
- 资产库能看到 seed 角色、规则、关系、线索。
- 图谱从结构化表构建，不依赖 legacy JSON runtime fallback。
- Writer tools 从新表读取上下文。

## Phase 6：Worldline / Character Console 创作链闭环

目标：

把世界线实验和角色互动接入写作链，形成：

```text
assets / graph -> worldline -> character console -> writer -> manuscript
```

详细文档和子章节：

| 步骤 | 必读文档 | 子章节 |
|---|---|---|
| 6.1 Worldline | `09-worldline.md` | 核心概念、工作流、Writer 引用、旧功能映射 |
| 6.2 Character Console | `10-character-console.md` | 核心流程、角色控制模式、Interaction Record、转章节草稿 |
| 6.3 Writer 引用 | `11-writer-workbench.md` | Draft Mode、Continue Mode、Tool System、API |
| 6.4 Agent Runtime | `13-agent-runtime.md` | Streaming、Human-in-the-loop、旧模块映射 |
| 6.5 Data Model | `14-data-model.md` | Worldline Tables、Character Console Tables、Writer Tables |

验收：

- Worldline saved path 可被 Writer 明确引用。
- Character interaction 可转成 draft scene。
- simulation/candidate/canon 边界清楚。
- 不恢复旧多分支 worldline 主模型。
- viewer 只能查看，不能采用事件或正文。

## Phase 7：Legacy import、覆盖矩阵验证和旧架构清理

目标：

证明旧功能没有丢失，并逐步移除旧 FastAPI public routes、legacy artifacts runtime fallback 和旧本地文件真相源。

详细文档和子章节：

| 步骤 | 必读文档 | 子章节 |
|---|---|---|
| 7.1 迁移路线 | `17-migration-roadmap.md` | Legacy Cleanup、迁移原则、验收清单 |
| 7.2 覆盖矩阵 | `18-legacy-coverage-matrix.md` | 全文所有覆盖表、覆盖验收规则 |
| 7.3 数据模型映射 | `14-data-model.md` | 旧表映射摘要、RLS 测试要求 |
| 7.4 API 兼容 | `15-api-contracts.md` | Compatibility |
| 7.5 数据真相源 | `docs/database/database-source-of-truth-matrix.md` | 与当前仓库数据迁移状态保持一致 |

验收：

- 每个旧页面状态从带 owner/wave 的 `planned` 推进到 `implemented` 或 `verified`。
- 每个旧 endpoint group 有新 API 或明确替代。
- 旧 SQLite/project artifacts 可生成 import report。
- 未完成导入不会被标记为成功。

## Phase 8：Ops / Billing / Security / Production hardening

目标：

将系统从可用变成可公网部署、可计费、可恢复、可审计。

详细文档和子章节：

| 步骤 | 必读文档 | 子章节 |
|---|---|---|
| 8.1 Deployment | `16-deployment-and-ops.md` | 环境、服务、Secrets、Backup |
| 8.2 Security | `16-deployment-and-ops.md` | Security、Rate Limit、Incident Playbook |
| 8.3 Multi-tenant hardening | `03-multi-tenant-saas.md` | 配额与用量、审计、数据删除、多租户测试 |
| 8.4 LLM cost | `12-llm-facility.md` | 用量与配额、并发控制、Trace 与隐私 |
| 8.5 API production | `15-api-contracts.md` | API 原则、错误格式、SSE/WebSocket |

验收：

- docker compose 可一键启动本地依赖。
- staging/prod 数据隔离。
- Postgres 备份可恢复。
- logs 不含 API Key、完整小说原文或完整 prompt。
- LLM 成本能按 tenant/project/module 汇总。

## 已批准的后续产品扩展

空项目从零创作和正文反哺资产库的完整方案见 `28-zero-start-writer-and-manuscript-asset-distillation.md`。该扩展把导入小说降为可选 Seed 入口，并新增 `manuscript -> disabled asset candidate -> explicit review/adoption -> Writer retrieval` 闭环；它不恢复 Agent 自动写 canon，不改变本文件 Phase 0-8 的当前完成定义。

## 并行开发规则

允许并行，但必须以本总纲阶段为主线。

- Phase 0 已冻结；除非当前 contract 明确变化，不重做治理阶段。
- Phase 1 不建议拆太散，Writer UI/API/Pi worker/LLM adapter 必须高频联调。
- Phase 2 可以按工具并行，但 shared tool result schema 必须先冻结。
- Phase 3 可以分 Infra、DB/RLS、Go API、Web Shell、Pi Worker、Python Worker 多窗口并行。
- Phase 5 可以 Seed、Assets、Graph 并行，但必须共享 canon table 契约。
- Phase 6 可以 Worldline 和 Writer 引用并行，但 Character Console 依赖 worldline session。

冲突控制详见 `19-parallel-development-orchestration.md`；具体任务由主控根据当前进度与活动任务板现场生成，不使用固定任务 prompt。

## 完成定义

完整开发完成必须满足：

- 用户可登录/选择租户/进入项目。
- 用户可在写作台运行 Pi Writer Agent，看到 stream、tool calls、trace 和 draft。
- 用户可上传小说并完成 seed。
- 资产库、图谱、worldline、角色控制都能向 Writer 提供上下文。
- draft 可采用到 manuscript，并可审校和导出。
- LLM Facility 完整控制所有模块绑定和用量。
- Postgres RLS 测试证明跨租户不可读。
- `18-legacy-coverage-matrix.md` 中旧功能达到 `verified` 或有明确非恢复说明。
- 旧多分支 worldline 主模型、mock 成功、静默 fallback、伪数据路径均未恢复。
