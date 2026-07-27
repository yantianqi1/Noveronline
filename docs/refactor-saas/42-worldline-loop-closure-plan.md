# 世界线推演闭环补齐计划（变量注入 / 采纳权重 / 步号口径）

创建时间：`2026-07-26`
状态：`verified_current`（2026-07-26 实施完成，live/browser 证据见文末"实施记录"）

## 文档职责

本文是"把世界线三个动作真正接成闭环"的唯一开发计划入口。范围以 `DEVELOPMENT_PLAN.md` 为准，世界线现状以 `09-worldline.md` 与当前 worktree 为准；冲突时以当前代码、schema、运行中 compose 和本轮测试输出为最终事实。

## 背景：为什么现在"好乱"

当前世界线把"注入变量 → 采纳事件 → 再推进一步"做成了三笔**互不知晓的写入**，没有一处把它们串进推演：

1. **注入变量是死数据。** `SQLVariableStore.InjectVariable` 只 `INSERT INTO worldline_variables` + 写一条 `worldline.variable.injected` 编排事件。全库 grep 确认 `worldline_variables` 除注入外**无任何 SELECT**，变量对 director LLM 隐形。
2. **变量锁是纯前端内存。** `handleToggleVariableLock` 只 `setVariables` 改本地 state，从不回写；刷新即丢，且无论 lock 与否都不进推演。"锁定 = 约束传入下一轮"目前没有任何实现支撑。
3. **采纳没有分量。** director 的 `load_session_context` 取"最近 12 条 status ∈ (candidate, canon) 的事件"，候选与正史混在一起喂给 LLM；采纳只改变一条事件以 canon 身份再次出现的形式，LLM 不知道哪些算数。
4. **步号口径不一致。** banner 的"第 X 步"来自 timeline `workflow_events.sequence`（编排序号，采纳一次就 +1），领域事件的 `step` 是 `MAX(step)+1`（一批候选共享），两者不是一回事，容易对不上。

目标：让"变量真的影响推演、采纳真的有权重、步号真的对齐"。

## 范围与边界

四层改动，闭环三处；一处显式不做。

| 层 | 改动 |
|---|---|
| DB（schema） | 新迁移 `0028_worldline_variable_lock_and_canon`（见下），不动 `worldline_variables` 已有列（`locked` 已存在，`idx_worldline_variables_session` 已存在） |
| Go（apps/api） | 变量 lock 回写路由 + 读侧；采纳→canon 语义不变；banner 步号口径数据源 |
| Python（apps/agent-runtime） | director / auto-evolution 的 `load_session_context` 增读 locked 变量与 canon 区分 |
| Web（apps/web） | lock 回写接 API、变量持久化读取、banner 步号改用领域 step |

**显式不做**：不引入新的 LLM 模块 key（复用 `worldline_director`）；不改 auto-evolution 的步进编排结构；不做候选编辑后重推；不做旧占位采纳行的数据回填（沿用既有 `worldline_event_adoptions` 语义）。

## 三处闭环设计

### 闭环 1：locked 变量真正注入推演（DB + Go + Python + Web）

- **DB**：迁移 `0028` 为 `worldline_variables` 补 `idx_worldline_variables_session_locked (tenant_id, project_id, session_id) WHERE locked = true` 部分索引；如评审确认无既有 `updated_by`/锁审计需要则不加列，保持最小。
- **Go**：新增 `PATCH /v1/worldline-sessions/{sessionId}/variables/{variableId}`（body `{locked}`），走 `SQLVariableStore.SetVariableLocked`（UPDATE … SET locked, updated_at，RETURNING 记录）；幂等（同 locked 重复 PATCH 返回现状 200）。新增 `GET /v1/worldline-sessions/{sessionId}/variables`（list，供前端水合）。两者走中央 auth/RBAC/CSRF + tenant context。
- **Python**：`PostgresWorldlineSourceLoader.load_session_context` 增查 `worldline_variables WHERE tenant/project/session AND locked = true ORDER BY updated_at DESC LIMIT 24`，产出 `locked_variables: [{name, description, impact_axis}]`；`_worldline_step_messages` 的 user payload 附 `session_context.locked_variables`,system prompt 明确"locked_variables 是作者注入的硬约束，必须贯穿本轮所有 candidate_events"。auto-evolution 复用同一 runner，自动受益，无需改编排。
- **Web**:`handleToggleVariableLock` 改为调用上述 PATCH 并乐观更新、失败回滚；会话装载时用 GET 水合 `variables`（替换现在的空数组初值）;banner 的"锁定变量"改读持久化后的 locked 集合。

**验收**：注入并锁定一个变量 → 推进一步 → director 的私有 trace / llm_activity 可见 prompt 含该变量；产出候选与变量语义一致；刷新页面 locked 状态仍在。

### 闭环 2：采纳有权重（Python，必要时 Go）

