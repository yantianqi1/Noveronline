# 11-Graph-重构路径与验收方案

## 1. 为什么单独立项

当前方案已将 graph 定义为必须迁移的核心能力，但在主链重构路径中没有被展开到和 `seed / worldline / writer` 同等级别。考虑到当前仓库已存在：

- `POST /api/project/build-graph`
- `GET /api/project/<project_id>/graph`
- `/story-graph` 工作台
- `AgentTemplateConfigurator`
- graph build task 状态测试
- local story graph pipeline 测试

因此 graph 不能继续作为附属能力处理，必须独立成专题方案。

---

## 2. 功能边界

本轮 graph 必须完整承接以下能力：

- 从项目和 seed 产物启动图谱构建
- 产出 graph snapshot artifact
- 建立 graph query projection
- 提供图谱读取 API
- 支持前端图谱渲染、节点查看、标签/图例、构建任务轮询
- 支持 agent template 配置与读取
- 为 archive/worldline 提供稳定只读输入

---

## 3. 目标架构

### 3.1 Bounded Context

`graph` 是独立 bounded context，与 `seed-analysis`、`archive-library`、`worldline` 通过 artifact 和 projection 解耦。

### 3.2 命令与工作流

- Command:
  - `StartGraphBuild`
  - `RebuildGraphProjection`
  - `UpdateAgentTemplateConfig`
- Workflow:
  - `GraphBuildWorkflow`
    - load seed artifacts
    - normalize entities
    - build graph snapshot
    - publish query projection
    - publish template config snapshot

### 3.3 主事实与投影

主事实：

- `graph_build_runs`
- `graph_nodes`
- `graph_edges`
- `graph_template_configs`
- `graph_snapshots` artifact metadata

查询投影：

- `graph_overview_view`
- `graph_node_detail_view`
- `graph_relation_view`
- `graph_build_status_view`

---

## 4. API 与前端承接

### 4.1 API

- `POST /api/v2/workspaces/{workspace_id}/graph-builds`
- `GET /api/v2/workspaces/{workspace_id}/graph`
- `GET /api/v2/workspaces/{workspace_id}/graph/nodes/{node_id}`
- `PATCH /api/v2/workspaces/{workspace_id}/graph-template-configs/{template_key}`

### 4.2 前端

`/story-graph` 页面必须完整承接：

- graph load
- graph build operation poll
- node/edge inspect
- labels / legends / filter
- template config panel
- empty / loading / failed states

---

## 5. 与其他模块的依赖边界

- `seed-analysis -> graph`：graph 读取 seed artifacts，不直接调用 seed 内部实现。
- `graph -> archive-library`：archive 只消费 graph projection 或 graph artifact，不读 graph workflow 内部状态。
- `graph -> worldline`：worldline 只消费 graph snapshot/ref，不耦合 graph build 过程。
- `writer` 不直接依赖 graph workflow，只依赖 chapter context 查询层。

---

## 6. 迁移策略

### 6.1 旧数据输入

- `story_graph.json` 原样归档为 artifact
- `story_graph.sqlite3` 不直接迁移为事实库，只作为旧索引重建参考

### 6.2 新系统导入

- 导入器读取旧 graph snapshot
- 校验节点数、边数、主要实体类型分布
- 重建 PostgreSQL query projection
- 重建前端消费 DTO

---

## 7. 回归与验收

至少覆盖以下现有测试语义：

- `test_graph_build_task_state.py`
- `test_local_story_graph_pipeline.py`
- `test_local_story_graph_builder.py`
- `test_local_story_graph_support.py`
- `test_agent_template_registry.py`

graph 完成的判定标准：

1. 构建图谱、读取图谱、模板配置三条链全可用。
2. `/story-graph` 页面非占位。
3. graph 对 `archive / worldline` 的输入语义稳定。
4. 不再依赖 `story_graph.sqlite3` 作为真源。
