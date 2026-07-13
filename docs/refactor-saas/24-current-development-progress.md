# SaaS Current Development Progress

更新时间：`2026-07-13`

## 文档职责

本文是完整 SaaS 重构的唯一当前进度入口。范围与最终 DoD 以 `DEVELOPMENT_PLAN.md` 为准，活动目标与文件所有权以 `tasks/refactor-saas-parallel-board.md` 为准；冲突时以当前 worktree、schema、运行中 compose 和本轮测试输出为最终事实。

不得使用历史 handoff、旧 progress、旧 parallel prompt 或默认 skip 的 live test 推导完成状态。

## 当前结论

| 项目 | 当前事实 |
|---|---|
| MAIN-100 | `awaiting_legacy_authorization`，本地、external provider 与 Legacy read-only plan coverage 已闭合；真实 cutover 未获授权前不能标记 complete |
| 本地/production-style 产品闭环 | 自助注册与个人工作区、登录、Recovery、邀请、成员、Seed/Assets/Graph、single-current-world、Character、Writer/Reviewer、显式 adoption、manuscript/export 已有当前 live/browser 证据 |
| 中央集成 | 产品 handlers/workers 已进入中央 auth/RBAC/CSRF/RLS/limiter/readiness 安全壳 |
| Compose | 全服务 health、15 migrations readiness、持久化 restart/recovery、worker queues 当前通过 |
| 当前未完成 | 唯一 Legacy 候选尚未获授权为真实业务数据；apply/verify/rollback/final cutover 尚未执行 |

本地 completion audit 已闭合：Coverage Matrix 当前为 `90 verified / 25 verified replacement / 5 explicit non-restored / 1 blocked`，无裸 `planned` / `implemented` / `in_progress` / `pending` 表格状态；Production/Ops 四行已按当前 billing、object storage、recovery、audit 证据校准，并由语义防漂移测试约束。external HTTPS provider 的真实成功证书已升级为 `verified`；机械状态归一化不得改写 `seed.stage.pending` 等真实代码标识的防回归测试也已通过。唯一 blocked row 为 real Legacy source，不能用 synthetic legacy fixture 替代。

### 证据冻结与重开规则

- 本文标记为 `verified_current` 且下游契约未变的领域视为关闭，不再因新会话、文档刷新或最终审计而重复实现、重复 browser journey 或重复 full regression。
- 已关闭领域仅在三种情况下重开：当前 runtime 真实失败；新改动触及其生产代码/schema/公共契约；`DEVELOPMENT_PLAN.md` 的明确 DoD 与现有证据发生可定位冲突。
- 修复只运行受影响的 focused tests，再运行由依赖关系决定的 broader regression；不得把单一 Legacy 输入 gate 扩大为全仓重新审计。
- 最终审计是对本表冻结证据和唯一未完成 gate 的逐项核对，不是重新发现范围或重新证明所有历史 green 项。

## 子目标状态

| 子目标 | 当前状态 | 当前证据 |
|---|---|---|
| P6-003-A Writer/Reviewer/Workspace/Manuscript | `verified_current` | `writer_dedup_extractor` 与 `writer_book_planner` 已经真实 Facility/Temporal producer、中央安全挂载、app-role SQL 和 browser 认证；只产出 disabled candidate/draft |
| P5-005-B Knowledge/Simulation | `verified_current` | Seed unified private trace app-role live、same-run retry replacement、Seed/Assets/Graph/Worldline/Character browser 与 full regression 当前通过 |
| P8-002-C Platform/Legacy/Ops | `verified_current` | model-sync app-role/live、retirement artifact、Legacy/Ops/Security、matrix closure 与 production override reviewer 当前通过 |

## 中央集成与安全

