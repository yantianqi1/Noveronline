# 连通性审查后续优化方案（doc 32 remediation）

更新时间：`2026-07-13`

## 文档定位

本文是 `32-current-module-connectivity-audit.md` 的执行方案，回答如何按优先级关闭零起点写作闭环断点。

本文不替代：

1. `DEVELOPMENT_PLAN.md`：范围与最终 DoD
2. `24-current-development-progress.md`：唯一当前进度
3. `tasks/refactor-saas-parallel-board.md`：活动任务与 next gate
4. 当前 worktree、schema、测试输出：冲突时的最终事实

范围边界：

- 属于 `Z-028` 后续产品扩展与 Writer/Pi/Knowledge 连通性修复
- **不改写** MAIN-100 / Phase 0-8 完成定义
- 中央 `server.go` / `main.go` / worker 注册改动走 MAIN-100 集成通道

## 已锁定决策

### 正文真相源（CONN-001）

`manuscript_blocks` 是唯一正文真相源。

- `scenes` 降为结构元数据：标题、大纲、brief、POV
- 不再在 Structure 面板保存 `scenes.content_text` 作为正文
- 手写、AI adoption、revise patch、restore 四来源写入同一 manuscript 版本链
- 蒸馏源以 `status='active'` 的 manuscript 内容与版本为边界，不要求 `source_draft_id IS NOT NULL`

### 范围

P0 + P1 连续创作：`CONN-001`~`011`、`015`~`017`。

明确不在本轮：

- `CONN-012` embedding 绑定重配
- `CONN-013` 真实闭环数据证据
- `CONN-014` / `CONN-018` fresh desktop/mobile 浏览器全链认证（Z7）

## 执行 Wave

```text
W1 CONN-001 正文单一真相源
  -> W2 CONN-002 章节/场景 typed 全链
  -> W10 CONN-008 Pi 连续上下文

W1 -> W5 CONN-004 事务性 outbox
  -> W6 CONN-005 proposal 版本生命周期
  -> W7 CONN-003 Graph canonical projection
  -> W12 CONN-010 Worldline/Character 上下文

并行：
  W3 CONN-006 并发保存保护
  W4 CONN-007 revise 行内回填
  W8 CONN-015 幂等 + Temporal 补偿（中央）
  W9 CONN-016/017 admission 全预检 + fail-closed（中央）
  W11 CONN-009 persistent thread/approvals（中央）
  W13 CONN-011 长章蒸馏 window/checkpoint
```

### 阶段 A — P0 数据完整性

| Wave | CONN | 目标 |
|---|---|---|
| W1 | 001 | 空白 manuscript block 创建；蒸馏接受任意 active block；scene 去正文 |
| W2 | 002 | Web -> Go -> admission -> Temporal -> Pi 全链传递 chapter/scene |
| W3 | 006 | 乐观锁冲突保留本地 draft，提供 compare/merge/另存 |
| W4 | 007 | revise 事件行内 diff + 专用 patch，禁止普通整块 adoption |
| W5 | 004 | adoption 与 distillation outbox 同事务；错误可观测可重放 |
| W6 | 005 | 真实 expected_target_version；conflict 可提交；finalize 顺序安全 |
| W7 | 003 | 接受 character/relationship/world_rule/plot_thread 时投影到 Graph 源表 |

### 阶段 B — P1 连续创作上下文与可靠性

| Wave | CONN | 目标 |
|---|---|---|
| W8 | 015 | Idempotency-Key replay；Temporal start 失败补偿 |
| W9 | 016/017 | 预检 orchestrator+composer；缺 Temporal fail closed |
| W10 | 008 | Pi 读取 active manuscript 邻域、显式 path、canon 资产 |
| W11 | 009 | 挂载 threads/messages/approvals 生产接线 |
| W12 | 010 | Worldline/Character 共享 preparation 与 Graph/entity 正确 ID |
| W13 | 011 | 长章 window/checkpoint/跨窗口 identity merge |

## 中央集成约束

以下项必须修改中央文件，不能由领域子目标单独合入：

- W5 dispatcher / adoption enqueue 接线：`apps/api/cmd/api/main.go`、`apps/api/internal/httpapi/server.go`
- W8 requestID / admission replay：`server.go`、`writer_admission.go`、`writer.go`
- W9 Temporal fail-closed / multi-module precheck：`main.go`、`server.go`
- W11 thread store 挂载与路由：`main.go`、`server.go`

## 验收映射

本方案完成后，对应 doc 32 最终验收定义中的：

- #2 #3 纯手写进入 manuscript 并可审校/导出
- #4 并发冲突正文可恢复
- #5 revise 不追加独立块
- #6 蒸馏 durable 且失败可见
- #8 二次 merge 不再固定 version=1
- #9 接受资产后 Graph 有节点/边
- #10 #11 Worldline/Character 消费完整上下文
- #12 #13 chapter/scene 作用域进入 Pi 与 adopted block
- #14 persistent thread/approval 可操作
- #17 幂等与 Temporal 补偿

仍待 Z7：#15 #16 独立 live stack 浏览器全旅程与截图。

## 验证策略

1. 每 wave 先跑 focused tests（Go / Web / Pi / Python）
2. 数据完整性 wave 增加 disposable Postgres live：
   - 空白 block 创建 + 蒸馏源
   - 二次/三次 merge
   - 并发同 identity
   - adoption + outbox 同事务
   - proposal acceptance -> Graph node/edge
3. 完成后校准 `24-current-development-progress.md` 与任务板中
   `implemented` / `connected` / `verified` 用词

## 状态

| Wave | 状态 |
|---|---|
| 文档落地 | `connected` |
| W1 CONN-001 正文单一真相源 | `connected` |
| W2 CONN-002 章节/场景 typed 全链 | `connected` |
| W3 CONN-006 并发保存保护 | `connected` |
| W4 CONN-007 revise 行内回填 | `connected` |
| W5 CONN-004 事务性 outbox + 可观测 | `connected`（adoption 后 enqueue 失败可见；dispatcher tick 记日志；claim 不再静默吞错） |
| W6 CONN-005 proposal 版本生命周期 | `connected`（真实 expected_target_version；conflict 先提交再返回） |
| W7 CONN-003 Graph projection | `connected`（accept 同事务投影；Graph rebuild 仍由 MAIN 触发） |
| W8 CONN-015 幂等 + Temporal 补偿 | `connected` |
| W9 CONN-016/017 admission 全预检 | `connected` |
| W10 CONN-008 Pi 连续上下文 | `connected` |
| W11 CONN-009 threads/approvals | `connected` |
| W12 CONN-010 Worldline/Character | `connected` |
| W13 CONN-011 长章 window | `connected` |
| Z7 browser 全链证据 | 不在本轮；仍 `in_progress` |

用词约定：`connected` = 代码路径已接线且 focused tests 通过；`verified` 仅在 disposable live / browser 证据齐备后使用。
