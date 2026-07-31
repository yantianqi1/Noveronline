# MiroFish-Novel SaaS Refactor Documentation

更新时间：`2026-07-10`

## 目标

本目录是 `MiroFish-Novel` 面向公网 SaaS、多租户、多用户并发和小说 Agent 工作流的完整重构文档集。目标不是在当前本地单机架构上打补丁，而是用更适合长期产品化的架构重建：

`Next.js SaaS App -> Go Control Plane -> Temporal Workflows -> Pi Writer Runtime + Python Agent Workers -> Postgres / pgvector / Redis / S3`

文档必须覆盖当前旧系统全部能力，并给后续 AI coding agent 一个足够明确的还原依据：拿到每个模块文档后，可以知道页面如何设计、API 如何切分、数据怎么落库、Agent 怎么运行、旧功能如何迁移和验收。

## SaaS 开发真相源

1. `DEVELOPMENT_PLAN.md` 只定义范围、阶段顺序和最终完成条件。
2. `24-current-development-progress.md` 是唯一当前进度、关键路径、风险和验证新鲜度入口。
3. `tasks/refactor-saas-parallel-board.md` 只维护活动任务、依赖和 next gate。
4. 当前 worktree、schema 和本轮实际测试输出高于任何文档。

Git history 负责保存历史。当前工作树不再保留中途 handoff、追加式 live log、模型专用开发计划或内嵌固定任务的 prompt preset。

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
- `17-migration-roadmap.md`：目标迁移顺序、原则和最终验收清单；不是当前进度入口。
- `18-legacy-coverage-matrix.md`：旧页面、路由、表、Agent 模块和功能的覆盖验收矩阵。
- `19-parallel-development-orchestration.md`：不含固定任务的多 agent 并行协作规则。
- `21-pi-writer-agent-runtime.md`：Writer-first Pi Agent Runtime、写作台最小闭环和分批接入方案；亦登记 Pi 已接入的候选式故事分析（`PiAnalysisRunWorkflow`）与 Worldline Cast Planner 两个独立域。
- `24-current-development-progress.md`：截至当前 worktree 的 SaaS 重构总进度、完成定义审计、验证新鲜度、关键风险和下一步队列；当前接手状态以此文档为第二入口。
- `29-seed-sse-live-progress-experience.md`：小说上传、真实 SSE 实时分析进度、动效、断线恢复和验收标准的设计提案；不代表当前实现已完成。
- `31-overview-progress-visual-motion-design.md`：Overview 分析进度画布的视觉与动效升级设计（阶段播报、数字缓动、阶段轨道、终态编排）；P1 运行在现有轮询上，P2 对接文档 29 的 SSE。
- `34-author-friendly-experience-plan.md`：面向产品负责人的作者友好优化说明，只描述作者可见变化、实施顺序和人工验收问题。
- `35-author-friendly-implementation-plan.md`：与文档 34 逐项对应的 Agent 实施蓝图，包含安全边界、代码入口、测试 Gate 和最终完成定义。
- `37-frontend-module-inventory.md`：前端必须具备的模块与产品面清单，供 Agent 确认范围；不规定实现顺序或编码步骤。
- `42-seed-batched-enrichment.md`：Seed 富化阶段（agent_profiles / archive_candidates）从单发全量改为确定性分批喂料 + 完整性对账补漏 + 就绪度瓷砖流式的实施设计；状态 `proposal`，落地重开 P5-005-B 验证。
- `44-full-module-bug-audit.md`：`apps/api` / `apps/web` / `apps/agent-runtime` / `apps/pi-agent-runtime` / `infra` 全模块只读缺陷审查；含 6 项已逐条复核的高危项（采纳授权缺失、采纳接口越权、goal-start 双跑、写作台丢未存编辑、导出漏软删过滤、资产写入漏租户上下文）、按模块分级的其余发现、1 项已否决的误报存档和分梯队处置顺序。
- `46-prelaunch-bug-audit-round2.md`：上线前第二轮只读缺陷审查（2026-07-31，6 路并行专项 + 主审复核）；含 3 项已复核 BLOCKER 鉴权缺口、8 项已复核 MAJOR 与按模块分级的其余发现和四梯队处置顺序。

## 总体决策

### 首选方案

采用 **Go Control Plane + Pi Writer Runtime + Python Agent Runtime** 的混合架构，并按 **Writer-first Pi Agent vertical slice** 的顺序开发。

- Go 负责公网 SaaS 控制面：用户、租户、权限、项目、资产、图谱查询、任务提交、实时推送、计费、用量、审计。
- Pi Writer Runtime 负责第一阶段写作台 Agent loop：writer run、tool calling、流式正文、draft 保存和采用。Pi 同时承载两条已接入的独立候选/agent 域：候选式故事分析（`PiAnalysisRunWorkflow`，候选→Go 导入资产）与 Worldline Cast Planner 选角；二者均不写 canon，不改变 Seed/Graph/Asset ingestion 归 Python 的边界。
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
2. `24-current-development-progress.md`
3. `tasks/refactor-saas-parallel-board.md`
4. 当前任务对应的领域文档
5. `18-legacy-coverage-matrix.md`（只作需求覆盖清单）

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
- `24-current-development-progress.md`
- `tasks/refactor-saas-parallel-board.md`

主控必须按当前任务现场生成 Objective、read/write scope、invariants 和 verification；不使用固定窗口 prompt。
