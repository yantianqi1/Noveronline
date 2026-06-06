# Import Plan Baseline

日期：`2026-04-11`

命令：

```bash
python3 -m migrations.import_plan backend/uploads
```

## 当前结果

- `entry_count`: `14`
- `skipped_rebuild_refs`:
  - `projects/proj_1edaa458dd75/story_graph.sqlite3`
- `anomalies`:
  - `graph_graph_demo_001: missing project.json`
  - `graph_graph_smoke: missing project.json`

## execution_mode 分布

### `direct_db`

- `projects/graph_graph_demo_001/worldlines/prepare.sqlite3`
- `projects/graph_graph_demo_001/worldlines/sessions/ws_4e33baffa33a/session.json`
- `projects/graph_graph_smoke/worldlines/prepare.sqlite3`
- `projects/graph_graph_smoke/worldlines/sessions/ws_3ffe941c7761/session.json`
- `projects/proj_1edaa458dd75/project.json`
- `system/archive_library.sqlite3`
- `system/chapter_meta.sqlite3`
- `system/llm_facility.sqlite3`
- `system/task_runtime.sqlite3`

### `object_then_db`

- `projects/proj_1edaa458dd75/analysis_blocks.json`
- `projects/proj_1edaa458dd75/anchor_points.json`
- `projects/proj_1edaa458dd75/chapter_segments.json`
- `projects/proj_1edaa458dd75/files/b1e2ffbe.txt`
- `projects/proj_1edaa458dd75/skeleton_timeline.json`

## 结论

- 当前已经能明确区分“先入对象存储再写元数据”和“直接结构化导入”的旧资产。
- `projection_rebuild_reference` 与项目级 anomaly 仍被显式保留，没有被 import plan 吞掉。
