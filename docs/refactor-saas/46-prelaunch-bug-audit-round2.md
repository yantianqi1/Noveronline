# 上线前缺陷审查报告（第二轮）

审核日期：`2026-07-31`
审核分支：`rewrite/web-clean-slate` @ `c97783d`（工作区干净，仅 `tools/ui-preview/shots/` 未跟踪）
审核范围：`apps/api`（Go 控制面）、`apps/web`（Next.js）、`apps/agent-runtime`（Python Temporal workers）、`apps/pi-agent-runtime`（Pi Writer Agent Runtime）、`packages/shared-contracts`、`infra`（迁移 / Compose / bootstrap / CI / ops）
审核方式：只读。6 路并行专项审查（Go 安全与鉴权、Go 领域与数据完整性、Web、Python runtime、Pi runtime+契约、infra/迁移），其后由主审对全部 BLOCKER 与关键 MAJOR 逐条复核（读处理器主体、读迁移原文、读 RLS 策略、比对同族实现）。**本次审核未修改任何文件、未写入任何数据库。**

测试基线（本轮复核时实际运行）：Web `npm run typecheck` 干净、`npm test` 121 passed / 1 skipped；Pi `vitest` 138 passed / 4 skipped + `tsc --noEmit` 干净；shared-contracts drift 4 passed；Go `go build ./...` + 聚焦单测通过；Python 聚焦单测通过（llm_quota 10、seed batch/recovery 41）。上一轮 `AUDIT-2026-07-31` 六项与 `AUDIT-044` 各项按仓库规则视为已闭合基线，仅核查同族回归，不重复上报。

---

## 0. 一句话结论

**测试全绿之下仍存在 3 个 BLOCKER 级鉴权缺口：三个只读接口（seed 运行列表、asset-ingestion 详情、style-extraction 详情）完全不认证、不校验成员关系，RLS 租户上下文取自攻击者可伪造的 `X-Tenant-Id` 头，且 `workflow_runs` 的 RLS 策略只按租户过滤、无用户/成员谓词。** 这是此前 P0-2 修复过的"启动/采纳缺 authorizeProject"模式的同族残留——list/详情变体漏网。

其余确认项集中在：世界线 events/timeline 读接口未声明硬 `LIMIT 100` 静默截断（与已修 AUDIT-WL-001 同族）、Web BFF 路径段未编码拼接（`%3F`/`%23` 注入）、角色控制台"拒绝"纯本地假装、Writer 自动保存无 save-on-unload、Pi token 流重试拼接两代文本、Python 配额按 UTF-8 字节预留约 2 倍超估、迁移 0029 非事务且 sentinel 不验 backfill、staging/production compose 凭据回退 dev 默认等。

修复性价比：BLOCKER 三项均为在处理器开头补一行 `authorizeProject*` 调用，改动极小。

### 0.1 本轮修复处置（2026-07-31）

后续修复已在当前 worktree 落地，以下项目已完成代码修复并通过对应回归：

- **B1–B3 + archive-memory 读侧**：seed-runs、asset-ingestion、style-extraction 详情和 archive memory/events 先做 owner-project 授权；archive reader 统一走 tenant context。
- **M-A1–M-A8**：BFF 路径段编码与注入拒绝、世界线 timeline/events 显式分页、角色 proposal reject 持久化、世界线读取错误态、Writer pagehide/keepalive 保存、Pi token stable provider-call key、Python token 估算、0029 事务与 backfill sentinel 均已修复。
- **M-G1–M-G4、M-G5 核心问题**：Worldline sequence advisory lock、蒸馏 RowsAffected、HTTP body cap、current-world admission guard、collections N+1 已修；collections 的显式分页仍待补。
- **M-P1–M-P4**：Pi 事件写链隔离、召回字段预览上限、analysis/cast quota + lease + stable provider identity + bounded retry、thread 按 run 收敛与序号锁已修。
- **M-S1–M-S2**：analysis 变更路由纳入 CSRF；HTTP 边界对数据库/driver 错误统一脱敏；未知邮箱登录执行 dummy bcrypt 比较。
- **M-Y2、M-Y3**：asset reindex 按 token/item 分块并递增 call index；Python HTTP response 有可配置上限；Worldline transient step errors 经过 bounded Temporal retry，最终由失败 activity 收敛状态；graph snapshot version 加锁并按 run/source hash 重放收敛。
- **M-I1–M-I5**：staging/production Compose 凭据改为 required secret；readyz 队列补齐；schema migration ledger 显式授权 app role；infra contract tests 纳入 CI。
- **相关 Minor**：Pi worker heartbeat 拒绝隔离、Web worldline step polling 支持卸载取消、Settings timer 卸载清理、logout 失败不再强行跳转 login、Pi writer timeline 显式报告每 session 的截断状态。

