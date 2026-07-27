# 全模块代码缺陷审查报告

审核日期：`2026-07-26`
审核分支：`rewrite/web-clean-slate`（含"世界线闭环 + 写作台会话轮次"未提交在制工作）
审核范围：`apps/api`（Go 控制面，11.7 万行）、`apps/web`（Next.js，2.3 万行）、`apps/agent-runtime`（Python Temporal workers，6.8 万行）、`apps/pi-agent-runtime`（Pi Writer Agent Runtime，1.6 万行）、`infra`（迁移 / Compose / bootstrap）
审核方式：只读。13 路并行专项审查覆盖各模块，其后由主审逐条复核关键结论（读迁移、读授权链、读处理器主体、比对同族实现）。**本次审核未修改任何文件、未写入任何数据库。**

---

## 0. 一句话结论

**四条测试线里三条全绿，但绿灯掩盖了一个会让写作台核心流 100% 失效的缺陷——本次未提交的新代码对一张只有 `SELECT/INSERT` 权限的表执行了 `UPDATE`。**

测试基线：Go `go test ./...` 全绿；Web `tsc` + 75 测试全绿；Pi `vitest` 132 通过 + `tsc` 全绿；**Python `pytest` 收集阶段即失败**（见 §3）。

绿灯为什么没抓到：Go 单测用假 queryer、Python 用假连接，**都绕过了真实 Postgres 的表授权与 RLS**。本报告中危害最大的三条（采纳授权、资产 RLS、trace 导出 RLS）全部属于"只在真实数据库上才会暴露"的一类。

修复性价比：P0 四项全部是小改动量——一条迁移、一处 `authorizeProject` 调用、一段前端 flush 对称化、一个准入守卫。

---

## 1. 已亲自核实的高危项

以下 6 项由主审逐条复核（读迁移原文、读授权链、读处理器主体、与同族实现比对），结论可直接据以动手。

### 🔴 P0-1　草稿采纳 100% 失败：对无 `UPDATE` 权限的表执行 `UPDATE`

| 项 | 内容 |
|---|---|
| 位置 | `apps/api/internal/workflows/writer_draft_adoption.go:453`（本次未提交新代码） |
| 迁移证据 | `infra/postgres/migrations/0019_writer_threads.sql:91,95` |

新增的 `thread_adoption` CTE 对 `writer_thread_messages` 执行 `UPDATE ... SET metadata_jsonb = ...`。但 0019 迁移先 `REVOKE ALL`、再**只授 `SELECT, INSERT`**：

```sql
REVOKE ALL ON writer_thread_messages FROM PUBLIC, mirofish_app;
GRANT SELECT, INSERT, UPDATE ON writer_threads TO mirofish_app;
GRANT SELECT, INSERT         ON writer_thread_messages TO mirofish_app;  -- 无 UPDATE
```

同批的 `writer_threads` / `writer_approvals` 都授了 `UPDATE`，唯独消息表没有——这是刻意的"消息只追加"设计。后续迁移无一补授（全库 grep `GRANT UPDATE ... thread` 为 NONE）。

根因链已完整坐实：
1. `mirofish_app` 是 NOLOGIN 组角色（`0001:8`）；
2. `0001:1369` 的 `GRANT ... ON ALL TABLES` 只覆盖**当时已存在**的表，而 `writer_thread_messages` 在 0019 才建，不在其中；
3. API 以 `mirofish_runtime` 连接（`docker-compose.yml:182`），该角色 `IN ROLE mirofish_app`（`bootstrap-compose-database.sh:400,414`），**非表 owner，无 owner 绕过**；
4. `AdoptDraft`（:179）经 `tx.QueryContext` 执行含该 UPDATE 的整条 CTE（:198）。

**Postgres 在执行器启动时对计划中所有关系做权限校验，与命中行数无关**——因此即使某次采纳没有任何匹配的线程消息，语句同样 42501 permission denied，整条 CTE 回滚，`AdoptDraft` 返回 `DRAFT_ADOPTION_WRITE_FAILED`。**采纳进手稿这一核心流在真实部署中每一次都失败。**

