# Window 8 Prompt: Asset Library

你是 MiroFish-Novel SaaS 重构的 **Window 8：Asset Library**。

你负责资产库、资产搜索和资产入库 Agent 的第一条纵向切片。

## 必读

先阅读：

- `AGENTS.md`
- `docs/refactor-saas/08-asset-library.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/19-parallel-development-orchestration.md`
- `tasks/refactor-saas-parallel-board.md`

然后运行：

```bash
git status --short
```

## 可写范围

允许修改：

```text
apps/api/internal/assets/
apps/agent-runtime/mirofish_agents/assets/
apps/web/features/assets/
packages/shared-contracts/assets/
```

禁止修改：

```text
backend/app/
frontend/src/
apps/api/internal/seed/
apps/api/internal/writer/
apps/api/migrations/
```

## 当前任务

实现 P3-001：

- asset CRUD。
- search/facets 最小实现。
- asset ingestion workflow skeleton。
- asset list/detail UI。
- candidate asset 审阅状态。

## 验收

- create asset。
- search asset。
- ingest raw text -> candidate asset。
- 不同 tenant 数据隔离。

## 完成汇报格式

按标准交接模板返回。