当前验证：Go `go test ./...` 通过；Python `510 passed, 31 skipped`；Pi `138 passed, 4 skipped` + typecheck/build；Web `123 passed, 1 skipped` + typecheck/build；infra `72 passed`；`git diff --check` 通过。

仍未闭合的边界：M-S3 注册邮箱验证需要产品确认邮件验证流程与 schema；M-Y1 中 assets/writer-review/worldline-prepare 等同族 workflow 的 retry/idempotency 还需逐个收敛；Worldline sessions/saved-paths/goal-starts/prepared-agents 与 Go collections 的显式分页仍待补；移动 drawer focus trap 等 Minor 尚未处理。Recovery request/reset UI、邀请接受 UI 与默认关闭 signup 契约已在当前 worktree 补齐。因而本报告不能标记为全部 `fixed_verified`，但原报告列出的 3 个 BLOCKER 已关闭。

---

## 1. 🔴 BLOCKER（主审逐条复核，结论可直接据以动手）

### B1　`GET /v1/projects/{projectId}/seed-runs` 无认证、无成员鉴权（跨租户读）

| 项 | 内容 |
|---|---|
| 位置 | `apps/api/internal/httpapi/server.go:4152`（`handleListSeedRuns`，路由 :2354） |
| 证据链 | 处理器只读 `X-Tenant-Id` 头 + 路径 projectId，直接调用 `seedRunReader.ListSeedRuns`；**不解析 actor、不调用 `authorizeProjectRead`、不要求会话**。读路径 `SQLSeedRunReader.ListSeedRuns`（`apps/api/internal/workflows/seed_reader.go:62`）→ `WriterEventSQLTenantQueryer.QueryTenantContext`（`writer_events.go:34`）执行 `app_set_tenant_context($tenantID, NULL::uuid, false)`，RLS 租户上下文来自客户端头。`workflow_runs` 策略 `tenant_isolation_workflow_runs`（`infra/postgres/migrations/0001_core_saas.sql:1926-1930`）`USING (tenant_id = current_setting('app.current_tenant_id'))`，**无用户/成员谓词**（`app.current_user_id` 传 NULL）。同族 `handleListAnalysisRuns`（`analysis_handlers.go:178`）与 `handleGetSeedRun`（:4229）均鉴权，此处漏。 |
| 影响 | 未认证调用者只要知道 victim 的 tenant+project UUID（URL/分享链接/日志常见泄露），即可读取对方 seed 任务列表（run id、状态、进度、错误信息）。浏览器经 BFF `GET /api/projects/{id}/seed-runs`（白名单内）同样可达。 |
| 修复 | 处理器开头补 `if !s.authorizeProjectRead(response, request, tenantID, projectID) { return }`（照抄 `handleListAnalysisRuns`）。 |

### B2　`GET /v1/asset-ingestions/{runId}` 无认证、无成员鉴权

| 项 | 内容 |
|---|---|
| 位置 | `apps/api/internal/httpapi/server.go:6033`（`handleGetAssetIngestion`，路由 :2436） |
| 证据链 | 信任头中 tenant + 路径 runId 直接查询 `GetAssetIngestion` → `SQLWorkflowReader.GetWorkflowRun`（`workflow_reader.go:56`），同样以客户端头设置 RLS 上下文；无会话、无 `authorizeProject*`。同族 start 端点（:5989）有 `authorizeAssetManage`，run-detail 同族（seed/writer/analysis）均 lookup 后授权。 |
| 影响 | 未认证跨租户读取 asset-ingestion 工作流元数据（message、error_code/error_message、时间戳、project id）。 |
| 修复 | 先查 run，再 `authorizeGlobalRunOwnerProjectRead(tenantID, run.ProjectID)`（同 `handleGetSeedRun`）。 |

### B3　`GET /v1/style-extractions/{runId}` 无认证、无成员鉴权