- Writer、Reviewer、Writer Planning、Writer Workspace、Manuscript Workspace、Export、Asset Catalog、Auth Recovery、Collaboration、LLM Admin 已由中央 router/main 构造和挂载。
- Phase 3 `packages/shared-contracts` 已以 Draft 2020-12 JSON Schema 冻结 Go -> Pi writer workflow input、Pi -> Go runtime event 与 Go -> Web public replay event；Go AST、Pi/Web TypeScript AST 和 Go/Python/Node serializer tests 会对实际消费者漂移 fail closed。
- Pi Writer 已真实实现 `query_world_rules` 与 `query_character_profile`：执行前 `Agent.beforeToolCall` 权限门控，app-role 查询显式约束 tenant/project，公开 event 去除 rule text/evidence/alias/private metadata，private trace 仅含 owner-project 上下文；同租户跨项目和跨租户 live 隔离、canon/adoption/manuscript 零写入均通过。
- `writer-planning` workflow/activity worker 已进入 base/staging/production compose、strict poller readiness 和 recovery force-recreate；book generation 与 dedup extraction 使用 exact POST route，中央 credential/CSRF 预检覆盖 malformed/method fail-closed。
- owner-aware resource routes 先解析真实 project owner，再做 project/tenant RBAC；不信任 body/header project identity。
- 自助注册使用单事务创建 user、bcrypt credential、首次 hash-only session、personal 工作区、owner membership、首项目与 project owner；真实浏览器注册后直接进入空项目，单工作区只显示“我的工作区”且隐藏切换器。
- development auth 默认关闭；只有显式 `local + MIROFISH_ENABLE_DEVELOPMENT_AUTH=1` 才启用。当前 Compose 无 Cookie 伪造 `X-User-Id` 返回 `401`，`/v1/auth/dev-sessions` 返回 `404`，API 端口只绑定 `127.0.0.1`。
- staging/production 会话 Cookie 不依赖容器内 API 请求是否带 TLS：反代终止 HTTPS 后仍强制 `Secure`，local HTTP 保持可用。
- Recovery 使用 strict canonical standard Base64 的 32-byte outbox key；staging/production 缺 key fail bootstrap。
- Collaboration invitation accept 使用 session + CSRF + signed trusted-client proof；无 project membership 的已认证 invitee 可进入 invitation acceptance，而不能进入项目资源。
- tenant last-owner 保护由真实成员页面验证；project membership 与 tenant ownership 不混淆。
- migration `0015_workspace_membership_scope` 以 `tenant | project_bridge` 区分工作区成员与项目邀请桥接；`0016_workspace_membership_scope_backfill` 会按项目邀请、成员创建/加入时间和“无工作区邀请”证据保守收敛历史项目受邀者，并保留私有回填审计。project bridge 的 app-role live test 只能读取受邀项目，不能读取同工作区兄弟项目，暂停的工作区成员接受项目邀请也不会恢复完整工作区 scope。
- Redis rate limit 已验证阈值、`Retry-After`、HMAC-only keys 和 backend outage `503`。
- provider health 从 tenant-owned DB channel/model 解析加密 credential，保持 SSRF/HTTPS/external opt-in 边界；公开面只返回 sanitized metadata。
- 正式 external channel 使用 `https://api.aiwanai.cc/v1`、`gpt-5.5`、`external_provider_opt_in=true` 和 canonical AES-GCM v1 encrypted credential；`/models` 同步 50 个模型，JSON mode、function tools 与 provider health 均真实 HTTP 200。当前项目 26 个非 embedding 模块已通过产品 API 绑定到该模型；provider 没有 embedding model，因此 `asset_search_embedding` 明确保留未绑定，未把聊天模型伪装成向量模型。
- 本地 external credential 解密密钥已写入 git-ignored、mode `0600` 的 `infra/.env`，不包含 provider API key；full compose rebuild/recreate 后 API 与 8 个 Python/Pi LLM worker 均加载该密钥，authenticated `/v1/llm-admin/provider-health` 再次返回 `healthy` / HTTP 200，证明配置跨重启持久化。
- LLM channel/catalog 与 module binding 的 app-role 路径已强制使用 tenant read/write transaction helpers；create/list/models/update/delete、list/upsert/resolve/delete、同租户跨项目、跨租户和 foreign target app-role live 均通过。HTTP create/patch 已真实承接 `external_provider_opt_in`，不再丢弃 Web 表单字段。
- migration `0014_llm_platform_defaults` 已补齐 platform channel/model 的 FORCE RLS 只读可见性和独立 platform-default binding；Go/Python/Pi resolver 统一执行 project > tenant > platform > explicit unbound，并跳过 disabled model。schema ledger、app-role live 与三端 focused tests 已通过。
- base/staging/production 的 Legacy source root 固定为 repo-owned `infra/legacy-import-source -> /legacy-import-source:ro`，不可由任意 host path 覆盖；空源继续 fail closed。
- Go/Python live fixture 已统一为 migration-ledger guard：升级库只验证 ledger/schema，绝不重放 raw revision；ledgerless 非空库 fail closed，只有空 public schema 的 disposable DB 可执行 baseline。

