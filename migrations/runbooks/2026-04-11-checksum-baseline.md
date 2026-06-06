# Checksum Baseline

日期：`2026-04-11`

## 输入

- inventory：`migrations.json_importers.legacy_inventory.scan_legacy_root`
- manifest：`migrations.checksums.manifest.build_checksum_manifest`
- 根目录：`backend/uploads`

## 结果

- checksum entry 总数：`15`

## 明细

### project

- `projects/graph_graph_demo_001/worldlines/prepare.sqlite3` `28672 bytes`
- `projects/graph_graph_demo_001/worldlines/sessions/ws_4e33baffa33a/session.json` `11711 bytes`
- `projects/graph_graph_smoke/worldlines/prepare.sqlite3` `28672 bytes`
- `projects/graph_graph_smoke/worldlines/sessions/ws_3ffe941c7761/session.json` `11866 bytes`
- `projects/proj_1edaa458dd75/analysis_blocks.json` `11530 bytes`
- `projects/proj_1edaa458dd75/anchor_points.json` `12387 bytes`
- `projects/proj_1edaa458dd75/chapter_segments.json` `1225318 bytes`
- `projects/proj_1edaa458dd75/files/b1e2ffbe.txt` `1247417 bytes`
- `projects/proj_1edaa458dd75/project.json` `795 bytes`
- `projects/proj_1edaa458dd75/skeleton_timeline.json` `5153090 bytes`
- `projects/proj_1edaa458dd75/story_graph.sqlite3` `0 bytes`

### system

- `system/archive_library.sqlite3` `1859584 bytes`
- `system/chapter_meta.sqlite3` `36864 bytes`
- `system/llm_facility.sqlite3` `49152 bytes`
- `system/task_runtime.sqlite3` `2527232 bytes`

## 风险提示

- `story_graph.sqlite3` 当前为 `0 bytes`，后续 dry-run 必须把它视为显式异常资产，而不是当成可用 query projection。
- `graph_graph_demo_001` 和 `graph_graph_smoke` 仍缺 `project.json`；manifest 已记录其 worldline 资产，但导入阶段必须继续保留 anomaly。