| 项 | 内容 |
|---|---|
| 位置 | `apps/api/internal/httpapi/server.go:6100`（`handleGetStyleExtraction`，路由 :2440） |
| 证据链 | 与 B2 完全同构：信任头 + runId 直接查询，无 authn/authz；同族 start 端点（:6056）鉴权。 |
| 影响 | 同 B2：未认证跨租户读取 style-extraction 工作流元数据。 |
| 修复 | 同 B2。 |

> 与 B1–B3 同族的 MAJOR（主审复核）：**archive-memory 读端点** `GET /v1/archive-assets/{assetId}/memories`、`/memory-events`（`server.go:5797/5820`）无 authn/authz；reader（`apps/api/internal/assets/assets.go:1182/1231`）用普通 `QueryContext`，**从不设置 tenant 上下文**——RLS 默认拒绝使所有合法用户读到空列表（功能静默失效），同时掩盖潜在 IDOR：一旦有人把 reader 接上 tenant context 而未加授权闸，即变为 B1–B3 同款未认证跨租户内容泄露（`payload_jsonb`）。修复须同时：先授权（`authorizeGlobalRunOwnerProjectRead` / 单资产授权）再设置 tenant context，照抄 `handleGetAsset`（:6517 → `authorizeSingleAssetManage`）模式。

---

## 2. 🟠 MAJOR（主审已亲自复核，证据具体）

### M-A1　Web BFF 捕获路由把未编码路径段拼进上游 URL（query 参数注入）

- 位置：`apps/web/app/api/projects/[projectId]/[...path]/route.ts:343`（`PROJECT_PATHS` 兜底 `/v1/projects/${projectId}/${rest}${query}` 用原始 `rest`），`TOP_LEVEL_ROUTES.toGo` 各捕获组已 `encodeURIComponent` 而兜底未做。
- 现象：Next 先解码路径参数，`chapters/abc%3Fx=evil` 到达 handler 时为 `abc?x=evil`，被白名单正则匹配后原样拼入上游 URL，`fetch()` 把 `?` 后内容当作 query string；`%23` 同理注入 `#` 片段。
- 影响：认证用户可向任意白名单参数化端点注入查询参数（可能改变 limit/过滤等后端行为）或丢弃真实 query；不越权但属 BFF 边界应自守的注入点。
- 修复：捕获组 `encodeURIComponent`；匹配前拒绝含 `?`/`#`/控制字符的 `rest`；补编码用例测试。

### M-A2　角色控制台「拒绝」是纯本地隐藏，从不落库

- 位置：`apps/web/app/projects/[projectId]/characters/character-console-workspace.tsx:238-241`（`handleRejectProposal` 只 `setProposals(prev => prev.filter(...))`）；`character-console-client.ts` 无 reject 函数；后端 `apps/api/internal/characterconsole/proposals.go` 仅有 adopt 路径。
- 现象：点「拒绝」卡片消失，任何 refetch/重进/刷新后提案复活；UI 呈现"已裁决"实为假装，违反仓库 no-mock-success / 不添加伪成功路径硬约束。
- 相关：`handleAdoptProposal`（:218-236）无 busy/幂等守卫，双击采纳并发两次 POST，第二次报假失败。
- 修复：后端补 reject/decide 端点，先落库成功再本地移除；采纳/拒绝按卡片加 busy 防重复。

### M-A3　世界线工作台把读取失败吞成空状态（与已修 picker 同族）

- 位置：`apps/web/app/projects/[projectId]/worldline/worldline-workspace.tsx:123-125`（`fetchWorldlineTimeline/Events/Variables(...).catch(() => [])`），另有 `:152/:159`（roster）与 `:184`（sessions）同类。
- 现象：timeline/events/variables 任一 5xx 时渲染"时间线还没有落下第一笔 / 尚无待定夺的候选"，无任何错误提示——真实后端故障被伪装成空业务数据（AUDIT-WEB-005 已修的同族反模式仍存活于世界线工作台本体）。
- 修复：读取失败按 rail 显式错误态，仅把真正空响应当空。

### M-A4　Writer 自动保存无 save-on-unload，卸载/关页丢未落盘编辑