## Browser / Cross-Service 证据

| 旅程 | 当前结果 |
|---|---|
| Seed upload/retry/reclaim/refresh | passed |
| Story Graph 1010-node build/inspect/candidate/adoption | passed |
| Asset detail/version/restore/collection/viewer privacy | passed |
| Worldline -> Character -> Pi candidate | `1 passed, 0 failed`; desktop/mobile；零 pageerror/privacy finding |
| Writer -> Reviewer -> adoption -> planning -> manuscript/export | 功能与隐私旅程原证据 `1 passed, 0 failed`, `18.8s`；book plan 保持 draft v2，dedup 保持 disabled candidate，artifact download/privacy passed。旧蓝色长页截图已撤销，不代表 Agent-first 视觉验收 |
| Recovery -> invite accept -> tenant/project members -> LAST_OWNER -> quota -> provider health | `1 passed, 0 failed`, `7116 ms`; zero pageerror/privacy finding；browser 后 recovery direct grants 仍为 0 |
| Signup -> personal workspace -> first project | passed；首次 session 与开户原子提交；单工作区切换器隐藏；验证账号随后精确清理 |

当前平台截图：

- `/tmp/mirofish-platform-browser-0013/platform-desktop.png` (`337425 B`)
- `/tmp/mirofish-platform-browser-0013/platform-mobile.png` (`194598 B`)
- `/tmp/mirofish-worldline-character-certification/` 下四张 Worldline/Character desktop/mobile 截图

旧 Writer 蓝色长页截图目录已删除并撤销；新 Agent-first Writer 必须生成 fresh desktop/mobile browser evidence 后才能恢复视觉认证。

## Compose / Recovery 证据

- `/readyz` exact GET 返回 Postgres/schema、Redis、Temporal/required pollers、object storage 四依赖 `ready`。
- migration ledger 目标为 `19:0019_writer_threads`；readiness 常量同步要求 19。Compose bootstrap 校验至 0019（writer_threads / messages / approvals + writer_runs.mode 含 revise；0018 四表/FORCE RLS/adopt snapshot reason/evidence 无 DELETE grant sentinel 仍保留）。
- 本地 fixture 清理器默认 preview、仅 `--apply` 删除固定 UUID + 精确 marker 的 allowlist，拒绝非 local/远程数据库、拒绝 libpq query 路由覆盖并保护管理员个人工作区；管理员的正常多设备会话不在清理范围。当前库清理后为 `1 user / 1 workspace / 1 project / 1 session`，测试 source/workflow 为 0，正式 LLM channel/model/binding 保持 `1 / 50 / 26`。
- 后续 live/E2E fixture 不再复用主库：`run-live-test-stack.sh` 为每次任务创建独立 Compose project、`mirofish_test_*` 数据库、live-test marker 和 volumes，退出统一 `down -v`；Go/Python/Web guard 会在写 fixture 前拒绝主 `mirofish` 库。历史清理器只保留为一次性旧污染收敛工具。
- recovery 私表对 `mirofish_app` 的 direct grants 当前为 `0`。
- `run-compose-recovery.sh` 当前通过：persisted auth、CSRF、foreign tenant denial、session rotation、logout、password change revocation、停 worker 后 queued workflow recovery；重启前、重启后与最终登录后均强制校验 recovery direct grants 为 0。
- Temporal readiness 不再 20-way burst：同一 fresh probe 以全局 4-slot Describe、失败项一次定向重试和 in-flight request coalescing 执行，无 TTL/永久成功缓存；runtime 证据为 `/readyz` 串行 `20/20`、五并发 `50/50` 全部 HTTP 200，独立 bounded worker probe `5/5`，单轮约 8.4 秒且低于 20 秒 healthcheck timeout。
- stateful Postgres/Redis/Temporal/MinIO 使用 persistent-volume restart；无状态 API/Web/Python/Pi workers 使用 force-recreate，规避 Docker Desktop restart 后 exec namespace 缺陷。
- API/Planning/Reviewer/Character/Worldline/Pi 的 `LLM_CREDENTIAL_ENCRYPTION_KEY` 均为 non-empty 64 chars，SHA-256 唯一值计数为 1。
- Legacy worker 当前 `healthy`，`LEGACY_IMPORT_SOURCE_ROOT=/legacy-import-source`，mount `rw=false`，容器内目录存在且不可写。

