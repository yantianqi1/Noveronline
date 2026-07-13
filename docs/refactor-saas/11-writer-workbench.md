# 11. Writer Workbench

更新时间：`2026-07-13`

## 模块定位

写作台是主要写作界面。它承载智能体写作记录、章节/场景管理、正文生成、续写、审校、手稿编译和世界数据更新。

旧写作台已有复杂能力，新系统必须完整覆盖，并让 UI 更像专业写作软件而不是调试面板。

## 旧功能覆盖

旧 writer 能力：

- writer-agent run。
- world-update。
- scene list/detail/update/delete/reorder/compile。
- presets。
- chapters CRUD。
- outline versions / restore。
- manuscript commit/list/update/delete/reorder/tag/move/export。
- continuation context。
- project migration。
- book plans。
- book run。
- forbidden lexicon。
- one-click actions：
  - complete outline。
  - align words。
  - scan lexicon。
  - fill relationships。
  - continue chapter。
- reviewer。
- dedup extractor。
- tool render cards。
- command palette。
- keyboard shortcuts。

新系统必须全部覆盖。

## 页面布局

```text
Compact Header
  Writer Agent identity / active workflow status / technical details

Primary Agent Thread
  author instruction
  retrieval and tool activity
  streamed candidate prose
  cancel / explicit adoption
  persistent mode switcher + composer + context attachments

Artifact Workspace
  manuscript editor
  chapter / scene structure
  reviewer and manuscript-derived asset candidates
  planning / rules / commands / export

Authorized Technical Drawer
  run / trace ids
  replay cursor
  raw event metadata and redacted trace export
```

桌面端为 Agent thread 与稿件 artifact 双栏分屏，作者始终先看到主要交互区；稿件区使用 `稿件 / 章节 / 审校 / 工作室` 互斥标签，不再把所有表单纵向平铺。小于 `960px` 时先显示完整 Agent thread，再显示稿件标签区。该结构提炼自 OpenHands 的 conversation/workspace 分屏、LangGraph Agent Chat UI 的 chat/artifact 分栏以及 assistant-ui 的 thread/composer/tool-call 组合，不复制其品牌视觉。

旧 `writer-workbench-prose-first`、`writer-studio-grid`、折叠 composer 和深色 `writer-agent-rail` 长页布局已退役，不得恢复或作为截图基线。

## 零起点写作入口（规划中）

完整方案见 [28. Zero-start Writer and Manuscript Asset Distillation](./28-zero-start-writer-and-manuscript-asset-distillation.md)。本节是待实现 Writer 契约，不表示现有 Overview 或 Writer 已支持该旅程。

- 空项目首屏直接进入 Writer Workbench，提供 `从一个想法开始` 和 `上传已有文本` 两条平等路径，不显示“必须先上传”的阻断页。
- idea-first 允许在没有 source file、Seed、ontology、graph 或 Worldline 的情况下建立故事前提、book plan、chapter/scene，然后手写正文或启动 Writer draft。
- Agent 生成 draft 必须通过独立 adoption API 才能进入 manuscript；空项目入口不自动生成 candidate asset、canon 或 manuscript。
- upload-first 保留现有 Upload -> Seed 旅程，Seed 完成后再向 Writer 建立或选择写作结构，不重复创建已有 chapter/scene/block。

## Writer 正文反哺与生命周期门（规划中）

- 资产提取只能从已保存的 manuscript block/version 检查点，或已显式采用的 Writer draft 增量启动。不在每次按键、普通 autosave 或 token stream 上启动。
- 提取结果仅写 `candidate + disabled`，不写 canon、manuscript 或既有资产。用户采用、合并、拒绝或暂缓后才改变资产生命周期。
- Writer 默认检索只读取 `enabled = true` 且 lifecycle 为 `seed | canon | material | manuscript` 的资产，排除 `candidate | draft | simulation | archived`。
- 待审 candidate 只能通过独立 preview contract 显式预览，并在 writing brief 中标记 `unconfirmed_candidate = true`，不混入默认 `query_assets`。完整 manuscript 正文仍由专属 manuscript context 工具按受控范围读取。

