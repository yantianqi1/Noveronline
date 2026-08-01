# Agent 工具总清单（最重要文档）

## 总表

编号 | 工具名称 | 工具类型 | 定义位置 | 注册位置 | 启用状态 | 主要用途 | 风险等级
---|---|---|---|---|---|---|---
W01 | query_project_context | Pi 自定义工具 | pi-writer-agent.ts writerTool() | activities 内 tool_names 数组 | ✅ 默认启用（orchestrator） | 读项目标题/体裁/语言/状态 | 低（只读）
W02 | query_chapter_scene | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 读目标章节/场景及相邻场景摘要 | 低（只读）
W03 | query_assets | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 读作者勾选资产 | 低（只读）
W04 | search_assets | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 语义/关键词混合召回设定 | 低（只读+embedding 网络调用）
W05 | search_manuscript | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 召回非相邻前文（呼应/伏笔） | 低（只读）
W06 | fuse_recall | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | RRF 融合多路召回（可带 LLM 重排） | 低（只读+可选付费重排）
W07 | query_world_rules | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 读世界规则（seed 证据+canon 资产） | 低（只读）
W08 | query_character_profile | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 读角色档案与别名 | 低（只读）
W09 | query_graph_neighbors | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 读图谱选中节点邻居 | 低（只读）
W10 | query_asset_relationships | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 1-hop 资产关联带出 | 低（只读）
W11 | query_worldline_paths | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 读保存的世界线路径+事件 | 低（只读）
W12 | query_manuscript_context | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 读当前场景/章节手稿块 | 低（只读）
W13 | save_draft_revision | Pi 自定义工具 | 同上 | 同上（tool_names 不含它） | ⛔ 保留名（orchestrator 被禁，执行时 TOOL_PERMISSION_DENIED） | 保留的运行时持久化 | 中（若被调用）
A01 | list_workspace_files | Pi 自定义工具 | pi-analysis-agent.ts analysisTool() | analysis 活动按 module 传 tool_names | ✅ 默认启用（analysis worker） | 列工作区文件 | 低（只读）
A02 | read_workspace_file | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 读工作区文件（≤24KB） | 低（只读）
A03 | list_source_segments | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 列源分段 | 低（只读）
A04 | read_source_segment | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 读源分段正文 | 低（只读）
A05 | write_workspace_file | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 写工作区文件（路径白名单） | 中（可逆写入，白名单约束）
A06 | update_todo | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 更新 00-plan/todo.json | 中（可逆写入，固定路径）
A07 | save_analysis_candidates | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 保存候选到 analysis_candidates | 中（写候选区，可删除重建）
C01 | query_project_context | Pi 自定义工具 | pi-worldline-cast-agent.ts castTool() | worldline-cast 活动 WORLDLINE_CAST_TOOLS | ✅ 默认启用 | 读项目元数据 | 低
C02 | query_character_profile | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 列可参演角色 | 低
C03 | query_assets | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 列 lore 资产 | 低
C04 | query_graph_neighbors | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用 | 查图谱邻居 | 低
C05 | commit_worldline_cast | Pi 自定义工具 | 同上 | 同上 | ✅ 默认启用（call once） | 提交选角（写 worldline_goal_starts） | 中（可逆写，run 级）

**统计**：Pi 自定义工具 25 个；Pi 内置工具 0；Extension 工具 0；MCP 工具 0；子 Agent 工具 0；未接通工具 0（全部有完整调用链）；疑似废弃 1（save_draft_revision，仅保留名）。

