# 项目 AI 交接档案

> 本档案是 `docs/project-audit/` 调查套件的主文档。目标是让从未看过本仓库的 AI 在只读本文件后即可理解项目全貌；需要细节时再查阅 02–11 号文档。
> 证据标记：【已确认】=有代码证据；【合理推断】=调用链推断；【待确认】=证据不足；【疑似废弃】=无入口；【未接通】=有定义无完整链路。
> 调查日期：2026-07-31。Branch：`rewrite/web-clean-slate`，commit `e995686`。工作区有 5 个未提交修改文件（pi-writer-activities 预览增强 + writer-rail/writer-run 前端对应 + 截图目录），内容已并入本档案描述。

## 1. 项目一句话描述

**MiroFish-Novel 是一个面向长篇小说创作的多智能体分析与写作 SaaS 平台**：上传小说 → 系统通读并抽取人物/关系/规则/时间线 → 建立故事图谱与档案资产库 → 在单世界世界线（worldline）上做剧情推演 → 由 Writer Agent 按作者指令检索设定、生成候选正文 → 作者显式采纳后才成为正式手稿；全程「AI 只提建议，作者做决定」。

## 2. 当前产品能力

- **上传与 Seed 流水线**：TXT/MD/PDF 上传（MinIO 存储）→ 分段精读（sequential_reader）→ 全局聚合 → ontology 生成 → 角色档案生成。Python Temporal worker 实现（`apps/agent-runtime/mirofish_agents/temporal/seed.py`）。
- **Pi Analysis（候选式故事分析，与 Seed 并行）**：Pi Agent 用 7 个工具读源分段、写分析工作区文件、提取候选（`analysis_candidates` 表），Go 侧可导入为 `source_kind='pi_analysis'` 资产。【已确认】`apps/api/internal/workflows/analysis_asset_import.go`
- **资产库**：统一 assets 表 + 版本 + 收藏 + 混合搜索（pgvector 语义 + 关键词 + 加权），spoiler gate（未到章节不剧透）。
- **Story Graph**：节点/边/聚类/证据，d3-force 交互画布，候选采纳制。
- **Worldline（单世界）**：goal → cast 选角（Pi Agent）→ director 推演步骤（Python）→ 候选事件 → 作者采纳为 canon 时间线 → 可保存为路径并附着到 Writer run 作为剧情时间线。
- **Writer 工作台（产品核心）**：主画布连续稿件 + 右侧常驻 Agent dock（thread + composer + 任务卡片）。每次请求 = 一个 run：检索规划 → 编排器工具循环（12 工具）→ 作曲器流式正文 →（可选）一致性检查 → 候选稿卡片 → 作者采纳入正文。
- **审校 / 计划 / 工具**：writer_reviewer（Python，无工具）、书籍计划、去重候选、禁用词、导出。
- **角色互动**：character console 与单个角色对话模拟，产出候选。
- **LLM Facility**：33 个模块统一绑定（渠道/模型/密钥加密/配额预留/并发锁/用量记账）。

## 3. 当前技术架构

```
浏览器(Next.js 15.5 :3999) → 同源BFF /api/* → Go Control Plane (:3888) → Temporal →
  ├─ Pi Agent Runtime (TS, writer-streaming / analysis-streaming / worldline-cast-streaming)
  ├─ Python Agent Runtime (seed-heavy / graph-heavy / asset-light / worldline-interactive / character-interactive / writer-reviewer / writer-planning / maintenance / legacy-import)
  └─ Postgres 16+pgvector (31 migrations) · Redis(限流) · MinIO(对象存储)
```