- 位置：`apps/web/app/projects/[projectId]/writer/writer-workspace.tsx:484-487`（卸载 effect 只清 timer 不 flush）；全仓 grep 无 `beforeunload`/`pagehide`/`visibilitychange`/`sendBeacon`/`keepalive`。
- 现象：1.4s 防抖窗口内点击导航（总览/设置/返回书架/browser back/关标签）→ 未落盘文本静默丢失。章节切换/视图切换/采纳/新建章节已 flush，唯独卸载路径没有。
- 修复：卸载/`pagehide` 时 flush（`fetch keepalive`/`sendBeacon` 走 block PATCH），或至少 `beforeunload` 提示 dirty 状态。

### M-A5　世界线 events/timeline 读接口未声明硬 `LIMIT 100` 静默截断

- 位置：`apps/api/internal/worldline/worldline.go:1904-1912,1955`（`SQLTimelineReader` 默认 limit=100）、`:2009-2015,2064`（`SQLEventReader` 默认 limit=100）；HTTP 入口 `server.go:5328/5354` 无分页契约；Web 一次拉取 `worldline-client.ts:196`。
- 现象：会话事件 >100 时，UI 时间线/候选队列静默缺失旧事件；会话记录里的 `canon_event_count`（`worldline.go:1510-1514` 无上限 `COUNT(*)`）与载荷自相矛盾（显示 105 而 payload 仅 100）。
- 性质：与已修 AUDIT-WL-001（Pi 侧移除全局 `LIMIT 60`）同族，仍存活在 Go HTTP 读路径；违反 doc 25 §8.3「不添加未经契约声明的硬截断」。
- 修复：去 cap 或加显式游标分页 + `has_more`/`truncated` 契约，Web 分页拉完；sessions/saved-paths/goal-starts/prepared-agents 的 LIMIT 50 一并处理。

### M-A6　Pi token 幂等键按本地序号，流中途重试拼接两代生成文本

- 位置：`apps/pi-agent-runtime/src/activities/pi-writer-activities.ts:1020,1439-1442`（`composer:token:${++chunkIndex}`）；去重 `postgres-pi-writer-deps.ts:2315-2325`（按 `runtime_event_key` 存在则跳过）。
- 现象：worker 在 composer 流中途崩溃，重试后 `chunkIndex` 归零，attempt2 的 token 1..k 与 attempt1 键冲突被丢弃、k+1..N 写入 → 公共 SSE 流为 attempt1[1..k]+attempt2[k+1..N] 的拼接，而落库草稿是 attempt2 全文——作者看到的流与保存的候选稿不一致。
- 修复：token 键改用内容哈希或 `${provider_call_id}:token:${index}`；或 composer 阶段粗粒度 checkpoint，使重试重发相同文本。

### M-A7　Python LLM 配额按 UTF-8 字节数预留 token，约 2 倍超估

- 位置：`apps/agent-runtime/mirofish_agents/llm_quota/gate.py:171`（`input_upper_bound += len(value.encode("utf-8"))`）；`llm_quota/postgres.py:90`（预留=字节和+max_tokens）、`:163-167`（`finalize` 在 `actual_tokens > reserved_tokens` 时抛 `LLM_USAGE_EXCEEDS_RESERVATION`）。
- 现象：中文（产品主内容）每字 3 字节，runtime 自带估算约 1.5 token/字 → 预留约 2 倍真实用量，用户实际预算打半折即被 `LLM_QUOTA_TOKENS_EXCEEDED` 终止；反之低字节/高 token 输入（emoji、重复空白）实际用量超预留，成功调用被硬判失败。
- 修复：用 token 估算器计算预留上限（或按模型 token/字符表）；`finalize` 允许可配置 overage 容差。

### M-A8　迁移 0029 非事务且 sentinel 不验 backfill，部分应用被静默 baseline

- 位置：`infra/postgres/migrations/0029_assets_search_index_sync.sql`（无顶层 `BEGIN/COMMIT`，触发器 :75-83 + 一次性 backfill `INSERT ... ON CONFLICT` :89）；`infra/scripts/bootstrap-compose-database.sh:350-357`（0029 marker 只验两个触发器存在）。
- 现象：升级库上 backfill 中途失败 → bootstrap 中止但触发器已存在；下次重跑 marker 满足 → 0029 记为 `baselined` 永不重跑，存量资产永久缺 `global_search_index` 行，`search_assets` 静默漏召回（0029 要修的正是不召回）。
- 修复：0029 包 `BEGIN; ... COMMIT;`；marker 增加 backfill 完成校验（如 `global_search_index` 中 `source='asset'` 行数 ≥ 预期）。

