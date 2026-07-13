# Refactor SaaS Active Goal Board

更新时间：`2026-07-13`

## 规则

- 范围与最终 DoD：`docs/refactor-saas/DEVELOPMENT_PLAN.md`
- 唯一当前进度：`docs/refactor-saas/24-current-development-progress.md`
- 最终事实：当前 worktree、schema、running compose、本轮 tests/live/browser 输出
- 子目标不得修改中央 `server.go`、`main.go`、base compose、central worker registration、唯一进度文档或本板。
- local provider/synthetic source 不得替代 external provider/real legacy cutover。
- `verified_current` 是关闭状态，不因新会话或最终审计重复实现/重复全量验证；仅在 runtime failure、受影响代码/schema/公共契约变更或明确 DoD 冲突时重开。
- `Z-028` 是 doc 28 后续产品扩展，不改写 MAIN-100 / Phase 0-8 完成定义；切片顺序 `Z0 → Z7` 见 `28-zero-start-writer-and-manuscript-asset-distillation.md`。

## 文件所有权

| 目标 | 独占范围 |
|---|---|
| MAIN-100 | shared HTTP/main/worker/base compose、全局 Web shell、跨域 integration/E2E/release、最终文档 |
| P6-003-A | Writer/Pi/Reviewer/Writer Workspace/Manuscript Workspace 领域实现与专属 Web/tests |
| P5-005-B | Seed/Assets/Graph/Worldline/Character 领域实现与专属 Web/runtime/tests |
| P8-002-C | Auth/Recovery/Collaboration/LLM Admin/Legacy/Ops/Security 领域实现、production overrides、migrations |
| Z-028 | 空项目从零创作、0018 distillation schema、manuscript asset distillation workflow/API/UI、proposal review；集成切片才动中央 main/server/worker/readiness |

## Active Goals

| ID | 状态 | 会话 ID | 当前结论 |
|---|---|---|---|
| MAIN-100 | `awaiting_legacy_authorization` | `019f4cad-2a6f-76e2-a0ec-b3d65b000e9b` | 本地 coverage/central/browser/regression、external provider、platform-default 与 Legacy complete plan 已闭合；等待 real cutover 写入授权 |
| P6-003-A | `verified_current` | `019f4cad-4146-7a50-b20c-252b5f26d7b8` | dedup/book planning producer、Facility、candidate/draft 边界、中央挂载与 browser 认证通过；shared writer contract 与 world-rule/character-profile tools 已补证 |
| P5-005-B | `verified_current` | `019f4cad-15a2-76e1-a6c1-7e49b2f3511c` | Seed trace/retry 与 Knowledge/Simulation full/live/browser 通过 |
| P8-002-C | `verified_current` | `019f4cac-fde5-71d1-b71f-090a037551af` | model-sync/retirement/Legacy/Ops/Security/matrix reviewer 通过 |
| Z-028 | `in_progress` | current | Z0–Z6 `connected` + 2026-07-13 disposable app-role live 绿（distillation/manuscript/empty-writer/worldline/character）与 Pi local-provider live 2/2；Z7 仍缺：Docker socket 权限下的 `--app` 全栈重建、Playwright 浏览器安装、authenticated zero-start desktop/mobile journey |

## 当前证据

1. Central handlers/workers/security shell、readiness migration 14、fixed read-only Legacy source root 已挂载；platform channel/default 的 FORCE RLS 与 project > tenant > platform resolver contract 已闭合。
2. Go/Python/Pi/Web/schema/infra full regression 当前通过；live DB fixtures 已禁止在 upgraded ledger DB 重放 raw migrations。
3. Writer、Worldline/Character、Platform 三条 production-style browser 旅程通过，零 privacy/pageerror finding；Platform browser 后 recovery direct grants 为 0。
4. Compose persistent recovery、backup/restore、rate limit、observability/alerts 当前通过；restart invariant 强制 recovery direct grants 为 0；Temporal readiness 已通过 20/20 串行、50/50 五并发和 bounded strict poller 5/5。
5. Coverage Matrix 当前为 `90 verified / 25 verified replacement / 5 explicit non-restored / 1 blocked`，无裸未决表格状态；唯一 blocked row 为 real Legacy source。
6. Phase 3 `packages/shared-contracts` 已由 JSON Schema + Go/Pi/Web AST drift tests 约束；Pi world-rule/character-profile app-role live 证明同租户跨项目与跨租户隔离、公开薄投影及零 canon/adoption/manuscript 写入。
7. Legacy relationship-owned evidence 兼容映射已修复；三个候选项目 plan 均 `complete` / zero blockers，deterministic replay 与公开报告 privacy scan 通过。

## Next Gate

| Gate | Owner | 所需输入 | 完成证据 |
|---|---|---|---|
| Coverage Matrix closure | P5/P6/P8 + MAIN review | 当前 worktree/runtime | `verified_current`：90/25/5/1，唯一 blocked row 为 real Legacy source |
| External provider success | MAIN-100 | 用户已授权 HTTPS provider；ADMIN_DATABASE_URL 由 MAIN 从本地 Compose 静默构造 | `verified_current`：strict 2 passed + JSON/tools/health 200 + encrypted formal channel + 26 bindings + privacy |
| Real legacy cutover | MAIN-100 + P8 contract | 用户确认当前候选为真实业务数据并授权 disposable target 写入，或提供另一组获授权 SQLite/artifacts | 当前 complete plan 绑定下的 apply/verify/rollback/final cutover sanitized reports |
| Final DoD audit | MAIN-100 | 上述唯一未完成 gate 通过 | 只复核冻结矩阵与 Legacy 直接影响证据；DEVELOPMENT_PLAN 每条 DoD 齐全后 Goal complete |
| Z7 Temporal provider + browser | Z-028 | healthy temporal-db-init + writer-planning worker + provider binding | real distill activity + desktop/mobile privacy journey |
| App-role live (done) | Z-028 | disposable Postgres schema 0018 | `TestLiveEmptyProject*` + `TestLiveAssetDistillation*` passed |

在 real Legacy source gate 完成前，MAIN-100 保持 active，不得改写为 100% complete。
`Z-028` 与 MAIN-100 并行，不替代 Legacy 授权 gate。
