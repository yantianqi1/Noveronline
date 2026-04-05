# 参考项目可借鉴功能点分析

> 对比对象：当前 MiroFish-Novel 写作Agent (`backend/app/services/writer_agent/`)
> 分析日期：2026-04-05

---

## 一、优先开发队列（Top 5）

### P0-1: 写后审计 + 自动修订循环

**来源**: InkOS — `continuity.ts` + `writer-repair.ts`

当前系统写完 scene 后直接存库，没有任何质量检查。InkOS 实现了 33 维连续性审计 + 5 种修订模式，形成"写→审→修→再审"的闭环。

**核心维度（建议首批实现）**:
- OOC 检测（角色行为是否偏离人设）
- 时间线冲突（事件先后矛盾）
- 伏笔健康度（stale hook、未推进线索）
- 词汇疲劳 / AI 痕迹检测（重复用词、标记性短语如"仿佛""不禁""宛如"）

**修订模式（建议首批实现）**:
- `local-fix`: 只修改被标记的句子，其余不动
- `polish`: 仅措辞和节奏优化
- `anti-detect`: 去 AI 痕迹（打断模式、自然化用语、变化句式长度）

**关键源文件**:
- 审计 agent: `可供参考项目/inkos/packages/core/src/agents/continuity.ts`
- 修订 agent: `可供参考项目/inkos/packages/core/src/agents/writer-repair.ts`
- 长跨度疲劳分析: `可供参考项目/inkos/packages/core/src/utils/long-span-fatigue.ts`
- 写后验证: `可供参考项目/inkos/packages/core/src/agents/post-write-validator.ts`
- 审计维度定义（含 fanfic 扩展）: `continuity.ts` 内 33 个 dimension 枚举
- 修订接受判定逻辑: `writer-repair.ts` 内 pre/post 对比（blocking/critical 数不恶化 + 至少一项改善）

---

### P0-2: 写后状态自动提取（Observer/Settler 模式）

**来源**: InkOS — `observer-prompts.ts` + `settler-delta-parser.ts`; NovelForge — `memory_extractors/`

当前系统的 `manage_entity`/`manage_thread`/`manage_relationship` 工具存在于 `tools.py`，但 orchestrator 不会在写作完成后自动调用它们。世界状态需要手动维护。

**InkOS 方案**:
- 写完后用低温 LLM（temperature 0.2）从文本中过度提取 9 类事实：角色、位置、资源、关系、情感、信息、线索（hooks）、时间、身体状态
- Reflector 合并时零推理（只记录文本中明确展示的内容）
- 输出 `RuntimeStateDelta` JSON（hookOps: upsert/mention/resolve/defer + currentStatePatch + newHookCandidates）

**NovelForge 方案**:
- 插件式 memory extractor：`character_dynamic.py`（角色状态）、`scene_state.py`（场景状态）、`relation.py`（关系变化）
- 带置信度评分，用户 preview 后保存（`card.needs_confirmation`）

**关键源文件**:
- InkOS Observer prompts: `可供参考项目/inkos/packages/core/src/agents/observer-prompts.ts`
- InkOS Settler delta parser: `可供参考项目/inkos/packages/core/src/agents/settler-delta-parser.ts`
- InkOS State reducer: `可供参考项目/inkos/packages/core/src/state/state-reducer.ts`
- InkOS Runtime state model: `可供参考项目/inkos/packages/core/src/models/runtime-state.ts`
- NovelForge 角色动态提取: `可供参考项目/NovelForge/backend/app/services/memory_extractors/character_dynamic.py`
- NovelForge 场景状态提取: `可供参考项目/NovelForge/backend/app/services/memory_extractors/scene_state.py`
- NovelForge 关系提取: `可供参考项目/NovelForge/backend/app/services/memory_extractors/relation.py`
- NovelForge 提取 prompt: `可供参考项目/NovelForge/backend/app/bootstrap/prompts/角色动态信息提取.txt`
- NovelForge 关系提取 prompt: `可供参考项目/NovelForge/backend/app/bootstrap/prompts/关系提取.txt`

---

### P0-3: Hook/伏笔生命周期增强

**来源**: InkOS — `hook-*.ts` 系列工具

当前系统 `plot_threads` 表只有 open/progressed/resolved 三态，没有健康度分析和自动排期。