---

## 3. 🟠 MAJOR（专项审查报告，证据具体，建议排期前先复核再动手）

### Go 领域（apps/api）

- **M-G1　`workflow_events.sequence` 无锁 `MAX(sequence)+1` 并发竞态**：`worldline/worldline.go:1243,2333,2564,2746,2991` 对 `UNIQUE (tenant_id, run_id, sequence)`（0001:226）可能撞 23505，并发采纳/注入/保存路径返回 500。修复：会话/run 行 `FOR UPDATE` 或 per-run advisory lock（同 `writer_threads.AppendMessage` 已修模式）。
- **M-G2　蒸馏 `Decide(accept_create)` 不检查 RowsAffected**：`assetdistillation/store.go:557-570` 候选 promote UPDATE 以 `lifecycle='candidate'` 过滤但不验证行数，候选并发变更时返回"accepted"但资产未 promote，仍投影到 Graph。修复：`RowsAffected()==1` 校验或 `FOR UPDATE` 资产行。
- **M-G3　多处 handler 无 body 上限**：`server.go:2728,2772,4089,3709,4707,5157,5393,3813`、`assetdistillation/handler.go:319` 用 `json.NewDecoder(request.Body)` 无 `MaxBytesReader`，15 分钟读超时下可内存放大 DoS；统一 cap（同 manuscriptworkspace 1 MiB）并限制 `block_ids` 长度。
- **M-G4　`StartSession` 绕过单当前世界护栏**：`worldline/worldline.go:1287-1335` 无条件插入 `lifecycle='active'` 会话；guard 只在 goal-start（`goal_start.go:177-205`）。直连 API 可建平行 active world。修复：插入事务内锁项目行并拒绝已存在 active 会话/非终态 goal-start。
- **M-G5　`assetcatalog.ListCollections` N+1 无上限**：`assetcatalog/collections.go:50-82` 每个 collection 一次额外查询，无 LIMIT；大目录页面慢/响应无界。修复：单查询 `jsonb_agg` 聚合 + 显式分页。

### Go 安全（apps/api）

- **M-S1　analysis-run 变更路由不在 CSRF 敏感清单**：`server.go:1567/1627` 的 `actorSensitiveRoutes`/`projectActorSensitiveRoutes` 未含 analysis-run 系列（`analysis_handlers.go:94/439/653`）。当前 SameSite=Lax 兜底，属纵深缺口。
- **M-S2　原始 SQL/driver 错误文本回给客户端**：多处 `AppError.Message` 直接拼 `err.Error()`（`assets/assets.go` 46 处、`worldline/*.go`、`storygraph/*.go`、`server.go:5814/5837/6308/6351/6398/7372-7449`、`worldline_goal_start_handlers.go:97/121`），客户端可见约束名/SQLSTATE/表名列名甚至输入值。修复：稳定公开 message + 内部日志保留原始错误。
- **M-S3　注册无邮箱验证 + 用户枚举**：`registration/service.go:77` 对任意合法格式邮箱直接建 active 用户；登录未知邮箱跳过 bcrypt（`auth/auth.go:599-619,714` 时间侧信道）；注册冲突返回 409 明确枚举。可被抢注/定向 squatting。

### Pi Writer Agent Runtime（apps/pi-agent-runtime）

