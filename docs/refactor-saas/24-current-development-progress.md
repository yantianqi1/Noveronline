# SaaS Current Development Progress

更新时间：`2026-07-19`

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
| P6-003-A Writer/Reviewer/Workspace/Manuscript | `verified_current` | `writer_dedup_extractor` 与 `writer_book_planner` 已经真实 Facility/Temporal producer、中央安全挂载、app-role SQL 和 browser 认证；只产出 disabled candidate/draft；Pi 另承载候选式故事分析（`PiAnalysisRunWorkflow`）与 Worldline Cast Planner 两个独立域，不写 canon |
| P5-005-B Knowledge/Simulation | `verified_current` | Seed unified private trace app-role live、same-run retry replacement、Seed/Assets/Graph/Worldline/Character browser 与 full regression 当前通过 |
| P8-002-C Platform/Legacy/Ops | `verified_current` | model-sync app-role/live、retirement artifact、Legacy/Ops/Security、matrix closure 与 production override reviewer 当前通过 |

## 中央集成与安全

- Writer、Reviewer、Writer Planning、Writer Workspace、Manuscript Workspace、Export、Asset Catalog、Auth Recovery、Collaboration、LLM Admin 已由中央 router/main 构造和挂载。
- Phase 3 `packages/shared-contracts` 已以 Draft 2020-12 JSON Schema 冻结 Go -> Pi writer workflow input、Pi -> Go runtime event 与 Go -> Web public replay event；Go AST、Pi/Web TypeScript AST 和 Go/Python/Node serializer tests 会对实际消费者漂移 fail closed。
- Pi Writer 已真实实现 `query_world_rules` 与 `query_character_profile`：执行前 `Agent.beforeToolCall` 权限门控，app-role 查询显式约束 tenant/project，公开 event 去除 rule text/evidence/alias/private metadata，private trace 仅含 owner-project 上下文；同租户跨项目和跨租户 live 隔离、canon/adoption/manuscript 零写入均通过。
- `writer-planning` workflow/activity worker 已进入 base/staging/production compose、strict poller readiness 和 recovery force-recreate；book generation 与 dedup extraction 使用 exact POST route，中央 credential/CSRF 预检覆盖 malformed/method fail-closed。
- Pi 候选式故事分析（文档 21）已实现并部署：`pi-agent-runtime-analysis` worker 监听 `analysis-streaming` 队列，消费 Go 投递的 `PiAnalysisRunWorkflow`（workflow type `analysis_run`），经 agent loop（`analysis_planner` / `analysis_worker` module）读源分段、写 workspace 候选，落 `analysis_candidates` 表（migration `0020`）后由 Go `SQLAnalysisAssetImporter` 投影为 `source_kind = pi_analysis` 资产；它是与 Python Seed 并行的候选路径，不替代 Seed canon 主流水线。
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
| Story Graph 力导向交互画布（2026-07-19） | passed；`lib/story-graph-force.ts`（d3-force 实时物理：链接/斥力/碰撞/锚定，tick 直驱 SVG 不经 React 渲染）+ explore 画布重写（节点拖拽全图联动、滚轮以光标为中心缩放、空白平移、minimap 跳转、悬停/选中邻居高亮与非邻居淡出、聚类概览↔节点视图）。106 节点 / 42 边真实项目浏览器实测：拖拽期间 106/106 节点被物理牵动、viewBox 1424→836（173%）、minimap 重定位、搜索过滤 2/106 后复原、仿真期间 rAF ≈60fps；聚类标识 `type:*` / `network:asset:<uuid>` 已换为友好显示名；desktop 画布恢复墨色底（此前 transparent 使节点浮在纸色页面上）；工具栏 select 加 `max-width` 防长 option 撑爆 |
| Asset detail/version/restore/collection/viewer privacy | passed |
| Worldline -> Character -> Pi candidate | `1 passed, 0 failed`; desktop/mobile；零 pageerror/privacy finding |
| Writer -> Reviewer -> adoption -> planning -> manuscript/export | 功能与隐私旅程原证据 `1 passed, 0 failed`, `18.8s`；book plan 保持 draft v2，dedup 保持 disabled candidate，artifact download/privacy passed。旧蓝色长页截图已撤销，不代表 Agent-first 视觉验收 |
| Recovery -> invite accept -> tenant/project members -> LAST_OWNER -> quota -> provider health | `1 passed, 0 failed`, `7116 ms`; zero pageerror/privacy finding；browser 后 recovery direct grants 仍为 0 |
| Signup -> personal workspace -> first project | passed；首次 session 与开户原子提交；单工作区切换器隐藏；验证账号随后精确清理 |