修复方向：新增迁移 `GRANT UPDATE ON writer_thread_messages TO mirofish_app`（并在 `bootstrap-compose-database.sh` 补 sentinel 断言），或改为 `INSERT ... ON CONFLICT` 记录采纳态而不 UPDATE 消息行（更贴合"只追加"原设计）。

### 🔴 P0-2　一族"启动 / 采纳"接口缺项目成员鉴权（越权 / IDOR）

`handleAdoptDraft`（`server.go:7522`）从 `X-Tenant-Id` 头直达 `AdoptDraft`，**从不调用 `authorizeProject`**。而其紧邻同族：

- `handleStartDraftReview`（:7576）→ `lookupDraftReviewOwnerProject` + `authorizeProject(PermissionCreativeWrite)`
- `handleCancelWriterRun` → `authorizeGlobalRunOwnerCreativeWrite`

`authorizeProject`（`server.go:3434`）内部调用 `authorizer.Authorize(AuthorizeInput{UserID, TenantID, ProjectID, Permission})`，**是把"会话用户 → 租户/项目成员 + 权限"绑定起来的唯一闸门**。跳过它意味着：任一持有效会话者，只要知道 `draftId` 并自行设定 `X-Tenant-Id`，即可向他人项目手稿写入内容（租户内越权；因 `tenantID` 取自客户端可控请求头且 RLS 亦只信该值，跨租户风险需一并评估）。

同类缺口（同一模式，均未调用 `authorizeProject`）：

| 处理器 | 位置 | 备注 |
|---|---|---|
| `handleAdoptDraft` | `server.go:7522` | 手稿写入；**经 Web BFF 可达**（`POST drafts/{id}/adoptions` 在白名单内）|
| `handleStartStoryGraphBuild` | `server.go:6018` | 消耗他人 LLM 预算、改图谱 |
| `handleStartStoryGraphBondGeneration` | `server.go:6057` | 同上 |
| `handleStartSeedRun` | `server.go:3979` | 对照 `handleStartAnalysisRun` 有 `creative_write` 鉴权 |
| `handleStartHelloAgent` | `server.go:7304` | 诊断用，危害较低 |

⚠️ **与 P0-1 的耦合**：今天采纳接口被 P0-1 挡着（写不进去），此越权尚不可利用；**一旦修好 P0-1，该漏洞立即变为活漏洞——两者必须同批修复。**

### 🔴 P0-3　世界线 goal-start 无"单活跃运行"护栏

位置：`apps/api/internal/worldline/goal_start.go:136-171`

准入链路只有三步：`lockGoalStartProject`（对 `projects` 行 `FOR UPDATE`，**仅串行化并发，不拒绝第二次**）→ `requireGoalStartAnchor` → `findGoalStartReplay`（**仅按 `request_id` 去重**，:246 `queued.payload_jsonb->>'request_id' = $4`）。

前端每次点击都会新铸 `X-Request-Id`，因此双击"整备"、或"整备中刷新页面后重新提交"（见 §2 Web 表中 `worldline-workspace.tsx:183`），两次提交各自通过重放检查，**各建一个 cast 编排、最终各建一个 `lifecycle='active'` 会话**——单世界产品的核心不变量被破坏，并双倍消耗 LLM。

对照：step 准入有 `WORLDLINE_STEP_ACTIVE`、自动演化有 `WORLDLINE_AUTO_EVOLUTION_ACTIVE` 守卫，**唯独 goal-start 没有等价护栏**。

### 🔴 P0-4　写作台"采纳 / 新建章节"静默丢弃未保存的手稿编辑

位置：`apps/web/app/projects/[projectId]/writer/writer-workspace.tsx:431-436`（`handleAdopt`）、:317（`handleNewChapter`）

`handleAdopt` 在 `await loadStructure` 后执行 `setSegments(服务器文本)` 覆盖本地状态，**却不像 `handleSelectChapter`(342-347) 那样先 flush 待存的防抖定时器**：

