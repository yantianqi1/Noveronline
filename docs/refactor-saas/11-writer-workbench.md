# 11. Writer Workbench

更新时间：`2026-06-27`

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
Top Bar
  project/chapter/scene
  writing mode
  run/save/review
  active workflow status

Left Rail
  chapters
  scenes
  outline
  manuscript TOC

Center
  editor / manuscript reader / outline editor

Right Rail
  context
  assets
  worldline references
  reviewer
  agent trace
  tool results
```

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
- Assets。
- Worldline。
- Reviewer。
- Trace。
- Tools。

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

### Stream

```http
GET /v1/writer-runs/{runId}/events
Accept: text/event-stream
```

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
