# 审查问题修复计划

更新时间：2026-08-01

本计划基于本目录的静态审查报告，并以当前 worktree、代码和测试为最终事实。严重度按“可能造成安全/成本/数据正确性影响”排序；报告中已经由此前审计修复的问题不重复改造。

## 一、问题清单（从重到轻）

| 优先级 | 类型 | 问题与证据 | 修复策略 | 验收 |
|---|---|---|---|---|
| P0 | 成本/资源控制漏洞 | Writer 的 `resolveQueryEmbedding` 直接请求 embedding provider，没有 quota reservation、并发 lease、usage telemetry；证据：`apps/pi-agent-runtime/src/runtime/postgres-pi-writer-deps.ts`。 | 把 embedding 请求纳入 Pi Writer 的统一 `executeLLMStage` 生命周期，使用独立的 `embedding` stage 和稳定 provider call id；失败时保留显式 keyword degradation。 | Pi focused quota/embedding tests；typecheck/build。 |
| P1 | 实时通信缺陷 | Web `use-writer-run.ts` 以 900ms 轮询读取事件，Go 已有 held-open SSE；造成事件表读放大、延迟和双实现维护成本。 | 通过同源 BFF 增加流式代理，Web 使用可恢复 SSE；25 秒 hold 到期、网络断开或非终态时按 event id 重连，仍保留 run status/draft 权威读取。 | Web SSE parser/reconnect tests；Go/Web typecheck/build；现有 reducer tests。 |
| P1 | 契约/维护 bug | `save_draft_revision` 既不注册给 Writer Agent，又存在于 Writer tool union、权限、schema 和 tool description 中；模型契约与真实能力不一致。 | 从模型可见 Writer tool contract 和权限清单移除；保留真正的 runtime `saveDraftRevision` persistence dependency，不改变 draft 落库。 | 全仓 active SaaS 搜索无死工具名；shared-contracts/Pi tests。 |
| P1 | 事件消费缺口 | `writer.consistency.clean/skipped/degraded` 已产生但 Web reducer 丢弃，作者无法区分“干净、跳过、降级”。 | 在 reducer 中保存一致性检查状态，并在 rail 显式呈现；不把审校结果误当成阻塞错误。 | Web reducer/UI focused tests。 |
| P2 | 内存增长 | `TemporalWriterStarter.runs` 只增不减；生产读路径以 SQL reader 为准，但长生命周期 API 进程仍会积累 run 元数据。 | 给辅助缓存设置有界容量并清理终态条目；不改变 SQL reader 和 admission 真相源。 | Go cache bound/tenant tests；`go test ./...`。 |
| P2 | 提示词可运维性 | 主要 system prompt 散落在 TS 函数中，无统一 key/version，无法在 trace 和回滚记录中识别版本。 | 建立轻量 prompt registry，集中声明 key/version，并让各阶段生成的 prompt 带稳定版本标识；本轮不引入新的数据库管理后台。 | Pi prompt registry tests；运行时 prompt snapshot 含版本标识。 |
| P3 | 扩展风险 | Writer/Cast 复用四个工具名但 schema 不同。当前 Agent 隔离，无现时越权 bug；合并会话时有覆盖风险。 | 本轮不改公网/运行时工具名，避免破坏现有契约；增加 namespace invariant 文档和测试，后续合并 Agent 前再做显式命名迁移。 | namespace contract test/documented follow-up。 |
| P3 | 产品待决 | `writer_approvals` 有表和 Go decide route，但当前没有 producer/UI；审批语义和是否保留未确认。 | 不删除表、不伪造审批成功路径；保留为明确 decision gate。产品确认后单独实现端到端 producer、列表、决策和事件恢复。 | 计划中记录为 blocked-by-decision。 |

## 二、本轮实施顺序

当前实施状态：P0 embedding quota、P1 SSE、P1 dead tool contract、P1 consistency event consumption、P2 run cache、P2 prompt registry 已完成并验证；P3 tool namespace 与审批流仍是后续决策项。

1. P0 embedding quota 生命周期。
2. P1 SSE BFF/客户端切换。
3. P1 移除死 Writer tool contract，并消费 consistency 状态事件。
4. P2 有界 run cache。
5. P2 prompt registry/version 标识。
6. 运行受影响 focused tests，再运行 Go/Pi/Web 全量验证；只提交本轮修复及当前审查关联的已有修改，不纳入 `tools/ui-preview/shots/` 截图产物。

## 四、最终验收记录（2026-08-01）

- Go API：`gofmt` + `go test ./...` 全部通过。
- Pi Runtime：`npm run typecheck`、`npm test`（17 个测试文件通过，141 passed / 4 skipped）和 `npm run build` 通过。
- Web：`npm run typecheck`、`npm test`（125 tests，124 passed / 1 skipped）和 `npm run build` 通过。
- active SaaS 代码中已无 `save_draft_revision` 模型工具残留；runtime-owned `saveDraftRevision` 持久化依赖保留。
- `tools/ui-preview/shots/` 是用户已有的未跟踪截图产物，本次不纳入提交。

## 三、不在本轮擅自改变的边界

- 不恢复旧 `frontend/`、多分支 Worldline、Legacy cutover 或旧式 LLM 环境变量 fallback。
- 不把 candidate/draft 自动升级为 canon。
- 不因“server.go 过大”做无测试保障的大规模路由拆分；后续以独立重构任务推进。
- 不未经产品确认删除 `writer_approvals` 或给它添加假的成功 UI。
- 不把 Pi SDK 升级当作本轮 bug 修复；升级需单独的兼容性和 live 验证窗口。