## 最新全仓验证

| 范围 | 当前结果 |
|---|---:|
| Go API full | `go test -count=1 ./...` passed |
| Python Agent Runtime full | `443 passed, 31 skipped` |
| Pi Runtime | `71 passed, 4 skipped`; typecheck/build passed；shared-contracts/Pi tool focused `44 passed`，app-role live `2 passed` |
| Web | 当前串行 full 为 `241 passed, 9 skipped`；LLM Facility settings 契约与 cookie abort 时序回归均已闭合；typecheck/build passed |
| Legacy Backend full | `829 passed, 5 skipped` |
| Matrix + retirement + production ops | `55 passed` |
| External provider strict Facility | `2 passed`；JSON/tools probes、formal provider health、26 non-embedding bindings passed |
| Infra/schema/release full | `67 passed` |
| Legacy importer focused | `49 passed, 1 skipped`；relationship-owned evidence compatibility regression passed |
| Production ops latest | `44 passed` |
| Compose recovery | passed |
| Compose health + `/readyz` | passed / ready；20/20 sequential + 50/50 at concurrency 5 |
| `git diff --check` | full worktree passed |

2026-07-13 仓库收口复验后，Web 串行 full 执行 `250` 项：`241 passed, 9 skipped`。旧 LLM Facility 对象字面量断言已校准到当前 settings helper，cookie-backed mid-flight abort 用例改为服务端接收后确定性中止；退役/Writer/content-boundary 契约、typecheck 和无告警 production build 均通过。

## 最终 DoD 审计

| MAIN-100 / DEVELOPMENT_PLAN DoD | 判断 |
|---|---|
| 登录、租户、项目、production session/recovery | `verified_current` |
| 上传 -> Seed -> Assets/Graph | `verified_current`，local provider/live/browser |
| single Worldline -> Character -> Writer | `verified_current`，local provider/live/browser |
| Writer stream/tools/trace/draft -> explicit adoption -> review/manuscript/export | `verified_current` |
| LLM Facility binding/quota/usage/trace/provider health | `verified_current` for local/current configured providers |
| Phase 3 shared contracts / Writer tool contract | `verified_current`：shared schemas + Go/Pi/Web AST drift guard；world rules/character profile app-role live |
| route-wide auth/RBAC/CSRF/RLS/privacy | `verified_current` |
| retry/cancel/concurrency/rate limit/billing | `verified_current` |
| compose health/restart/recovery/backup+restore/observability/alerts | `verified_current` |
| external provider explicit opt-in success | `verified_current`：`/models` 200 + exact `gpt-5.5`；strict Facility `2 passed`；binding/encrypted credential/quota/usage/activity/private trace；JSON/tools/provider-health 200；formal opt-in channel + 26 non-embedding bindings；public privacy passed |
| real Legacy import report/apply/verify/rollback/cutover | **awaiting authorization**：唯一候选 inspect 与三项目 deterministic plan 均 `complete` / zero blockers；真实性未获授权，apply/verify/rollback/final cutover 未执行 |
| legacy coverage/cleanup/non-restored decisions | `verified_current` for current decisions：matrix 为 90/25/5/1，无裸未决状态；唯一 blocked row 为 real Legacy source |
| 无 mock success、静默 fallback、旧 LLM env fallback、自动 candidate adoption、多分支 worldline | `verified_current` |

## 精确授权 Gate

