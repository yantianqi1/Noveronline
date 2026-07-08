# 07. Story Graph

更新时间：`2026-07-07`

## 模块定位

故事图谱是小说世界的可视化结构层。它不只是“节点和边”，还应该帮助作者理解：

- 谁是谁。
- 谁和谁有什么关系。
- 哪些事件推动关系变化。
- 哪些世界规则约束角色行动。
- 哪些伏笔/剧情线尚未解决。
- 当前选中的角色组合可以生成哪些羁绊和支线。

旧图谱页面问题：

- 构建、概览、筛选、节点详情、多选、羁绊生成、档案生成挤在一个页面。
- D3 直接渲染复杂图，节点多时容易乱。
- 图谱缺少故事语义分层。
- 证据和 canon/candidate 状态不够突出。

新图谱要以可读性和创作操作为目标重做。

## 旧功能覆盖

旧能力：

- 选择项目。
- `buildGraph` 启动图谱构建任务。
- `getProjectGraph` 读取 graph。
- GraphBuildConsole 展示构建进度。
- WorldOverviewDashboard 展示世界概览。
- StoryGraphPanel 渲染图谱。
- StoryGraphInspector 查看节点/边。
- 节点类型过滤。
- 边标签开关。
- 单选/多选。
- GraphBondGeneratorDialog 基于选中节点生成羁绊/支线。
- generateArchiveCandidates / generateArchives 生成档案。

新系统必须覆盖并拆清楚模式。

## 工作模式

### Explore Mode

默认模式。

用途：

- 浏览故事世界。
- 搜索角色/组织/地点/规则/事件。
- 查看节点和边详情。
- 看证据片段。

UI：

- 左侧图层/过滤。
- 中央图谱。
- 右侧 inspector。

### Build Mode

用途：

- 构建或重建图谱。
- 查看输入数据健康状态。
- 查看构建阶段。
- 查看失败 trace。

不和浏览模式混在一起。构建完成后回到 Explore。

### Curate Mode

用途：

- 合并重复节点。
- 修改节点类型。
- 隐藏噪声节点。
- 标记 canon/candidate。
- 绑定实体和档案。

操作必须进入审计日志。

### Compose Mode

用途：

- 多选角色/组织/事件。
- 生成羁绊。
- 生成支线剧情。
- 保存到资产库或 plot_threads。

覆盖旧 GraphBondGeneratorDialog。

## 图谱数据模型

旧 `graph_*` 表可作为起点，但需要增强：

### Graph Snapshot

```text
story_graph_snapshots
  tenant_id
  project_id
  graph_id
  version
  status
  build_run_id
  source_version_hash
  node_count
  edge_count
  created_at
```

### Graph Node

```text
story_graph_nodes
  tenant_id
  project_id
  graph_id
  node_id
  canonical_entity_id
  node_type
  title
  summary
  lifecycle
  importance
  cluster_id
  attributes_json
  evidence_count
  created_at
```

node_type：

- character
- organization
- faction
- location
- artifact
- plot_event
- plot_thread
- world_rule
- concept
- manuscript_scene

lifecycle：

- seed
- candidate
- canon
- simulation
- manuscript

### Graph Edge

```text
story_graph_edges
  tenant_id
  project_id
  graph_id
  edge_id
  source_node_id
  target_node_id
  edge_type
  label
  summary
  weight
  lifecycle
  attributes_json
  evidence_count
```

edge_type：

- relationship
- participates_in
- belongs_to
- opposes
- constrained_by
- causes
- reveals
- foreshadows
- located_in
- mentions

### Evidence

```text
story_graph_evidence
  tenant_id
  project_id
  graph_id
  evidence_id
  owner_type
  owner_id
  source_type
  source_id
  chapter_id
  segment_id
  snippet
  confidence
```

## 构建输入

优先从结构化主库读取：

- entities
- relationships
- entity_evidence
- character_events
- relationship_events
- world_events
- plot_threads
- world_rule_evidence
- chapter_meta
- scenes
- assets/archive_entity

旧 artifact 只在迁移导入时使用：

- reading_notes
- seed_analysis
- story_memory
- local_block_facts
- block_analyses
- chapter_continuity

## Graph Build Workflow

```text
StoryGraphBuildWorkflow
  validate_project
  load_canon_sources
  compute_source_hash
  extract_node_candidates
  merge_nodes
  extract_edge_candidates
  resolve_edges
  cluster_graph
  persist_snapshot
  build_view_indexes
  finalize
```

构建进度要覆盖旧阶段：

- load_artifacts
- collect_entities
- merge_nodes
- build_relationships
- build_events
- build_artifacts_rules
- persist
- finalize