- **Python**:`load_session_context` 的 recent_events 查询改为在结果里区分 `canon` 与 `candidate`（保留各最近若干条），并在 user payload 中分列 `confirmed_canon` 与 `pending_candidates`;system prompt 明确"`confirmed_canon` 是已确认正史，续写须与其一致；`pending_candidates` 是未采纳草案，仅供参考、不得当作已发生"。不改 candidate 只产候选、采纳才进正史的安全契约。
- **Go**：无需改写入；仅当评审要求 canon/candidate 分限额时才动 `load_session_context` 的 SQL（Python 侧自包含即可）。

**验收**：同一 session 下，canon 事件在 prompt 中与 candidate 分开展示；canon 变化（新采纳）会改变下一步产出方向；candidate 不被当作既定事实引用。

### 闭环 3：步号口径统一（Go 读侧 + Web）

- **语义定锚**：以"领域步"= `MAX(worldline_events.step)`（本会话已产出事件的最新推演步）为唯一对外"第 X 步"。编排 `workflow_events.sequence` 仅作内部序号，不再暴露为"步"。
- **Go**：在 `worldline_sessions` 读侧（`SessionRecord` 或 session detail）补 `current_step`（`SELECT COALESCE(MAX(step),0) FROM worldline_events WHERE …`），或在 timeline 读侧附 `max_step`；二选一，以改动最小且前端一次可取为准，实施时定。
- **Web**:`WorldlineStateBanner` 的 `currentStep` 与 `timelineEventsToWorldlineEvents` 的 step 口径统一改用领域步；折叠条的"第 1 – N 步"、卡片"第 N 步"与 banner 对齐。

**验收**:banner"第 X 步"恒等于时间线最大领域步；采纳事件不再把 banner 步号无推演地推高；折叠范围与卡片步号一致。

## 影响面与回归约束

- 触及 `09-worldline.md` 与 P5-005-B（Knowledge/Simulation，当前 `verified_current`）——按"证据冻结与重开规则"，因新改动触及生产代码而重开该域，完成后需重新取 browser/live 证据。
- 不破坏 `worldline_director` module binding、quota、candidate-only 安全契约。
- 变量 PATCH/GET 走中央安全壳（auth/RBAC/CSRF/RLS），owner-aware 路由沿用既有 `authorizeWorldlineSessionProjectRead`/写授权。
- Python loader 改动需保持 `WORLDLINE_SOURCE_*` 错误码与 fail-closed 语义；locked 变量缺失时为空数组而非报错。

## 测试计划

- **Go**:`worldline_test.go` 增 `SetVariableLocked` 单测（UPDATE/RETURNING/幂等）;`server_test.go` 增 PATCH/GET variables 路由与鉴权用例、current_step 读侧用例。
- **Python**:`test_worldline_workflow.py` 增 `load_session_context` 含 locked_variables 的用例与 canon/candidate 分列用例（fake scope store / dict_row)；确认 system/user prompt 装配断言。
- **Web**:`worldline-goal-start.test.mjs` 或新 `worldline-loop.test.mjs` 增契约测试：lock 走 PATCH、变量经 GET 水合、banner 步号用领域步、BFF 放行 PATCH/GET variables。
- **端到端（live + browser）**：在运行中 compose 注入并锁定变量 → 推进 → 验证候选体现变量；采纳一条 → 再推进 → 验证 prompt 区分 canon/candidate；核对 banner 步号与卡片一致。live 证据写入本文"实施记录"。

## 迁移与回滚

- 迁移 `0028_worldline_variable_lock_and_canon.sql` 仅加部分索引（幂等 `IF NOT EXISTS`)，可 `DROP INDEX` 回滚；无数据改写。
- Go 新增路由为纯增量，回滚即撤路由；Python loader 回滚即恢复旧 context；均为向后兼容的增量，无破坏性 schema 变更。

## 实施顺序（依赖）

1. **迁移 + Go 变量 PATCH/GET + current_step 读侧**（闭环 1 的 Go 半边 + 闭环 3 的数据源）。
2. **Python loader + prompt**（闭环 1、闭环 2 的核心）——可在 1 之后并行于 3。
3. **Web 接线**（lock 回写、变量水合、banner 步号）。
4. focused tests → live/browser 证据 → 更新本文与 24 进度。

## 开放决策（实施前确认）

- **D1 current_step 暴露位置**：挂在 `SessionRecord.current_step`（前端已取 session，零额外请求）还是 timeline 响应附 `max_step`？倾向前者。
- **D2 locked 变量上限**:prompt 注入取 `LIMIT 24` 是否合适；是否需要 impact_axis 进 prompt（倾向带，帮助 LLM 理解约束方向）。
- **D3 canon/candidate 条数配比**:recent 12 条是改为 `canon 最近 8 + candidate 最近 4` 还是统一按时间混排但打标？倾向分列+各限额，避免 candidate 挤掉正史。
- **D4 变量是否需要"解锁即失效"语义**：当前设计 locked=false 即不进 prompt，描述/历史仍保留；确认无需额外的"已生效/已消耗"状态机（本轮不做）。

