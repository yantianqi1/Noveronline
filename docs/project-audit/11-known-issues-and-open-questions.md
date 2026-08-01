# 已确认问题、架构风险与待确认问题

## 1. 已确认问题（有代码证据）

1. **前端未用 SSE**：Go 侧 `writeWriterEventsSSEHeldOpen` 完整实现（`Accept: text/event-stream` + `stream=1`），前端 `use-writer-run.ts` 用 900ms JSON 轮询 + 100 条/页游标。重复实现、实时性差、请求量大。（apps/api/internal/httpapi/server.go、apps/web/app/projects/[projectId]/writer/use-writer-run.ts）
2. **embedding 调用绕过配额预留**：`resolveQueryEmbedding`（postgres-pi-writer-deps.ts）直连 fetch embedding 端点，不走 `executeLLMStage` 的 quota reservation/lease/telemetry（与 rerank 不同）。成本与并发控制存在缺口。
3. **工具重名跨 Agent**：`query_project_context`/`query_character_profile`/`query_assets`/`query_graph_neighbors` 在 Writer 与 Cast 两个 Agent 中同名但参数 schema 不同（Writer 版无参，Cast 版 query_graph_neighbors 有必填参数）。当前因 Agent 隔离无冲突，未来合并会话有覆盖风险。
4. **save_draft_revision 是死工具名**：保留在 WriterToolName 联合类型中、有 description、有权限拒绝执行，但从不传入 tool_names。模型永远看不到它（未注册）却存在于契约中，属于契约噪音。
5. **Go `TemporalWriterStarter.runs` map 无清理**：进程内 run 缓存无限增长（低危，DB 是真相源）。
6. **系统提示词全部硬编码在 TS 源码**：修改 prompt 需改代码发版；无 prompt 版本管理/回滚（composer 支持 settings.system_prompt 覆盖，其余不支持）。
7. **writer_approvals 无前端消费**：`createWriterApproval`（postgres-pi-writer-deps.ts）已实现并有 pending 状态，但无任何前端审批 UI 路径（rg 无前端引用）；`writer.approval.required/resolved` 事件类型存在于契约与 reducer 默认分支，无 UI 呈现。
8. **事件契约包含未使用事件**：`writer.approval.*`、`writer.consistency.clean/skipped/degraded` 等事件前端 reducer 不消费（default 分支吞掉）——功能冗余但无害。

## 2. 架构风险（扩展时易出现）

1. **server.go 单体路由**（约 1 万行）：新 handler 极易遗忘集中安全壳（CSRF/限流/RLS），需强制走 mount 白名单。
2. **三端事件契约漂移**：shared-contracts 冻结了 writer 事件，但 analysis/worldline-cast 事件无共享契约（仅各自测试）；扩展事件需同时改 Pi/Go/Web 三处。
3. **每次 run 全新建 Agent + 全量事件轮询**：长对话场景（thread 已存在）下，模型上下文不含历史（每次都从 DB 重检索）——「记忆」完全依赖数据库检索质量；若资产库膨胀，检索预算（12000 token）会成为硬瓶颈。
4. **单世界 Worldline 语义**：未来若需要多世界/分叉，当前 schema（worldline_sessions 单 current_world、状态机、canon 分列）不支持，需大改。
5. **轮询对事件表压力**：每个活跃 run 每 900ms 查一次 workflow_events；多用户并发时 DB 读放大（有索引与 advisory lock，但无缓存层）。
6. **Temporal 任务队列较多**（12 个 queue）：worker 部署矩阵复杂，queue 配置错误会导致任务静默排队（有 readiness 检查但无端到端消息延迟告警）。

## 3. 待确认问题（静态调查无法定论）

1. embedding 调用绕过配额是否为**有意设计**（embedding 便宜）还是缺口——需要询问负责人。
2. `writer_approvals` 审批流是否为**未完成功能**（前端未接）还是已废弃。
3. 生产环境模型供应商现状：progress doc 提到 `https://api.aiwanai.cc/v1` + `gpt-5.5` 的 external channel 验证记录，但本调查未读取真实 `.env`/DB，无法确认当前绑定。
4. 伏笔管理是否有独立 UI/流程（搜索只见 `search_manuscript` 的 foreshadowing 召回注释，未见独立伏笔表——`foreshadowing` 可能是 asset_type 之一）。
5. Pi `thinkingLevel` 各档位（minimal/low/medium/high/xhigh）在模型不支持时是否降级（模型能力表 model_capabilities.ts 有逻辑，未逐档验证）。
6. 前端「采纳后跨 tab 同步」的最终一致性（useWriterRun 终态后一次性拉 draft）在极端竞态下是否可能显示旧状态。
7. Python worker 的 writer_review 与 writer_planning 是否完全无工具（无工具数组）——已确认无工具，但「审校为什么不用工具查设定」是产品决策问题。
8. 旧 `backend/` 中 writer_agent.py / worldline.py 等 legacy 实现与 SaaS 新实现的功能对应关系（未逐文件比对）。

## 4. 疑似废弃模块

| 模块 | 判定 | 证据 |
|---|---|---|
| 根目录 `frontend/`（已删除） | 疑似废弃（已退役） | AGENTS.md/README 声明 |
| `backend/` Legacy FastAPI | 疑似废弃（仅迁移参考） | AGENTS.md；仅 legacy_import 在 SaaS 中活跃使用 |
| SSE 流式路径 | 疑似废弃（实现但无消费者） | 仅测试引用 |
| writer_approvals | 疑似废弃/未接通 | 无前端路径 |
| `首页-手机端/` 目录 | 疑似废弃 | 未参与 compose/构建（未深入调查） |
| save_draft_revision 工具名 | 疑似废弃（保留名） | 永不注册 |
| 多分支 Worldline 接口（/branches、/comparison） | 疑似废弃 | AGENTS.md 明确不扩展 |

## 5. 建议向项目负责人询问的问题

1. MAIN-100（Legacy 授权导入）的授权状态与计划？
2. embedding 调用是否应纳入配额预留？（安全审计项 2）
3. 审校（writer_reviewer）与书籍计划（writer_book_planner）为何不带工具？后续是否计划接入检索工具？
4. 前端是否计划切换到 SSE？（后端已就绪）
5. 是否有伏笔（foreshadowing）管理的独立产品规划？
6. `tools/ui-preview/shots/` 未提交截图的用途与归属？
7. Pi SDK 是否有升级计划（0.80.3 → 新版）？升级后 Agent API 兼容性评估是否做过？
8. 生产环境的模型渠道当前绑定情况（哪些模块绑到哪个渠道）？