### P5 Skeleton Status

当前 skeleton 已落地：

- Postgres `story_graph_*` target schema、RLS、grants 和基础索引。
- Go API `POST /v1/projects/{projectId}/story-graph/builds`，在有 Temporal + admission store 时写 `workflow_runs` / `workflow_events` 后启动 `StoryGraphBuildWorkflow` 到 `graph-heavy`；无 backend 时返回 `STORY_GRAPH_BUILD_BACKEND_UNCONFIGURED`。
- Go API `GET /v1/projects/{projectId}/story-graph/current`，只读取 latest public snapshot counts/metadata；无 reader 时返回 `STORY_GRAPH_BACKEND_UNCONFIGURED`。
- Go API `GET /v1/projects/{projectId}/story-graph/views/{viewId}`、`/nodes/{nodeId}`、`/edges/{edgeId}`，读取 latest graph viewport 和 latest current graph 内的单节点/单边 public detail；node/edge detail 先解析 current snapshot graph id 再查询目标行，避免同一 node/edge id 命中旧 snapshot。响应递归清洗 attributes 中的 prompt/body/content/raw text/snippet/credential 字段，且不返回 evidence snippets。
- Go API `GET /v1/projects/{projectId}/story-graph/nodes/{nodeId}/evidence`、`/edges/{edgeId}/evidence`、`/layouts/{viewId}`、`/clusters`，读取 latest graph 的 public evidence source metadata、sanitized layout payload 和 sanitized cluster summaries；默认公共读侧不返回 snippet/raw text/prompt/credential。`include_full=true` 会先经过 `StoryGraphEvidenceAccess` 权限门控，默认 backend 返回 `STORY_GRAPH_EVIDENCE_ACCESS_DENIED` 且不会调用 reader；授权后 reader 才会读取并返回 evidence `snippet`。
- Python Agent Runtime `graph-heavy` worker 注册 `StoryGraphBuildWorkflow` / `story_graph_build_activity`，校验 tenant/project/run/module/permission context；未配置 `DATABASE_URL` 或未注入 graph builder 时返回 `STORY_GRAPH_BUILDER_UNCONFIGURED` 并写 sanitized failed event。配置 `DATABASE_URL` 时，默认 `PostgresStoryGraphBuilder` 会从 tenant/project scoped `entities`、`relationships`、`plot_threads`、`world_rule_evidence` 和可公开 asset metadata 构建 `story_graph_snapshots`、nodes、edges、public evidence metadata、layout 和 clusters；`PostgresWorkflowRunStatusWriter` 会同步把 `workflow_runs` 更新为 `completed` / `failed`，成功 result 只保存 graph id/counts，失败只保存稳定 error code/message；公开 result/event/status 不包含 evidence snippet、raw text、prompt/body/content、`content_text` 或 credential 字段。
- Next `/graph` shell 显示 current snapshot explicit success/error、默认 world viewport 节点/边摘要、public evidence、layout、clusters、build start explicit success/error、Compose Mode bond generation start explicit success/error、counts-only canvas placeholder，以及基于真实 build/bond `runId` 的 workflow progress surface。构建或 bond start 成功返回的 `run_id` 会进入 URL，页面刷新后通过 `GET /v1/workflow-runs/{runId}` 和 `GET /v1/workflow-runs/{runId}/events` 读取 public workflow metadata/events；未选择 run 时显示显式空状态，不伪造进度或候选结果。

仍未完成：

- 更完整的 semantic merge / graph layout / health diagnostics builder。
- React Flow 画布、完整 inspector 和 view persistence。
- GraphBondGeneratorDialog candidate persistence / adoption。
- live DB-backed graph build E2E。

## 前端图谱渲染

### React Flow

目标：

- 可控 viewport。
- 节点自定义显示。
- minimap。
- controls。
- selection。
- 节点拖动保存布局偏好。

### 布局策略

不要一上来展示全量乱图。提供层级：

1. World Overview：核心角色、核心组织、主线冲突。
2. Character Network：角色关系。
3. Plot Threads：剧情线和事件。
4. World Rules：规则和受影响角色。
5. Locations：地点/势力空间关系。
6. Custom Selection：用户自定义节点篮子。

### 大图处理

超过阈值：

- 默认显示 top N 重要节点。
- 其余按 cluster 折叠。
- 搜索命中局部展开。
- Inspector 可以查看隐藏邻居。
- 不一次渲染 5000 个 DOM 节点。

## Inspector

节点 inspector tabs：

