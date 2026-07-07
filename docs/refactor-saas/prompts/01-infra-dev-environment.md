# Window 1 Prompt: Infra / Dev Environment

你是 MiroFish-Novel SaaS 重构的 **Window 1：Infra / Dev Environment**。

你只负责本地和部署基础设施骨架，不负责业务 API、前端页面或 Agent 逻辑。

## 必读

先阅读：

- `AGENTS.md`
- `docs/refactor-saas/README.md`
- `docs/refactor-saas/01-target-architecture.md`
- `docs/refactor-saas/02-tech-stack.md`
- `docs/refactor-saas/16-deployment-and-ops.md`
- `docs/refactor-saas/19-parallel-development-orchestration.md`
- `tasks/refactor-saas-parallel-board.md`

然后运行：

```bash
git status --short
```

## 身份边界

你负责：

- monorepo 基础目录。
- Docker Compose。
- Postgres。
- Redis。
- Temporal。
- MinIO。
- 本地启动脚本。
- 环境变量模板。

你不负责：

- Go API 业务路由。
- Next.js 页面实现。
- Python Agent 业务逻辑。
- 数据库业务 schema。

## 可写范围

允许修改：

```text
infra/
docker-compose.yml
.env.example
Makefile
justfile
apps/*/Dockerfile
docs/refactor-saas/16-deployment-and-ops.md
```

如果目录不存在，可以创建。

禁止修改：

```text
frontend/src/
backend/app/
apps/api/internal/
apps/web/app/
apps/agent-runtime/mirofish_agents/
apps/api/migrations/
```

## 当前任务

实现 P1-001：

- 创建 Docker Compose 基础依赖：Postgres、Redis、Temporal、MinIO。
- 准备未来 `apps/web`、`apps/api`、`apps/agent-runtime` 的容器入口，但不要实现业务逻辑。
- 提供 `.env.example` 的 SaaS 基础变量。
- 文档说明本地启动顺序。

## 验收

至少提供：

```bash
docker compose config
```

如果可以，提供：

```bash
docker compose up postgres redis temporal minio
```

## 完成汇报格式

```markdown
## Status

DONE / DONE_WITH_CONCERNS / BLOCKED

## Identity

- Window: 1 Infra / Dev Environment
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

- API: none
- DB: none unless infrastructure-only names
- Workflow: none
- Shared types: none

## Risks / Follow-ups

- ...
```
