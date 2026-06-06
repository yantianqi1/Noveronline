# Legacy Inventory Baseline

日期：`2026-04-11`

## 扫描目标

- 根目录：`backend/uploads`
- 扫描器：`migrations.json_importers.legacy_inventory.scan_legacy_root`

## 汇总

- 项目目录数：`3`
- system SQLite：
  - `archive_library.sqlite3`
  - `chapter_meta.sqlite3`
  - `llm_facility.sqlite3`
  - `task_runtime.sqlite3`

## anomaly

- `graph_graph_demo_001: missing project.json`
- `graph_graph_smoke: missing project.json`

这两个目录目前只体现 graph/worldline 运行时残留，不满足完整项目导入前提。后续迁移脚本必须将其作为显式 anomaly 报告，不允许静默当成完整 project 导入成功。

## 项目明细

### `graph_graph_demo_001`

- top-level JSON：无
- top-level SQLite：无
- manuscripts：无
- worldline prepare：`prepare.sqlite3`
- worldline runtime：无
- worldline sessions：`ws_4e33baffa33a/session.json`

### `graph_graph_smoke`

- top-level JSON：无
- top-level SQLite：无
- manuscripts：无
- worldline prepare：`prepare.sqlite3`
- worldline runtime：无
- worldline sessions：`ws_3ffe941c7761/session.json`

### `proj_1edaa458dd75`

- top-level JSON：
  - `analysis_blocks.json`
  - `anchor_points.json`
  - `chapter_segments.json`
  - `project.json`
  - `skeleton_timeline.json`
- top-level SQLite：
  - `story_graph.sqlite3`
- manuscripts：
  - `files/b1e2ffbe.txt`
- worldline assets：当前未发现

## 后续动作

- 基于这份 inventory 建立 artifact checksum 清单
- 将 anomaly 项纳入 dry-run 输出，而不是在导入时隐式跳过
- 下一步补 `story_graph.json` / `worldlines/runtime.sqlite3` 等缺失资产的分类规则