**InkOS Hook 系统**:
- 7 种状态: open → progressing → deferred → resolved
- **mention vs advance 区分**: 提及不等于推进，只有真正的状态变化才算 advance
- **Hook 健康度分析**: stale debt 检测（N 章未推进告警）、pressure window（即将可收束检测）、active cap（默认最多 8 个活跃伏笔）、no-advance window 告警
- **Hook Arbiter**: 新伏笔候选去重（用词提取 + 中文 bigram 相似度匹配，防止同义伏笔重复）
- **Hook Agenda**: Planner 自动排期哪些章推进/收束哪些伏笔，防止 hook debt 爆炸

**关键源文件**:
- Hook 治理总控: `可供参考项目/inkos/packages/core/src/utils/hook-governance.ts`
- Hook 健康度分析: `可供参考项目/inkos/packages/core/src/utils/hook-health.ts`
- Hook 生命周期: `可供参考项目/inkos/packages/core/src/utils/hook-lifecycle.ts`
- Hook 去重仲裁: `可供参考项目/inkos/packages/core/src/utils/hook-arbiter.ts`
- Hook 自动排期: `可供参考项目/inkos/packages/core/src/utils/hook-agenda.ts`
- Hook 数据模型: `可供参考项目/inkos/packages/core/src/models/runtime-state.ts` (HookRecord schema)

---

### P0-4: Input Governance 分层（Planner → Composer 分离）

**来源**: InkOS — `planner.ts` + `composer.ts`

当前系统 orchestrator 一步到位收集所有上下文，没有"先规划意图→再按相关性筛选上下文"的分离。这导致上下文膨胀和不精准。

**InkOS 方案**:
- **Planner**: 读取 author_intent + current_focus + story_bible + volume_outline + chapter_summaries + book_rules → 输出 `ChapterIntent`（goal, must-keep, must-avoid, conflicts, hook agenda）
- **Composer**: 根据 ChapterIntent 按相关性从 7 个 truth files 中筛选上下文，构建 4 层 RuleStack:
  - L1: hard_facts（优先级 100）— 不可违反的世界设定
  - L2: author_intent（优先级 80）— 作者长期方向
  - L3: planning（优先级 60）— 章节规划
  - L4: current_task（优先级 70）— 当前任务指令
- 输出 governance artifacts: `chapter-XXXX.intent.md` + `chapter-XXXX.context.json` + `chapter-XXXX.rule-stack.yaml` + `chapter-XXXX.trace.json`

**关键源文件**:
- Planner agent: `可供参考项目/inkos/packages/core/src/agents/planner.ts`
- Composer agent: `可供参考项目/inkos/packages/core/src/agents/composer.ts`
- Input governance model: `可供参考项目/inkos/packages/core/src/models/input-governance.ts`
- Context filter: `可供参考项目/inkos/packages/core/src/utils/context-filter.ts`
- POV filter: `可供参考项目/inkos/packages/core/src/utils/pov-filter.ts`
- Memory retrieval: `可供参考项目/inkos/packages/core/src/utils/memory-retrieval.ts`

---

### P0-5: 风格指纹自动提取

**来源**: InkOS — `style-analyzer.ts`

当前系统的角色语音（`get_character_voice` 工具）依赖手动维护的 `speech_style`/`verbal_habits_json`/`example_quotes_json` 字段。InkOS 用纯统计方法（不依赖 LLM）自动提取风格指纹。

**InkOS 方案**:
- **句长分布**: 均值、中位数、标准差、分布直方图
- **段落长度统计**: 每段句数分布
- **词汇多样性**: Type-Token Ratio（中文按字符计算）
- **修辞模式频率**: 比喻、排比、反问、夸张、拟人、短句节奏
- **开头模式**: 统计句首前2字的高频模式
- **对话指纹**: 提取每个角色近5章的说话模式，用于语音一致性检查
- 可从外部文件导入风格（`inkos style import <file>`）

**关键源文件**:
- 风格分析器: `可供参考项目/inkos/packages/core/src/agents/style-analyzer.ts`
- 对话指纹提取逻辑: `可供参考项目/inkos/packages/core/src/agents/writer.ts`（buildUserPrompt 中 dialogue fingerprint 部分）
- 风格 CLI 命令: `可供参考项目/inkos/packages/cli/src/commands/style.ts`

---

## 二、InkOS 可借鉴功能全集