当前平台截图：

- `/tmp/mirofish-platform-browser-0013/platform-desktop.png` (`337425 B`)
- `/tmp/mirofish-platform-browser-0013/platform-mobile.png` (`194598 B`)
- `/tmp/mirofish-worldline-character-certification/` 下四张 Worldline/Character desktop/mobile 截图
- `/tmp/mirofish-story-graph-certification/story-graph-desktop-verify.png` 与 `story-graph-zoomed-verify.png`（力导向画布全景与 173% 聚焦高亮态）

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

## 并行：Seed 分批富化（doc 42，2026-07-25 落地）

`docs/refactor-saas/42-seed-batched-enrichment.md` 全三切片已实现并重开 P5-005-B 域验证（规则：受影响 runtime 代码 + 公共契约变更）。

| 切片 | 状态 | 证据 |
|---|---|---|
| 1 agent_profiles 分批 | `verified_current` | 解除 LIMIT 200；按 canonical_name 确定性分批（默认 5，clamp 1..20，module setting `batch_size`）；retry→bisect→missing 恢复；逐批 Route-A 累积快照（单条 CTE `ON CONFLICT` jsonb 按 canonical_name 合并，app-role/RLS 下原子执行）；期望 vs 实际对账 + 一次补漏；真实 `profile_count`；`missing_entities` 可见不静默 |
| 2 archive_candidates 分批 | `verified_current` | 同骨架分批；接入 `source_context`（原为空）；逐批写 assets，`source_ref = {batch}:archive:{global_index}` 全局 offset 唯一；readiness 瓷砖经现有 2.5s 轮询逐块 slam-in（前端瓷砖零改动） |
| 3 进度事件 + Web 子进度 | `verified_current` | runner `progress_callback` → `_attach_enrichment_progress` 桥接；公开事件 `seed.agent_profiles.progress` / `seed.archive_candidates.progress`（白名单 metadata-only，无正文/prompt/credential）；run 进度 80→86 / 86→92 插值；Web `reduceSeedProgress` 两个 case + `EnrichmentBlock` 子进度条（中文文案由后端发出） |

**R4 quota 幂等键**：分批后每批唯一 call id 由 `stable_provider_call_id(context, module, stage, call_index)` 保证——`stage` 嵌入批输入 digest，批间消息不同 → digest 不同 → call id 唯一；以 `test_seed_quota_chat_client_gives_distinct_call_identity_per_enrichment_batch` 锁定。

**回归证据（2026-07-25）**：Go API `go test ./...` 27 包全 ok；Python agent-runtime `484 passed, 30 skipped`（含 seed workflow 183 + ontology 11 + quota）；Pi `125 passed` + typecheck/build；Web `50 passed` + typecheck + production build。**live**：seed live e2e 对一次性 `mirofish_test_*` 库（全量 migration 链 + ledger）`8 passed`（quota-gated 分批落库、进度事件、隐私扫描、idempotent 重跑）。live fixtures 修正已提交：foundation 回填 tenant-scope quota policy（镜像 0017）、各 `llm_models` 补 `context_window`、entity_resolution 重试复用 trace_id 使命中 quota replay（单次真实 LLM 调用）、run progress 断言对齐阶段锚点 80。

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

**设计原则调和（2026-07-13 → 2026-07-19）**：原「Agent-first（thread 占主区）」重新定义为 **manuscript-primary（手稿主导原则）+ conversation-first IA + 常驻 Agent dock**。手稿工作区是主导画布（连续稿件文档，章节内片段按序渲染、选中就地编辑）；画布头可见视图分段（稿件/章节/审校/工具）；Writer Agent 作为常驻协作者（连续 thread + 常驻 composer + 选区驱动调用）位于右侧 dock，不占半屏。`data-layout="conversation-first"` 为现行契约；`CLAUDE.md` / `AGENTS.md` 已校准。退役基线不变：`writer-studio-grid`、`writer-agent-rail`、折叠 composer、旧蓝色长页不得恢复。

