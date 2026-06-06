# Import-Only Baseline

日期：`2026-04-11`

命令：

```bash
python3 -m migrations.import_only backend/uploads sqlite:////tmp/mirofish_import_only.db
```

## 当前结果

- `workspace_count`: `1`
- `project_count`: `1`
- `artifact_object_count`: `5`
- `manuscript_count`: `1`
- `artifact_count`: `4`
- `blocked_targets`: `[]`

## 当前 anomaly

- `graph_graph_demo_001: missing project.json`
- `graph_graph_smoke: missing project.json`
- `ws_3ffe941c7761: imported legacy branch branch_1 as current_world; ignored 2 extra branches`

说明：

- 这两组 worldline 资产现在已经可以作为 orphan worldline 被导入，`worldline_sessions.project_id` 允许为空。
- anomaly 仍保留，因为缺 `project.json` 仍是事实，不能静默抹掉。

## 已打通的导入范围

- `projects`
- `artifact_objects`
- `manuscripts`
- `artifacts`
- `workflow_runs` / `workflow_steps` / `workflow_events`（来自 `task_runtime.sqlite3` 与 `progress_detail_json.timeline`）
- `chapters` / `chapter_history_items`（来自 `chapter_meta.sqlite3`）
- `llm_providers` / `llm_channels` / `llm_models` / `llm_module_bindings`
- `entities` / `archives` / `memories` / `memory_events`
- `worldline_preparations` / `prepared_agent_dossiers`
- `worldline_sessions` / `world_states` / `timeline_events`
- `session_agents` / `agent_state_snapshots` / `agent_actions` / `agent_dialogues` / `relation_events`

## 结论

- migration foundation 现在已经从“只出计划”推进到“可以做最小 import-only 落库”。
- 当前真实旧数据里不再有 import-only 级别的 blocked target，剩余问题只表现为 anomaly。
- 对于旧 multi-branch worldline，当前规则是：显式记录 anomaly，只导入 `session.json` 第一条 branch 作为 `current_world`，其余 branch 不会被静默吞掉。
