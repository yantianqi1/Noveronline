# Prompt、上下文、Skill 与记忆

## 1. 所有主要 System Prompt（【已确认】，全部内嵌于 TS 代码）

| Prompt | 位置 | 内容要点 |
|---|---|---|
| Orchestrator | pi-writer-agent.ts `orchestratorSystemPrompt()` | 「你是 MiroFish writer orchestrator。调用只读工具后产出简明写作简报。绝不写正文/不采用稿件。不要调用 save_draft_revision；运行时显式持久化 composer 结果。」 |
| Composer | `composerSystemPrompt(request)` | 支持 `settings.system_prompt` 覆盖；revise 模式默认「修订选中文本，只返回修订后文本」；draft 模式默认「按写作简报写原创正文，只返回正文」；均禁止声称采纳/审校完成 |
| Retrieval Planner | `retrievalPlannerSystemPrompt()` | 输出 JSON（intent/coverage/queries/budget）；2–5 条查询；channel 语义（hybrid/keyed/manuscript/graph）；用小说语言写查询；绝不虚构 canon |
| Reranker | `rerankSystemPrompt()` | 输出 JSON ranked_ids；按对写作意图的有用度排序；绝不虚构 id |
| Consistency Checker | `consistencySystemPrompt()` | 输出 JSON violations（canon_label/conflict/severity）；只报真矛盾；空数组=一致 |
| Analysis Planner | pi-analysis-agent.ts `systemPrompt()`（module_key=analysis_planner 分支） | 中文输出强制；写 task-pack.md + todo.json；不虚构源文 |
| Analysis Worker | 同上（worker 分支） | 中文强制；20-notes/sequential/N.md、30-candidates/{characters,relationships,world_rules,timeline}.json 精确 JSON 形状；90-review/summary.md；候选非 canon |
| Cast Planner | pi-worldline-cast-agent.ts `systemPrompt()` | 3–5 个参与角色（≤8）；agent_refs 只用工具返回的真实 id；commit 恰好一次；中文 rationale |

## 2. 用户 Prompt（每次调用前构造）

全部为 JSON.stringify 结构（非自然语言模板）：

- writer 各阶段：`orchestratorPrompt(request)` 含 mode/instruction/chapter/scene/selected_asset_ids/graph_node_ids/worldline_path_ids/target_words + **worldline_timeline**（参考性剧情序列 + 指示「按 step 顺序展开，不重排不跳过，除非作者指示」）+ **always_on_canon**（常驻规则，指示「已注入，不必重新检索」）+ **retrieval_plan**（planner 产出的查询计划 + 每 channel 的执行指引 + 「引用你用的内容」）。
- composer：`composerPrompt(request)` 含 instruction/writing_brief/target_words + constant_canon + worldline_timeline（排序后的 adopted events）。
- analysis：`userPrompt` = {task, mode, instruction, hints, workspace_roots}。
- cast：`userPrompt` = {task:"select_worldline_cast", goal}。

## 3. 一次模型调用前的上下文组装顺序（【已确认】，来自代码证据）

Writer 双阶段 run 的真实组装顺序：

```
[编排器阶段]
1. systemPrompt（orchestratorSystemPrompt，纯代码常量）
2. 用户消息 = orchestratorPrompt(request) JSON：
   a. 请求基础字段（mode/instruction/chapter_id/scene_id/选中资产/图谱节点/世界线路径/目标字数）
   b. worldline_timeline（活动层预取，按 step 排序的 adopted events；无则省略）
   c. always_on_canon（活动层预取，常驻规则，逐字注入；无则省略）
   d. retrieval_plan（planner 阶段输出；无则省略）
3. 之后每轮工具结果（JSON）进入消息历史：
   - 工具结果经 packRetrievalToolResult 预算裁剪（12000 token 默认，先裁低排名）
   - fuse_recall 结果含 always_on 第一通道（不裁剪）
   - 工具描述+参数 schema 由 Agent 自动注入（typebox → JSON Schema）
4. 模型输出 → writing_brief

[作曲器阶段]
1. systemPrompt（composerSystemPrompt：settings.system_prompt 或默认）
2. 用户消息 = composerPrompt JSON：instruction + writing_brief + target_words + constant_canon + worldline_timeline
3. 无工具、无历史（单轮生成）
```