```ts
// handleSelectChapter：先冲刷再切换
clearTimeout(timer);
void persistSegment(blockId);

// handleAdopt：直接覆盖，无冲刷
await loadStructure(selection);
const segs = await loadChapterSegments(selection, activeChapterId);
setSegments(segs);
```

而 `persistSegment`(:254) 在定时器**触发时**才读 `segmentsRef.current`——此刻已被回滚成服务器文本。失效时序：

1. 作者输入 → `handleEditSegment` 更新状态并挂起 1400ms 防抖定时器；
2. 作者在防抖窗口内点"采用进手稿"；
3. `setSegments(segs)` 把画布与 ref 一并回滚成**不含该次编辑**的服务器文本；
4. 挂起的定时器随后触发，读到已回滚的文本，把服务器自己的旧文本写回。

净结果：**作者刚敲的字既从画布消失、也从未落库**。`handleNewChapter` 同缺口。修复即把 `handleSelectChapter` 的 flush 逻辑抽出复用。

### 🟠 P1-5　手稿导出漏 `status='active'` 过滤，软删段落混入成品

位置：`apps/api/internal/workflows/writer_manuscript_export.go:181-184`

```sql
FROM manuscript_blocks
WHERE tenant_id::text = $1
  AND project_id::text = $2
ORDER BY block_order ASC, created_at ASC
```

**无 `status='active'`**。手稿工作区删除段落是软删（置 `status='deleted'`），故已删除的正文会重新出现在导出成品里。更糟的是 `idx_manuscript_blocks_active_order` 是 `WHERE status='active'` 的**偏索引**，已删块可与其活跃替代块共用同一 `block_order`，导致旧文错位插进正文中间。全库其它读侧都带该过滤，唯导出遗漏。

### 🟠 P1-6　Python 资产写入漏设租户 RLS 上下文，真实库必失败

位置：`apps/agent-runtime/mirofish_agents/temporal/assets.py:476`（`write_candidates`）、:557（`load_material`）

`set_postgres_tenant_context` 在 `assets.py` **仅第 24 行 import、无任何调用点**；两处均 `self._connect()` 后直接读写 `assets`。对照 `graph.py` 在 :297 / :425 / :502 三处都正确设置了上下文。

`assets` 表为 `FORCE ROW LEVEL SECURITY`（`0001:1680`），未设 `app.current_tenant_id` 时：INSERT 违反 WITH CHECK 被拒、SELECT 见零行。**资产入库与风格取材在真实生产必然失败，且是在 LLM 调用花费之后才失败。**

---

## 2. 其余重要发现（专项审查报告，证据具体，建议复核后修）

以下为各路专项审查产出、主审未逐条复现的条目。均附 `file:line` 与可判定的失效场景，建议按级别排期复核。

### Go —— 工作流与并发

| 位置 | 级别 | 问题 |
|---|---|---|
| `workflow_retry.go:530` | high | 重试复用固定 workflow ID `seed_run_<id>_retry`；SDK 默认吞掉 `WorkflowExecutionAlreadyStarted` 并返回旧句柄 → 取消后重试静默空转，run 永卡 `queued`，无对账器可救 |
| `workflow_retry.go:745` | high | 重试未栅栏隔离上一 attempt；seed 活动无 heartbeat、Python `_update_status` 无 status/attempt 守卫 → 僵尸活动回写覆盖新 attempt 的状态 |
| `workflow_cancellation.go:214` | medium | 取消无条件 `UPDATE status='cancelled'`，缺 `status IN ('queued','running')` 守卫 → 可覆盖已 `completed` 的终态 |
| `writer_threads.go:262`、`writer_draft_adoption.go:314` | medium | `MAX(sequence)+1` / `MAX(block_order)+1` 无锁分配 → 并发追加/采纳撞唯一约束（23505），请求失败 |
| `worldline/worldline.go`（`sqlTenantRows.Close()`）| medium | 在 `defer rows.Close()` 内部执行 `Commit()`，调用方一律丢弃其返回错 → COMMIT 失败仍返回 200 与 RETURNING 行 |
| `worldline/goal_start.go:562` | medium | `GetGoalStart` 未查 `rows.Err()`，把迭代错误一律映射成 `NOT_FOUND` → 轮询期间瞬时故障被前端当作"运行不存在" |