| 阶段 | 状态 | 证据 |
|---|---|---|
| 0 传输底座 | `verified_current` | 增量事件轮询（`lib/writer-event-store.ts` + `/api/writer-events/[tenantId]/[projectId]` route + `components/writer-live-draft.tsx`）替换假串流全页刷新；normalized store 去重/排序/terminal（completed/failed/cancelled）；连接横幅（reconnecting/interrupted + retry）；创建 run 带 `Idempotency-Key`；窄化 aria-live。store 11/11、recovery 6/6、ux-completion 19/19、typecheck/build passed |
| 1.1 版面反转 | `verified_current` | shell 主画布 `writer-artifact-canvas`（`<main>` 主导）+ Agent `writer-agent-dock`（`<aside>` 常驻副）；现行 `data-layout="conversation-first"`（产物主导原则保留）；CSS grid（canvas 1.62fr / dock 0.82fr）；契约「Writer is conversation-first with a persistent Agent dock and canvas」 |
| 1.2 左侧结构导航 | `superseded` | 左结构轨已由章节切换器 + 可见「章节」视图替代；`writer-structure-nav.tsx` 组件保留可复用，page/shell 不再注入 `structureNav`；`data-has-structure="false"` |
| 1.5 连续稿件画布 | `verified_current` (2026-07-19) | `writer-manuscript-flow.tsx`：章节内片段连续渲染为文档；选中片段内联 TipTap；分隔条管理菜单（重排/标签/移动/归档/版本）；空章「开始写这一章」；文末次级「添加空白片段」；page 并行 `getPrivateBlock`（上限 20）+ 默认第一章；画布头 `WriterArtifactTabChrome` 可见 tabs；文案「正文块」→「片段」；structureNav 死取数已删 |
| 1.3 ⌘K 命令面板 | `verified_current` | 新增 `writer-workbench-context.tsx`（共享 activeTab + 面板开合 + ⌘K/Ctrl+K window keydown）与 `writer-command-palette.tsx`（role=dialog 面板 + 可见触发按钮 + 5 条命令：切四个 tab / 聚焦 Agent 对话框；方向键/回车/Esc/背景关闭）；`writer-artifact-tabs.tsx` 改为「有 provider 用 context、无则本地 state」；shell 用 provider 包裹并在 header 放触发按钮；契约锁定 WriterCommandPalette/WriterWorkbenchProvider/role=dialog/metaKey/useWriterWorkbench；writer 路由 6.04→7.79 kB；当前 Web full/typecheck/build passed |
| 1.4 顶栏 breadcrumb / save-state | `verified_current` | header eyebrow → 面包屑（项目总览链接 › 写作 Agent，沿用页面内部路由风格，非公钥深链）；meta → `WriterRunStateChip`（idle/active/error 状态点，active 脉冲，`prefers-reduced-motion` 降级）；actions 加 `已同步/Synced` 指示（诚实反映 server-action 即时持久化，Phase 2 接入实时 save-state）；契约锁定 writer-breadcrumb/WriterRunStateChip/writer-sync-chip；Web 串行 full `250` 项 `241 passed, 9 skipped`、typecheck、build passed |

**Phase 1（四区布局）收口后演进：** 写作台现行为 conversation-first 双栏：中手稿连续文档画布（可见 tabs：稿件/章节/审校/工具）+ 右常驻 Agent dock；章节切换器负责日常换章；⌘K 仍可驱动 tabs。2026-07-19 已落地连续稿件流与可见 tab chrome。
| 2 TipTap 编辑器 | `connected` | TipTap + PE textarea；空白 manuscript block 创建；scene 结构元数据不再承载正文（CONN-001） |
| 3 选区驱动调用 + 行内 diff | `connected` | `writer.revision.proposed` → `pendingRevision` 行内 diff；accept 走块级 optimistic patch，禁止普通整块 adoption（CONN-007）；并发 OPTIMISTIC_CONFLICT 保留 localDraft compare/merge/另存（CONN-006） |
| 4 持久 thread + activity timeline + context chips | `connected` | SQLWriterThreadStore 中央挂载；user 指令与 Pi agent 完成消息均写入 `writer_thread_messages`；approval create/decide 路径具备；Writer page 传 `threadMessages` + `decideApprovalAction`（CONN-009） |
| 5 真实 SSE 推送 + approvals + continuity | `connected` | held-open SSE + EventSource；approval 决策接线；Idempotency-Key 进入 requestID；Temporal start 失败补偿（CONN-015） |
| 6 视觉打磨 + a11y + 验收截图 | `connected`（截图 pending Z7） | paper/selection/diff/timeline/approval CSS；fresh desktop/mobile browser 截图仍待 Z7 |

