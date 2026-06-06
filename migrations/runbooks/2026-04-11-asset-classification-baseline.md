# Asset Classification Baseline

日期：`2026-04-11`

## 输入

- asset list：`migrations.checksums.manifest.build_checksum_manifest`
- classifier：`migrations.json_importers.asset_classification.classify_legacy_asset`

## 当前 15 条资产的分类结果

### `structured_import`

- `projects/graph_graph_demo_001/worldlines/prepare.sqlite3` -> `worldline_preparations`
- `projects/graph_graph_demo_001/worldlines/sessions/ws_4e33baffa33a/session.json` -> `worldline_sessions+world_states+timeline_events`
- `projects/graph_graph_smoke/worldlines/prepare.sqlite3` -> `worldline_preparations`
- `projects/graph_graph_smoke/worldlines/sessions/ws_3ffe941c7761/session.json` -> `worldline_sessions+world_states+timeline_events`
- `projects/proj_1edaa458dd75/anchor_points.json` -> `artifacts+anchor_point_projection`
- `projects/proj_1edaa458dd75/chapter_segments.json` -> `artifacts+chapter_segment_projection`
- `projects/proj_1edaa458dd75/files/b1e2ffbe.txt` -> `manuscripts+artifact_objects`
- `projects/proj_1edaa458dd75/project.json` -> `projects`
- `system/archive_library.sqlite3` -> `archives+memories+memory_events`
- `system/chapter_meta.sqlite3` -> `chapters+chapter_history_items`
- `system/llm_facility.sqlite3` -> `llm_channels+llm_models+llm_module_bindings`
- `system/task_runtime.sqlite3` -> `workflow_runs+workflow_steps`

### `artifact_archive`

- `projects/proj_1edaa458dd75/analysis_blocks.json` -> `artifacts`
- `projects/proj_1edaa458dd75/skeleton_timeline.json` -> `artifacts`

### `projection_rebuild_reference`

- `projects/proj_1edaa458dd75/story_graph.sqlite3` -> `graph_query_projection`

## 当前没有落入 anomaly 的 checksum 资产

说明：

- checksum 清单里的 15 条文件都已获得显式分类。
- 但 inventory 层仍保留两条项目 anomaly：`graph_graph_demo_001` 与 `graph_graph_smoke` 缺 `project.json`。
- 导入器必须同时消费“asset classification + inventory anomalies”两类输出，不能因为文件本身可分类就忽略项目级异常。
