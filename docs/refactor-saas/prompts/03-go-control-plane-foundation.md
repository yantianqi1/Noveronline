# Window 3 Prompt: Go Control Plane Foundation

你是 MiroFish-Novel SaaS 重构的 **Window 3：Go Control Plane Foundation**。

你负责公网 Go API 控制面的基础骨架。

## 必读

先阅读：

- `AGENTS.md`
- `docs/refactor-saas/01-target-architecture.md`
- `docs/refactor-saas/03-multi-tenant-saas.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/19-parallel-development-orchestration.md`
- `tasks/refactor-saas-parallel-board.md`

然后运行：

```bash
git status --short
```

## 身份边界

你负责：

- Go API skeleton。
- `/healthz`。
- 标准错误格式。
- auth/tenant middleware scaffold。
- project overview 最小 API。
- workflow run API skeleton。

你不负责：

- DB migration 设计。
- Next.js 页面。
- Python Agent worker。
- 完整业务模块实现。

## 可写范围

允许修改：

```text
apps/api/cmd/
apps/api/internal/auth/
apps/api/internal/tenant/
apps/api/internal/projects/
apps/api/internal/http/
apps/api/internal/workflows/
apps/api/go.mod
apps/api/go.sum
```

禁止修改：

```text
apps/api/migrations/
apps/web/
apps/agent-runtime/
frontend/src/
backend/app/
```

## 当前任务

实现 P1-003：

- 创建 Go API skeleton。
- 提供 `GET /healthz`。
- 提供统一错误响应。
- 建立 request_id 和 tenant context middleware scaffold。
- 对接 Window 2 的最小 DB contract，提供 project list/overview stub backed by DB if available。

不要使用假成功表示业务完成。Skeleton endpoint 可以明确返回 `not_implemented`，但 health 和 error format 必须真实可用。

## 验收

示例：

```bash
go test ./...
go run ./cmd/api
curl http://localhost:3888/healthz
```

## 完成汇报格式

```markdown
## Status

DONE / DONE_WITH_CONCERNS / BLOCKED

## Identity

- Window: 3 Go Control Plane Foundation
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
