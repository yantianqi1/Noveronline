# Window 5 Prompt: Python Agent Runtime Foundation

你是 MiroFish-Novel SaaS 重构的 **Window 5：Python Agent Runtime Foundation**。

你负责 Python Agent Runtime 的基础骨架和 Temporal worker。

## 必读

先阅读：

- `AGENTS.md`
- `docs/refactor-saas/01-target-architecture.md`
- `docs/refactor-saas/12-llm-facility.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/19-parallel-development-orchestration.md`
- `tasks/refactor-saas-parallel-board.md`

然后运行：

```bash
git status --short
```

## 身份边界

你负责：

- `apps/agent-runtime` package。
- Temporal Python worker。
- AgentContext。
- trace event interfaces。
- hello workflow/activity。
- LLM router interface scaffold。

你不负责：

- Seed/Graph/Writer 具体业务迁移。
- Go API。
- Next.js UI。
- DB migrations。

## 可写范围

允许修改：

```text
apps/agent-runtime/
packages/shared-contracts/workflows/
```

禁止修改：

```text
backend/app/
frontend/src/
apps/api/internal/
apps/web/
apps/api/migrations/
```

## 当前任务

实现 P1-005：

- 创建 Python Agent Runtime 基础包。
- 创建 Temporal worker 入口。
- 定义 AgentContext。
- 实现 hello workflow/activity。
- 为后续 LLM router、trace writer 留接口，但不要伪装已完成真实 LLM 调用。

## 验收

示例：

```bash
python -m pytest
python -m mirofish_agents.temporal.worker --help
```

如果需要 Temporal 服务，说明如何通过 docker compose 启动。

## 完成汇报格式

```markdown
## Status

DONE / DONE_WITH_CONCERNS / BLOCKED

## Identity

- Window: 5 Python Agent Runtime Foundation
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
