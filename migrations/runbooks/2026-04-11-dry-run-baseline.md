# Dry-Run Baseline

日期：`2026-04-11`

命令：

```bash
python3 -m migrations.dry_run backend/uploads
```

## 当前输出摘要

- `project_count`: `3`
- `entry_count`: `15`
- `zero_byte_assets`:
  - `projects/proj_1edaa458dd75/story_graph.sqlite3`
- `anomalies`:
  - `graph_graph_demo_001: missing project.json`
  - `graph_graph_smoke: missing project.json`

## classification_counts

- `artifact_archive:artifacts` -> `2`
- `projection_rebuild_reference:graph_query_projection` -> `1`
- `structured_import:archives+memories+memory_events` -> `1`
- `structured_import:artifacts+anchor_point_projection` -> `1`
- `structured_import:artifacts+chapter_segment_projection` -> `1`
- `structured_import:chapters+chapter_history_items` -> `1`
- `structured_import:llm_channels+llm_models+llm_module_bindings` -> `1`
- `structured_import:manuscripts+artifact_objects` -> `1`
- `structured_import:projects` -> `1`
- `structured_import:workflow_runs+workflow_steps` -> `1`
- `structured_import:worldline_preparations` -> `2`
- `structured_import:worldline_sessions+world_states+timeline_events` -> `2`

## 结论

- 当前 dry-run 已能把 inventory/checksum/classification 统一收口为单一 JSON 摘要。
- `zero_byte_assets` 与 `anomalies` 已显式暴露，不存在静默跳过。
- 后续 `import-only / verify-only / activate` 都应复用这套摘要结构，而不是重新发明报告格式。