- 前端：`apps/web`（React 19 + Tailwind 4 + motion），工作台 7 区（overview/assets/characters/graph/worldline/writer/settings）。
- 控制面：`apps/api`（Go 1.24，约 12 万行，`internal/httpapi/server.go` 约 1 万行集中路由）。
- 事件通道：`workflow_events` 表（唯一公共事件流）；`agent_traces`（私有 trace）；SSE 后端已实现但前端用 900ms 轮询。
- 认证：会话 Cookie + CSRF + X-Tenant-Id + 数据库 RLS（`app_set_tenant_context`）三端（Go/Pi/Py）同构。
- 契约：`packages/shared-contracts` JSON Schema 冻结 Go→Pi 输入、Pi→Go 运行时事件、Go→Web 公共事件。

## 4. Pi Agent 在项目中的位置

- 依赖：`@earendil-works/pi-agent-core@0.80.3` + `@earendil-works/pi-ai@0.80.3`（`apps/pi-agent-runtime/package.json`）。**直接使用，无内部二次封装框架**（有三个业务封装工厂：`createPiWriterExecution`/`createPiAnalysisExecution`/`createPiWorldlineCastExecution`）。
- **没有** createAgentSession（0.80.3 用 `new Agent()`）；**没有** Extension/Skill/MCP/RPC/Subagent/steer/followUp/continue 使用（SDK 能力存在但项目未用）。
- 每次 LLM 阶段调用都新建 `Agent` 实例（`sessionId: run_id`），用完即弃；「会话」由 DB（writer_threads + workflow_events）承载，前端据此重建 UI。
- 模型调用：`streamFn = models.streamSimple`（openai-completions API），provider 由 LLM Facility 绑定（channel 表 base_url + 解密后的 apiKey），每轮带 `Idempotency-Key` 与 `X-MiroFish-*` 追踪头。
- 三个 Agent：
  - **Pi Writer**（`src/runtime/pi-writer-agent.ts`）：5 个独立阶段（planner 无工具 / orchestrator 12 工具 / composer 无工具 / reranker 无工具 / consistency 无工具），全部由活动 `runDualStagePiWriterActivity`（`src/activities/pi-writer-activities.ts`，2256 行）编排。
  - **Pi Analysis**（`pi-analysis-agent.ts`）：planner/worker 两模块，7 工具。
  - **Pi Worldline Cast**（`pi-worldline-cast-agent.ts`）：5 工具，产出选角提交。

## 5. 一次用户请求的完整数据流

以「写作台输入『续写第三章场景一』」为例（【已确认】全链路）：

1. 前端 `writer-composer.tsx` → `startWriterRun()`（`lib/api/writer-client.ts:414`）POST `/api/projects/{pid}/writer-runs`（BFF 代理，带 X-Tenant-Id/X-CSRF-Token/X-Request-Id）。
2. Go `server.go` handler：RBAC（PermissionWriterRun）→ 限流（12 次/300s）→ worldline 附件归属校验 → LLM 模块绑定解析（writer_orchestrator 必须 supports_tools；review_after_write 需 writer_reviewer 绑定）→ EnsureThread（writer_threads）→ `TemporalWriterStarter.StartWriterRun`。
3. Admission 事务（`writer_admission.go`）：插 `workflow_runs` + `writer_runs(queued)` + `workflow_events(workflow.queued)`；request_id 幂等重放。
4. Temporal `PiWriterRunWorkflow`（queue `writer-streaming`）→ 活动 `runPiWriterRunActivity` → 校验 payload（`worker-spec.ts`）→ 已完成 run 重放检查 → run.started 事件 → status=running。
5. 活动内 `executeLLMStage` × N：解析模块绑定 → 解密凭据 → 配额预留（llm_quota_reservations）→ 并发租约（resource_locks slot）→ 阶段执行 → 配额 finalize → 记录 llm_activity/usage_events。
6. 阶段序列：**planner**（JSON 检索计划）→ **always_on 常驻规则加载** → **worldline 时间线加载**（canon 事件按 step 排序）→ **orchestrator**（12 工具循环，≤24 次调用，beforeToolCall 权限门控，工具结果 12000 token 预算裁剪，工具事件写入 workflow_events + agent_traces）→ **composer**（流式 token → writer.token 事件）→ **consistency**（可选，违规只记录不阻塞）→ saveDraftRevision（幂等单条）→ writer.draft.saved → 线程消息 → run.completed。
7. 前端 `use-writer-run.ts` 每 900ms 轮询 events（100 条/页 + after_event_id 游标）→ `reduceWriterRun`（`lib/api/writer-run.ts`）→ 任务卡片（步骤/引用/候选流/终态）→ 作者点「采纳」→ adoptDraft → 正文块插入 `manuscript_blocks`。

