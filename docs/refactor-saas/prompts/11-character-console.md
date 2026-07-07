# Window 11 Prompt: Character Console

你是 MiroFish-Novel SaaS 重构的 **Window 11：Character Console**。

你负责角色第一人称互动、turn 记录和互动转章节草稿。

## 必读

先阅读：

- `AGENTS.md`
- `docs/refactor-saas/10-character-console.md`
- `docs/refactor-saas/09-worldline.md`
- `docs/refactor-saas/11-writer-workbench.md`
- `docs/refactor-saas/19-parallel-development-orchestration.md`
- `tasks/refactor-saas-parallel-board.md`

然后运行：

```bash
git status --short
```

## 可写范围

允许修改：

```text
apps/api/internal/character_console/
apps/agent-runtime/mirofish_agents/character_console/
apps/web/features/character-console/
packages/shared-contracts/character-console/
```

禁止修改：

```text
backend/app/
frontend/src/
apps/api/internal/worldline/
apps/api/internal/writer/
apps/api/migrations/
```

## 当前任务

实现 P4-003：

- interaction session API。
- add turn。
- stream turn events。
- first-person mode UI skeleton。
- convert interaction to draft workflow skeleton。

## 验收

- select worldline session and agent。
- record interaction turn。
- convert request creates draft scaffold with explicit workflow status。

## 完成汇报格式

按标准交接模板返回。