### Pi Writer Agent Runtime

| 位置 | 级别 | 问题 |
|---|---|---|
| `workflows/pi-writer-workflow.ts:5` | high | 工具循环无步数上限、`proxyActivities` 未设重试策略 → 超 10 分钟的 stage 在 Temporal 默认无限重试下从头重跑，run 卡非终态并重复烧 token |
| `activities/pi-*-activities.ts`（写作/分析/cast）| high | 载荷校验位于 try/catch **之外**并抛可重试错 → 非法载荷成"毒丸"被无限重试，run 永卡 `queued`，不产生 failed 事件 |
| `runtime/postgres-pi-worldline-cast-deps.ts:177` | high | `query_project_context` 选取 `name, summary`，而 `projects` 表实为 `title/description` → 每次调用 42703 报错 |
| `runtime/postgres-pi-worldline-cast-deps.ts:404,481` | high | `admitPreparation`/`startSession` 非幂等（每次 `randomUUID`）且轮询忽略 abort → Temporal 重试或用户取消时重复创建 preparation 与 session |
| `runtime/postgres-pi-writer-deps.ts:1475` | medium | 无 chapter/scene 的 run 把 `''` 转 `uuid` → `search_manuscript` 每次报错（两路审查独立命中，可信度高）|
| `llm/quota/postgres-quota-store.ts:171` | medium | 每次 `reserve()` 过期该租户所有超 TTL 预留（默认 300s < 10 分钟 stage 预算）→ 长 stage 自己的预留被循环内 rerank 挤掉，事后 finalize 失败 |

### Web

| 位置 | 级别 | 问题 |
|---|---|---|
| `writer/use-writer-run.ts:70` | high | 900ms 轮询无在途守卫；事件数 >100 页时游标不前进且不 break → 同一页被反复重拉的串行请求风暴 |
| `writer/use-writer-run.ts:107` | high | 终态判定在"读事件 / 读运行详情"之间存在竞态 → 终末事件漏读，纺锤永转、编排器锁死至刷新 |
| `lib/api/writer-client.ts:332` | high | `GET /drafts/{id}` 既不在 BFF 白名单、Go 也无该路由 → 草稿跟随功能整体静默失效（两路模块审查 + 契约审查三方一致）|
| `writer/writer-workspace.tsx:181,356` | medium | 线程历史整体覆盖抹掉乐观 turn（`liveTurnIdsRef` 写入但从未读取）；刷新后 `activeRunIds` 不重建 → 可并发起第二个 run |
| `worldline/worldline-workspace.tsx:124,329` | high | `failed` 从不写入 `worldline_sessions`（Python 与 Go 均回写 `paused`）→ 失败面板与"这一步推演失败了"是不可达死 UI，作者得不到任何反馈 |
| `worldline/worldline-workspace.tsx:141,616` | medium | `loadSessionData` 无条件覆盖 `variables` → 冲掉在途锁定 PATCH；`busyId={busy ? undefined : null}` 恒不等于 `event_id` → 采纳按钮从不禁用，可重复提交 |
| `worldline/worldline-workspace.tsx:183` | medium | 挂载时不重建在途 goal-start → 整备中刷新回落起点态，重新提交即触发 P0-3 的双跑 |
| `lib/server/api-proxy.ts:57` | medium | 限流证明签在客户端可控的 `X-Forwarded-For` 最左值上 → 登录/注册的按 IP 限流可被伪造绕过 |

### Python agent-runtime