> 项目路径: `可供参考项目/inkos/`
> 技术栈: TypeScript + Node.js + SQLite + Zod + React (Studio)
> 核心架构: 10-agent 串行 pipeline（Planner → Composer → Writer → Observer → Reflector → Settler → ChapterAnalyzer → LengthNormalizer → ContinuityAuditor → WriterRepair）

### 2.1 时序记忆数据库

每个事实有 `validFromChapter` / `validUntilChapter`，可查"角色X在第N章知道什么"。支持知识边界隔离（角色只能获取自己视角能知道的信息）。

**源文件**:
- Memory DB: `packages/core/src/state/memory-db.ts`
- Runtime state model: `packages/core/src/models/runtime-state.ts`（Fact schema 含 validFromChapter/validUntilChapter/sourceChapter）
- Memory retrieval: `packages/core/src/utils/memory-retrieval.ts`

### 2.2 长度治理

双模计数（`zh_chars` vs `en_words`）、soft/hard 区间、超限自动 normalize（单次，防止破坏性循环）、length telemetry 追踪（writerCount → postNormalizerCount → postReviseCount → finalCount）。

**源文件**:
- 长度指标: `packages/core/src/utils/length-metrics.ts`
- 长度治理模型: `packages/core/src/models/length-governance.ts`
- 长度规范器 agent: `packages/core/src/agents/length-normalizer.ts`

### 2.3 POV 感知上下文过滤

根据当前 POV 角色过滤上下文，限制 AI 只注入该角色能知道的信息，防止"上帝视角"泄漏。

**源文件**:
- POV filter: `packages/core/src/utils/pov-filter.ts`
- Context filter: `packages/core/src/utils/context-filter.ts`

### 2.4 章节分析器（ChapterAnalyzer）

对每章进行类型分类（Progression/Setup/Transition/Payoff/Combat），聚合摘要为时序记录。

**源文件**:
- Chapter analyzer agent: `packages/core/src/agents/chapter-analyzer.ts`

### 2.5 Genre Profile 系统（15 个内置类型）

每个 genre 定义：chapterTypes、fatigueWords（疲劳词列表）、numericalSystem flag、powerScaling、eraResearch、pacingRule、satisfactionTypes、auditDimensions。支持自定义 genre。

**源文件**:
- Genre model: `packages/core/src/models/genre-profile.ts`
- Genre 定义目录: `packages/core/genres/`（litrpg.md, xianxia.md, xuanhuan.md, sci-fi.md 等 15 个）

### 2.6 Fanfic 支持

4 种模式（canon/au/ooc/cp）、原作角色档案导入、信息边界控制（前后分歧点的角色知识追踪）、fanfic 专属审计维度。

**源文件**:
- Fanfic canon importer: `packages/core/src/agents/fanfic-canon-importer.ts`（如存在）
- Fanfic 审计维度: `packages/core/src/agents/continuity.ts`（fanfic dimensions 部分）
- Fanfic CLI: `packages/cli/src/commands/fanfic.ts`

### 2.7 Daemon 自主写作 + Webhook 通知

`inkos up` 启动后台守护进程，按计划自动写章节。支持 Telegram、飞书、企业微信、自定义 webhook（HMAC-SHA256 签名）通知。

**源文件**:
- Pipeline runner: `packages/core/src/pipeline/runner.ts`
- CLI daemon: `packages/cli/src/commands/` (up 命令)

### 2.8 Multi-Model 路由

不同 agent 可配置不同 LLM：writer 用 Claude（创意），auditor 用 GPT-4o（快速），radar 用本地模型（免费）。

**源文件**:
- LLM provider: `packages/core/src/llm/provider.ts`
- Model config CLI: `packages/cli/src/commands/` (config set-model)

### 2.9 导入/续写已有小说

从外部文本反向工程所有 7 个 truth files（当前状态、伏笔、章节摘要等），自动生成风格指纹，支持断点续传（`--resume-from <chapter>`）。

**源文件**:
- Import 命令: `packages/cli/src/commands/import.ts`
- State bootstrap: `packages/core/src/state/state-bootstrap.ts`

### 2.10 Studio Web 工作台

可视化 hook 时间线、审计仪表盘（issue 分类统计）、长度遥测图表、风格指纹对比、token 用量追踪。

**源文件**:
- Studio pages: `packages/studio/src/pages/`（Analytics.tsx, TruthFiles.tsx, StyleManager.tsx, DaemonControl.tsx 等）

---

## 三、NovelForge 可借鉴功能全集

