# MiroFish-Novel SaaS Refactor Documentation

更新时间：`2026-07-05`

## 目标

本目录是 `MiroFish-Novel` 面向公网 SaaS、多租户、多用户并发和小说 Agent 工作流的完整重构文档集。目标不是在当前本地单机架构上打补丁，而是用更适合长期产品化的架构重建：

`Next.js SaaS App -> Go Control Plane -> Temporal Workflows -> Pi Writer Runtime + Python Agent Workers -> Postgres / pgvector / Redis / S3`

文档必须覆盖当前旧系统全部能力，并给后续 AI coding agent 一个足够明确的还原依据：拿到每个模块文档后，可以知道页面如何设计、API 如何切分、数据怎么落库、Agent 怎么运行、旧功能如何迁移和验收。

## 文档清单

- `DEVELOPMENT_PLAN.md`：开发总纲、最优阶段顺序、每一步对应详细文档和子章节。
- `00-product-vision-and-scope.md`：产品定位、用户角色、旧功能覆盖边界和新 SaaS 成功标准。
- `01-target-architecture.md`：目标系统架构、服务边界、请求链路、长任务链路和多语言分工。
- `02-tech-stack.md`：推荐技术栈、为什么使用 Go + Python hybrid、关键库和不选项。
- `03-multi-tenant-saas.md`：用户、组织、租户、权限、数据隔离、并发和配额模型。
- `04-design-system-and-ui.md`：全局信息架构、视觉系统、布局规范和各工作台 UI 原则。
- `05-overview-dashboard.md`：总览页面、项目入口、上传分析、任务流和运营状态。
- `06-seed-pipeline.md`：小说上传、解析、分段、精读、聚合、本体和角色档案生成。
- `07-story-graph.md`：故事图谱构建、查询、布局、聚类、编辑、证据和前端重做方案。
- `08-asset-library.md`：统一资产库、资产入库 Agent、标准资产格式、检索和审阅。
- `09-worldline.md`：单世界 worldline、变量注入、推演、候选事件、保存路径和写作引用。
- `10-character-console.md`：作者第一人称降临角色、互动写作、角色记忆和章节转化。
- `11-writer-workbench.md`：写作台、章节/场景/正文/审校/去重/世界数据更新。
- `12-llm-facility.md`：LLM 渠道、模型、模块绑定、用量、审计和租户级配置。
- `13-agent-runtime.md`：Agent Runtime、工具调用、trace、工作流、重试、人工审阅。
- `14-data-model.md`：Postgres 主数据模型、RLS、向量检索、事件表和旧表映射。
- `15-api-contracts.md`：Go API surface、SSE/WebSocket、worker payload 和兼容路线。
- `16-deployment-and-ops.md`：部署拓扑、环境、监控、备份、安全、限流和运维。
- `17-migration-roadmap.md`：从当前仓库迁移到 SaaS 架构的阶段计划。
- `18-legacy-coverage-matrix.md`：旧页面、路由、表、Agent 模块和功能的覆盖验收矩阵。
- `19-parallel-development-orchestration.md`：多个 Codex 窗口/多终端/多智能体并行开发编排方案。
- `20-agent-window-identities-and-prompts.md`：每个开发窗口的身份卡和可复制启动提示词清单。
- `21-pi-writer-agent-runtime.md`：Writer-first Pi Agent Runtime、写作台最小闭环和分批接入方案。
- `22-midstream-handoff-summary.md`：当前重构中途总结、完成度估算、风险、下一步建议和新对话启动提示词。
- `23-a4-story-graph-runner-fix-handoff.md`：A4 Story Graph Runner blocking fixes 历史/外部 handoff note；不是 Wave 0 产出的完成证据，后续 agent 必须先核对实际 git diff/commit 和测试输出再视为 product-complete。
- `prompts/`：各窗口可直接复制到新 Codex 终端的启动提示词。

## 总体决策

### 首选方案

采用 **Go Control Plane + Pi Writer Runtime + Python Agent Runtime** 的混合架构，并按 **Writer-first Pi Agent vertical slice** 的顺序开发。

- Go 负责公网 SaaS 控制面：用户、租户、权限、项目、资产、图谱查询、任务提交、实时推送、计费、用量、审计。
- Pi Writer Runtime 负责第一阶段写作台 Agent loop：writer run、tool calling、流式正文、draft 保存和采用。
- Python 负责智能体和小说理解：seed pipeline、图谱构建、资产入库 Agent、worldline 推演、角色控制，以及暂不迁移到 Pi 的领域逻辑。
- Temporal 负责长任务：seed、graph、asset ingestion、worldline prepare/auto-evolution、writer run、reviewer run。
- Postgres 是主数据库，RLS 是租户隔离底线，pgvector 支撑长期语义检索。
- S3 / R2 / MinIO 存上传原文、解析产物、导出文件和大 trace 附件。

### 明确不采用

- 不采用本地单机优先的补丁式改造。
- 不从零自研 Writer Agent 的通用 agent loop；优先使用 `earendil-works/pi` 的 SDK 基座并包在 MiroFish 权限、trace、LLM Facility 和工具系统内。
- 不把 Python Agent 层全部重写成 Go。
- 不把所有 Agent 逻辑一次性迁到 Pi；Seed、Graph、Asset ingestion、Worldline 第一阶段继续保留 Python 领域逻辑。
- 不继续扩展旧多分支 worldline 模型；新系统仍以单世界 `current_world` 为主语义。
- 不新增假成功、静默 fallback、伪数据和吞错路径。
- 不把 API Key、用户小说原文、LLM trace 或私有数据库写入 git。

## 旧功能覆盖原则

旧系统主链必须全部覆盖：

`上传小说 -> seed pipeline -> ontology / graph -> archives / assets -> worldline -> character console -> writer agent -> manuscript`

旧页面必须全部覆盖：

- 总览
- 故事图谱
- 资产库
- 世界线
- 角色控制
- 写作台
- 帮助指南
- LLM 设施面板

旧后端域必须全部覆盖：

- project / novel / graph / archive / assets / unified-assets / worldline / writer-agent / llm
- `/api` 兼容功能语义
- `/api/v2` 已有重建接口语义
- 任务进度、trace、SSE、LLM 模块绑定和统一数据库

## 后续使用方式

实施前先读：

1. `DEVELOPMENT_PLAN.md`
2. `22-midstream-handoff-summary.md`
3. `21-pi-writer-agent-runtime.md`
4. `00-product-vision-and-scope.md`
5. `01-target-architecture.md`
6. `02-tech-stack.md`
7. `03-multi-tenant-saas.md`
8. `18-legacy-coverage-matrix.md`

第一阶段开发 Writer-first Pi Agent 最小闭环时，优先读：

- `DEVELOPMENT_PLAN.md`
- `21-pi-writer-agent-runtime.md`
- `11-writer-workbench.md`
- `12-llm-facility.md`
- `13-agent-runtime.md`
- `14-data-model.md`
- `15-api-contracts.md`

开发某个模块时再读对应模块文档。例如重做故事图谱，应同时读：

- `07-story-graph.md`
- `14-data-model.md`
- `15-api-contracts.md`
- `18-legacy-coverage-matrix.md`

如果要多窗口并行开发，先读：

- `19-parallel-development-orchestration.md`
- `20-agent-window-identities-and-prompts.md`
- `tasks/refactor-saas-parallel-board.md`

然后从 `prompts/` 复制对应窗口身份的启动提示词。