## 6. AgentSession 创建与管理

| 问题 | 答案 |
|---|---|
| 在哪创建 | `new Agent({...})`，pi-writer-agent.ts（5 处）、pi-analysis-agent.ts、pi-worldline-cast-agent.ts；无单独 session 层 |
| 每用户/每项目/每请求 | **每请求**（每 run 每阶段新建）；无共享/复用 |
| 存活期 | 单次活动内；活动结束即销毁（无泄漏，无缓存） |
| 持久化 | 无 Agent 状态持久化；业务状态在 DB |
| 模型选择 | LLM Facility 绑定解析（project 级 > tenant 级 > platform 默认），模块键如 writer_orchestrator |
| System Prompt | 代码内函数（见 §8） |
| 工具来源 | 活动层 `tool_names` 数组 → 工厂函数构造 AgentTool |
| 会话 ID | `run_id`（透传 provider 做缓存感知） |

## 7. 模型与供应商配置

- 模型供应商：任意 OpenAI-compatible HTTP 端点，由 `llm_channels` 表配置（provider/base_url/encrypted_api_key/max_concurrency）；模型目录 `llm_models`（支持 tools/json 能力）；绑定 `llm_module_bindings` + 平台默认 `llm_platform_module_defaults`。
- 33 个模块（`apps/api/internal/llm/registry.go`）：story_ontology、sequential_reading、analysis_planner/worker、character_agent_profile、graph_bond_generator、asset_search_embedding、style_extractor、character_dialogue、worldline_cast_planner、worldline_director、worldline_agent_*、writer_retrieval_planner/rerank、writer_consistency、writer_orchestrator、writer_composer、writer_dedup_extractor、writer_book_planner、writer_asset_distiller、writer_reviewer 等。
- 切换：管理界面（settings 工作台）改绑定；代码不硬编码渠道。
- Thinking Level：run options `thinking_level`（off/minimal/low/medium/high/xhigh）透传 Agent；模型能力表（`src/llm/model-capabilities.ts`）做工具/JSON 支持推断。
- 成本：每 provider 调用走配额预留（token/成本策略），llm_activity + usage_events 记账。

## 8. System Prompt、上下文和 Skill

- **无 Skill 使用、无 AGENTS.md 注入、无 RAG 之外的长记忆、无摘要压缩**。【已确认】
- 全部 prompt 为 TS 代码内字符串 + JSON 用户消息（见 06 号文档）。
- 编排器上下文组装顺序：systemPrompt（常量）→ 用户消息 JSON{请求字段 + worldline_timeline(参考性) + always_on_canon(常驻规则) + retrieval_plan(检索计划)} → 工具循环结果（裁剪、脱敏、带引用）。
- 作曲器：systemPrompt（可被 settings.system_prompt 覆盖）→ JSON{instruction + writing_brief + constant_canon + worldline_timeline}。无历史。
- 上下文来源全部经过门控：lifecycle IN (seed/canon/material)、spoiler gate、worldline 仅 canon 事件、candidate 永不进写作上下文。【已确认】

## 9. 全部 Agent 工具总览（25 个，完整总表）

### Writer Orchestrator 工具（12 个启用 + 1 个保留）