### Real Legacy Source Data

当前唯一候选来自旧工作区数据库与 artifacts；只读 inspect/report 已生成，但项目名、业务计数和 artifact 形态呈明显 test/demo/synthetic 特征，未经用户确认不能认证为真实业务源或执行写入：

- `/tmp/mirofish-legacy-candidate-public/inspect.json`: `status=complete`
- `/tmp/mirofish-legacy-candidate-public/plan-{1,2,3}-fixed.json`: 均为 `status=complete`、`blockers=[]`、evidence deferred `0`
- `/tmp/mirofish-legacy-candidate-public/plan-1-fixed-replay.json`: plan hash 与首次 plan 一致，证明 deterministic replay
- source fingerprint: `afbed40d55c6b63dc7ea5773171d6bee42df481d3df6b95c9cd0a555b24e24c0`
- 已修复的兼容缺口：Legacy `entity_evidence.owner_type=relationship` 现在映射为 SaaS `relationship_events`，不再误报 `ENTITY_DEPENDENCY_MISSING`
- 每个 plan 有 17 个 uploadable objects 和 1 个 metadata-only source；后者仅为契约批准的 `APPROVED_LEGACY_SOURCE_PATH_UNSUPPORTED`，不使 plan partial
- inspect counts 包含 `project_meta=3`、`archive_sources=3`、`assets=12`、`graph_nodes=72`、`graph_edges=180`、JSON artifacts `1020`；公开报告 privacy scan clean。

Synthetic inspect/plan/apply/verify/rollback 与 MinIO version ownership 已通过，但不能替代获授权 real source 的 cutover/rollback 证据。

解除授权 Gate 需要用户明确确认该候选的三个项目均为真实业务数据并允许写入 disposable target，或提供另一组可授权的 Legacy SQLite 与 artifact root。随后只执行 Legacy apply/verify/rollback/final cutover 及其直接影响回归，不重开已冻结产品领域。

## 下一 Gate

1. 获得当前候选或替代 real Legacy source 的明确写入授权，完成真实 apply/verify/rollback/final cutover。
2. 只重跑 Legacy 直接影响的 schema/readiness/object-storage/rollback 证据；按冻结矩阵核对最终 DoD 后标记 MAIN-100 complete。

## 并行：Frontend UX Optimization

范围与波次以 `docs/refactor-saas/26-frontend-ux-optimization.md` 为准；不改写已冻结 MAIN-100 / P5 / P6 / P8 领域证据。

**收口结论（2026-07-13）：前端 UX 优化源码结构已闭合；旧蓝色 Writer 证据已撤销，fresh Agent-first browser 视觉验收待补。**

| 波次 | 状态 | 证据 |
|---|---|---|
| 1 内容边界回归 | `verified_current` | 全作者 shell + product workspace 源码契约 |
| 2 公共组件 / 纸墨 token / Shell | `verified_current` | token + SubmitButton/Confirm/Drawer/ModeSwitcher 接线 |
| 3 Assets / Overview | `verified_current` | CompactFilterBar + Inspector + WorkflowProgress + SubmitButton |
| 4 Graph / Worldline / Character | `verified_current` | 互斥模式（Graph 四态；Worldline 三态；Character 三态） |
| 5 Writer 主视图 | `verified_current` | Agent thread 主交互 + 常驻 composer + artifact tabs；诊断 dialog；product 去 id/error_code 主渲 |
| 6 LLM 作者/管理分层 | `verified_current` | `canManageAdmin` owner/admin 门控 |
| 7 验收 | `in_progress` | Agent-first/retirement、matrix、Web full `241 passed, 9 skipped`、typecheck/build passed；fresh desktop/mobile browser evidence 因当前无可用浏览器实例且 Writer 需真实登录而 pending |

## 并行：Writer Agent 化重构（Agentification）

用户已确认将写作台重构为「可商用、美观、真实 Agent、用户好用」的编辑工作室，起步选择「阶段 1：四区布局」、编辑器 TipTap/ProseMirror、后端可改。遵循 `build-novel-agent-ui` 技能的编辑室原则（手稿主导画布 + 可观察的 Agent 协作者）。