- Summary：标题、类型、摘要、重要度。
- Evidence：原文证据。
- Relations：邻居和边。
- Assets：关联资产/档案。
- Timeline：相关事件。
- Actions：加入选择、生成羁绊、创建资产、隐藏/合并。

边 inspector tabs：

- Summary：关系类型、事实、强度。
- Evidence：证据。
- History：关系变化事件。
- Actions：升级 canon、编辑、删除 candidate。

## 羁绊/支线生成

覆盖旧 `graph_bond_generator`。

流程：

1. 用户多选 2-6 个节点。
2. Compose Mode 显示选择篮子。
3. 用户输入创作方向。
4. 启动 `GraphBondGenerationWorkflow` 或同步短任务。
5. Python `graph_bond_generator` 生成：
   - bonds
   - plot_threads
   - conflict_triggers
   - evidence assumptions
6. 结果作为 candidate asset 展示。
7. 用户选择保存到：
   - relationships
   - plot_threads
   - assets
   - worldline seed variable

## API

### Build

```http
POST /v1/projects/{projectId}/story-graph/builds
```

### Current Snapshot

```http
GET /v1/projects/{projectId}/story-graph/current
```

### Viewport Query

```http
GET /v1/projects/{projectId}/story-graph/views/{viewId}
```

Query:

```text
types=character,organization
cluster=main
search=角色名
limit=300
include_edges=true
```

### Node Detail

```http
GET /v1/projects/{projectId}/story-graph/nodes/{nodeId}
```

### Public Evidence

```http
GET /v1/projects/{projectId}/story-graph/nodes/{nodeId}/evidence
GET /v1/projects/{projectId}/story-graph/edges/{edgeId}/evidence
```

返回 public evidence source metadata、chapter/segment refs、confidence 和时间戳。默认响应不返回 snippet/raw text；`include_full=true` 必须通过 full evidence 权限检查，未授权返回 `STORY_GRAPH_EVIDENCE_ACCESS_DENIED`，授权后才返回 `snippet`。

### Layout / Clusters

```http
GET /v1/projects/{projectId}/story-graph/layouts/{viewId}
GET /v1/projects/{projectId}/story-graph/clusters
```

layout 和 cluster payload 会递归清洗 prompt/body/content/raw text/snippet/credential 字段。

### Generate Bonds

```http
POST /v1/projects/{projectId}/story-graph/bond-generations
```

当前实现状态：Go API 已提供 fail-closed/Temporal-backed start contract；配置 Temporal + Postgres 时会写入 sanitized workflow admission 并启动 `GraphBondGenerationWorkflow`，Python `graph-heavy` worker 已注册 `graph_bond_generation_activity`。Next `/graph` Compose Mode 已接入该 start endpoint，用户可提交明确的 node ids、graph id、focus 和 mode；成功/错误状态进入 URL，并复用 generic workflow read side 显示真实 run progress/events。`graph_bond_generator` LLM Facility-backed runner 已接入：它解析 module binding/credential，schema-validate bonds、plot threads 和 conflict triggers，要求 relationship candidates 携带 `source_entity_name`、`target_entity_name`、`relationship_type`，并只把清洗后的候选写入 lifecycle=`candidate` assets。缺 binding、credential、provider schema 或 runner 依赖时仍 fail closed，不生成 mock output。runner 不自动 adoption，也不在 public result/event/status 中公开 selected node ids、focus text、prompt/response、candidate body、API key、encrypted credential 或 `credential_ref`；backend explicit adoption API/store 已可把候选采用为 `relationships` 或 `plot_threads` 并写 audit metadata。候选查看/adoption UI、React Flow canvas 和 live browser/cluster E2E 仍 pending。

## 旧功能映射

| 旧功能 | 新功能 |
|---|---|
| activeTab overview/graph | Work modes: Explore/Build/Curate/Compose |
| GraphBuildConsole | Build Mode + WorkflowSurface |
| WorldOverviewDashboard | World Overview view |
| StoryGraphPanel D3 | React Flow canvas |
| StoryGraphInspector | Unified Inspector |
| visibleTypes | Layer filter |
| showEdgeLabels | Display option |
| selectedNodeIds | Selection basket |
| GraphBondGeneratorDialog | Compose Mode |
| generateArchiveCandidates | Asset/Archive action from selection |

## 验收清单

- 可以启动图谱构建并查看进度。
- 构建失败显示真实 trace。
- 图谱能从 seed 结构化表构建。
- 1000 节点项目默认可读，不是毛线团。
- 搜索角色后能定位节点。
- 选中节点能查看证据和关系。
- 多选节点能生成羁绊/支线。
- 生成结果能进入资产库或剧情线。
- viewer 不能执行 curate 写操作。
