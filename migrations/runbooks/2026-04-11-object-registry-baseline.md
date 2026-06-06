# Object Registry Baseline

日期：`2026-04-11`

命令：

```bash
python3 - <<'PY'
from pathlib import Path
from migrations.object_registry_plan import build_object_registry_plan
plan = build_object_registry_plan(Path('backend/uploads'))
for entry in plan.entries:
    print(entry.registry_kind, entry.relative_path, entry.storage_key)
PY
```

## 当前结果

- `entry_count`: `5`

### `artifact_payload`

- `projects/proj_1edaa458dd75/analysis_blocks.json`
- `projects/proj_1edaa458dd75/anchor_points.json`
- `projects/proj_1edaa458dd75/chapter_segments.json`
- `projects/proj_1edaa458dd75/skeleton_timeline.json`

### `manuscript_source`

- `projects/proj_1edaa458dd75/files/b1e2ffbe.txt`

## 说明

- 当前 object registry plan 只覆盖需要进入对象存储的旧资产。
- `project.json`、system SQLite、worldline runtime/prepare/session 等仍走 `direct_db` 导入计划，不进入 object registry。
- `story_graph.sqlite3` 继续归类为 `projection_rebuild_reference`，不进入 object registry。