**全部工具共享的注册与启用机制**：
- 工具不是静态注册表，而是**按 run 动态构造**：活动把 `tool_names` 数组传入 `orchestrateWritingBrief()`/`runAnalysisStage()`/`runCastStage()`，agent 内 `writerTool(name, request)` 工厂按名生成 `AgentTool`。
- Writer orchestrator 的 tool_names 硬编码于 `pi-writer-activities.ts`（`runDualStagePiWriterActivity` 内数组，12 个，不含 save_draft_revision）；Analysis 由 `request.tool_names`（Go 侧传入）决定；Cast 用 `WORLDLINE_CAST_TOOLS` 常量。
- 权限门控：`beforeToolCall` → `assertToolAllowed()`（tools/permissions.ts）→ 拒绝则 block + reason；另有硬上限 24 次工具调用（ORCHESTRATOR_TOOL_CALL_MAX）。
- 工具结果 JSON 序列化为 `content: [{type:"text", text: JSON.stringify(details)}]` 进入模型上下文；`details` 同时透传给事件记录。
- 模型看到的 schema：typebox `ObjectSchema`，`additionalProperties:false`（除 analysis 的 update_todo/save_candidates 是 `additionalProperties:true`）。

---

## W01. 工具：query_project_context

1. **基本身份**：显示名「查阅全书设定」（前端 TOOL_LABELS）；模型名 `query_project_context`；类别 Writer 只读；状态 ✅ 已接通；定义 `pi-writer-agent.ts` `writerTool()`；执行 `postgres-pi-writer-deps.ts` `executeWriterTool` case；注册于 `pi-writer-activities.ts` tool_names；测试：无独立单测（活动测试覆盖）；前端展示：writer-rail.tsx 步骤行。
2. **模型看到的说明**：「Read project title, genre, language, and status.」清晰；与其他工具无混淆。
3. **输入参数**：无（`noArguments`，additionalProperties:false）。验证：typebox 拒绝额外字段。
4. **执行逻辑**：`SELECT title, description, genre, language, status FROM projects WHERE tenant_id=$1 AND project_id=$2 LIMIT 1`（带租户上下文）。调用链：tool execute → `executeWriterTool` → `queryWithTenantContext` → Postgres。
5. **返回结果**：`{project: {...}|null}`；小体积；模型可判断成功/失败。
6. **副作用**：无（只读）。
7. **权限与风险**：低。租户/项目上下文强制；无敏感字段。
8. **注册与启用**：默认启用；在 orchestrator run 固定 tool_names 中；无环境变量/权限分支。
9. **UI 与事件**：tool_execution_start/end → `writer.tool.started/completed` → 前端步骤「查阅全书设定」。
10. **测试**：无专属单测；活动级测试覆盖事件路径。
11. **已发现问题**：无。
12. **非程序员解释**：相当于 AI 写之前先看一眼「这本书叫什么、什么类型、什么语言」。只读不改变任何东西。

## W02. 工具：query_chapter_scene

1. **基本身份**：显示名「查阅章节与场景」；定义/执行同 W01；状态 ✅。
2. **说明**：「Read the requested chapter and scene identifiers plus existing draft metadata.」清晰。
3. **输入参数**：无。但执行时从 `writer_runs` 行取 run 目标 chapter_id/scene_id（或 request 兜底）。
4. **执行逻辑**：查 writer_runs → chapters（title/status/order/brief/outline）→ scenes（+content_text）→ 同章最多 12 个相邻场景摘要（LEFT 280 字符）。所有文本经 `limitWriterContextRecord` 截断到 280 字符。
5. **返回结果**：`{target, chapter, scene, neighbor_scenes}`；受限体积。
6. **副作用**：无。
7. **风险**：低。返回 scene.content_text 前 280 字符（小说原文进上下文是产品语义，非泄漏——作者自己的项目）。
8. **注册**：默认启用。
9. **UI**：步骤「查阅章节与场景」。
10. **测试**：无独立单测。
11. **问题**：无。
12. **解释**：AI 写某章前先看这章的场景安排和相邻场景，相当于翻开你的大纲。

## W03. 工具：query_assets