**Phase 2–6 完整实现蓝图见 `30-writer-agentification-and-editor-plan.md`**（编辑器方向已定为 TipTap + PE 回退 + 动态加载；含前后端工作流、组件与视觉规范、验收策略）。用户指示：先落方案文档、后续全按推荐的美观方案开发、后端可较大改动、唯一要求是效果要好。

**设计原则调和（2026-07-13）**：原「Agent-first（thread 占主区）」重新定义为 **manuscript-primary（手稿主导）+ 常驻 Agent dock**。手稿工作区是主导画布；Writer Agent 作为常驻协作者（连续 thread + 常驻 composer + 选区驱动调用）位于右侧 dock，不占半屏。`CLAUDE.md` / `AGENTS.md` 已同步。退役基线不变：`writer-studio-grid`、`writer-agent-rail`、折叠 composer、旧蓝色长页不得恢复。

| 阶段 | 状态 | 证据 |
|---|---|---|
| 0 传输底座 | `verified_current` | 增量事件轮询（`lib/writer-event-store.ts` + `/api/writer-events/[tenantId]/[projectId]` route + `components/writer-live-draft.tsx`）替换假串流全页刷新；normalized store 去重/排序/terminal（completed/failed/cancelled）；连接横幅（reconnecting/interrupted + retry）；创建 run 带 `Idempotency-Key`；窄化 aria-live。store 11/11、recovery 6/6、ux-completion 19/19、typecheck/build passed |
| 1.1 版面反转 | `verified_current` | shell 主画布 `writer-artifact-canvas`（`<main>` 主导）+ Agent `writer-agent-dock`（`<aside>` 常驻副）；`data-layout="manuscript-primary"`；CSS grid 反转（canvas 1.62fr / dock 0.82fr）+ 两处响应式断点更新；契约演进（data-layout、顺序断言反转、新结构类锁定）「Writer is manuscript-primary with a persistent Agent dock」passed；当前 Web full/typecheck/build passed |
| 1.2 左侧结构导航（真三区） | `verified_current` | 新增 `components/writer-structure-nav.tsx`（纯导航 GET 表单，渐进增强；选章重置场景、块选择独立保留）+ loading skeleton；shell 加 `structureNav` slot / `writer-structure-rail` 单元格 / `data-has-structure` 属性，形成 左结构 / 中手稿 / 右 Agent dock 三列；page 以独立 Suspense 注入 `WriterStructureNavData`（listChapters/listScenes/listManuscriptBlocks）；CSS 三列 grid + 属性选择器覆盖两处响应式（≤960 隐藏左栏，structure tab 仍可编辑）；契约锁定 writer-structure-rail/structureNav/data-has-structure + 导航组件 method="get"；当前 Web full/typecheck/build passed |
| 1.3 ⌘K 命令面板 | `verified_current` | 新增 `writer-workbench-context.tsx`（共享 activeTab + 面板开合 + ⌘K/Ctrl+K window keydown）与 `writer-command-palette.tsx`（role=dialog 面板 + 可见触发按钮 + 5 条命令：切四个 tab / 聚焦 Agent 对话框；方向键/回车/Esc/背景关闭）；`writer-artifact-tabs.tsx` 改为「有 provider 用 context、无则本地 state」；shell 用 provider 包裹并在 header 放触发按钮；契约锁定 WriterCommandPalette/WriterWorkbenchProvider/role=dialog/metaKey/useWriterWorkbench；writer 路由 6.04→7.79 kB；当前 Web full/typecheck/build passed |
| 1.4 顶栏 breadcrumb / save-state | `verified_current` | header eyebrow → 面包屑（项目总览链接 › 写作 Agent，沿用页面内部路由风格，非公钥深链）；meta → `WriterRunStateChip`（idle/active/error 状态点，active 脉冲，`prefers-reduced-motion` 降级）；actions 加 `已同步/Synced` 指示（诚实反映 server-action 即时持久化，Phase 2 接入实时 save-state）；契约锁定 writer-breadcrumb/WriterRunStateChip/writer-sync-chip；Web 串行 full `250` 项 `241 passed, 9 skipped`、typecheck、build passed |