- **M-P1　事件写入链一个失败毒化整条链并失败整个 run**：`pi-writer-activities.ts:1372-1406`（`eventWriteChain.then(...)`，任一 `recordWorkflow/recordTrace` reject 后后续全跳过，最终 `await` 抛错）；token 路径同（`onToken` 被 await）。DB 抖动 → run failed 且重试（3 次 × 全阶段）重复烧钱。修复：链上 `.catch(log)` 隔离 + 独立重试/有界缓冲。
- **M-P2　召回工具全文注入 LLM 上下文**：`postgres-pi-writer-deps.ts:345-355,380-386,396-412,632-672`（`query_chapter_scene`/`query_assets`/`query_world_rules`/`query_manuscript_context` 返回完整 `content_text`），budget packer 只覆盖 `search_assets`/`search_manuscript`（:1778-1815）。长场景/多资产 → context overflow 或成本爆炸。修复：统一 280 字预览截断或走共享 packer。
- **M-P3　analysis/worldline-cast LLM 阶段无配额/租约/用量记账 + 默认无限重试**：`pi-worldline-cast-activities.ts:385-408`、`pi-analysis-activities.ts:508-530`；deps（`postgres-pi-worldline-cast-deps.ts:26-42`、`postgres-pi-analysis-deps.ts`）未接 `acquireLLMLease`/`reserveQuota`；`pi-analysis-workflow.ts`/`pi-worldline-goal-start-workflow.ts` `proxyActivities` 无 retry 配置。修复：镜像 writer 路径接 quota/lease/usage + `maximumAttempts` 有界 + 阶段 checkpoint。
- **M-P4　线程消息不按 run 收敛**：`postgres-pi-writer-deps.ts:2013-2068`（选"项目最新 active thread"而非 run 的 thread；最终 `UPDATE ... status='active'` 会 bump 项目内所有 active thread；无幂等；`MAX(sequence)+1` 无锁）。并行 run 消息交错/重复/丢失。修复：按 run 收敛 + `(run_id, kind)` 去重 + per-thread advisory lock。

### Python Agent Runtime（apps/agent-runtime）

- **M-Y1　故事图 workflow 默认无限重试 + 非幂等快照写入 → 重复 graph 版本**：`temporal/graph.py:2965-2988`（`execute_activity` 无 `retry_policy`）；`_write_event` 在 try 外（:1721/1899）；`build()` 每次新 `graph_id`（:495）、`max(version)+1`（:740-749）、普通 INSERT（:904-924，`UNIQUE (tenant_id, project_id, version)`）。事件写失败 → 无限重试重跑 build → 重复快照。同模式还在 `assets.py:2320-2354`、`writer_review.py:610-620`、`worldline_prepare.py:927-935`。修复：显式 `RetryPolicy(maximum_attempts=3)` + 确定性/upsert 收敛。
- **M-Y2　资产 reindex 单请求塞全量语料**：`temporal/assets.py:648-674`（`all_texts = embedding_texts + manuscript_texts` 一次 `execute_embedding`，`call_index=0`）；`_load_embedding_assets/_load_embedding_manuscript_blocks`（:843-977）无数量/大小上限。中型项目必超 provider 输入上限（如 2048 inputs）/token 配额；且无 bounded retry。修复：按输入数+token 预算分块、稳定递增 `call_index`、有界重试。
- **M-Y3　世界线交互步把瞬时 LLM 错误当终态**：`temporal/worldline.py:325`（`run_step` catch `LLMFacilityError` 后 return failed dict）、`:2476`（activity 见 status=failed 即返回 failed 结果，不抛异常）→ `WORLDLINE_ACTIVITY_RETRY_POLICY`（:37-43，max 3）对最常见失败类（429/5xx/超时）形同虚设，会话一次瞬时故障即终态。修复：瞬时错误 raise `ApplicationError(non_retryable=False)` 让有界重试生效，永久错误保持终态。

### Infra / 部署

- **M-I1　staging compose DB/MinIO 凭据 split-brain**：`infra/compose.staging.yml:30,65-68,88-96` 只对 `api`/`legacy-import-worker` 要求真实 `DATABASE_URL`，其余 10 个 Python/JS worker 继承 base（`docker-compose.yml:184` 等）dev 默认 `APP_DATABASE_PASSWORD:-mirofish_runtime_dev_password` 与 MinIO dev 凭据——要么认证失败要么静默跑在已知默认凭据；production overlay 处理正确，staging 与其行为不一致。修复：照 production 补齐 `:?` 覆盖。
- **M-I2　production compose 静默接受 dev 默认 DB/MinIO 凭据**：`compose.production.yml` 未覆盖 `POSTGRES_PASSWORD`/`MINIO_ROOT_PASSWORD`/`APP_DATABASE_PASSWORD`，base 默认 `mirofish_dev_password`；`infra/tests/test_production_ops.py:65` 只断言 overlay 文本不含该串（合并后配置仍含），造成假信心。修复：overlay 用 `${VAR:?}` 重声明 + 合并配置测试。
- **M-I3　`/readyz` 未含 analysis/worldline-cast 队列**：`cmd/api/main.go:1102-1110`（`TemporalTaskQueues` 缺 `ANALYSIS_TASK_QUEUE`/`WORLDLINE_CAST_TASK_QUEUE`）；compose 的 `worker-readiness` 已覆盖但直连 API 的探针（文档所述生产路径）看不到这两类 worker 下线。修复：补入队列 env。
- **M-I4　迁移 ledger 无 app-role 显式 SELECT 授权**：`bootstrap-compose-database.sh:13-19`（`mirofish_schema_migrations` 建后 `REVOKE ALL ... FROM PUBLIC` 未授权 app 角色）；全新安装碰巧被 0001 的 `GRANT ... ON ALL TABLES`（:1369）覆盖，但升级/恢复（baseline 0001 不执行）路径上 runtime 读 ledger 永久 `POSTGRES_SCHEMA_UNAVAILABLE`，`/readyz` 永不 ready。修复：建表后无条件 `GRANT SELECT ... TO mirofish_app`。
- **M-I5　CI 从不跑 `infra/tests/**`**：`.github/workflows/ci.yml` 无 infra job；live-test 安全契约（`mirofish_test_*` 专用库、`down -v` 清理、生产 ops 守卫等）无任何自动化信号。修复：加 `pytest infra/tests -q` job（静态/契约测试，不需 Docker）。