| 位置 | 级别 | 问题 |
|---|---|---|
| `temporal/worldline.py:2549`、`worldline_auto_evolution.py:449` | high | 候选提交后的持久化失败被转成 `mark_failed_status=False` 的**返回值**而非抛出 → Temporal 视作正常结束不再重试，session 永卡 `running`，后续步全被拒且无恢复路径 |
| `llm_quota/clients.py:171` | high | 生产 seed 客户端硬编码 60s `urlopen` 超时，而批预算为 60k 输入 / 30k 输出 token → 长生成必然超时，重试与二分各自再付一次费 |
| `llm_quota/clients.py:57` | high | 生产路径用裸 `json.loads`，不容代码围栏/前置散文；容错解析器只存在于仅测试使用的 `OpenAICompatibleJSONClient` |
| `llm_quota/postgres.py:645,869` | medium | 重放写入跳过 + 敏感词清洗 → Temporal 重试后返回的数据与首次不同（静默偏移，违"不静默降级"约定）|
| `temporal/seed.py:10494` | medium | 整书 LLM 活动无 heartbeat、无重试上限、仅末尾持久化 → 超时预算的大部头从头无限重读，只烧钱不前进 |
| `temporal/seed.py:2033,3255` | medium | 重试时快照数组无条件追加、审计事件无 `ON CONFLICT` → 计数虚高、生成事件重复 |

### LLM 设施 / 平台（Go）

| 位置 | 级别 | 问题 |
|---|---|---|
| `traces/trace.go:316` | high | `RecordExport` 未走租户上下文即 INSERT 强制 RLS 的 `audit_logs` → 违反 WITH CHECK，trace 导出在真实库恒失败 |
| `sourcefiles/object_writer.go:88` | high | 上传全链路无大小上限，先整拷至 `/tmp` 再比对声明大小 → 单请求即可写满磁盘拖垮 API |
| `cmd/api/readiness.go:28` | medium | 就绪门仍要求迁移 `0022` / count 22，而 schema 已至 0028 → 缺 0023–0028 的库仍被判 ready |
| `llm/analysis_ensure.go:93` | medium | 模块未绑定时静默借用他模块 binding 顶替（silent fallback，违"缺绑定须显式失败"策略）|
| `llm/bindings.go:302` | medium | 列绑定未过滤 `c.enabled = TRUE` → 已软禁用（"删除"）的渠道仍显示为已配置，运行时却报 `LLM_MODULE_UNBOUND` |
| `llm/catalog.go:383` | medium | 能力位以"存储值 OR 名称推断"生效且健康检查会写回 → 运维把 `supports_tools` 关成 false 无效 |
| `cmd/api/main.go:56,1214` | medium | ~70 个独立连接池 × 4 连接 → 单实例可要 250+ 连接，超 Compose Postgres 默认 `max_connections=100`；且裸 `ListenAndServe`，无超时、无优雅关停 |

### 协作 / 鉴权（Go）

| 位置 | 级别 | 问题 |
|---|---|---|
| `collaboration/service.go:527` | high | 租户 `admin` 被当作完全 manager，可给他人或自己授予 `owner` → 先自升 owner 再降原 owner，完成租户接管 |
| `collaboration/service.go:228` | medium | `AcceptInvitation` 无条件覆盖既有成员角色，绕过"最后一名 owner"不变量 → 可把唯一 owner 降级至零 owner |

### 资产蒸馏（Go）

| 位置 | 级别 | 问题 |
|---|---|---|
| `assetdistillation/graph_projection.go:380` | high | `excerpt[:240]` 按**字节**截断多字节 UTF-8（中文必中）→ 产生非法字节序列被 PG 拒绝，world_rule 采纳事务恒失败且截断点确定、重试无用 |
| `assetdistillation/store.go:221` | high | 指纹重放去重匹配任意历史请求且硬编码状态 `'queued'` → 工作流失败后同内容**永远无法再蒸馏**，UI 还显示幻影排队 |
| `assetdistillation/store.go:874` | medium | `assertSourcesCurrent` 在 `withTenant` 内返回错误导致标记 `stale` 的 UPDATE 被回滚 → 提案永远停在 `pending`，每次采纳都失败 |

