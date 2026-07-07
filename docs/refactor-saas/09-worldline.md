# 09. Worldline

更新时间：`2026-06-27`

## 模块定位

世界线是作者拓展小说灵感的实验室。作者可以选择角色、组织、档案、世界变量，观察故事接下来如何发展，并把有价值的发展路径保存下来，供 Writer Agent 写作时引用。

长期语义仍是单世界 `current_world`。旧多分支 `/branches`、`/comparison` 不恢复为主模型。

## 旧功能覆盖

旧 worldline 能力：

- prepare session。
- prepared agents。
- start prepared session。
- create/list/get session。
- timeline。
- step。
- variable injection。
- agent action。
- agent dialogue。
- auto evolve。
- candidate/canon events。
- event adoption/edit。
- agent detail/history/actions/dialogues/memory。
- relation history。
- inspiration generation。

新系统必须全部覆盖。

## 核心概念

### Worldline Session

一次世界线实验。

字段：

- session_id。
- project_id。
- label。
- focus_question。
- selected_assets。
- selected_agents。
- variables。
- status。
- current_step。
- created_by。

### Prepared Agent

推演前为角色/组织生成的 dossier。

字段：

- agent_id。
- display_name。
- source_entity_id。
- source_archive_id。
- public_profile。
- private_profile。
- runtime_seed_state。
- relationship_view。
- memory_seed_summary。

### World Variable

用户注入的变量。

字段：

- variable_id。
- name。
- description。
- impact_axis。
- locked。
- source。

### Candidate Event

Agent/Director 推演出的候选事件。

字段：

- event_id。
- step。
- title。
- summary。
- involved_agents。
- state_changes。
- confidence。
- status：candidate/canon/rejected。

### Saved Path

作者保存的一条发展路径。

字段：

- path_id。
- session_id。
- title。
- summary。
- selected_event_ids。
- writer_instruction。
- lifecycle：simulation/material/canon_reference。

## 工作流

### WorldlinePrepareWorkflow

```text
validate_selection
load_sources
materialize_agents
validate_dossiers
compose_world_snapshot
ready_to_start
```

覆盖旧 `WorldlinePrepareService`。

### WorldlineAutoEvolutionWorkflow

```text
load_session
load_agents
for each step:
  collect_agent_proposals
  director_judgement
  persist_candidate_events
  update_agent_states
  update_relation_states
  emit_progress
finalize
```

### Manual Variable Injection

同步或短 workflow：

```text
validate_variable
append_to_session
recompute_world_state_hint
record_event
```

### Event Adoption

```text
validate_permission
load_candidate_event
mark_canon
write_world_events
write_assets optional
update_writer_context_index
audit
```

## UI 设计

### Layout

```text
Header
  session selector
  status
  start/continue
  save path

Left Panel
  project/asset/character selection
  variables
  prepare controls

Center Panel
  current world state
  director timeline
  step cards
  thinking/progress overlay

Right Panel
  candidate review
  prepared agent inspector
  saved paths
```

### Author Flow

1. 选择一个项目。
2. 从资产库/角色档案中选择角色。
3. 输入变量：例如“主角亲族提前失踪”。
4. prepare agents。
5. 启动推演。
6. 查看候选事件。
7. 采用或编辑事件。
8. 保存发展路径。
9. 在写作台引用该 path。

## 数据模型

```text
worldline_sessions
worldline_agents
worldline_variables
worldline_events
worldline_event_adoptions
worldline_saved_paths
worldline_agent_state_snapshots
worldline_agent_actions
worldline_agent_dialogues
worldline_agent_memories
worldline_relation_events
```

所有表包含：

- tenant_id。
- project_id。

## Agent 模块

| 模块 key | 职责 |
|---|---|
| `worldline_agent_prepare` | 生成角色/组织 dossier |
| `worldline_character_proposal` | 角色自主提案 |
| `worldline_director` | 天道/导演裁决 |
| `worldline_agent_dialogue` | 显式对话回复 |
| `worldline_agent_action` | 传统自动动作兼容 |
| `worldline_goal_evaluator` | 判断目标是否达成 |
| `parallel_world_config` | 旧名保留，语义改为 current_world 起始配置 |

## Writer 引用

保存路径后，Writer Agent 可检索：

- path summary。
- selected events。
- involved agents。
- unresolved conflicts。
- author notes。
- world state changes。

Writer request 中可显式传：

```json
{
  "worldline_path_ids": ["wpath_..."],
  "use_worldline_as": "reference"
}
```

不能自动把 simulation 变 canon。采用需要用户动作。

## API

所有 Worldline 写入口的 JSON decode validation failure 都只返回稳定 `VALIDATION_FAILED` message 和空 public details；不得回显 decoder 原始错误、unknown field 名称、Go struct field 名称，或可能包含 `api_key`、`prompt`、`credential_ref`、draft/manuscript 等敏感词的输入字段。

### Prepare

```http
POST /v1/projects/{projectId}/worldlines/preparations
```

### Start Session

```http
POST /v1/projects/{projectId}/worldlines/sessions
```

### Auto Evolve

```http
POST /v1/worldline-sessions/{sessionId}/auto-evolutions
```

### Inject Variable

```http
POST /v1/worldline-sessions/{sessionId}/variables
```

### Events

```http
GET /v1/worldline-sessions/{sessionId}/events?status=candidate
```

### Adopt

```http
POST /v1/worldline-events/{eventId}/adoptions
```

### Save Path

```http
POST /v1/worldline-sessions/{sessionId}/saved-paths
```

## 旧功能映射

| 旧功能 | 新功能 |
|---|---|
| SelectionPanel | Source Selection |
| ControlPanel | Prepare/Run controls |
| VariableLockPanel | Variable editor |
| DirectorPanel | Evolution timeline + candidate review |
| InspirationPanel | Prompted inspiration generation |
| SimulationRoster | Agent roster |
| candidate events | Candidate Review |
| event adoption | Adopt to saved path/canon |
| agent memory/history | Agent Inspector |

## 验收清单

- 可以选择角色/档案启动 prepare。
- prepare 失败可续传。
- 变量可注入并显示在当前世界状态。
- auto-evolution 产生候选事件。
- 候选事件可采用、编辑、拒绝。
- 保存路径能在资产库和写作台被引用。
- 同一 session 不允许两个 auto-evolution 并发写。
- viewer 只能查看，不能采用事件。