---

## 4. 🟡 MINOR（择要；完整项见各专项输出）

### Web
- 世界线 `handleStep` 轮询循环卸载后继续最长 10 分钟并可覆盖新会话状态（`worldline-workspace.tsx:335-352`）。
- 登录页「忘记密码」指向不存在的 `/recovery`（404，`login-form.tsx:139`）；邀请接受无 UI 路由。
- 登出失败仍跳 `/login` 造成半登出态（`user-menu.tsx:41-52`），login 页不校验会话。
- 设置页 `noticeTimer`/`savedTimers` 无卸载清理（`settings-workspace.tsx:84-85,117-120,374-376`）。
- 移动端 drawer `role="dialog" aria-modal` 无焦点陷阱/滚动锁（`workbench-nav-drawer.tsx:59-71`）。

### Go
- 世界线 `ListSessions`/`ListSavedPaths`/`ListGoalStarts`/`ListPreparedAgents` LIMIT 50 无分页契约（长项目丢旧会话）。
- `handleGetSeedRun` 等已授权路径之外的少量 handler 存在同族遗漏排查清单（本轮 B1–B3/M1 为已确认实例）。
- 认证细节经复核为良好：cookie 标志、token 随机 nonce、哈希存储、固定会话防护、JWT alg/iss/aud/iat/exp 校验、恢复流 30min TTL + 原子消费 + 全会话吊销、邀请精确邮箱匹配、last-owner 守卫、限流 keyed Redis 固定窗口（prod 强制）均正确。

### Pi
- 世界线 timeline 注入无上限（与 M-P2 同族，`postgres-pi-writer-deps.ts:1139-1194`）。
- 单阶段 fallback 写事件无幂等键（`pi-writer-activities.ts:641-648`）。
- worker heartbeat `setInterval` 未 catch（Node ≥15 未处理 rejection 会崩进程，`worker.ts:94-116`、`analysis-worker.ts:110-126`、`worldline-cast-worker.ts:115-131`）。
- 共享契约 drift 测试只测信封枚举/字段名，payload 形状（`state_changes`、`canon_event_count`、`chunk_index`、tool 结果）无覆盖（`contracts.test.mjs:76-140`）。
- composer 10 分钟硬预算易被多工具循环+逐 token 落库打爆（`pi-writer-workflow.ts:13-26`）。

### Python
- `temporal/seed.py:8724-8737` 的 `except TypeError` 测试兼容 fallback 会掩盖真实 bug（静默二次调用）。
- 三处 HTTP helper `response.read()` 无大小上限（`llm_quota/clients.py:168-177`、`seed/sequential_reader.py:1089-1091`、`temporal/seed.py:6722-6724`）。
- story-graph snapshot `max(version)+1` 并发竞态（`temporal/graph.py:740-749`）。

### Infra
- worker 健康检查只 grep `/proc/1/cmdline`，五个 agent-runtime worker 同串无法区分（`docker-compose.yml:260,392,417,444,470,503,537`）。
- 0004 bootstrap sentinel 只验 9 表之 5（`bootstrap-compose-database.sh` 0004 marker）。
- `asset_links` 单列 FK 不约束目标租户（`0027_asset_links.sql:12-13`；完整性缺陷，非泄露）。
- `docs/refactor-saas/16-deployment-and-ops.md` 过时（bucket 命名、ledger/sentinel、`run-live-test-stack.sh` 均未记录）。

