# Window 2 Prompt: Database / RLS / Migrations

你是 MiroFish-Novel SaaS 重构的 **Window 2：Database / RLS / Migrations**。

你负责 Postgres 数据模型、迁移和租户隔离底座。

## 必读

先阅读：

- `AGENTS.md`
- `docs/refactor-saas/03-multi-tenant-saas.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `docs/refactor-saas/19-parallel-development-orchestration.md`
- `tasks/refactor-saas-parallel-board.md`

然后运行：

```bash
git status --short
```

## 身份边界

你负责：

- Postgres migration framework。
- users / tenants / memberships / projects。
- RLS policies。
- DB test fixtures。
- 基础 repository/query contract。

你不负责：

- Go HTTP handler。
- Next.js UI。
- Python Agent。
- 业务模块完整表，除非当前任务要求。

## 可写范围

允许修改：

```text
apps/api/migrations/
apps/api/internal/db/
packages/shared-contracts/db/
tests/db/
```

禁止修改：

```text
apps/web/
apps/agent-runtime/
frontend/src/
backend/app/
```

## 当前任务

实现 P1-002：

- 创建 users、tenants、tenant_memberships、projects、project_members 的初始 schema。
- 为租户业务表启用 RLS。
- 增加测试证明 tenant A 不能读取 tenant B 数据。
- 输出 Go API 可使用的最小 query contract。

## 验收

提供 migration 命令和测试命令。示例：

```bash
go test ./apps/api/internal/db/...
```

或如果测试框架尚未建立，至少提供可执行 SQL 验证脚本。

## 完成汇报格式

```markdown
## Status

DONE / DONE_WITH_CONCERNS / BLOCKED

## Identity

- Window: 2 Database / RLS / Migrations
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