1. **身份**：显示名「查阅勾选资产」；状态 ✅。
2. **说明**：「Read the author's explicitly selected project assets (by id)... Returns nothing when the author selected none — use search_assets...」清晰，且防误用（明确指路）。
3. **参数**：无（author-sovereign path：selected_asset_ids 由 run 上下文带，非模型参数）。
4. **执行逻辑**：selected_asset_ids 为空 → 直接返回 `{assets:[], selection:"none", recall:"search_assets"}`；否则按 id 查 assets（lifecycle IN seed/canon/material，LIMIT 50，pinned 优先）→ 每条截断到 280 字符。
5. **返回**：`{assets:[...]}` 或空说明。
6. **副作用**：无。
7. **风险**：低（仅作者勾选的资产；生命周期门控）。
8. **UI**：`writer.tool.completed` 时前端将结果作为引用行（citations）展示。
9. **测试**：活动测试覆盖。
10. **问题**：无。
11. **解释**：AI 读你勾选过的「必看设定」，你没勾就返回空并建议它自己搜。

## W04. 工具：search_assets（最复杂工具）

1. **身份**：显示名「语义召回设定」；状态 ✅；有专属单测（postgres-pi-writer-deps.test.ts）。
2. **说明**：「Semantic recall over project canon/seed/material assets. Supply a query... Returns ranked matches with citations; degrades to keyword when embeddings are unavailable.」清晰。
3. **输入参数**：
   | 参数 | 类型 | 必填 | 默认 | 范围 | 含义 |
   |---|---|---|---|---|---|
   | query | string | ✅ | — | 非空 | 检索意图 |
   | asset_types | string[] | 否 | 无过滤 | — | 资产类型过滤 |
   | top_k | number | 否 | 10 | 1–25 | 返回数 |
   | mode | enum | 否 | hybrid | keyword/vector/hybrid | 检索模式 |
   | channel | enum | 否 | hybrid | hybrid/keyed | keyed=确定性人名召回 |
   | expand_relations | boolean | 否 | false | — | 附带 1-hop 关联 |
   Schema 库：typebox；额外字段拒绝；非法值钳制（top_k clamp、mode 非法回落 hybrid）；query 空 → VALIDATION_FAILED。
4. **执行逻辑**：keyed 分支（channel="keyed"）→ `executeKeyedAssets`：从 query+context_texts+最近 6 段手稿尾巴做标题/别名子串匹配（≤12 个，含 entity alias 注入）；hybrid/vector 分支 → 先解析 `asset_search_embedding` 模块绑定并请求 embedding（fetch POST {base_url}/embeddings，失败 → 显式降级 keyword + degrade_reason）→ 大 SQL（global_search_index tsvector + ILIKE term 匹配 + vector 余弦 + recency/lifecycle/pinned 加权，0.45/0.55 hybrid 权重）→ spoiler gate（reveal_after_chapter_order ≤ 当前章序）→ 结果 280 字符预览。
5. **返回**：`{query, mode_used, degraded, count, assets[], citations[]}`；每个 asset 带 content_preview/scores；前端展示为引用行（标题/生命周期/预览）。
6. **副作用**：读 DB + 调用 embedding 供应商（付费网络调用，走 LLM Facility 绑定但**不**走 executeLLMStage 配额预留——【已确认】`resolveQueryEmbedding` 直连 fetch；这是与 rerank 的主要差异）。
7. **风险**：低–中。无写入；embedding 调用未配额预留（成本风险有限但存在）；spoiler gate 防剧透。
8. **注册**：默认启用。
9. **UI**：引用行 + degraded 标记 + 步骤。
10. **测试**：`postgres-pi-writer-deps.test.ts`（tokenize、keyed、gate）；活动测试。
11. **问题**：embedding 调用不经配额预留/lease（与「所有 provider 调用都走 executeLLMStage」的设计声明有出入）；【待确认】这是有意为之还是缺口。
12. **解释**：AI 的「搜索引擎」——它描述想找什么，系统按语义+关键词混合搜出设定并告诉它每条来自哪里。

## W05. 工具：search_manuscript