| # | 工具名 | 参数 | 执行内容 | 写? | 风险 |
|---|---|---|---|---|---|
| W01 | query_project_context | 无 | 读 projects（title/genre/language/status） | 否 | 低 |
| W02 | query_chapter_scene | 无 | 读 run 目标章节/场景+相邻场景摘要(≤12,280字符) | 否 | 低 |
| W03 | query_assets | 无 | 读作者勾选资产（无勾选→空+指引 search_assets） | 否 | 低 |
| W04 | search_assets | query*;asset_types;top_k(10,1-25);mode(keyword/vector/hybrid);channel(hybrid/keyed);expand_relations | 混合检索（pgvector+关键词+加权+spoiler gate）；keyed=人名/别名确定性召回；embedding 失败显式降级 | 否 | 低-中 |
| W05 | search_manuscript | query*;top_k(5,1-12) | 前文向量召回（block_order<游标，绝不召回未来） | 否 | 低-中 |
| W06 | fuse_recall | channels*;top_k(≤25);rerank;query | RRF 融合 + 可选 LLM 重排（走配额）；always_on 通道自动注入 | 否 | 低 |
| W07 | query_world_rules | 无 | world_rule_evidence + canon 规则资产（≤50） | 否 | 低 |
| W08 | query_character_profile | 无 | entities 角色 + 角色资产（≤50，含别名聚合） | 否 | 低 |
| W09 | query_graph_neighbors | 无（run 上下文带节点） | 图谱选中节点邻居（≤100） | 否 | 低 |
| W10 | query_asset_relationships | asset_id*;relation_types;top_k(10,1-25) | asset_links 1-hop 带出（召回一个带出一串） | 否 | 低 |
| W11 | query_worldline_paths | 无（run 上下文带路径） | 保存路径 + 仅 canon 事件展开（reference_only） | 否 | 低 |
| W12 | query_manuscript_context | 无 | 当前场景/章节 active 正文块（≤32+12） | 否 | 低 |
| W13 | save_draft_revision | 无 | ⛔ 保留名：永不注册；执行必被 TOOL_PERMISSION_DENIED | 运行时专用 | 中(锁死) |

### Analysis 工具（7 个）

| # | 工具名 | 参数 | 执行内容 | 写? | 风险 |
|---|---|---|---|---|---|
| A01 | list_workspace_files | 无 | 列 analysis_workspace_files | 否 | 低 |
| A02 | read_workspace_file | path* | 读工作区文件（白名单，≤24KB） | 否 | 低 |
| A03 | list_source_segments | limit(1-200) | 列源分段 | 否 | 低 |
| A04 | read_source_segment | segment_index* | 读分段正文 | 否 | 低 |
| A05 | write_workspace_file | path*;kind;content*;mime_type | 白名单路径写工作区（DB 表，非真实 FS） | 是(可逆) | 中 |
| A06 | update_todo | todo/items(宽松) | 写 00-plan/todo.json | 是(可逆) | 中 |
| A07 | save_analysis_candidates | candidates[](宽松) | 写 analysis_candidates（不进 assets） | 是(候选区) | 中 |

### Worldline Cast 工具（5 个）

| # | 工具名 | 参数 | 执行内容 | 写? | 风险 |
|---|---|---|---|---|---|
| C01 | query_project_context | 无 | 读项目元数据 | 否 | 低 |
| C02 | query_character_profile | 无 | 三源角色花名册（entities+assets+graph nodes,≤80） | 否 | 低 |
| C03 | query_assets | 无 | 列 lore 资产（≤50） | 否 | 低 |
| C04 | query_graph_neighbors | graph_node_ids*(1-20) | 图谱邻居（≤100） | 否 | 低 |
| C05 | commit_worldline_cast | agent_refs*(1-8);source_refs(≤20);rationale* | 校验 ref 真实性后 UPDATE worldline_goal_starts | 是(可逆) | 中 |

