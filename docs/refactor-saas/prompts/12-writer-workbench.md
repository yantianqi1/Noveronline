# Window 12 Prompt: Writer Workbench

你是 MiroFish-Novel SaaS 重构的 **Window 12：Writer Workbench**。

你负责章节、场景、手稿、writer run、draft adoption 和 reviewer/dedup scaffold。

## 必读

先阅读：

- `AGENTS.md`
- `docs/refactor-saas/DEVELOPMENT_PLAN.md`
- `docs/refactor-saas/21-pi-writer-agent-runtime.md`
- `docs/refactor-saas/11-writer-workbench.md`
- `docs/refactor-saas/12-llm-facility.md`
- `docs/refactor-saas/13-agent-runtime.md`
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
apps/api/internal/writer/
apps/pi-agent-runtime/
apps/web/features/writer/
packages/shared-contracts/writer/
```

禁止修改：

```text
backend/app/
frontend/src/
apps/api/internal/worldline/
apps/api/internal/character_console/
apps/api/migrations/
```

## 当前任务

实现 P1-004 / P1-005：

- 写作台接入 writer run stream。
- 展示 token stream。
- 展示 tool trace rail。
- 展示 draft preview。
- 支持 adopt draft to manuscript。

不要伪造 AI 正文。如果 Pi Runtime 或 LLM 未接好，返回明确 workflow blocked/error。

## 验收

- create chapter/scene。
- start writer run。
- stream events。
- adopt draft to manuscript。

## 完成汇报格式

按标准交接模板返回。