**Phase 1（四区布局）收口：** 1.1–1.4 全部 `verified_current`。写作台已是 manuscript-primary 三区编辑室：左结构导航 / 中手稿画布（四 artifact tabs）/ 右常驻 Agent dock，顶栏含面包屑 + run-state + sync，⌘K 命令面板驱动 tabs。
| 2 TipTap 编辑器 | `implemented` | `writer-manuscript-editor.tsx` TipTap + 隐藏/PE `textarea name="content"` + `next/dynamic ssr:false`；`WriterManuscriptPanelClient` 集成；书卷纸面 CSS |
| 3 选区驱动调用 + 行内 diff | `implemented` | 选区工具条、`lib/writer-diff.ts` 纯函数、行内 diff UI；shared `mode=revise` + options.revise；Pi revise 输出 `writer.revision.proposed`；Web reviseSelection action |
| 4 持久 thread + activity timeline + context chips | `implemented` | migration `0019_writer_threads`（threads/messages/approvals + RLS）；Go store；`writer-activity-timeline` / `writer-context-chip` / thread helpers；shell 可渲持久消息 |
| 5 真实 SSE 推送 + approvals + continuity | `implemented` | Go held-open SSE（stream=1 / active run + Last-Event-ID）；Web EventSource 优先、poll 回退；`writer-approval-card` + approval 事件类型 |
| 6 视觉打磨 + a11y + 验收截图 | `implemented`（截图 pending） | paper/selection/diff/timeline/approval CSS、reduced-motion、契约测试；fresh desktop/mobile browser 截图仍待真实登录 + 浏览器实例 |

**Phase 2–6 实现收口（2026-07-13）：** 源码与契约已落地，见 `30-writer-agentification-and-editor-plan.md`。验证以 focused Web/Go/Pi/shared-contracts 为准；fresh browser 视觉证据仍 pending。

## 并行：Z-028 Zero-start Writer / Manuscript Asset Distillation

范围与切片以 `docs/refactor-saas/28-zero-start-writer-and-manuscript-asset-distillation.md` 为准；**不属于 MAIN-100 / Phase 0-8 完成定义**，不得把 planned distillation API 计为 MAIN complete。

| 切片 | 状态 | 当前证据 |
|---|---|---|
| Z0 空项目创作契约 | `verified_current` (app-role) | unit/web 双入口 + bootstrap；disposable Postgres live `TestLiveEmptyProjectWriterPathWithoutSeedArtifacts` passed |
| Z1 0018 schema/RLS | `verified_current` (app-role) | schema ledger 含 `0018`；live settings/admission/proposals/accept/reject + cross-tenant isolation + evidence private gate passed |
| Z2 手动蒸馏 | `verified_current` (unit + admission live) | module registry + Go admission fingerprint replay live；Python workflow/validator unit passed；真实 provider Temporal E2E 仍可选增强 |
| Z3 Proposal Review | `verified_current` (API live + UI wired) | accept_create/reject live；Writer proposal rail + settings UI 已接线 |
| Z4 Update/Merge | `implemented` | accept_update/version conflict 代码与 unit path 具备；live update merge 用例可后续补强 |
| Z5 Outbox | `implemented` | adopt snapshot + claim function + adoption enqueuer + dispatcher；live claim 执行无报错 |
| Z6 检索/设置 | `verified_current` (unit) | Pi lifecycle 白名单；settings API/UI |
| Z7 完整认证 | `in_progress` | app-role disposable live 已绿；全栈 Temporal provider + browser journey 未跑（compose temporal-db-init 在完整 stack 上曾失败，DB-only path 已证明） |

实现入口：

- `apps/api/internal/assetdistillation/`
- `apps/agent-runtime/mirofish_agents/temporal/manuscript_asset_distillation.py`
- `infra/postgres/migrations/0018_manuscript_asset_distillation.sql`
- Writer proposal rail + Overview dual entry

最新 disposable live（Postgres-only schema-init 至 0018）：

```text
go test ./internal/assetdistillation/ ./internal/workflows/ \
  -run 'TestLiveAssetDistillation|TestLiveEmptyProject' -count=1
# ok assetdistillation ; ok workflows
```