**关键机制**：
- 工具 = 动态构造（活动传 tool_names → 工厂函数生成 AgentTool），无静态注册表、无 Extension/MCP 动态发现。
- 双层权限：`beforeToolCall` 门控（tools/permissions.ts 等三份）+ 执行层校验；参数若含 tenant/project/run_id 必须与上下文一致。
- 工具结果 = JSON 字符串进模型上下文；公开事件经 `publicWriterToolResult` 脱敏（去 content_text/alias/rule_text，280 字符预览）。
- 全部工具经租户/项目上下文参数化 SQL；无 shell、无任意文件、无删除、无跨租户。【已确认】
- 写入类工具（A05/A06/A07/C05）均 sequential 执行模式；无任何工具需要人工审批（审批表存在但未接 UI）。

## 10. 小说核心业务状态

- 结构：projects → chapters(含版本) → scenes(含版本) → manuscript_blocks（正文事实，乐观锁 expected_version）→ writer_drafts（候选）。
- 知识：assets（lifecycle: seed/canon/material/candidate/draft/simulation，spoiler gate，always_on 标记）、asset_links、asset_versions；entities/entity_aliases（角色状态 state_summary）；world_rule_evidence；story_graph_nodes/edges。
- Worldline：sessions（current_world 单世界）→ events（candidate/canon 分列）→ variables（变量注入/锁定）→ saved_paths（作者保存路径，可附着 writer run）→ goal_starts（cast 提交）。
- 审校：draft_reviews + draft_review_issues（项目级队列）。
- 「候选→正式」转换点：writer_drafts 采纳（adoption）、asset_candidate_proposals 采纳、worldline candidate 采纳、analysis_candidates 导入——**全部需要用户动作或显式策略**（AGENTS.md 硬约束）。

## 11. 前后端通信

- 浏览器只连同源 BFF（`app/api/**`），白名单代理到 Go（`lib/server/project-proxy.ts`）；服务端转发 cookie、注入 X-CSRF-Token、代签 trusted-client proof。
- 事件：**HTTP 轮询**（900ms，100 条/页，after_event_id 游标，按 sequence 去重排序）；Go 同时实现 SSE（held-open ≤25s）但前端未用。
- 停止：cancel POST → DB cancelled + Temporal cancel → AbortSignal → agent.abort()。
- 恢复：刷新后从 writer_threads 重建对话，任务卡按 run_id 重拉事件；幂等：X-Request-Id + Go request_id 重放防护 + draft/事件幂等键。
- 事件映射与 Mermaid 时序图见 07 号文档。

## 12. 数据和持久化

- Postgres 16 + pgvector，31 migrations；无 ORM（Go pgx / TS pg / Python psycopg 手写参数化 SQL + RLS）。
- 业务事实/候选/聊天记录分离（08 号文档 §3）；重启丢失仅限内存物（Pi Agent 实例、Temporal 阶段 checkpoint、Go 缓存 map）。
- 一致性保障：run 状态双表单事务更新；draft 幂等；advisory lock 防事件乱序；LLM 配额预留/finalize/checkpoint 防重复计费；资源锁（resource_locks slot）控并发。
- 已知风险：Go runs map 无清理；前端轮询对事件表读放大。

## 13. 当前功能完成度

- 本地产品闭环**已完整实现并通过真实浏览器验收**（上传→图谱→写作→采纳→导出），测试量大（Go 1073 / Py 502 / Pi 138 / Web 122 / infra 72，progress doc 2026-07-31）。
- 唯一阻塞上线项：MAIN-100 `awaiting_legacy_authorization`（Legacy 数据导入未获授权，非代码缺口）。
- 未接通/疑似废弃清单：SSE 前端路径、writer_approvals 审批 UI、save_draft_revision 工具名、多分支 Worldline、旧 frontend/、伏笔独立管理页（待确认）。
- 完整状态矩阵见 09 号文档。

## 14. 已确认问题与风险

