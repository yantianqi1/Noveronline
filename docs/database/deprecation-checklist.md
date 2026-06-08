# Legacy Runtime Read Deprecation Checklist

更新时间：2026-06-08

## 目标

数据库统一迁移的最终状态要求运行时只读写统一主库。旧 JSON、旧 SQLite 和 worldline 文件系统路径只能保留为迁移、导入、导出或审计工具。

本清单配合扫描护栏：

```bash
cd backend
env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 ../.venv/bin/python -m pytest tests/test_legacy_runtime_read_guard.py -q
```

也可直接运行：

```bash
cd backend
../.venv/bin/python scripts/audit_legacy_runtime_reads.py
```

CI 入口：`.github/workflows/legacy-runtime-read-guard.yml`。该 workflow 在 `backend/app/**`、护栏脚本、护栏测试和本清单变更时自动运行。

## 当前已登记兼容点

以下路径仍包含 legacy 标记，但已被显式登记。新增路径不得绕过扫描测试。

| 路径 | 保留原因 | 清理方向 |
|---|---|---|
| `backend/app/services/migration_verifier.py` | 迁移校验器必须读取 legacy source | 保留为 migration-only 工具 |

## 收口规则

- 新运行时代码不得新增 `ProjectManager.load_project_json(` 或 `ProjectManager.save_project_json(`。
- 新运行时代码不得新增 `ReadingNotesManager.load(` 作为运行时状态恢复入口；seed reading notes 的运行时真相源是 `project_artifacts.reading_notes`。
- 新运行时代码不得直接读取 `project.json`；项目元数据运行时真相源是 `project_meta.project_json`。
- 新运行时代码不得直接读取 `extracted_text.txt`；提取正文运行时真相源是 `project_artifacts` 的 `extracted_text`。
- 新运行时代码不得查询 `sqlite_master` 做旧库/表探测；schema 校验仅允许出现在 migration/verify 工具中。
- 新运行时代码不得直连 `novel.sqlite3`、`story_graph.sqlite3`、`archive_library.sqlite3`、`assets_library.sqlite3`、`project_assets.sqlite3`、`llm_facility.sqlite3`、`task_runtime.sqlite3`、`global_search.sqlite3` 或 `worldlines/runtime.sqlite3`。
- 必须新增 legacy 导入能力时，应放在 migration/import/verify 工具路径，并同步更新本清单。
- 每移除一个登记路径，都应同时从 `DEFAULT_ALLOWED_PATHS` 中删除并运行护栏测试。