---

## 5. 复核为良好（无发现项）

- **迁移权限矩阵**：0030 已补 `writer_thread_messages` UPDATE（`0030_writer_thread_message_adoption.sql:4` ↔ `manuscriptworkspace/store.go:205`、`writer_draft_adoption.go:458`）；0001 后建表逐表核对 GRANT 与 `ENABLE+FORCE RLS` + `tenant_isolation_*` 策略（USING+WITH CHECK）完整；仅 `users/tenants/credentials/sessions` 等身份表与函数中介的 auth/audit 表无租户 RLS（正确）。
- **写路径鉴权**：seed/analysis/writer run detail+events、trace list/export（含 `include_full` 复检）、goal-start、worldline/character、资产 mutation/adoption 均带正确 `authorizeProject*`/preflight。
- **工作流/并发加固**：draft adoption `FOR UPDATE` + advisory lock + 幂等重放；writer threads/manuscript blocks 序号锁；蒸馏 admission advisory lock + outbox `FOR UPDATE ... SKIP LOCKED`；Worldline 失败终态。
- **基础设施**：`run-live-test-stack.sh`（唯一 `mirofish_test_*` 库、`mirofish.live_test=on`、`down -v` 全路径清理、无主库引用）；备份/恢复一致性守卫；gitleaks allowlist 仅限确定性的 dev/test 值；CI 最小权限（`contents: read`）；无默认管理员（dev-sessions 限于 local+显式开启）；readiness 31 迁移/`0031` sentinel 一致。

---

## 6. 处置顺序建议

**第一梯队（上线前必修；改动小、影响大）**

1. B1–B3：三个只读接口补 `authorizeProjectRead` / lookup 后授权（各一行级改动；**必须同批修 M1 archive-memory 授权闸**，否则接上 tenant context 即变活漏洞）。
2. M-A5：世界线 events/timeline 去未声明 `LIMIT 100` 或加显式分页契约。
3. M-A8：0029 包事务 + sentinel 校验 backfill。
4. M-A1：BFF 路径段编码 + 拒绝 `?`/`#`/控制字符。

**第二梯队（真实环境高概率触发）**

M-A6（Pi token 流重试拼接）、M-A3（世界线吞错）、M-A4（Writer 失存）、M-Y1（故事图重复快照+重试风暴）、M-Y3（世界线瞬时错误终态）、M-P1（事件链毒化）、M-P4（线程消息收敛）。

**第三梯队（数据正确性与成本）**

M-A7（配额字节超估）、M-Y2（reindex 单请求全量）、M-P3（analysis/cast 无配额记账）、M-G2（RowsAffected）、M-G1（sequence 竞态）。

**第四梯队（加固与卫生）**

M-I1/M-I2（staging/prod compose 凭据）、M-I3（readyz 队列覆盖）、M-I4（ledger 授权）、M-I5（CI infra job）、M-G3（body cap）、M-G4（StartSession 单世界）、M-G5（N+1）、M-S1/M-S2/M-S3、§4 MINOR 批。

---

## 7. 本次审核的边界

- 只读审核：未运行 Compose、未连接真实数据库、未执行任何迁移。B1–B3 的"未认证跨租户可读"结论基于**处理器主体 + 读路径 `app_set_tenant_context` 调用 + RLS 策略原文**推导；建议修复后各跑一次真实库/真实 HTTP 冒烟以获取运行时证据。
- §1–§2 由主审逐条复核；§3 由 6 路专项审查产出并附具体证据，主审抽查了代表项（Pi token 键、Python 配额字节、0029 事务性），排期时建议先复核再动手。
- 上一轮 `AUDIT-2026-07-31`（doc 25 §8/§9）六项与 `AUDIT-044`（doc 44 §7）各项按仓库规则视为已闭合基线；本报告仅上报新发现与同族残留，未重复列举已修复项。
- `backend/` 为遗留参考目录，未纳入审查范围（仅 legacy_import 在真实路径上时才会评估）。
- **本报告第 0.1 节记录了当前修复状态。** 原始审查结论仍保留在 §1–§4 作为证据链；已修复项以当前 worktree 与验证输出为准，残余项不得标记为 `fixed_verified`。
