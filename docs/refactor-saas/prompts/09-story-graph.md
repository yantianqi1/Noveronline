# Window 9 Prompt: Story Graph

你是 MiroFish-Novel SaaS 重构的 **Window 9：Story Graph**。

你负责故事图谱 schema/API/workflow/UI 的第一条纵向切片。

## 必读

先阅读：

- `AGENTS.md`
- `docs/refactor-saas/07-story-graph.md`
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
apps/api/internal/graph/
apps/agent-runtime/mirofish_agents/graph/
apps/web/features/story-graph/
packages/shared-contracts/graph/
```

禁止修改：

```text
backend/app/
frontend/src/
apps/api/internal/seed/
apps/api/internal/assets/
apps/api/migrations/
```

## 当前任务

实现 P3-002：

- graph snapshot API。
- graph build workflow skeleton。
- React Flow canvas。
- node/edge inspector。
- compose mode scaffold as explicit not-implemented state, not fake output。

## 验收

- graph snapshot renders in React Flow。
- node detail inspector works。
- graph build run emits progress。

## 完成汇报格式

按标准交接模板返回。