1. 前端轮询 vs 后端 SSE 双实现（冗余）。
2. embedding 调用绕过配额预留/lease（成本控制缺口）。
3. 工具重名跨 Agent（Writer/Cast 四个同名工具 schema 不同）。
4. server.go 约 1 万行集中路由（维护/审查成本）。
5. 提示词硬编码源码，无版本管理。
6. Pi SDK 0.80.3 较旧（无 Extension/Skill；升级需重测全链路）。
7. 事件契约含未消费事件（writer.approval.* 等）。
8. 模型上下文无历史注入——「记忆」完全依赖检索质量与预算（12000 token）。
9. analysis 写工具参数宽松，依赖 prompt 约束。
10. 单世界 Worldline 语义限制未来分叉扩展。

## 15. 最值得继续深入研究的代码位置

| 优先级 | 位置 | 为什么 |
|---|---|---|
| ★★★ | `apps/pi-agent-runtime/src/activities/pi-writer-activities.ts` | 三 Agent 编排核心（阶段、工具、配额、事件、降级） |
| ★★★ | `apps/pi-agent-runtime/src/runtime/postgres-pi-writer-deps.ts` | 全部 Writer 工具 SQL 与门控、budget 裁剪、keyed 召回 |
| ★★★ | `apps/web/app/projects/[projectId]/writer/use-writer-run.ts` + `lib/api/writer-run.ts` | 前端轮询与事件→UI 状态机 |
| ★★ | `apps/api/internal/httpapi/server.go`（writer-runs 区域） | 入口校验/绑定/限流/admission |
| ★★ | `apps/api/internal/workflows/writer_admission.go` | 幂等与补偿 |
| ★★ | `apps/api/internal/llm/`（registry/bindings/quota） | LLM Facility 全貌 |
| ★ | `apps/pi-agent-runtime/src/runtime/pi-writer-agent.ts` | 5 阶段 Agent 构造与 prompt |
| ★ | `apps/agent-runtime/mirofish_agents/temporal/writer_review.py`、`worldline.py` | Python 侧 LLM 调用（JSONChatClient） |
| ★ | `packages/shared-contracts/schemas/*.json` | 三端契约真相源 |

## 16. 重要文件索引

- AGENTS.md（接手规则）、docs/refactor-saas/DEVELOPMENT_PLAN.md（范围）、24-current-development-progress.md（进度真相源）、tasks/refactor-saas-parallel-board.md（任务板）
- 本套档案：00-README / 01-executive-summary / 02-repository-map / 03-system-architecture / 04-pi-agent-runtime / 05-agent-tools-catalog / 06-prompts-context-skills / 07-frontend-agent-communication / 08-data-state-persistence / 09-feature-status-matrix / 10-security-observability-testing / 11-known-issues-and-open-questions

## 17. 未解决问题

见 11 号文档 §3（8 项待确认）+ §5（8 个建议询问负责人的问题）。核心：embedding 配额设计意图、审批流去留、SSE 切换计划、Pi SDK 升级计划、生产渠道绑定现状、伏笔管理规划。

## 18. 对下一位 AI 的阅读建议

1. 先读 `04-pi-agent-runtime.md` 与 `05-agent-tools-catalog.md`（本仓库与其他项目差异最大之处）。
2. 改动任何事件/工具/契约时，同时检查三端：Pi（activities/agent）→ Go（server.go + workflows）→ Web（writer-run.ts reducer + writer-rail.tsx），并对照 `packages/shared-contracts` JSON Schema。
3. 修改 `apps/web` 后必须连真实后端（compose 栈）验收，禁止 stub/mock（AGENTS.md 硬约束）。
4. live 测试必须走 `infra/scripts/run-live-test-stack.sh`（隔离 `mirofish_test_*` 库），禁止碰主库。
5. 新增工具必须：加进契约类型 → 实现 executeWriterTool case → 加 tool_names → 加权限断言 → 加前端 TOOL_LABELS → 加测试；并在 05 号文档登记。
6. 不要恢复：旧 frontend/、多分支 Worldline、旧 LLM 环境变量 fallback、表单堆叠式 Writer 长页。