## 工作模式

### Draft Mode

写当前场景。

输入：

- project。
- chapter。
- scene。
- POV。
- involved entities。
- scene focus。
- user instruction。
- selected worldline path。
- style assets。

输出：

- draft revision。
- writer tokens。
- tool trace。

### Continue Mode

续写当前章节或场景。

必须使用：

- previous manuscript blocks。
- continuation context。
- dedup constraints。
- current chapter outline。

### Outline Mode

维护章节大纲。

覆盖旧 outline view 和 outline versions。

### Manuscript Mode

阅读、编排和导出手稿。

覆盖：

- manuscript TOC。
- block reorder。
- block tag。
- export。

### Review Mode

审校和修订。

覆盖 `writer_reviewer`。

## WriterRunWorkflow

```text
validate_request
load_project_context
retrieval_planning
orchestrator_tool_loop
compose_writing_brief
writer_composer_stream
save_draft_revision
post_process
review_optional
dedup_extract_optional
finalize
```

## Agent 分层

### Retrieval Planner

模块 key：`writer_retrieval_planner`

职责：

- 判断写作前需要哪些工具。
- 不直接写正文。
- 输出检索计划。

### Orchestrator

模块 key：`writer_orchestrator`

职责：

- 调用工具。
- 收集项目上下文。
- 查询实体、关系、世界规则、资产、worldline、manuscript。
- 生成 writing brief。

### Composer

模块 key：`writer_composer`

职责：

- 根据 writing brief 写正文。
- 可流式输出。
- 不直接查询数据库。

### Reviewer

模块 key：`writer_reviewer`

职责：

- 检查修辞密度、场景雷同、POV 漂移、时间线冲突、重复句式。
- 输出 issues。

### Dedup Extractor

模块 key：`writer_dedup_extractor`

职责：

- 从已采用章节中抽取重复风险模式。
- 写入 dedup index。

## 数据模型

### Chapters

```text
chapters
  tenant_id
  project_id
  chapter_id
  chapter_order
  title
  status
  summary
  outline_json
  pov_entity_id
  created_at
  updated_at
```

### Scenes

```text
scenes
  tenant_id
  project_id
  scene_id
  chapter_id
  scene_order
  title
  status
  content
  writing_brief_json
  involved_entities_json
  source_worldline_path_ids
```

### Draft Revisions

```text
drafts
  tenant_id
  project_id
  draft_id
  chapter_id
  scene_id
  run_id
  status
  content
  metadata_json
  created_by
  created_at

draft_events
  tenant_id
  draft_id
  event_id
  event_type
  payload_json
  created_at
```

### Manuscript Blocks

```text
manuscript_blocks
  tenant_id
  project_id
  block_id
  chapter_id
  scene_id
  block_order
  content
  tags_json
  source_draft_id
  status
```

可以继续物化到 `assets` 作为 `manuscript_block`，但主写作表建议独立。

## Tool System

旧 writer tools 必须保留语义：

- query_entity。
- query_relationship。
- query_graph_neighbors。
- global_search。
- query_worldline_session。
- list_worldline_branches 语义需改名或兼容为 list_worldline_paths/current_world。
- manage_entity。
- manage_thread。
- manage_world_rule。
- manage_relationship。
- record_character_event。
- propose_*。
- splice/rewrite。
- forbidden lexicon。

新工具执行规则：

- read tools 可并行。
- write tools 串行。
- 每个 tool call 写 trace。
- write tool 需要权限。
- candidate/propose tool 默认不写 canon。

## UI 细节

### Editor

目标使用 Tiptap：

- 段落。
- selection。
- inline suggestion。
- reviewer issue marks。
- rewrite span。
- comments。

第一阶段可保留 textarea，但文档目标是富文本编辑器。

### Right Rail

Tabs：