> 项目路径: `可供参考项目/NovelForge/`
> 技术栈: Electron + Vue 3 + FastAPI + SQLModel + LangChain
> 核心架构: 双 Agent（灵感助手 + 工作流智能体）+ 可视化工作流 DSL

### 3.1 可视化工作流 DSL

用户可自定义写作流程，用代码式 DSL 编排节点（AI.LLM → Card.Create → AI.StructuredGenerate），支持条件分支（Logic.Condition）、等待（Logic.Wait）、批量操作（AI.BatchStructured）。有 checkpoint/恢复机制。

**源文件**:
- 工作流引擎: `backend/app/services/workflow/`
- DSL 解析器/验证器: `backend/app/services/workflow/validator.py`
- 节点注册表: `backend/app/services/workflow/registry.py`
- AI 节点: `backend/app/services/workflow/nodes/ai/`（LLM, StructuredGenerate, BatchStructured, Agent, Debate）
- Card 节点: `backend/app/services/workflow/nodes/card/`（Create, BatchUpsert, Update, Query, Delete）
- Logic 节点: `backend/app/services/workflow/nodes/logic/`（SelectProject, Wait, Expression, Condition）
- 执行状态: `backend/app/services/workflow/engine/execution_state.py`
- Trigger 系统: `backend/app/services/workflow/trigger_extractor.py`
- 前端编辑器: `frontend/src/renderer/src/views/workflow/CodeWorkflowEditor.vue`

### 3.2 Schema 驱动的卡片系统

所有创作内容用 JSON Schema 约束（角色卡、场景卡、概念卡、物品卡、组织卡、大纲卡、正文卡）。AI 输出经 schema 验证。

**源文件**:
- Card 模型: `backend/app/db/models.py`（Card, CardType）
- 内置卡片类型: `backend/app/bootstrap/card_types.py`
- 卡片 API: `backend/app/api/endpoints/cards.py`

### 3.3 Context @DSL 声明式上下文注入

用 DSL 语法声明式拉取上下文：`@type:角色卡[previous:global].{content.name,content.personality}`。支持 `@parent`、`@self`、`[previous:N]`、`[index=filter:条件]` 等修饰符。

**源文件**:
- Context DSL 解析: `backend/app/api/endpoints/context.py`
- 模板字段: `backend/app/db/models.py`（Card.ai_context_template, CardType.default_ai_context_template）

### 3.4 Instruction Flow 逐字段生成

AI 逐字段输出 `{"op":"set","path":"/field","value":...}` 指令，前端实时预览每个字段的生成结果，用户确认后才保存。

**源文件**:
- 指令执行器: `backend/app/services/ai/generation/`
- 生成 prompt: `backend/app/bootstrap/prompts/内容生成.txt`
- 前端指令流处理: `frontend/src/renderer/src/components/` (相关 card 编辑组件)

### 3.5 AI 修改确认机制

`card.ai_modified` + `card.needs_confirmation` + `card.last_modified_by`（'user'|'ai'），AI 修改的内容标记为待确认，用户 review 后生效。

**源文件**:
- Card 模型: `backend/app/db/models.py`（ai_modified, needs_confirmation, last_modified_by 字段）
- Assistant service: `backend/app/services/ai/assistant/assistant_service.py`

### 3.6 知识图谱动态更新

写完章节后自动提取角色动态信息、场景状态、关系变化。带置信度评分，支持用户 preview-before-save。Provider pattern 支持 SQLite 和 Neo4j 切换。

**源文件**:
- KG provider: `backend/app/services/kg_provider.py`
- 关系图谱服务: `backend/app/services/relation_graph_service.py`
- 角色动态提取: `backend/app/services/memory_extractors/character_dynamic.py`
- 场景状态提取: `backend/app/services/memory_extractors/scene_state.py`
- 关系提取: `backend/app/services/memory_extractors/relation.py`
- 提取 prompts: `backend/app/bootstrap/prompts/角色动态信息提取.txt`, `场景状态提取.txt`, `关系提取.txt`

### 3.7 伏笔追踪系统

ForeshadowItem 模型：type（goal/item/person/other）+ status（open/resolved）+ chapter_id 关联。前端有专门的伏笔面板。

**源文件**:
- 伏笔模型: `backend/app/db/models.py`（ForeshadowItem）
- 伏笔 API: `backend/app/api/endpoints/foreshadow.py`
- 前端面板: `frontend/src/renderer/src/components/` (ForeshadowPanel)

