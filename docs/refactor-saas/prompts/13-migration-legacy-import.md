# Window 13 Prompt: Migration / Legacy Import

你是 MiroFish-Novel SaaS 重构的 **Window 13：Migration / Legacy Import**。

你负责旧项目、旧 SQLite、旧 artifacts 到新 SaaS 数据模型的导入方案和工具。

## 必读

先阅读：

- `AGENTS.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/17-migration-roadmap.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `docs/database/database-source-of-truth-matrix.md`
- `docs/refactor-saas/19-parallel-development-orchestration.md`
- `tasks/refactor-saas-parallel-board.md`

然后运行：

```bash
git status --short
```

## 可写范围

允许修改：

```text
apps/api/internal/importer/
apps/agent-runtime/mirofish_agents/migration/
tools/migration/
tests/legacy/
docs/refactor-saas/18-legacy-coverage-matrix.md
```

覆盖矩阵状态变更必须明确标注证据。

禁止修改：

```text
frontend/src/
backend/app/
apps/web/
apps/api/internal/writer/
apps/api/internal/worldline/
apps/api/migrations/
```

## 当前任务

实现 P5-001：

- legacy project import report skeleton。
- 导入旧 project metadata fixture。
- 映射旧 assets/entities/graph 的最小样例。
- 生成导入报告，不直接删除旧数据。

## 验收

- import one project metadata fixture。
- report lists imported/skipped/failed items。
- no user raw novel text printed to logs。

## 完成汇报格式

按标准交接模板返回。
