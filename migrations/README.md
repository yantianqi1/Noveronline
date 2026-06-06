# Migration Baseline

本目录用于收口旧系统到新系统的所有迁移逻辑。

固定模式：

- `dry-run`
- `import-only`
- `verify-only`
- `activate`

固定子目录：

- `sqlite_extractors/`
- `json_importers/`
- `checksums/`
- `runbooks/`
- `versions/`

后续迁移脚本必须幂等，并以 `project_id / artifact_sha256 / legacy_primary_key` 做去重。