## 实施记录（2026-07-26）

### 开放决策落地

- **D1** → `SessionRecord.current_step`：session 读侧 SQL 补 `COALESCE((SELECT MAX(step) FROM worldline_events …), 0)`，前端零额外请求。
- **D2** → `LIMIT 24`，`{name, description, impact_axis}` 进 prompt（impact_axis 帮助 LLM 理解约束方向）。
- **D3** → 分列+各限额：`confirmed_canon` 最近 8 条 + `pending_candidates` 最近 4 条，替换原混排 `recent_events LIMIT 12`。
- **D4** → 不做状态机：locked=false 即不进 prompt，描述保留。

### 落地清单

- **DB**：迁移 `0028_worldline_variable_lock_and_canon.sql`（部分索引 `idx_worldline_variables_session_locked (tenant_id, project_id, session_id) WHERE locked = true`）+ 回滚脚本 + bootstrap sentinel；compose schema-init 已应用，ledger 记录 `0028`。
- **Go**：`VariableStore` 接口扩 `SetVariableLocked`（UPDATE…RETURNING，幂等，tenant/actor context）与 `ListVariables`（tenant context）；`SessionRecord.current_step`；`PATCH /v1/worldline-sessions/{id}/variables/{vid}`（creative-write 授权）与 `GET …/variables`（project-read 授权）进中央路由与 actorSensitiveRoutes。
- **Python**：`PostgresWorldlineSourceLoader.load_session_context` 增查 locked 变量与 canon/candidate 分列；`_worldline_step_messages` system prompt 明确 locked_variables 硬约束、confirmed_canon 一致续写、pending_candidates 仅供参考。
- **Web**：`setWorldlineVariableLocked` / `fetchWorldlineVariables` 客户端；BFF 放行嵌套变量 PATCH（variableId 重新编码）；workspace 变量水合、lock 乐观更新+失败回滚；banner `currentStep = session.current_step`；timeline 映射的领域 step 取被采纳正史事件 step；编排标记显示"整备"不再冒号步号；折叠范围 `stepRangeLabel` 口径统一。

### 测试

- Go：`TestSQLVariableStoreSetVariableLockedUpdatesAndReturnsCurrentRow`（UPDATE/RETURNING/幂等）、`…NotFoundForUnknownVariable`、`TestSQLVariableStoreListsSessionVariablesInCreationOrder`、disabled fail-closed；`TestSQLSessionStoreListsAndGetsTenantScopedPublicSessions` 覆盖 current_step 子查询；server_test 增 5 例（PATCH 上下文/鉴权、畸形路径 404、fail-closed；GET 鉴权/列表、fail-closed）。
- Python：`test_postgres_worldline_session_context_splits_canon_candidates_and_locked_variables`、空集语义、`_worldline_step_messages` prompt 装配断言。
- Web：`tests/worldline-loop.test.mjs` 6 例（PATCH 回写/回滚、GET 水合、BFF 放行、banner 领域步、卡片步号、inspector 步号）。
- 回归：Go `go test ./...` 全 ok；Python `451 passed, 11 skipped`；Web `72 passed` + typecheck + production build。

### live 证据（compose，2026-07-26）

- 会话 `ff92a593`（项目"如果许七安辞官游历"）：`GET …/worldline-sessions/{id}` 返回 `"current_step": 2`（领域步）。
- 注入并锁定变量"许新年病重"（`impact_axis: kinship_pressure`）→ 推进一步（run `e8bfb9d2`）：产出 3 条 step-3 候选全部围绕病重/探病（"许七安闻讯赶回探病"/"王捕头探望病重许新年"/"许新年病中反思"），`llm.provider.response` trace 与候选落库一致；locked 变量从死数据变为推演硬约束。
- PATCH 幂等：locked true→false→true→true 均 200 返回当前行；GET variables 列表水合正确。
- 采纳"许七安闻讯赶回探病"进正史后：session `current_step` 恒为 3（采纳不再把 banner 步号无推演推高）；loader 复跑显示 `confirmed_canon` 6 条含新采纳、"pending_candidates" 4 条，canon/candidate 在 prompt 中分列。
- browser（web-preview 3101 + 真实登录）：banner 显示"第 3 步·已暂停·🔒 1"；折叠条范围"第 1 – 1 步"；编排标记显示"整备"不冒号步号；变量卡点击解锁→banner 🔒 消失、再点锁定→恢复；刷新后 🔒 状态仍在（持久化水合）。截图见本机预览会话。

### 影响面

- 按"证据冻结与重开规则"，本轮触及 P5-005-B 生产代码，该域重开后以上述 live/browser 证据重新闭合；`worldline_director` binding、quota、candidate-only 安全契约未变。
- 附带修正：timeline 折叠条两处"第 X – Y 步"旧口径文案统一收敛到 `stepRangeLabel`（编排标记 step=0 不再显示为"第 0 步"）。