1. **身份**：显示名「召回前文呼应」；状态 ✅。
2. **说明**：「Semantic recall over prior manuscript prose that is NOT adjacent to the current scene — foreshadowing and callbacks... unavailable when prose embeddings are not indexed.」清晰。
3. **参数**：query（必填）、top_k（默认 5，1–12）。
4. **执行逻辑**：embedding 请求（失败 → 显式 degraded 返回空）→ `resolveManuscriptCursorBound`（写作游标：目标场景尾巴 < 严格小于；空章则前章尾+1；全项目最后+1）→ `manuscript_block_embeddings` 余弦检索 `block_order < cursor`（绝不召回未来正文）→ 片段 240 字符。
5. **返回**：`{mode_used:"vector", manuscript_blocks[], citations[]}`。
6. **副作用**：embedding 网络调用（同 W04 无配额预留）。
7. **风险**：低–中。
8. **UI**：引用行「前文呼应 · 第 N 段」。
9. **测试**：活动/依赖测试。
10. **问题**：无 embedding 索引时静默降级为空（有 degrade_reason，可见）。
11. **解释**：AI 查「之前哪一段写过这个伏笔」，避免写穿帮。

## W06. 工具：fuse_recall

1. **身份**：显示名「融合多路召回」；状态 ✅。
2. **说明**：「Fuse several recall channels you already ran (keyed/hybrid/manuscript) into one RRF-ranked list...」清晰。
3. **参数**：channels[]（每项 {channel, items[]}，必填）、top_k（默认全部，≤25）、rerank（bool）、query（rerank 时必填）。
4. **执行逻辑**：`reciprocalRankFusion`（recall-fusion.ts）→ 可选 rerank：`request.rerank_executor`（活动注入，走 `writer_retrieval_rerank` 模块 executeLLMStage 配额+lease）失败 → 显式 `rerank_degraded` 回落 RRF → 结果 ≤top_k。活动层还会把 always_on 资产作为第一通道注入（不裁剪）。
5. **返回**：`{count, fused[], reranked, citations[]}`。
6. **副作用**：可选付费重排调用（有配额预留）。
7. **风险**：低（rerank 有配额与降级）。
8. **UI**：前端将 always_on 通道显示为「常驻」引用。
9. **测试**：recall-fusion.test.ts + 活动测试。
10. **问题**：无。
11. **解释**：AI 同时查了好几个渠道（人名、语义、前文），这个工具把结果合并去重排优先级。

## W07. 工具：query_world_rules

1. **身份**：显示名「查阅世界规则」；状态 ✅。
2. **说明**：「Read extracted project world rules as private writing context.」
3. **参数**：无。
4. **执行逻辑**：`world_rule_evidence`（seed，≤40，按 created_at）+ assets 中 world_rule/worldview 类型（≤40，spoiler gate）→ 合并 50 条 → 280 截断。
5. **返回**：`{rules:[{rule_evidence_id, category, confidence, source, lifecycle, title,...}]}`（内容在 rule_text，公开事件不含 rule_text——`publicWriterToolResult` 只留元数据字段）。
6. **副作用**：无。
7. **风险**：低。
8. **测试**：活动测试（含事件脱敏断言）。
9. **问题**：无。
10. **解释**：AI 查「这个世界有哪些不能违反的规则」，比如「魔法不能凭空造物」。

## W08. 工具：query_character_profile

1. **身份**：显示名「查阅角色档案」；状态 ✅。
2. **说明**：「Read project character identities, aliases, and current state as private writing context.」
3. **参数**：无。
4. **执行逻辑**：entities(entity_type=character, ≤40, 带 aliases 聚合) + assets(character/seed_character, ≤40, spoiler gate) → 合并 50 条。
5. **返回**：`{profiles:[...]}`；公开事件只留 entity_id/canonical_name/importance/state_summary/source/lifecycle/category（无 alias 原文）。
6. **副作用**：无。
7. **风险**：低。
8. **测试**：有（含脱敏）。
9. **问题**：无。
10. **解释**：AI 查「这个角色现在是什么状态、有没有别名」，避免把角色写死又复活。