Analysis / Cast 阶段类似：systemPrompt + 单条 JSON 用户消息 + 工具循环结果。

## 4. 动态变量与数据来源

| 变量 | 来源 |
|---|---|
| always_on 资产 | `assets.always_on = TRUE` + lifecycle 白名单 + spoiler gate（loadAlwaysOnAssets，≤8 条，280 字符预览） |
| 世界线时间线 | `worldline_events WHERE status='canon'` 按 step 排序（loadWorldlineTimeline，≤200 事件/session，state_changes 脱敏） |
| 检索计划 | planner 模型输出 JSON（parseRetrievalPlan，容错 fence，≤6 查询，channel 白名单） |
| 一致性 canon | `assets(world_rule/worldview)` + `entities(character)` 各 ≤40 条，每条 ≤400 字符 |
| 项目/章节/场景 | projects/chapters/scenes 表（工具） |
| 角色/规则 | entities/asset 表（工具） |

## 5. RAG / 向量检索 / 长期记忆

- **RAG 存在且成熟**：search_assets（hybrid：pgvector 余弦 + tsvector/ILIKE 关键词 + 加权）、search_manuscript（纯向量 + 时间线门）、keyed 人名确定性召回、RRF 融合、可选 LLM 重排、token 预算裁剪、spoiler gate、引用（citations）。
- 向量存储：`asset_embeddings`、`manuscript_block_embeddings`、`global_search_index`（pgvector，Postgres 内嵌）。
- 长期记忆：**无聊天式长期记忆/摘要压缩**。业务事实持久化在 assets/entities/worldline 表；「记忆」= 每次 run 从数据库重新检索。【已确认】无 summarize/compact 调用。
- 数据库事实与聊天历史分离：是——聊天历史在 writer_threads/writer_thread_messages + workflow_events；业务事实在业务表；Agent 只通过工具读业务表。

## 6. 用户未确认设定是否可能进入上下文

【已确认】有严格门控：
- 工具查询全部限定 `lifecycle IN ('seed','canon','material')` —— candidate/draft/simulation 资产永远不进写作上下文。
- spoiler gate：`reveal_after_chapter_order > 当前章序` 的资产不返回。
- worldline 仅 `status='canon'` 事件进时间线；candidate/rejected 事件隔离。
- always_on 同样过生命周期与 spoiler 门。

## 7. AGENTS.md / Skill

- 仓库有 `AGENTS.md`（给 coding agent 的项目规则），**但不参与运行时 Prompt**（无加载代码）。
- **无 Pi Skill 使用**（rg 无结果）；无 prompt template 文件；无 skills 目录加载逻辑。

## 8. Token 限制

- 检索上下文预算：默认 12000 token（planner 可指定 budget.max_context_tokens；`resolveRetrievalTokenBudget`）。
- 模型 contextWindow/maxTokens：来自 `settings`（默认 128000 / 4000–8192，pi-writer-agent.ts openAICompatibleModel）。
- 工具结果裁剪：preview 280 字符；scene/chapter 280；manuscript snippet 240；workspace file 24000。
- 一致性 canon 每条 400 字符；violations ≤20。

## 9. 结论：模型真正看到的消息构成

模型（编排器）看到的 = 1 条 system prompt（代码常量）+ 1 条 JSON 用户消息（请求字段 + 时间线 + 常驻规则 + 检索计划）+ 若干轮 tool_call/tool_result 消息（结果已裁剪）。模型（作曲器）看到的 = system prompt + 1 条 JSON 消息（简报+常驻规则+时间线）。**没有任何对话历史注入**（每次 run 独立）；前端显示的「对话」是任务卡片/线程渲染，不是模型上下文。
