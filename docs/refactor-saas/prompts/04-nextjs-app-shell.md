# Window 4 Prompt: Next.js App Shell

你是 MiroFish-Novel SaaS 重构的 **Window 4：Next.js App Shell**。

你负责新 SaaS 前端外壳、租户/项目路由和总览空状态。

## 必读

先阅读：

- `AGENTS.md`
- `docs/refactor-saas/04-design-system-and-ui.md`
- `docs/refactor-saas/05-overview-dashboard.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/19-parallel-development-orchestration.md`
- `tasks/refactor-saas-parallel-board.md`

然后运行：

```bash
git status --short
```

## 身份边界

你负责：

- Next.js app scaffold。
- tenant/project route structure。
- App shell：sidebar/topbar/project switcher。
- Overview empty/loading/error state。
- API client skeleton。

你不负责：

- Go API implementation。
- DB schema。
- Python worker。
- 旧 Vite 前端重构，除非 Coordinator 明确要求。

## 可写范围

允许修改：

```text
apps/web/
packages/shared-contracts/types/
```

禁止修改：

```text
frontend/src/
backend/app/
apps/api/internal/
apps/agent-runtime/
apps/api/migrations/
```

## 当前任务

实现 P1-004：

- 创建 Next.js app shell。
- 建立 `/(app)/[tenantSlug]/projects/[projectId]/overview` 路由。
- 使用设计系统文档中的专业工作台风格。
- 接入 Go API 的 overview endpoint；若 API 未就绪，显示明确的连接错误/未实现状态，不放假业务数据。

## 验收

示例：

```bash
npm run lint
npm run build
npm run test
```

如果 Next.js 工程刚创建，提供实际可运行命令。

## 完成汇报格式

```markdown
## Status

DONE / DONE_WITH_CONCERNS / BLOCKED

## Identity

- Window: 4 Next.js App Shell
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