## W09. 工具：query_graph_neighbors

1. **身份**：显示名「查阅故事图谱」；状态 ✅（writer 与 cast 各有一个同名工具，定义在不同文件，参数不同——见「重名工具」检查）。
2. **说明**：「Read explicitly selected story graph nodes and their direct relationships.」
3. **参数**：无（writer 版，graph_node_ids 来自 run 上下文）；cast 版参数 `graph_node_ids`（1–20 必填）。
4. **执行逻辑**：CTE 查询选中节点 + 邻居（边 join，≤100，weight 排序）。
5. **返回**：`{node, nodes[], neighbors[]}`。
6. **副作用**：无。
7. **风险**：低。
8. **测试**：活动测试。
9. **问题**：writer 版与 cast 版**同名但 schema 不同**——模型若跨 agent 混用（不可能，不同 run）无影响，但文档/审计注意区分。
10. **解释**：AI 查「这个人物和谁有关系、什么关系」。

## W10. 工具：query_asset_relationships

1. **身份**：显示名「带出关联资产」；状态 ✅。
2. **说明**：「Bring out one recalled asset's 1-hop related assets (召回一个、带出一串)...」中文注释说明其设计意图。
3. **参数**：asset_id（必填，非空校验）、relation_types[]（可选过滤）、top_k（默认 10，1–25）。
4. **执行逻辑**：asset_links join assets（生命周期门控 + spoiler gate）→ direction 计算 → ≤top_k。
5. **返回**：`{asset_id, relationships[]}`。
6. **副作用**：无。
7. **风险**：低。
8. **测试**：有。
9. **问题**：asset_id 为空抛 VALIDATION_FAILED（错误会被模型看到并自我纠正）。
10. **解释**：AI 搜到一个人物后用它查出「他的门派、武器、盟友」。

## W11. 工具：query_worldline_paths

1. **身份**：显示名「查阅世界线走向」；状态 ✅。
2. **说明**：「Read explicitly selected saved worldline paths as non-canon references.」——明确「非 canon」防模型误当正式设定。
3. **参数**：无（worldline_path_ids 来自 run 上下文）。
4. **执行逻辑**：worldline_saved_paths（≤20）→ 展开 selected_event_ids → worldline_events **仅 status='canon'** → 按作者保存顺序重排 → state_changes 脱敏（publicWorldlineStateChanges）。
5. **返回**：`{paths[], canon_status:"reference_only", selection_required?}`。
6. **副作用**：无。
7. **风险**：低（严格 canon-only + reference_only 标记）。
8. **测试**：有。
9. **问题**：无。
10. **解释**：AI 看作者保存过的「剧情走向方案」，但明确知道这只是参考不是定案。

## W12. 工具：query_manuscript_context

1. **身份**：显示名「查阅现有手稿」；状态 ✅。
2. **说明**：「Read recently adopted manuscript blocks for continuation context.」
3. **参数**：无。
4. **执行逻辑**：优先当前 scene 的 active blocks（≤32）+ 同章其他场景补足（≤12）；无 scene 用 chapter；兜底全项目最后 32 块反序。280 截断。
5. **返回**：`{target, manuscript_blocks[]}`。
6. **副作用**：无。
7. **风险**：低（仅 active/adopted 块）。
8. **测试**：有。
9. **问题**：无。
10. **解释**：AI 看「当前场景已经写了什么」，保证续写接得上。

## W13. 工具：save_draft_revision（疑似废弃/保留名）

