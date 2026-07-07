# Window 14 Prompt: Pi Writer Runtime

你是 MiroFish-Novel SaaS 重构的 **Window 14：Pi Writer Runtime**。

你负责把 `earendil-works/pi` SDK 接入 MiroFish Writer Agent 后端。你的目标不是开发整个 SaaS，也不是迁移所有 Agent，而是优先跑通 Writer-first Pi Agent 最小闭环。

## 必读

先阅读：

- `AGENTS.md`
- `docs/refactor-saas/DEVELOPMENT_PLAN.md`
- `docs/refactor-saas/21-pi-writer-agent-runtime.md`
- `docs/refactor-saas/11-writer-workbench.md`
- `docs/refactor-saas/12-llm-facility.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/19-parallel-development-orchestration.md`
- `tasks/refactor-saas-parallel-board.md`

然后运行：

```bash
git status --short
```

## 身份边界

你负责：

- `apps/pi-agent-runtime` Node/TypeScript runtime。
- `@earendil-works/pi-agent-core` 接入。
- `@earendil-works/pi-ai` model/provider adapter。
- Pi event 到 workflow event 的映射。
- Writer tool registry 和最小 tools。
- LLM Facility adapter 接口。
- draft persistence bridge。

你不负责：

- Seed / Graph / Worldline 的 Python 领域逻辑迁移。
- Next.js App Shell。
- Postgres 全量 schema。
- 旧前端大规模重构。
- 使用 `pi-coding-agent` CLI 作为产品后端。

## 可写范围

允许修改：

```text
apps/pi-agent-runtime/
packages/shared-contracts/writer/
docs/refactor-saas/21-pi-writer-agent-runtime.md
```

如果 Coordinator 明确要求兼容当前后端，可谨慎修改：

```text
backend/app/api_fastapi/
backend/app/services/
frontend/src/pages/writer/
```

禁止修改：

```text
backend/uploads/
backend/data/
apps/api/migrations/
frontend/src/pages/story-graph/
frontend/src/pages/worldline/
```

## 当前任务

实现 Writer-first Pi Agent vertical slice 的后端 runtime：

- 创建 Pi Writer Runtime skeleton。
- 使用 faux/test provider 跑通 deterministic writer run。
- 定义 writer run input/output/event contract。
- 实现最小 event mapper。
- 实现最小 writer tools：
  - `query_project_context`
  - `query_chapter_scene`
  - `query_assets`
  - `query_manuscript_context`
  - `save_draft_revision`
- 缺 LLM module binding 时返回明确错误，不使用环境变量 fallback。

## 验收

至少提供：

```bash
npm run test
npm run build
```

并说明：

- faux/test provider 如何产生 token stream。
- Pi event 如何映射 workflow event。
- 缺绑定错误如何返回。
- draft 如何保存或在兼容期如何桥接。

## 完成汇报格式

```markdown
## Status

DONE / DONE_WITH_CONCERNS / BLOCKED

## Identity

- Window: 14 Pi Writer Runtime
- Branch:
- Worktree:

## Files Changed

- ...

## What Changed

- ...

## Verification

- Command:
- Result:

## Contract Changes

- API:
- DB:
- Workflow:
- Shared types:

## Risks / Follow-ups

- ...
```
