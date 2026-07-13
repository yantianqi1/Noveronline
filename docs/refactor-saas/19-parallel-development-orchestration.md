# 19. Parallel Development Orchestration

更新时间：`2026-07-10`

## 目的

本文只定义多 agent 并行协作规则，不包含固定任务、当前进度、历史测试数字或可复制的旧启动 prompt。

当前任务必须由主控根据以下真相源现场生成：

1. `DEVELOPMENT_PLAN.md`：范围、顺序和完成定义。
2. `24-current-development-progress.md`：唯一当前进度与验证新鲜度。
3. `tasks/refactor-saas-parallel-board.md`：活动任务、依赖和 next gate。
4. 当前 worktree 和本轮测试输出：最终事实。

不得从历史 handoff、追加式日志、旧模型专用计划或固定窗口 prompt 推断当前任务。

## 角色

### 主控 Agent

主控负责：

- 读取当前状态并拆分任务。
- 冻结共享 API、DB、workflow 和 event contract。
- 给每个子任务定义独占写入范围和验收门槛。
- 合并结果、处理冲突并执行 broader verification。
- 统一更新当前进度文档、活动任务板和 coverage matrix。

### 子 Agent

子 agent 只负责已分配的具体子任务：

- 不重新设计总体路线或改写 Phase 状态。
- 不修改未获分配的共享文件。
- 不回滚用户或其他 agent 的未提交改动。
- 发现 contract 冲突、跨域依赖或不完整证据时立即报告。
- 完成实现不等于有权声明 task/Phase/Goal verified。

## 可并行边界

适合并行：

- 不同服务或独立包的只读审计。
- 独立 API package、worker module、Web page 或 live fixture。
- 实现、spec review、quality/privacy review 和验证矩阵审计。

不适合并行：

- 多个 agent 同时编辑同一 migration、共享 contract 或大型测试文件。
- schema 尚未冻结时并行实现多个消费者。
- 一个 agent 改状态机，另一个 agent 按旧状态机编写 live E2E。
- 多个 agent 同时更新进度文档、任务板或 coverage matrix。

## 任务分配格式

每个子任务必须明确：

```text
Objective:
Read first:
Write scope:
Do not touch:
Required invariants:
Verification:
Expected handoff:
```

`Objective` 必须是可独立完成的单一结果。`Write scope` 应按目录或文件收窄；涉及共享文件时由主控串行安排。

## 实现规则

- 行为变更采用 RED -> implementation -> GREEN -> broader verification。
- 数据写入必须 tenant/project/run 或对应 session scope。
- LLM 调用必须通过 LLM Facility module binding。
- 缺依赖、缺 binding、缺 backend 时显式 fail closed。
- 不新增 mock success、silent fallback、fake data 或吞错。
- candidate -> canon、draft -> manuscript 必须是明确用户动作或已审计策略。
- Worldline 保持单世界 `current_world`，不恢复旧 branches/comparison 主模型。
- 公共 API/UI/event/log 不得泄露 prompt、provider response、raw content、credential、object key、draft 或 manuscript 正文。

## 共享 Worktree 规则

当多个 agent 共享同一 worktree 时：

- 开工前运行 `git status --short`。
- 把出现的未知改动视为用户或其他 agent 的改动，不回滚。
- 编辑前确认目标文件没有其他 agent 正在写。
- 子 agent 完成后立即报告修改文件和仍在运行的命令。
- 主控在合并前重新读取最终文件，不能只依赖子 agent 摘要。

使用独立 worktree 时，仍必须从主控确认的同一 commit/contract 基线开始；不要在独立分支重新引入已删除的历史进度文档。

## Review 与验证

高风险切片至少需要：

1. Spec review：验证范围、contract、fail-closed 和产品语义。
2. Quality/privacy review：验证错误边界、租户隔离、敏感数据和可维护性。
3. Focused tests：证明新行为。
4. Broader tests：覆盖受影响包或服务。
5. 对真实执行链需要相应 live-local、browser、external-provider/cluster 或 production 证据。

默认 skip 的 live test、recording client、metadata-only shell 和源码正则测试不能上卷成产品 E2E。

## 交接格式

```markdown
## Status
DONE / DONE_WITH_CONCERNS / BLOCKED

## Files Changed
- ...

## Behavior
- ...

## Verification
- command: result

## Risks
- ...

## Next Gate
- ...
```

## 文档更新权限

- 主控统一更新 `24-current-development-progress.md`、活动任务板和 coverage matrix。
- 子 agent 只提交建议状态与验证证据，除非任务明确授权其修改这些文件。
- 不再创建新的 handoff、live-progress、模型专用开发计划或固定任务 prompt 文档。
- 需要历史时使用 Git；当前工作树只保留当前真相源。