1. **身份**：模型名 `save_draft_revision`；状态 ⛔ 保留名——不在 orchestrator tool_names 中；即使模型硬调，`executeWriterTool` case 直接抛 `TOOL_PERMISSION_DENIED: draft persistence is runtime-owned`；description 也明示「Reserved runtime persistence tool. The orchestrator must not call it.」；`executionMode: "sequential"`。
2. **说明**：保留给运行时（活动层 `saveDraftRevision` 是真实持久化入口）。
3. **参数**：无 schema（noArguments）。
4. **执行逻辑**：运行时侧 `saveDraftRevision`（postgres-pi-writer-deps.ts）：advisory lock + 幂等（同 run 只 1 条）+ 写 writer_drafts(status=candidate, word_count=字数)。
5. **风险**：中（若被误调用，有权限门控双保险）。
6. **解释**：这个「工具名」被保留但锁死了——草稿保存只能由系统程序完成，AI 没有钥匙。

## A01–A04. 工具：list_workspace_files / read_workspace_file / list_source_segments / read_source_segment

1. **身份**：Analysis Agent 只读工具；显示即模型名；状态 ✅。
2. **说明**（pi-analysis-agent.ts toolDescription）：「List files already written in this analysis workspace folder.」「Read one workspace file by path (for example 00-plan/task-pack.md).」「List available source novel segments with titles and previews.」「Read one source segment body by segment_index.」清晰。
3. **参数**：A01/A03 无（A03 有 limit 1–200）；A02 path 必填；A04 segment_index ≥0。
4. **执行逻辑**：A01/A02 → analysis_workspace_files 表（path 白名单 `isAllowedAnalysisWorkspacePath`：00-plan/10-source/20-notes/30-candidates/90-review/，拒绝 `..`，≤512 字符）；A02 内容 ≤24000 字符；A03/A04 → text_segments（upload 的源分段），A04 返回分段正文（含截断）。
5. **返回**：列表/文件内容/分段。
6. **副作用**：无。
7. **风险**：低（白名单 + 租户上下文）。
8. **测试**：`analysis-permissions.test.ts` + 运行时测试。
9. **解释**：分析 AI 的「文件浏览器」——只能看它自己的分析工作区和小说源文件。

## A05. 工具：write_workspace_file

1. **身份**：Analysis 写工具；状态 ✅；executionMode sequential。
2. **说明**：「Write or overwrite a workspace file under 00-plan/, 20-notes/, 30-candidates/, or 90-review/.」
3. **参数**：path（必填）、kind（可选）、content（必填）、mime_type（可选）。Schema additionalProperties:false。
4. **执行逻辑**：白名单校验（拒绝 .. 与越界路径）→ UPSERT analysis_workspace_files（内容 SHA-256、size）。
5. **副作用**：写 DB 表（可逆：可覆盖，Go 侧可删）。无真实文件系统写入（表存储）【已确认】。
6. **风险**：中——可覆盖同一 run 的 workspace 文件；白名单约束有效；多轮并行写有 last-write-wins 风险（sequential 模式缓解）。
7. **测试**：有（白名单单测）。
8. **解释**：AI 的分析笔记本——它把分析笔记/任务计划写进项目里的指定文件夹。

## A06. 工具：update_todo

1. **身份**：固定写 `00-plan/todo.json` 的便捷工具；状态 ✅；sequential。
2. **说明**：「Update 00-plan/todo.json with current task statuses.」
3. **参数**：todo/items 两个 additionalProperties:true 的对象（宽松）。
4. **执行逻辑**：JSON.stringify(args) 写入 todo.json（复用 writeWorkspaceFile，kind=todo）。
5. **风险**：中（低：固定路径+可覆盖）。
6. **解释**：AI 的待办清单打卡器。

## A07. 工具：save_analysis_candidates

1. **身份**：候选持久化工具；状态 ✅；sequential。
2. **说明**：「Persist structured candidate rows extracted from the novel.」
3. **参数**：candidates[]（additionalProperties:true，宽松）。
4. **执行逻辑**：`saveAnalysisCandidates(db, {replace_run:false, import_to_assets:false})` → 只写 analysis_candidates 表（不导入 assets；最终化由 Go `SQLAnalysisAssetImporter` 完成）。
5. **副作用**：写候选表（可删）；不触碰 canon。
6. **风险**：中（写库但仅候选区；参数宽松 → 依赖系统提示词约束 JSON 形状）。
7. **解释**：AI 把从小说里提取的角色/规则候选存到「待审」区，作者审核后才转正。