### 基础设施

| 位置 | 级别 | 问题 |
|---|---|---|
| `infra/postgres/rollbacks/0028_*.sql` | high | 回滚只 DROP 索引、**不删 `mirofish_schema_migrations` 台账行**（0018/0019/0027 回滚均含该 DELETE）→ 回滚后 bootstrap 校验 sentinel 失败并 exit 1，schema-init 永久卡死且迁移无法重放 |
| `infra/compose.staging.yml:37` | high | staging 仅给 `api` 与 `legacy-import-worker` 注入 `TEMPORAL_NAMESPACE`，其余 seed/graph/asset/worldline/character/reviewer 及三个 pi worker 仍回退 `default` → 派发与轮询命名空间分裂，工作流全部零 poller 挂起（production overlay 已正确覆盖全部服务）|
| `infra/docker-compose.yml:73` | medium | `TEMPORAL_DB` / `TEMPORAL_VISIBILITY_DB` 只喂 `temporal-db-init`，temporal 自身（`SKIP_DB_CREATE=true` 且无 `DBNAME`）仍连默认库 → 一旦覆盖即崩溃循环，阻塞全部依赖服务 |
| `infra/scripts/check-temporal-workers.sh:29` | low | 就绪队列清单遗漏 `analysis-streaming` 与 `worldline-cast-streaming` → 这两个 worker 的 poller 注册从不被校验 |

---

## 3. 测试与卫生（已复现）

**Python 测试整套无法收集。** `apps/agent-runtime/tests/test_legacy_import.py:10` 执行 `from scripts.legacy_import import parser`，但 `apps/agent-runtime/scripts/` 已在提交 `de42419` 作为"死代码"删除，真实包在 `mirofish_agents/legacy_import`。该文件连同 import 它的 `test_legacy_import_live.py` 一并收集报错：

```
E   ModuleNotFoundError: No module named 'scripts'
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
```

后果：**整个 legacy-import 回归套件失效**；且被删的 CLI 其实仍被 `test_cli_apply_and_verify_require_plan_binding` 使用（校验 `--expected-source-fingerprint` / `--expected-plan-hash` 强制绑定），并非死代码。

修复方向：从 `de42419^` 恢复 `scripts/legacy_import.py`，或将该 CLI 迁入 `mirofish_agents/legacy_import/cli.py` 并同步修改两处 import。

---

## 4. 已否决的误报（存档以备追溯）

**"1-hop 关系扩展绕过剧透门控泄漏未解锁资产"——经复核为假，不予采纳。**

专项审查报称 `postgres-pi-writer-deps.ts:512` 处 `query_asset_relationships` 与批量扩展 `loadRelatedAssets` 均未施加 `reveal_after_chapter_order` 门控。实际读取全块后确认**两者都带门控**：

- `query_asset_relationships`：:519 `AND (related.reveal_after_chapter_order IS NULL OR related.reveal_after_chapter_order <= $6)`
- `loadRelatedAssets`：:1488 同形门控（:1455-1457 注释亦明确写有 "the same spoiler gate as direct recall"）

误报成因：该审查只引用了 `JOIN ... ON` 片段至 `lifecycle` 那一行，漏看紧随其后的门控条件。**0024 剧透门控在召回、常驻注入、关系扩展三条路径上均已正确生效。**

---

## 5. 处置顺序建议

**第一梯队（上线前必修；均为本次在制新代码引入或直接破坏核心流）**

1. P0-1 采纳 `GRANT`（一条迁移 + bootstrap sentinel 断言）
2. P0-2 采纳接口 `authorizeProject`（**必须与 P0-1 同批**，否则修好写入即敞开越权）
3. P0-4 写作台 flush 对称化（抽出 `handleSelectChapter` 的冲刷逻辑复用）
4. P0-3 goal-start 单活跃运行守卫（对齐既有 `WORLDLINE_STEP_ACTIVE` 模式）

