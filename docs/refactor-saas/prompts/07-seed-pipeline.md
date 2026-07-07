# Window 7 Prompt: Seed Pipeline

你是 MiroFish-Novel SaaS 重构的 **Window 7：Seed Pipeline**。

你负责上传、解析、分段和 seed workflow 的第一条纵向切片。

## 必读

先阅读：

- `AGENTS.md`
- `docs/refactor-saas/05-overview-dashboard.md`
- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/19-parallel-development-orchestration.md`
- `tasks/refactor-saas-parallel-board.md`

然后运行：

```bash
git status --short
```

## 可写范围

允许修改：

```text
apps/api/internal/uploads/
apps/api/internal/seed/
apps/agent-runtime/mirofish_agents/seed/
apps/web/features/seed/
packages/shared-contracts/seed/
```

禁止修改：

```text
backend/app/
frontend/src/
apps/api/internal/llm/
apps/api/migrations/
```

## 当前任务

实现 P2-002：

- TXT 上传登记。
- SeedPipelineWorkflow skeleton。
- parse/segment activity scaffold。
- workflow progress events。
- 总览页能看到 seed run 状态。

不要把完整 LLM 精读伪装完成。LLM 未就绪时，明确显示 blocked/unbound。

## 验收

- TXT upload starts seed run。
- workflow events 可查询。
- 至少写入 source file / segments / workflow run。

## 完成汇报格式

按标准交接模板返回。