**Phase 2–6 + doc 32 remediation 代码连通（2026-07-13）：** 见 `33-connectivity-remediation-plan.md`。`connected` 表示代码路径与 focused tests 已接线；`verified` 仍要求 disposable live / browser 证据。Z7 全链浏览器认证不在本轮。

## 并行：Z-028 Zero-start Writer / Manuscript Asset Distillation

范围与切片以 `docs/refactor-saas/28-zero-start-writer-and-manuscript-asset-distillation.md` 为准；连通性修复见 `33-connectivity-remediation-plan.md`。**不属于 MAIN-100 / Phase 0-8 完成定义**。

| 切片 | 状态 | 当前证据 |
|---|---|---|
| Z0 空项目创作契约 | `verified_current` (app-role) | unit/web 双入口 + bootstrap；disposable Postgres live `TestLiveEmptyProjectWriterPathWithoutSeedArtifacts` passed |
| Z1 0018 schema/RLS | `verified_current` (app-role) | schema ledger 含 `0018`；live settings/admission/proposals/accept/reject + cross-tenant isolation + evidence private gate passed |
| Z2 手动蒸馏 | `connected` + app-role live | 任意 active manuscript 可作蒸馏源；长章 window/checkpoint/identity merge；`enabled_asset_types` 过滤 prompt（CONN-001/011） |
| Z3 Proposal Review | `connected` + app-role live | accept 投影 character/relationship/world_rule/plot_thread 到 Graph 源表（entities/relationships/plot_threads/world_rule_evidence）；accept 后启动 `story_graph_build`（CONN-003） |
| Z4 Update/Merge | `connected` + app-role live | 真实 `expected_target_version`；conflict 先提交；Update/Restore/Delete 调用 StaleProposals（CONN-005） |
| Z5 Outbox | `connected` + app-role live | adoption 与 distillation outbox 同事务；claim/tick 可观测（CONN-004） |
| Z6 检索/设置 | `connected` + Pi local-provider live | Pi active manuscript 邻域、worldline path、canon 资产规则/角色；draft chapter/scene COALESCE；local-provider Pi live E2E 2/2（CONN-008/010） |
| Z7 完整认证 | `in_progress` | 2026-07-13：disposable `mirofish_test_*` app-role live 已绿（distillation/manuscript/empty-writer/worldline/character + Pi local-provider）。**未闭合**：Docker CLI socket 权限导致无法 `run-live-test-stack.sh --app` 全栈重建；Playwright Chromium 下载与 headless Chrome 被环境拦截；浏览器仅 MCP 公共页（landing/login）证据，无 authenticated zero-start full journey 截图 |

实现入口：

- `apps/api/internal/assetdistillation/`
- `apps/agent-runtime/mirofish_agents/temporal/manuscript_asset_distillation.py`
- `infra/postgres/migrations/0018_manuscript_asset_distillation.sql`
- Writer proposal rail + Overview dual entry

最新 disposable live（2026-07-13，现有 Compose Postgres 上新建 `mirofish_test_z7_conn_*` + `mirofish.live_test=on` + migrations 0001–0019；**未**写主库 `mirofish`）：

```text
go test ./internal/assetdistillation/ -run TestLive -count=1   # ok
go test ./internal/manuscriptworkspace/ -run TestLive -count=1 # ok
go test ./internal/workflows/ -run TestLiveEmptyProjectWriter -count=1 # ok
go test ./internal/worldline/ -run Live -count=1               # ok
go test ./internal/characterconsole/ -run TestLive -count=1   # ok
# Pi local-provider (not external HTTPS):
npx vitest run src/runtime/pi-writer-live-e2e.test.ts         # 2 passed
# storygraph live still requires graph_nodes alias tables (name drift); projection
# evidence covered via distillation accept -> entities/relationships.
```
