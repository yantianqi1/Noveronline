# Worldline Runtime Projection Baseline

日期：`2026-04-12`

命令：

```bash
python3 -m migrations.import_only backend/uploads sqlite:////tmp/mirofish_import_only_runtime.db
```

## 当前结果

- `blocked_targets`: `[]`
- 新增显式 anomaly：
  - `ws_3ffe941c7761: imported legacy branch branch_1 as current_world; ignored 2 extra branches`

## 导入后计数

基于 `/tmp/mirofish_import_only_runtime.db` 实际查询：

- `worldline_sessions`: `2`
- `session_agents`: `2`
- `agent_state_snapshots`: `4`
- `agent_actions`: `0`
- `agent_dialogues`: `0`
- `relation_events`: `0`

## 说明

- `system/global_worldlines/graphs/*/worldlines/runtime.sqlite3` 现在已进入 inventory、checksum manifest、import plan 和 import-only。
- 旧 runtime.sqlite 当前真实样本只含：
  - `agent_registry`
  - `agent_state_snapshots`
- 未发现真实 `agent_action_log` / `agent_dialogue_log` / `relation_state_log` 数据行，因此导入结果为 `0`，不是 importer 漏导。
- 旧多 branch session 不会被静默全量并入新单世界模型；当前只导入第一条 branch 作为 `current_world`，并显式保留 anomaly。

## 结论

- worldline runtime 迁移已经从“schema 预留”推进到“真实旧数据可导入 runtime projection”。
- 新 `/api/v2/worldlines` 的 agent console 查询现在可以直接基于 PostgreSQL projection 读取，而不是继续停在 `501`。
