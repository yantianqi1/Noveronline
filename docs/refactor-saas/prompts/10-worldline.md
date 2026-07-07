# Window 10 Prompt: Worldline

你是 MiroFish-Novel SaaS 重构的 **Window 10：Worldline**。

你负责单世界 worldline session、prepare、变量、事件和 saved path。

## 必读

先阅读：

- `AGENTS.md`
- `docs/refactor-saas/09-worldline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/19-parallel-development-orchestration.md`
- `tasks/refactor-saas-parallel-board.md`

然后运行：

```bash
git status --short
```

## 可写范围

允许修改：

```text
apps/api/internal/worldline/
apps/agent-runtime/mirofish_agents/worldline/
apps/web/features/worldline/
packages/shared-contracts/worldline/
```

禁止修改：

```text
backend/app/
frontend/src/
apps/api/internal/writer/
apps/api/internal/character_console/
apps/api/migrations/
```

## 当前任务

实现 P4-001：

- worldline session API。
- prepare workflow skeleton。
- variable injection。
- candidate event lifecycle。
- saved path。
- worldline UI skeleton。

保持单世界 `current_world` 语义，不恢复旧多分支主模型。

## 验收

- create session。
- inject variable。
- create candidate event。
- save path。

## 完成汇报格式

按标准交接模板返回。