**第二梯队（真实环境必现，单测因假连接结构性漏检）**

P1-6 assets RLS 上下文、`traces` 导出 RLS、Pi `query_project_context` 列名漂移、Python worldline 步失败卡死、0028 回滚台账、staging `TEMPORAL_NAMESPACE`。

**第三梯队（数据正确性）**

P1-5 导出软删块、蒸馏 UTF-8 字节截断、蒸馏失败后不可再蒸馏、重试/取消状态机（`workflow_retry` / `workflow_cancellation`）。

**第四梯队（卫生与加固）**

修复 Python 测试收集；就绪门升至 0028；收敛 DB 连接池数量并补服务器超时/优雅关停；协作 `owner` 越权；上传大小上限。

---

## 6. 本次审核的边界

- 只读审核，未运行 Compose、未连接真实数据库、未执行任何迁移。P0-1 / P1-6 / trace 导出三项的"真实库必失败"结论基于**迁移原文 + 角色链 + Postgres 权限与 RLS 语义**推导，建议在 Compose 上各跑一次端到端验证以获取运行时证据。
- §1 六项由主审逐条复核；§2 各项由专项审查产出并附具体证据，主审未逐条复现——排期时建议先复核再动手。
- `backend/` 为遗留参考目录，按仓库约定未纳入审查范围。

---

## 7. 修复结论（2026-07-27）

本报告四个梯队中的确认缺陷已全部闭合；§4 的 1-hop 剧透门控项保持 `false_positive`，未为误报修改生产逻辑。原审计证据保留在上文，以下是当前 worktree 的处置真相源。

### 第一梯队

| 条目 | 状态 | 修复与证据 |
|---|---|---|
| P0-1 草稿采纳表权限 | `fixed_verified` | `0030_writer_thread_message_adoption` 只补 `UPDATE`、继续拒绝 `DELETE`；app role live 采纳通过 |
| P0-2 写入口项目鉴权 | `fixed_verified` | Seed、Graph build/bond、Hello、Draft adoption 均在副作用前做 owner-project `creative_write` 鉴权；denial regression 通过 |
| P0-3 goal-start 单活跃护栏 | `fixed_verified` | project lock 内拒绝第二个非终态 goal-start 或已有 current world；Web 同步恢复 pending run 并锁提交 |
| P0-4 Writer 未保存编辑 | `fixed_verified` | 切章、新章、采纳均等待逐 block autosave queue；失败时停止动作并保留本地稿件 |

### 第二梯队

| 条目 | 状态 | 修复与证据 |
|---|---|---|
| Asset runtime RLS | `fixed_verified` | candidate write/material read 均先设置 tenant/project context |
| Trace export audit RLS | `fixed_verified` | export audit 改为可写 tenant transaction；app-role live 通过 |
| Pi cast project 列漂移 | `fixed_verified` | 查询改为 `title AS name, description AS summary` |
| Worldline 提交后失败卡死 | `fixed_verified` | event/status 持久化失败重新抛给 Temporal；最终失败写 session `failed`，Web 失败态可达 |
| 0028 rollback ledger | `fixed_verified` | rollback 删除对应 ledger；infra rollback/sentinel regression 通过 |
| staging Temporal namespace | `fixed_verified` | 全部 Python/Pi workers 与投递端统一注入 namespace；readiness 补齐两个 streaming queues |

### 第三梯队

| 条目 | 状态 | 修复与证据 |
|---|---|---|
| 手稿导出软删块 | `fixed_verified` | export 只读 `status='active'` |
| 蒸馏 UTF-8 截断/stale 回滚 | `fixed_verified` | rune-safe 截断；stale 状态在独立成功事务提交 |
| 蒸馏失败指纹不可重试 | `fixed_verified` | `0031_asset_distillation_retryable_fingerprint` 移除全局唯一约束，以 advisory lock 串行 admission；只重放 queued/running/completed，failed/cancelled 可创建新 run；live 通过 |
| workflow retry/cancel | `fixed_verified` | 每次整 run retry 使用唯一 workflow id 和 attempt fencing；旧 attempt 不得回写；cancel 只改 queued/running |
| Writer sequence/block order | `fixed_verified` | thread message sequence 与 manuscript block order 在分配前加锁 |
| Worldline rows/iteration | `fixed_verified` | read-only query rollback；`Err()` 主动 finalize 并暴露 commit error；全部 rows path 检查迭代错误 |

