# MiroFish-Novel SaaS 100% Subagent Development Plan

更新时间：`2026-07-07`

## 用途

本文把 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 当前 SaaS 重构状态，整理成一份从约 `55%-60%` 推进到 `100%` 的 subagent 开发方案。它不替代：

- `docs/refactor-saas/DEVELOPMENT_PLAN.md`：阶段总纲。
- `docs/refactor-saas/22-midstream-handoff-summary.md`：中途接手事实。
- `tasks/refactor-saas-live-progress.md`：实时进度记录。
- `tasks/refactor-saas-parallel-board.md`：任务状态看板。
- `docs/refactor-saas/18-legacy-coverage-matrix.md`：旧功能覆盖真相源。

本文的目标是让后续 `/goal` 能直接启动连续 subagent 开发，直到重构达到真实产品闭环，而不是停在 schema、API skeleton、fail-closed shell 或 metadata-only path。

## 工作区硬边界

所有重构任务只允许在下面的 worktree 进行：

```text
/Users/yantianqi/Documents/Noveronline-saas-mainline
```

主仓库 `/Users/yantianqi/Documents/Noveronline` 只作为 git common dir 和参考基线，不用于 SaaS 重构实现，不用于判断当前重构进度，不允许覆盖其中未提交改动。

每轮开始必须运行：

```bash
git -C /Users/yantianqi/Documents/Noveronline-saas-mainline status --short
git -C /Users/yantianqi/Documents/Noveronline-saas-mainline branch --show-current
```

预期分支：

```text
codex/saas-mainline
```

## 当前真实状态

按产品闭环估算，当前 SaaS 重构约完成 `55%-60%`。

| Phase | 当前进度 | 真实缺口 |
|---|---:|---|
| Phase 0 | 100% | 已完成文档、覆盖矩阵和 worktree 基线。 |
| Phase 1 | 80%-90% | Writer 真实 streaming/tool loop/live LLM E2E/draft adoption 仍未完整闭环。 |
| Phase 2 | 70%-80% | Writer 已能读 assets/graph/worldline paths，但 proposal tools 和 live reference E2E 未闭环。 |
| Phase 3 | 70%-80% | Go API、Next shell、Postgres/RLS、workers skeleton 已有；Auth/project picker/full compose health 未闭环。 |
| Phase 4 | 75%-85% | LLM Facility 主体已有；quota/billing/retry/live provider/cluster E2E 未闭环。 |
| Phase 5 | 50%-65% | Seed/Assets/Graph 有大量 DB-backed path；Story Graph adoption backend API/store 已推进；browser E2E、provider success chain、vector/hybrid、Graph adoption UI/live E2E 未闭环。 |
| Phase 6 | 35%-45% | Worldline/Character 仍偏 metadata/admission；runtime、dialogue、interaction -> draft 闭环未完成。 |
| Phase 7 | 0%-10% | Legacy import 和旧架构清理基本未开始。 |
| Phase 8 | 0%-10% | Auth/Ops/Billing/Security/production hardening 大多仍是设计。 |

## 100% 完成定义

重构达到 `100%` 必须同时满足：

1. 用户能完成真实产品链路：

```text
login -> tenant/project -> upload novel -> seed -> assets/search -> graph -> worldline/character context -> writer draft -> review/dedup -> adopt manuscript -> export
```

2. 所有 LLM 调用均通过 LLM Facility module binding，不存在旧式 env fallback、mock success、fake data 或 silent fallback。
3. 所有业务写入和 runtime 调用具备 tenant/project/run 或 session context，并通过 RLS/RBAC 验证。
4. Agent 输出默认只能是 candidate/draft；candidate -> canon、draft -> manuscript 必须是明确用户动作或已记录策略。
5. 公共 API、UI、workflow event、trace export、log 不公开 prompt、provider response、raw body/content、API key、encrypted credential、`credential_ref`、object key、draft 或 manuscript 正文。
6. `docs/refactor-saas/18-legacy-coverage-matrix.md` 每一行都变成 `verified`、`deprecated-with-reason`、`blocked-with-owner` 或带 owner/wave 的 `planned`。
7. 至少一个真实旧项目完成 dry-run import report、selected import、failure/rollback report 验收。
8. full-stack compose、browser E2E、provider E2E、Temporal cluster E2E、backup/restore、observability 和 security gates 全部通过。