- Context。
- 候选资产：默认展示当前正文检查点的未决候选，支持接受为正典/素材、合并到已有资产和拒绝。
- Assets / Worldline：已采用上下文和显式引用。
- Worldline。
- Reviewer。
- Trace。
- Tools。

候选项必须显示类型、摘要、章节/场景/源版本、短证据和 `新增 | 更新 | 冲突` 文本状态。批量审阅按类型和目标资产分组，冲突合并必须展示现值、候选差异和最终结果。

小于 `860px` 时 Writer 不保留固定三栏：正文为主视图，章节树进入 Drawer，候选资产进入底部 Sheet、抽屉或独立详情视图；保存、提取和候选数量入口保持可达。触控目标不小于 `44px`，状态不仅用颜色表达。

### One-click Actions

不要散落按钮。统一到 command row：

- 完善大纲。
- 对齐字数。
- 扫描禁用词。
- 补关系。
- 续写章节。

每个 action 都是 workflow 或短任务，并显示 trace。

## API

### Writer Run

```http
POST /v1/projects/{projectId}/writer-runs
```

```http
GET /v1/writer-runs/{runId}
```

受 tenant/project 权限保护的 run read 返回 `mode` 与 `instruction`，用于刷新后恢复作者消息；不得把作者指令写入 URL query。

### Stream

```http
GET /v1/writer-runs/{runId}/events
Accept: text/event-stream
```

Next Writer Agent must expose replay as an explicit recovered-stream cursor action. The technical drawer submits `after_event_id` together with selected run/trace metadata through a GET form so refresh/reopen keeps the chosen replay window. Writer Events / Trace Events diagnostics display event metadata only and never serialize raw payload JSON. The authenticated primary thread may concatenate the current run's public `writer.token` values into candidate prose; it must not render prompt snapshots, provider responses, credentials, `credential_ref`, object keys, raw tool payload JSON, or adopted/private manuscript bodies.

The 2026-07-07 blue long-page browser screenshot and its `Writer Workbench` visual baseline are retired. They verified only fail-closed replay metadata and must not be reused as current UI evidence. Fresh Agent-first desktop/mobile browser evidence is required before claiming visual certification for this layout.

### Adopt Draft

```http
POST /v1/drafts/{draftId}/adoptions
```

### Reviewer

```http
POST /v1/drafts/{draftId}/reviews
```

### Manuscript Export

```http
GET /v1/projects/{projectId}/manuscript/export
```

当前 SaaS API 只实现 metadata-only export manifest/readiness。该 endpoint 返回 project id、`metadata_manifest` format、block count、total word count、generated timestamp 和 block id/order/word count metadata；它不返回正文、不生成 fake PDF/DOCX/TXT、不设置 `exported_at` artifact 成功状态。真正内容导出仍需后续显式 artifact/export service，并必须继续遵守 draft/manuscript 正文不进入公共 API/UI/events/logs 的边界。

## 旧功能映射

| 旧功能 | 新功能 |
|---|---|
| useWriterState | writer workspace state store + server data |
| SceneEditor | Tiptap scene editor |
| SceneListPanel | chapter/scene navigator |
| ManuscriptTocPanel | manuscript navigator |
| ManuscriptProseView | manuscript reader/editor |
| ContinuationContextPanel | context tab |
| ReviewerPanel | review tab |
| AgentTracePanel | unified trace drawer/rail |
| AgentProgressPanel | workflow progress |
| PresetEditor | project/tenant writing presets |
| book plan | book planning workflow |
| forbidden lexicon | asset + writer constraint |

## 验收清单

- 能创建章节和场景。
- 能运行 writer agent 并看到 stream。
- writer run 失败显示真实错误。
- 能查看 tool calls 和 prompt trace。
- 能采用 draft 到 manuscript。
- 能运行 reviewer。
- 能导出手稿。
- 能引用 worldline path。
- 能从角色控制 interaction 转入章节草稿。
- 同一 scene 并发写有锁或冲突提示。
