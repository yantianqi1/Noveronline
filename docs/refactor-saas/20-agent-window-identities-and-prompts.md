# 20. Agent Window Identities and Prompt Presets

更新时间：`2026-07-03`

## 目的

多窗口并行开发时，每个 Codex 终端都必须有明确身份。身份定义包括：

- 我是谁。
- 我负责哪条泳道。
- 我应该读哪些文档。
- 我能改哪些文件。
- 我不能改哪些文件。
- 我当前任务是什么。
- 我完成后怎么汇报。

没有身份卡的窗口不要开工。

## 使用方式

1. Coordinator 先确认基线分支和 worktree。
2. 为每个窗口创建独立 worktree / branch。
3. 打开新 Codex 窗口。
4. 复制 `docs/refactor-saas/prompts/` 中对应文件全文作为第一条消息。
5. 工作窗口按 prompt 执行，不重新设计总体架构。
6. 完成后按 prompt 中的交接模板返回结果。

## Prompt 文件清单

| 窗口 | 身份 | Prompt |
|---|---|---|
| Window 0 | Coordinator / Integrator | `prompts/00-coordinator.md` |
| Window 1 | Infra / Dev Environment | `prompts/01-infra-dev-environment.md` |
| Window 2 | Database / RLS / Migrations | `prompts/02-database-rls-migrations.md` |
| Window 3 | Go Control Plane Foundation | `prompts/03-go-control-plane-foundation.md` |
| Window 4 | Next.js App Shell | `prompts/04-nextjs-app-shell.md` |
| Window 5 | Python Agent Runtime Foundation | `prompts/05-python-agent-runtime-foundation.md` |
| Window 6 | LLM Facility | `prompts/06-llm-facility.md` |
| Window 7 | Seed Pipeline | `prompts/07-seed-pipeline.md` |
| Window 8 | Asset Library | `prompts/08-asset-library.md` |
| Window 9 | Story Graph | `prompts/09-story-graph.md` |
| Window 10 | Worldline | `prompts/10-worldline.md` |
| Window 11 | Character Console | `prompts/11-character-console.md` |
| Window 12 | Writer Workbench | `prompts/12-writer-workbench.md` |
| Window 13 | Migration / Legacy Import | `prompts/13-migration-legacy-import.md` |
| Window 14 | Pi Writer Runtime | `prompts/14-pi-writer-runtime.md` |

## 身份规则

### Coordinator 是唯一总控

只有 Coordinator 可以：

- 改并行看板。
- 分配任务。
- 改高冲突共享契约。
- 合并多个窗口成果。
- 修改覆盖矩阵状态。

工作窗口不能自行升级自己为总控。

### 工作窗口只在自己泳道内行动

工作窗口必须遵守：

- 只改 prompt 允许的目录。
- 遇到共享契约变更，先停下并汇报。
- 遇到别的窗口负责的文件，不自行修改。
- 不把未完成能力伪装成完成。

### 每个窗口都有固定交付格式

完成后必须返回：

```markdown
## Status

DONE / DONE_WITH_CONCERNS / BLOCKED

## Identity

- Window:
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

## 推荐开工顺序

先开 Writer-first 最小闭环：

1. Window 0 Coordinator。
2. Window 14 Pi Writer Runtime。
3. Window 12 Writer Workbench。
4. Window 6 LLM Facility。
5. Window 3 Go Foundation 或当前后端兼容桥。

等 Writer-first 闭环跑通后再开 SaaS 基座：

- Window 1 Infra。
- Window 2 Database/RLS。
- Window 4 Web Shell。
- Window 5 Python Agent Runtime。

然后开知识层：

- Window 7 Seed Pipeline。
- Window 8 Asset Library。
- Window 9 Story Graph。
- Window 10 Worldline。

最后开：

- Window 11 Character Console。
- Window 13 Migration。

## Prompt 维护规则

- 如果某个窗口职责变化，先改本文件和对应 prompt。
- 如果新增窗口，必须新增 prompt 文件。
- 如果共享契约变更，Coordinator 负责同步相关 prompt。
- Prompt 中禁止写真实 API Key、用户小说原文或私有数据库路径。