### 3.8 多 Agent 辩论节点

工作流中的 `AI.Debate` 节点支持多个 AI agent 对同一问题进行多轮辩论推理。

**源文件**:
- Debate 节点: `backend/app/services/workflow/nodes/ai/` (Debate 相关)

### 3.9 灵感助手（Tool-augmented Chat）

独立的对话式 AI 助手，带 7 个工具（search_cards, create_card, update_card, modify_card_field, replace_field_text, get_card_type_schema, read_card_content），支持 React protocol 降级。

**源文件**:
- Assistant service: `backend/app/services/ai/assistant/assistant_service.py`
- Assistant tools: `backend/app/services/ai/assistant/tools.py`
- 系统 prompt: `backend/app/bootstrap/prompts/灵感对话.txt`, `灵感对话-React.txt`

### 3.10 内容审核工作流

章节审核 + 阶段审核，AI 对已写内容进行结构化审核。

**源文件**:
- 审核 prompt: `backend/app/bootstrap/prompts/章节审核.txt`, `阶段审核.txt`
- 审核卡片: `backend/app/bootstrap/card_types.py`（内容审核卡片，singleton per project）

### 3.11 三级大纲层次

分卷大纲（Volume）→ 阶段大纲（Stage，多章故事弧）→ 章节大纲（Chapter，per-chapter beat sheet with entity_list）。

**源文件**:
- 大纲卡片定义: `backend/app/bootstrap/card_types.py`（分卷大纲、阶段大纲、章节大纲 card types）

---

## 四、AI-Novel-Lab 可借鉴功能全集

> 项目路径: `可供参考项目/ai-novel-lab/`
> 技术栈: React 19 + Vite（阅读前端）+ DeepSeek（LLM）+ Markdown 文件系统
> 核心架构: AGENTS.md 定义的 4 阶段 SOP（上下文检索 → 写作 → 归档 → 进度更新）

### 4.1 结构化进度追踪

每章记录：状态（待写/已完成/优化中）、字数、完成日期、关键人物、一致性检查结果。全局 progress.md 作为看板。

**源文件**:
- 进度追踪: `progress.md`（492 行，100 章完整记录）
- 状态定义: 待写 / 已完成 / 优化中

### 4.2 前 N 章回看 + 全局摘要

写新章前必须回看前 3 章 + `workspace/summary.md` 全局摘要，防止情节矛盾（"吃书"）。

**源文件**:
- Agent SOP: `AGENTS.md`（Phase 1: Context Retrieval 部分）
- 摘要机制: `workspace/summary.md`（聚合已写章节的摘要）

### 4.3 波次修订系统

P0-P2 优先级分波修订。修前修后对比评分（叙事连贯度 73/100 → 93/100）。修订类型：时间线混乱、角色工具化、科技跳跃、语言重复、爽点分布不均。

**源文件**:
- 修订总结报告: `优化完成总结.md`
- 修订策略: 问题分类 → 优先级分波 → 最小干预原则 → 前后评分对比

### 4.4 禁止要素清单

明确的不允许出现的内容清单：不提及章节号、不用真实公司名、不 meta 引用、不系统升级结局。持久化于大纲文档中。

**源文件**:
- 禁止要素: `章节大纲.md`（禁忌事项部分）

### 4.5 爽点密度指标

每章保证 3+ 个小高光 + 1 个大高潮。冲突发生后 1-3 章内反击。敌人"智商在线、运气极差，死得有节奏"。

**源文件**:
- 爽文法则: `章节大纲.md`（爽文核心法则部分）
- Agent 写作规则: `AGENTS.md`（Phase 2 写作规范）

### 4.6 能力等级渐进系统

角色能力有明确等级线（T5→T10→超脑），每个等级解锁新能力，有对应的章节区间。防止能力跳跃或降级。

**源文件**:
- 能力体系: `章节大纲.md`（超脑系统 Level 1-3 + Terminal 部分）

### 4.7 角色声音模板

每个主要角色有固定的声音特征模板（冷酷但保留人性、治愈系、野心女王、冰美人等），用于写作时保持语音一致性。

**源文件**:
- 角色声音: `章节大纲.md`（角色定义部分，含语音风格描述）

### 4.8 Bridge 章节插入

修订时发现节奏不平滑，额外插入 10 个桥接章节平滑过渡，而非修改已有章节。