### 第四梯队与专项加固

| 条目组 | 状态 | 修复与证据 |
|---|---|---|
| Python 测试收集/Legacy CLI | `fixed_verified` | CLI 迁入 package，full collection 恢复 |
| readiness/schema/Compose | `fixed_verified` | ledger/readiness/bootstrap 至 `31:0031_asset_distillation_retryable_fingerprint`；Temporal DB name、worker queues 与 staging namespace 对齐 |
| API 资源边界 | `fixed_verified` | 共享 DB pool 收敛；HTTP read/write/idle/header timeout 与 graceful shutdown；Go source upload 100 MiB、413、`LimitReader`；非法 limit 配置启动失败 |
| Next upload BFF | `fixed_verified` | 不再 `arrayBuffer()` 无界读取；Content-Length 与流累计双重 100 MiB 限制，超限 413，非法配置 500 |
| Collaboration owner 不变量 | `fixed_verified` | 只有 owner 可授 owner；admin 不可自升；低角色邀请不降级现有 owner；同时修复 tenant membership UPDATE 的 SQL placeholder 错误；app-role live 通过 |
| LLM binding/capability | `fixed_verified` | disabled channel 不参与绑定；analysis 无绑定 fail closed；显式 capability 不再被名称推断或 health sync 覆盖 |
| Python LLM/Temporal | `fixed_verified` | LLM timeout 可配置且 JSON 容忍围栏/前置文本；Seed/Worldline activity bounded retry + heartbeat；Seed snapshot/event retry 去重 |
| Pi runtime | `fixed_verified` | activity retry bounded；tool calls 有硬预算；非法 payload 为 non-retryable；cast UUID/abort/replay/DB conflict 幂等；空 chapter/scene 使用 `NULLIF`；reservation TTL 为 900s |
| Pi 非法 payload 事件边界 | `verified_by_design` | 完全不可解析且没有可信 tenant/run identity 的 payload 不伪造租户事件；有有效运行上下文的错误仍写 durable failed event |
| Quota 过期清理 | `verified_by_design` | 仅清理 `expires_at <= now()` 的真实过期 reservation；900s TTL 与稳定 provider-call replay 防止活动内误释放，不移除正常过期回收 |
| Web polling/history/worldline | `fixed_verified` | writer polling 单飞、分页推进并补终态事件；thread optimistic/history 合并；draft read route/BFF 补齐；goal-start refresh、variable PATCH、busy id 与 failed session UI 对齐 |
| Trusted proxy IP | `fixed_verified` | 不再信任客户端任意最左 `X-Forwarded-For`，按可信代理边界解析限流 IP |

### 验证

- Go API full：`go test ./...` passed。
- Python Agent Runtime full：`504 passed, 31 skipped`。
- Pi Runtime：`133 passed, 4 skipped`，typecheck/build passed。
- Web：`92 passed, 1 skipped`，typecheck/build passed。
- Infra：production ops focused `49 passed`；当前 `infra/tests` full `72 passed`。
- 隔离 app-role live：asset distillation、collaboration、workflows、worldline、traces、sourcefiles 六包全部通过；数据库为唯一 `mirofish_test_*`，带 `mirofish.live_test=on`，退出已 `down -v`。
- `git diff --check` passed。真实隔离 API/Web 启动与同源 BFF 认证结果记录在 `24-current-development-progress.md`。

本审计完成不改变 MAIN-100 的独立 Legacy gate：状态继续为 `awaiting_legacy_authorization`。