## Subagent 总规则

Coordinator 负责拆分、整合、验收、看板和文档。实现型 subagent 负责独立代码 slice。每个实现 slice 必须有两个 review subagent：

1. Spec Reviewer：检查是否满足 wave/task 规格，是否少做或多做。
2. Quality Reviewer：检查代码质量、隐私边界、测试充分性和维护风险。

每个实现 subagent 必须：

- 只在 assigned 文件/模块范围内写入。
- 明确报告修改文件、验证命令、剩余风险。
- 不修改其他 subagent 的工作，不回滚用户或其他 agent 改动。
- 行为变更采用 TDD：RED -> implementation -> GREEN -> focused regression。
- 完成后不直接宣称 phase verified，除非该 wave 的所有验收门槛已由 Coordinator 复核。

每个 wave 结束后，Coordinator 必须同步：

- `tasks/refactor-saas-live-progress.md`
- `tasks/refactor-saas-parallel-board.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- 相关 phase 文档，例如 `13-agent-runtime.md`、`14-data-model.md`、`15-api-contracts.md`

每个 wave 独立提交。不要把多个未验收 wave 混进一个提交。

## Wave 0：治理与验收矩阵校准

目标：先把“什么叫完成”固定下来，避免后续 subagent 把 skeleton 当闭环。

Subagents：

| Agent | 责任 | 写入范围 |
|---|---|---|
| Coverage Auditor | 逐行审计 coverage matrix，把裸 `planned` 转成后续任务归属 owner/wave。 | `docs/refactor-saas/18-legacy-coverage-matrix.md` 建议稿，由 Coordinator 合并。 |
| Phase Consistency Auditor | 统一 `DEVELOPMENT_PLAN.md`、`17-migration-roadmap.md`、看板中的 Phase 编号和状态词。 | `docs/refactor-saas/*.md` 相关状态段。 |
| Acceptance Matrix Agent | 生成最终验收命令矩阵和 live E2E gating。 | `tasks/refactor-saas-live-progress.md` 与本计划后续更新。 |

验收：

```bash
rg -n "planned|Phase 11|Phase 12|blocked \\|.*verified" docs/refactor-saas tasks
git diff --check
```

通过标准：

- Phase 编号一致。
- `planned` 行都有 owner/wave。
- `P6-003` reviewer/dedup 状态与 coverage matrix 不再冲突。

## Wave 1：Writer Live Closure

目标：把 Writer 从 admission/skeleton 推到真实 live LLM draft 闭环。

Subagents：

| Agent | 责任 | 写入范围 |
|---|---|---|
| Pi Streaming Agent | 实现真实 token streaming、tool started/completed、tool loop invocation。 | `apps/pi-agent-runtime/src/**` |
| Draft Adoption Agent | 补 SaaS draft read/preview/adopt API，draft -> manuscript 显式动作。 | `apps/api/internal/workflows/**`、`apps/api/internal/httpapi/**`、必要 migration。 |
| Writer UI Agent | Next Writer draft preview、recovered event replay、adopt action。 | `apps/web/components/writer-workbench-shell.tsx`、`apps/web/lib/api.ts` |
| Writer E2E Agent | live/local provider E2E，刷新后恢复 run/draft。 | tests only first, then minimal harness. |

验收命令：

```bash
cd apps/api && go test ./internal/workflows ./internal/httpapi -run 'Writer|Draft|Trace|LLM|Workflow' -count=1
cd apps/pi-agent-runtime && npm run test && npm run typecheck
cd apps/web && npm run test -- --test-name-pattern='Writer|writer'
```

产品验收：

- live run 产生 `writer.token`、`writer.tool.started`、`writer.tool.completed`、`writer.draft.saved`、`writer.run.completed`。
- 页面刷新后可恢复 run 状态、events、draft。
- draft adoption 只能由用户显式触发。
- 不公开 prompt/API key/credential/draft/manuscript 私密正文。

## Wave 2：SaaS Auth / Tenant / Project / RBAC

目标：从开发期 `X-Tenant-Id` / `X-User-Id` 过渡到真实 SaaS auth context。

Subagents：

| Agent | 责任 | 写入范围 |
|---|---|---|
| Auth API Agent | `/v1/me`、login/dev session、tenant/project list/create。 | `apps/api/internal/auth/**`、`apps/api/internal/httpapi/**` |
| RBAC Agent | membership lookup、role matrix、trace/full access gate、writer/LLM/action permissions。 | `apps/api/internal/**` |
| Web Tenant Agent | tenant/project picker、session context、移除关键路径 header trust。 | `apps/web/app/**`、`apps/web/components/**` |
| Security Test Agent | cross-tenant 403/404、RLS/RBAC integration tests。 | tests |

验收命令：

```bash
cd apps/api && go test ./internal/httpapi ./cmd/api -run 'Auth|Tenant|Project|Membership|RBAC' -count=1
cd apps/web && npm run test && npm run typecheck
```

通过标准：

- 无伪造 headers 也能从 session/auth claims 得到 tenant/user。
- 跨租户读写失败。
- viewer/editor/admin 权限区分生效。

## Wave 3：LLM Facility Production Hardening

目标：让 LLM Facility 从可配置变成可运营、可限额、可诊断。

Subagents：

| Agent | 责任 | 写入范围 |
|---|---|---|
| Provider E2E Agent | live model sync/provider call success/failure E2E。 | `apps/api/internal/llm/**`、tests |
| Quota Agent | tenant/project/module usage aggregation、budget/quota/rate limit admission。 | `apps/api/internal/llm/**`、migration |
| Concurrency Agent | channel/module/resource locks 在多 worker 下生效和释放。 | `apps/api/internal/llm/**`、runtime deps |
| Diagnostics Agent | binding health、provider failure diagnostics、UI 状态。 | `apps/web/components/llm-facility-shell.tsx` |

验收命令：

```bash
cd apps/api && go test ./internal/llm ./internal/httpapi -run 'LLM|Quota|Usage|ModelSync|Concurrency' -count=1
cd apps/pi-agent-runtime && npm run test
cd apps/web && npm run test -- --test-name-pattern='LLM|llm'
```

通过标准：

- provider 成功/失败都有稳定 public 状态。
- quota 超限拒绝，不进入 provider call。
- 并发锁在失败、取消、worker crash 后可释放或被 lease recovery 处理。

## Wave 4：Seed 产品闭环

目标：把 Seed 从 partial live harness 推到真实 browser/provider pipeline。

Subagents：

| Agent | 责任 | 写入范围 |
|---|---|---|
| Browser Upload Agent | `/overview` browser upload -> object PUT -> complete -> start -> event replay。 | `apps/web/components/overview-seed-shell.tsx`、`apps/api/internal/sourcefiles/**` |
| Seed Provider Agent | sequential/global/ontology/entity/profile/finalize provider success chain。 | `apps/agent-runtime/mirofish_agents/temporal/seed.py`、tests |
| Seed Retry Agent | failed segment retry backend、worker recovery、cluster diagnostics。 | `apps/api/internal/workflows/**`、`apps/agent-runtime/**` |
| OCR/Segmentation Agent | OCR PDF 或明确 postponed flag；语义分段增强。 | `apps/agent-runtime/mirofish_agents/seed/**` |

验收命令：

```bash
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_live_e2e.py tests/test_seed_workflow.py -q
cd apps/api && go test ./internal/sourcefiles ./internal/workflows ./internal/httpapi -run 'Seed|Upload|SourceFile|Retry|LLM|Activity|Usage' -count=1
cd apps/web && npm run test -- --test-name-pattern='Seed|seed|Overview|overview'
```

通过标准：

- live tests 在配置 live env 时必须 executed，不能只 skipped。
- browser 上传 TXT/MD/PDF 后可启动 Seed 并看到持久化进度。
- provider success 写 canon/readiness/asset projection。
- 失败 segment retry 不伪造成功。

## Wave 5：Assets / Search / Vector

目标：补齐资产库的向量、hybrid、reindex 和 provider E2E。

Subagents：

| Agent | 责任 | 写入范围 |
|---|---|---|
| Embedding Agent | `asset_embeddings`、manuscript/worldline embeddings、pgvector schema。 | migration、`apps/api/internal/assets/**` |
| Hybrid Search Agent | keyword/vector/hybrid ranking、filters、sanitized result contract。 | `apps/api/internal/assets/**`、`apps/web/lib/api.ts` |
| Reindex Agent | DB-backed live reindex、bulk/memory-review browser check。 | `apps/api/internal/workflows/**`、`apps/agent-runtime/temporal/assets.py` |
| Provider Asset Agent | ingestion/style/archive provider E2E。 | `apps/agent-runtime/mirofish_agents/temporal/assets.py` |

验收命令：

```bash
cd apps/api && go test ./internal/assets ./internal/workflows ./internal/httpapi -run 'Asset|Search|Vector|Reindex|Archive|Ingestion|Style' -count=1
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_asset_ingestion_workflow.py -q
cd apps/web && npm run test -- --test-name-pattern='Asset|asset'
```

通过标准：

- keyword/vector/hybrid 都可查。
- reindex 写真实索引/embedding rows。
- provider 输出只进入 candidate，显式 adoption 才能 canon/material。

## Wave 6：Story Graph 完整闭环

目标：补 Graph build/UI/adoption/canon 端到端。

Subagents：

| Agent | 责任 | 写入范围 |
|---|---|---|
| Graph Build Agent | DB-backed graph build live E2E。 | `apps/agent-runtime/mirofish_agents/temporal/graph.py`、`apps/api/internal/storygraph/**` |
| React Flow Agent | 真实 canvas、search locate、inspector、large graph layout。 | `apps/web/components/story-graph-shell.tsx` |
| Bond Adoption Agent | candidate viewer、explicit adoption API/UI、relationships/plot_threads/canon 写入。 | `apps/api/internal/storygraph/**`、`apps/web/**` |
| Evidence Agent | evidence gating、snippet access audit、privacy tests。 | `apps/api/internal/storygraph/**` |

验收命令：

```bash
cd apps/api && go test ./internal/storygraph ./internal/workflows ./internal/httpapi -run 'StoryGraph|Graph|Bond|Evidence|Adoption' -count=1
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_story_graph_workflow.py -q
cd apps/web && npm run test -- --test-name-pattern='Story Graph|graph'
```

通过标准：

- graph 从 Seed structured canon 构建。
- 1000 节点项目默认可读。
- bond candidate 不自动 canon。
- adoption 有审计并写入明确归属表。

## Wave 7：Worldline Runtime

目标：把 Worldline 从 metadata/admission 推到真实 runtime candidate generation。

Subagents：

| Agent | 责任 | 写入范围 |
|---|---|---|
| Prepare Runtime Agent | dossier、prepared agents、private runtime seed state。 | `apps/agent-runtime/mirofish_agents/temporal/worldline.py`、Go read side |
| Auto Evolution Agent | agent proposal、director judgement、candidate event loop、state/relation updates。 | `apps/agent-runtime/**`、`apps/api/internal/worldline/**` |
| Saved Path Agent | runtime path proposal/save/adopt boundary。 | `apps/api/internal/worldline/**`、`apps/web/components/worldline-shell.tsx` |
| Worldline E2E Agent | provider/Postgres/Temporal/live read-side E2E。 | tests |

验收命令：

```bash
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py tests/test_worldline_live_e2e.py -q
cd apps/api && go test ./internal/worldline ./internal/httpapi -run 'Worldline|Preparation|Step|Event|Adoption|SavedPath' -count=1
cd apps/web && npm run test -- --test-name-pattern='Worldline|worldline'
```

通过标准：

- prepare 写真实 prepared agents。
- runtime 生成 candidate events。
- saved path 可供 Writer 引用。
- candidate -> canon 仍为显式 adoption。

## Wave 8：Character Console Runtime

目标：让 Character Console 产生真实角色互动，同时不越权写 canon/manuscript。

Subagents：

| Agent | 责任 | 写入范围 |
|---|---|---|
| Character Runtime Agent | first-person/director/dialogue mode workflow/activity。 | `apps/api/internal/characterconsole/**`、`apps/agent-runtime/**` |
| Memory Agent | agent memory/history/action/dialogue loader。 | `apps/api/internal/characterconsole/**` |
| Events Agent | `events` endpoint 从 pending 变真实 replay/stream。 | `apps/api/internal/httpapi/**`、`apps/web/components/character-console-shell.tsx` |
| Handoff Agent | interaction -> Writer specialized draft workflow。 | `apps/api/internal/workflows/**`、`apps/pi-agent-runtime/**` |

验收命令：

```bash
cd apps/agent-runtime && .venv/bin/python -m pytest tests -q -k 'character or worldline'
cd apps/api && go test ./internal/characterconsole ./internal/httpapi -run 'CharacterInteraction|CharacterConsole|Events|Turns|ChapterDraft' -count=1
cd apps/pi-agent-runtime && npm run test && npm run typecheck
```

通过标准：

- AI/world reaction 作为 public turn/candidate metadata 记录。
- 不直接写 manuscript。
- interaction -> draft revision -> adopt manuscript 可追踪。

## Wave 9：Legacy Import / Cleanup

目标：证明旧功能没有漏、旧架构不再作为产品运行时。

Subagents：

| Agent | 责任 | 写入范围 |
|---|---|---|
| Importer Agent | 旧项目 discovery、dry-run report、id mapping、selected import。 | `apps/api/internal/importer/**` 或专用 migration tool |
| Coverage Agent | 旧 page/API/table/module 逐项 verified/deprecated。 | `docs/refactor-saas/18-legacy-coverage-matrix.md` |
| Cleanup Agent | 关闭旧 public route/fallback/local truth source。 | legacy route wiring、docs |
| Migration QA Agent | 真实旧项目 import + rollback/failure report。 | tests |

验收命令：

```bash
cd apps/api && go test ./... -run 'Import|Legacy|Migration|Coverage' -count=1
cd backend && .venv/bin/python -m pytest tests/test_full_legacy_migration.py tests/test_migration_verifier.py -q
rg -n "planned" docs/refactor-saas/18-legacy-coverage-matrix.md
```

通过标准：

- 至少一个真实旧项目 dry-run + import + failure report 通过。
- coverage matrix 无裸 `planned`；允许带 owner/wave 的 `planned`。
- 保留的 legacy code 仅服务 migration/export。

## Wave 10：Ops / Production Hardening

目标：补齐上线前最低生产约束。

Subagents：

| Agent | 责任 | 写入范围 |
|---|---|---|
| Compose Agent | api/web/workers/dependencies 一键健康。 | `infra/docker-compose.yml`、Dockerfile |
| Observability Agent | metrics/logs/traces/alerts、redaction tests。 | `apps/api/**`、runtime logging |
| Backup Agent | backup/restore drill。 | `infra/**`、scripts |
| Security Agent | CSRF/cookie/rate limit/secret redaction/data deletion/export。 | `apps/api/internal/security/**`、tests |

验收命令：

```bash
docker compose --env-file infra/.env.example -f infra/docker-compose.yml config --quiet
docker compose --env-file infra/.env.example -f infra/docker-compose.yml up -d --build
```

通过标准：

- web/api/workers/dependencies 全部 healthy。
- backup restore drill 通过。
- 日志扫描不含 `api_key`、`credential_ref`、`sk-`、prompt 原文或 manuscript 正文。

## Wave 11：最终验收

目标：独立审计重构是否可以标记为 100%。

Subagents：

| Agent | 责任 |
|---|---|
| Final Product E2E Agent | 跑 login -> upload -> seed -> assets/graph/worldline/character -> writer -> adopt -> export。 |
| Security/RLS Agent | RBAC/RLS/cross-tenant/secret redaction 全面审计。 |
| Legacy Coverage Agent | `18-legacy-coverage-matrix.md` 全行验收。 |
| Ops Readiness Agent | compose、backup、observability、incident playbook 验收。 |

最终命令基线：

```bash
cd apps/api && go test ./... -count=1
cd apps/agent-runtime && .venv/bin/python -m pytest tests -q
cd apps/pi-agent-runtime && npm run test && npm run typecheck
cd apps/web && npm run test && npm run typecheck && npm run build
cd backend && .venv/bin/python -m pytest tests/test_saas_phase3_rls_schema.py tests/test_saas_phase3_infra.py -q
docker compose --env-file infra/.env.example -f infra/docker-compose.yml config --quiet
git diff --check
```

通过标准：

- 所有命令 exit 0。
- live/browser/provider/cluster E2E 记录在 `tasks/refactor-saas-live-progress.md`。
- 看板、coverage matrix、handoff summary 与实际状态一致。
- 无未提交实现改动。

## 可直接启动任务的提示词

将下面提示词复制到新对话或 `/goal` 中即可开始下一轮开发：

```text
/goal 按照 `/Users/yantianqi/Documents/Noveronline-saas-mainline/tasks/refactor-saas-100-percent-subagent-development-plan.md` 继续 MiroFish-Novel SaaS 重构，使用 subagent 推进到 100%。

硬边界：
- 只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 工作。
- 不修改 `/Users/yantianqi/Documents/Noveronline`。
- 开始前运行 `git status --short` 和 `git branch --show-current`，确认分支是 `codex/saas-mainline`，并识别是否有用户未提交改动。
- 不回滚用户或其他 agent 改动。

必须阅读：
- `docs/refactor-saas/DEVELOPMENT_PLAN.md`
- `docs/refactor-saas/22-midstream-handoff-summary.md`
- `tasks/refactor-saas-live-progress.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-100-percent-subagent-development-plan.md`
- 当前 wave 对应的 `docs/refactor-saas/*.md`

执行方式：
1. 从 Wave 0 开始，除非看板明确显示 Wave 0 已 verified。
2. 每个 wave 使用 subagent：实现 agent + spec reviewer + quality reviewer。
3. 每个实现 slice 必须 TDD：RED -> implementation -> GREEN -> focused regression。
4. 每个 subagent 只能写自己负责的目录/模块，避免冲突。
5. Coordinator 负责整合、运行 broader verification、更新 docs/tasks、提交。

硬约束：
- 不新增 mock success、fake data、silent fallback、swallowed error 或旧式 LLM env fallback。
- 所有 LLM 调用必须走 LLM Facility module binding。
- 公共 API/UI/events/logs 不得暴露 prompt、provider response、raw body/content、API key、encrypted credential、`credential_ref`、object key、draft 或 manuscript 正文。
- candidate -> canon、draft -> manuscript 必须是明确用户动作或已记录策略。
- Worldline 保持单世界 `current_world`，不恢复旧多分支主模型。

每个 wave 完成后：
- 更新 `tasks/refactor-saas-live-progress.md`
- 更新 `tasks/refactor-saas-parallel-board.md`
- 更新 `docs/refactor-saas/18-legacy-coverage-matrix.md`
- 如涉及 API/data/runtime，同步 `15-api-contracts.md` / `14-data-model.md` / `13-agent-runtime.md`
- 跑该 wave 的验收命令和 `git diff --check`
- 单独提交

先执行 Wave 0：治理与验收矩阵校准。完成后继续 Wave 1，除非发现必须先修正计划或阻塞项。
```