**源文件**:
- Bridge 策略: `优化完成总结.md`（10 个新桥接章节的记录）

---

## 五、当前系统已有优势（无需借鉴）

| 能力 | 说明 |
|------|------|
| 两阶段编排 | cheap 模型收集上下文 → 强模型写作，已实现 |
| 丰富的数据模型 | entities, relationships, plot_threads, timeline events, world_rules + evidence chains |
| 并行工具执行 | ThreadPoolExecutor 并行调用工具 |
| FTS5 全文检索 | Trigram tokenizer 支持中文，14 张 FTS 表 |
| 手稿续写系统 | manuscript_blocks + continuation context builder + token budget 分配 |
| outline 版本管理 | 快照 + 恢复，每章最多 20 个版本 |
| 证据链追踪 | world_rule_evidence + entity_evidence 关联源章节 |
| Preset 系统 | 用户自定义写作风格 prompt，per-project 或 global |

---

## 六、功能来源速查表

| 功能 | 来源项目 | 核心文件 |
|------|---------|---------|
| 33维连续性审计 | InkOS | `inkos/packages/core/src/agents/continuity.ts` |
| 5种修订模式 | InkOS | `inkos/packages/core/src/agents/writer-repair.ts` |
| Observer/Settler 状态提取 | InkOS | `inkos/.../agents/observer-prompts.ts`, `settler-delta-parser.ts` |
| Hook 健康度分析 | InkOS | `inkos/.../utils/hook-health.ts` |
| Hook 自动排期 | InkOS | `inkos/.../utils/hook-agenda.ts` |
| Hook 去重仲裁 | InkOS | `inkos/.../utils/hook-arbiter.ts` |
| Planner → Composer 分离 | InkOS | `inkos/.../agents/planner.ts`, `composer.ts` |
| 4层规则栈 | InkOS | `inkos/.../models/input-governance.ts` |
| 风格指纹分析 | InkOS | `inkos/.../agents/style-analyzer.ts` |
| 长度治理 | InkOS | `inkos/.../utils/length-metrics.ts`, `agents/length-normalizer.ts` |
| 时序记忆数据库 | InkOS | `inkos/.../state/memory-db.ts` |
| POV 感知过滤 | InkOS | `inkos/.../utils/pov-filter.ts` |
| Genre Profile 系统 | InkOS | `inkos/.../models/genre-profile.ts`, `genres/` |
| Fanfic 支持 | InkOS | `inkos/.../agents/fanfic-canon-importer.ts` |
| Daemon 自主写作 | InkOS | `inkos/.../pipeline/runner.ts` |
| Multi-Model 路由 | InkOS | `inkos/.../llm/provider.ts` |
| 导入已有小说 | InkOS | `inkos/.../cli/src/commands/import.ts` |
| 可视化工作流 DSL | NovelForge | `NovelForge/backend/app/services/workflow/` |
| Schema 驱动卡片 | NovelForge | `NovelForge/backend/app/bootstrap/card_types.py` |
| Context @DSL | NovelForge | `NovelForge/backend/app/api/endpoints/context.py` |
| Instruction Flow | NovelForge | `NovelForge/backend/app/services/ai/generation/` |
| AI 修改确认机制 | NovelForge | `NovelForge/backend/app/db/models.py` |
| 知识图谱动态更新 | NovelForge | `NovelForge/backend/app/services/memory_extractors/` |
| 伏笔追踪面板 | NovelForge | `NovelForge/backend/app/api/endpoints/foreshadow.py` |
| 多 Agent 辩论 | NovelForge | `NovelForge/.../workflow/nodes/ai/` |
| 灵感助手 | NovelForge | `NovelForge/.../ai/assistant/assistant_service.py` |
| 三级大纲层次 | NovelForge | `NovelForge/backend/app/bootstrap/card_types.py` |
| 进度追踪看板 | AI-Novel-Lab | `ai-novel-lab/progress.md` |
| 前N章回看+全局摘要 | AI-Novel-Lab | `ai-novel-lab/AGENTS.md` |
| 波次修订系统 | AI-Novel-Lab | `ai-novel-lab/优化完成总结.md` |
| 禁止要素清单 | AI-Novel-Lab | `ai-novel-lab/章节大纲.md` |
| 爽点密度指标 | AI-Novel-Lab | `ai-novel-lab/章节大纲.md` |
| Bridge 章节插入 | AI-Novel-Lab | `ai-novel-lab/优化完成总结.md` |