## C01–C04. 工具（Cast Agent）：query_project_context / query_character_profile / query_assets / query_graph_neighbors

1. **身份**：worldline-cast-planner 只读工具；状态 ✅。
2. **说明**（pi-worldline-cast-agent.ts）：「Read project metadata...」「List character entities, character assets, and graph character nodes available for casting.」「List enabled lore/assets...」「Inspect relationships around selected graph node IDs.」
3. **参数**：C01–C03 无；C04 graph_node_ids（1–20 必填）。
4. **执行逻辑**（postgres-pi-worldline-cast-deps.ts executeCastTool）：C02 三源合并（entities 40 + assets 40 + graph nodes 60 → 80）；C03 assets ≤50；C04 CTE 邻居 ≤100。
5. **副作用**：无。
6. **风险**：低。
7. **解释**：选角 AI 的「角色花名册」——它先看有哪些角色可选。

## C05. 工具：commit_worldline_cast

1. **身份**：cast 写工具；状态 ✅；sequential；「Call exactly once when ready.」
2. **说明**：「Commit the final agent_refs and source_refs for this simulation goal.」
3. **参数**：agent_refs（1–8，{source_kind, source_id} 必填项）、source_refs（≤20 可选）、rationale（必填）。
4. **执行逻辑**：活动层（pi-worldline-cast-activities.ts）先校验 refs 真实性（asset/entity 必须存在于本租户项目）→ `commitCast` UPDATE worldline_goal_starts（status IN queued/casting/preparing）。
5. **副作用**：写 worldline_goal_starts（可逆：状态机可重开）。
6. **风险**：中（写业务状态但限定 run 且值经验证）。
7. **测试**：worldline-cast-worker-spec.test.ts 等。
8. **解释**：选角 AI 的最后一步——把「这局推演由哪几个角色参与」正式提交。

---

## 交叉检查结论

**检查 1 定义 vs 注册数量**：定义 25 = 注册 25（运行时按名构造，无静态注册表差异）；实际传入 Agent 的：writer 12（13 定义中 save_draft_revision 不传）、analysis 按 Go 传入（7 全）、cast 5。仅测试中使用：无。疑似废弃：1（W13）。

**检查 2 多个注册入口**：不同 agent 不同工具集（writer 12 / analysis 7 / cast 5）；不同页面不改变工具集；开发/生产环境工具相同；无用户权限加载差异（权限是运行时门控而非加载过滤）；无 feature flag；无 Extension/MCP 动态注册。

**检查 3 重名工具**：`query_project_context`/`query_character_profile`/`query_assets`/`query_graph_neighbors` 在 writer 与 cast **两个 agent 中重名**——但 schema 不同（writer 版无参数/run 上下文驱动，cast 版 query_graph_neighbors 有必填参数）。因 agent 实例隔离，不会互相覆盖；但若未来合入同一会话会冲突。前端 TOOL_LABELS 只映射 writer 版名。

**检查 4 隐藏工具**：无工厂 map 动态生成（工具由显式 name 分支构造）；无配置文件声明工具；无 DB 配置工具；无目录扫描。

**检查 5 工具调用记录**：workflow_events（writer.tool.started/completed，含 tool_call_id/tool_name/result 脱敏版）、agent_traces（tool_call/tool_result，full 级别含参数与结果）、前端 TOOL_LABELS 已知 12 个 writer 工具名。反向核对无遗漏。

**风险等级汇总**：无「高/严重」工具（无 shell、无任意文件写、无跨租户、无删除）；全部工具经 tenant/project 上下文参数化 SQL；写入类仅 analysis workspace（白名单）与 cast commit（run 限定）。
