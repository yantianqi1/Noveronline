# 世界线剧情时间线 → 写作台召回(实现方案)

> 状态:**已修复并验证** / 2026-07-31（上线前审查发现项；验证命令见 §9）
> 目标:在写作台用 `@` 提及一条世界线,把**整场推演的正史事件**(按 step 有序)作为「剧情时间线」注入写作上下文,让合著者**顺着这条时间线**把事件丰富成后续小说剧情。

## 0. 需求与已确认的取舍

- **召回粒度:整场推演的正史** —— `@` 一个世界线会话,取该 session 全部 `status='canon'` 的 `worldline_events`,按 `step ASC` 排序作为时间线。
- **注入地位:参考但强引导** —— 事件仍以 `reference_only` 身份注入(不破坏「世界线不污染正典」的安全闸门),但在提示层明确标注「按此时间线顺序展开剧情」,强引导模型遵循。

## 1. 现状(事实锚点)

| 层 | 事实 | 位置 |
|---|---|---|
| 正史事件已持久化、有序 | `worldline_events` 有 `step / title / summary / kind / status`,正史 = `status='canon'`、`lifecycle='canon_reference'` | `infra/postgres/migrations/0001_core_saas.sql:979` |
| 已有按 step 排序的正史读 | `SQLEventReader.ListEvents`,`Status="canon"` 时 `ORDER BY e.step ASC` | `apps/api/internal/worldline/worldline.go:1948` |
| 已有 HTTP 读端点 | `GET /v1/worldline-sessions/{id}/events?status=canon` → `ListEvents` | `apps/api/internal/httpapi/server.go:5304` |
| BFF 已放行该读 | catch-all 代理已含 `worldline-sessions/{id}/events` | `apps/web/app/api/projects/[projectId]/[...path]/route.ts:222` |
| 前端已有取事件客户端 | `fetchWorldlineEvents(projectId, sessionId, ...)` | `apps/web/lib/api/worldline-client.ts:196` |
| writer 契约已带世界线字段 | `WriterRunInput.worldline_path_ids: string[]`,工具权限已挂 `query_worldline_paths` | `apps/pi-agent-runtime/src/contracts/writer-run.ts:15,75` |
| 世界线召回工具存在但浅 | `query_worldline_paths` 只查 `worldline_saved_paths` 的 title/summary,**不展开 `selected_event_ids_jsonb`** | `apps/pi-agent-runtime/src/runtime/postgres-pi-writer-deps.ts:529` |
| 无任何代码展开事件 | `selected_event_ids_jsonb` 全仓只在 Go 读写,从不 join `worldline_events` | (勘察确认) |
| 召回通道无 worldline | `RETRIEVAL_QUERY_CHANNELS = {keyed, hybrid, graph, manuscript}` | `apps/pi-agent-runtime/src/runtime/pi-writer-agent.ts:225` |
| 世界线工具由 LLM 决定是否调 | 非 run 启动自动注入;planner 也不产生 worldline 通道 | `apps/pi-agent-runtime/src/activities/pi-writer-activities.ts:1228` |
| 写作台无 `@` 提及 | composer 是纯 `<textarea>`,onSend 只传字符串 | `apps/web/app/projects/[projectId]/writer/writer-composer.tsx:40` |
| run 启动不带世界线 | `startWriterRun` body 仅 `{mode, instruction, chapter_id?, scene_id?}` | `apps/web/lib/api/writer-client.ts:408`、`writer-workspace.tsx:508` |
| 可复用的下拉模板 | `role="listbox"` 章节选择器(视觉/ARIA 模板) | `apps/web/app/projects/[projectId]/writer/writer-canvas-top.tsx:187` |

## 2. 总体设计

```
写作台 composer ──@选择世界线路径──▶ path_id + session_id
        │
        ▼ startWriterRun 携带 worldline_path_ids + worldline_session_ids
Go writer-runs 入口 ──透传──▶ WriterRunInput (pi runtime)
        │
        ▼ run 启动时「确定性预取」(不靠 LLM 临时决定)
   对每条 session: ListEvents(status='canon') → 按 step 排序
        │
        ▼ 注入为「剧情时间线」参考块(canon_status=reference_only + 强引导提示)
        ▼ 同时 query_worldline_paths 工具升级为可展开事件(供模型中途深查)
   合著者顺着时间线起草剧情
```

**核心决策:run 启动时做「确定性正史预取」,而不是只把工具挂给 LLM 让它自己调。**
理由:你要的是「顺着这条时间线写」——时间线必须**必然**出现在上下文里,而不是赌 orchestrator 会不会调 `query_worldline_paths`。工具升级(§3.3)只是补充,让模型写作中途能再深查某条路径的细节。

## 3. 改动清单(按依赖序)

### 3.1 契约:writer-run 增加世界线会话载体 — pi-agent-runtime

- `apps/pi-agent-runtime/src/contracts/writer-run.ts`
  - `WriterRunInput` 增加 `worldline_session_ids: string[]`(整场正史的会话来源)。
  - `runtimeContextFromInput` 无需改(`query_worldline_paths` 权限已在)。
- `apps/pi-agent-runtime/src/worker-spec.ts:66` 附近:解析 `worldline_session_ids`(沿用 `stringArray(...)` 模式)。

### 3.2 召回端:确定性正史时间线预取 — pi-agent-runtime

新增一个 activity / 依赖方法 `fetchWorldlineTimeline`,在 run 启动编排阶段对每个 `worldline_session_ids` 执行:

- `apps/pi-agent-runtime/src/runtime/postgres-pi-writer-deps.ts`
  - 新增 case / 依赖方法,SQL 直接复刻 `ListEvents` 的投影,限定 `status='canon'`、`session_id = ANY($n)`,`ORDER BY e.step ASC, e.created_at ASC`:
    ```sql
    SELECT e.event_id::text, e.session_id::text, e.step, e.title, e.summary, e.kind,
           COALESCE(e.state_changes_jsonb,'{}'::jsonb) AS state_changes
      FROM worldline_events e
     WHERE e.tenant_id=$1 AND e.project_id=$2
       AND e.session_id = ANY($3::uuid[])
       AND e.status='canon'
     ORDER BY e.session_id, e.step ASC, e.created_at ASC
    ```
  - 走 `queryWithTenantContext`(RLS 已强制租户隔离,见 migration:1815)。
  - 返回标注 `canon_status: "reference_only"`。
- `apps/pi-agent-runtime/src/activities/pi-writer-activities.ts`
  - 在编排写作简报前(orchestrateWritingBrief,~1243 前)调用上述预取,把结果作为 **`worldline_timeline` 块**注入 brief,而不是塞进 RRF 融合通道(时间线是「结构」,不是「相关度候选」,不该被 rerank 打乱 step 顺序)。

### 3.3 工具升级:`query_worldline_paths` 展开事件 — pi-agent-runtime

- `postgres-pi-writer-deps.ts:529` 的 case 升级为:
  1. 仍读 `worldline_saved_paths`(title/summary/writer_instruction);
  2. **追加**按 `selected_event_ids_jsonb` 数组顺序 join `worldline_events`,展开每条事件的 `step/title/summary`,保持作者保存路径时的人工排序;
  3. 返回仍标 `canon_status: "reference_only"`。
- 同步把 `pi-writer-activities.ts:1641` 的 `pickFields` allowlist 补上展开后的事件字段(现在列了 `selected_event_ids` 但 SQL 没返回,会被静默丢弃)。

### 3.4 提示层:强引导 — pi-agent-runtime

- `apps/pi-agent-runtime/src/runtime/pi-writer-agent.ts`
  - 在编排系统提示 / brief 注入处,对 `worldline_timeline` 块加明确指令:
    > 「以下是世界线推演的正史事件,按发生顺序(step)排列。它们是**参考而非不可变正典**,但你应当**顺着这个时间线的顺序**,把每个事件铺陈、丰富成连贯的后续剧情;不要打乱事件先后,除非作者在本次指令中明确要求改动。」
  - 不改动 `RETRIEVAL_QUERY_CHANNELS`(时间线走预取,不作为检索通道)。

### 3.5 Go 入口:writer-runs 透传世界线字段 — apps/api

- writer-runs 创建处理器(catch-all 代理 `route.ts:94` 的 `POST /^writer-runs$/` 上行到 `/v1/projects/{id}/writer-runs`):
  - 请求体增加可选 `worldline_path_ids`、`worldline_session_ids`,校验为 UUID 数组;
  - 透传进 Temporal writer 工作流输入(最终落到 `WriterRunInput`)。
  - **安全校验**:确认传入的 `session_id` 属于该 `tenant_id + project_id`(可复用 `worldline_sessions` 的存在性检查模式),防止跨项目引用。

### 3.6 前端:composer `@` 提及 — apps/web

这是全新交互,分三块:

1. **会话级状态**:`writer-workspace.tsx` 增加 `attachedWorldline: { session_id, path_id?, title } | null`,随 `handleSend`(508)并入 `startWriterRun` 入参。
2. **`@` 触发 + 下拉**:`writer-composer.tsx`
   - 监听输入,光标处出现 `@` 时进入提及模式,后续字符作为过滤词;
   - 用 `writer-canvas-top.tsx:187` 的 `role="listbox"` 下拉做模板,列出可选世界线(见 3.7 取数);
   - 选中后把 mention 渲染为文本内的只读 chip(或直接置为 attachedWorldline 并从文本清除),Esc/退格退出。
   - 键盘可达:↑↓ 移动、Enter 选中(注意不要与现有 Enter=发送冲突——提及模式下 Enter 优先选中)。
3. **客户端取数**:`writer-client.ts:408` 的 `startWriterRun` input 类型加 `worldline_session_ids?` / `worldline_path_ids?`。

### 3.7 前端:`@` 下拉的世界线来源 — apps/web + 读端点

`@` 下拉要列出「可顺写的世界线」。两个候选源:

- **A. 已保存路径** `GET /v1/.../worldline/saved-paths`(BFF `route.ts:69` 已放行,`SQLSavedPathReader.ListSavedPaths` 按 project 列,`worldline.go:868`):带 title/summary,适合作者认得出的命名路径。**推荐做主源。**
- **B. 世界线会话** `worldline-sessions`(已有列表端点):覆盖没显式保存路径的整场推演。

建议:下拉同时列出「保存的路径」(主)与「各推演会话」(次),选中任一并存其 `session_id`(路径记录自带 `session_id`);若选的是路径再附带 `path_id` 供 §3.3 精查。**无需新增 Go 读端点**,现有 `ListSavedPaths` 与 `ListEvents` 已够用。

## 4. 安全与一致性约束(必须守住)

- **不污染正典**:所有世界线事件注入一律 `reference_only`;`search_assets` 的 `SEARCH_ASSETS_LIFECYCLES = [seed, canon, material]`(`postgres-pi-writer-deps.ts:676`)**保持不变**,世界线事件不进资产检索池。
- **候选沙盘不外泄**:只取 `status='canon'`;`candidate`/`rejected` 事件永不进入写作上下文。
- **剧透闸门**:若未来正史事件要带 `reveal_after_chapter_order` 之类的章节门控,需在 §3.2 预取时套用与 `resolveCurrentChapterOrder` 相同的过滤;当前 `worldline_events` 无此列,**本期不做**,但留扩展位。
- **租户/项目隔离**:所有新 SQL 走 `queryWithTenantContext`(RLS),Go 入口校验 session 归属。

## 5. 测试

- **pi-agent-runtime**
  - `postgres-pi-writer-deps.test.ts`:正史预取只回 `canon`、按 step 排序、空 session 返回空且标 `reference_only`;`query_worldline_paths` 展开事件且保持 `selected_event_ids` 顺序。
  - 编排测试:注入 `worldline_session_ids` 时 brief 含 `worldline_timeline` 块;未注入时不出现。
  - `recall-fusion` 不受影响(时间线不进 RRF)。
- **apps/api**:writer-runs 入口对世界线字段的校验(非法 UUID、跨项目 session → 4xx)。
- **apps/web**:composer `@` 触发/选中/退出的交互测试;`handleSend` 携带世界线字段。
- 运行:`cd apps/pi-agent-runtime && npm test && npm run typecheck`;`cd apps/api && go test ./...`;`cd apps/web && npm test && npm run typecheck && npm run build`。

## 6. 分阶段交付

| 阶段 | 内容 | 价值 | 依赖 |
|---|---|---|---|
| **P1(最小可用)** | 3.1 + 3.2 + 3.4 + 3.5 | 不靠 UI,手动/程序传入 session_id 即可让写作**顺着正史时间线写** | 无 |
| **P2(工具深化)** | 3.3 | 模型写作中途可深查某条保存路径的事件细节 | P1 |
| **P3(@ 交互)** | 3.6 + 3.7 | 写作台 `@` 提及世界线,完整闭环 | P1 |

> 建议先做 P1:它独立可用、立刻兑现「顺着时间线创作」,且为 P2/P3 提供数据通道。P3 的 `@` 是交互增强,不改召回语义。

## 7. 待你拍板的开放点

1. `@` 下拉是否同时列「保存路径」和「原始会话」(§3.7 推荐两者都列)?
2. 是否允许一次 `@` 多条世界线(多 session 合并成一条时间线,按 step 全局排序),还是限一条?(方案默认支持多条,但 UI 可先限单条。)
3. 正史事件是否需要按章节做剧透门控(§4 扩展位),还是相信作者自己选了这条线就该全看见?

## 8. 上线前缺陷修复设计（2026-07-31）

本节是本轮上线前审查的修复真相源。修复范围只覆盖当前 worktree 已确认的问题；不恢复旧多分支 worldline 语义，不引入 mock 成功路径。

### 8.1 缺陷与设计决策

| ID | 缺陷 | 修复设计 | 验收条件 |
|---|---|---|---|
| AUDIT-WL-001 | 时间线 SQL 的 `LIMIT 60` 是跨 session 全局硬截断，长时间线或第二个 session 会无提示丢事件 | 移除隐式全局截断；按查询结果完整构造每个 session 的 canon 时间线。若未来必须做上下文预算，必须在契约中显式返回 `truncated`/分页状态并由产品层展示 | 61+ 个 canon 事件全部进入时间线；多 session 不互相消耗额度；无未声明 `LIMIT` |
| AUDIT-WL-002 | Go writer-run 入口只 trim 世界线 ID；路径 ID 不做 UUID/归属校验，失效路径可静默空读 | 在 admission 边界统一校验两个数组中的每个 ID 为 UUID、去重并保留首次顺序；session 继续确认 tenant+project 归属；path 通过 DB-backed saved-path reader 确认 tenant+project 归属，任何无效/失效引用在启动前返回稳定 4xx | 非法 UUID、重复 ID、跨项目 session/path、已删除 path 均不调用 WriterStarter；稳定 `VALIDATION_FAILED`/`FORBIDDEN` |
| AUDIT-WL-003 | timeline 预取和 prompt 丢失 `state_changes`，Writer 看不到世界/角色状态变化 | runtime timeline 类型增加公开 `state_changes`；SQL 与 path deep-read 仅投影该公开字段；orchestrator/composer prompt 显式传递并保持 reference-only，不读取私有正文/trace | canon event 的 state changes 在 orchestrator 与 composer prompt 中可见；candidate/rejected 仍不可见 |
| AUDIT-WEB-004 | writer start 失败后保留未持久化的 optimistic user turn | API 失败时从 turns 和 live-turn 集合回滚该 turn，保留顶部稳定错误；成功路径保持单次持久化 | 429、未绑定模块、非法世界线引用后不出现幽灵消息；重试不产生重复气泡 |
| AUDIT-WEB-005 | worldline picker 将读错误吞成空数组，并对每个 session 发一个事件请求 | 增加明确的 worldline load state；任一真实读取失败显示错误而非空成功；使用可复用批量 canon-count 读端点或至少有显式、可解释的请求预算 | 后端 5xx/未配置时作者能看到错误；正常数据不产生无界 N+1 请求 |
| AUDIT-OPS-006 | live shelf 验收脚本硬编码测试账号密码 | 改为必填环境变量，缺失时立即失败；不在脚本、日志或 git 中打印密码 | 脚本无内置凭据；环境变量缺失不会尝试登录 |

### 8.2 实施顺序

1. 先修复 Pi SQL/类型/prompt 与 API admission，补边界测试，保证世界线数据契约完整且 fail-closed。
2. 再修复 Web optimistic state、picker 错误状态和 live 验收脚本，补失败路径测试。
3. 运行 Go、Pi、Web、shared-contracts 受影响测试，再运行 SaaS 全量回归；Web 页面验收仍必须使用真实 Go API/BFF。
4. 更新本节状态、当前进度和活动任务板；审查 `git diff --check`、敏感信息扫描和最终 diff 后提交。

### 8.3 不变约束

- 不把候选事件、rejected 事件或私有 prompt/response/body/credential 注入 Writer。
- 不用 `catch(() => [])` 把真实后端故障伪装为空业务数据。
- 不添加未经契约声明的硬截断、静默 fallback 或跨租户/跨项目读取。
- 所有 live/E2E 写操作继续通过 `infra/scripts/run-live-test-stack.sh` 的隔离栈执行。

## 9. 修复结果与验证（2026-07-31）

- `AUDIT-WL-001`：Pi timeline 查询移除全局 `LIMIT 60`；新增 61×2 session 边界测试。
- `AUDIT-WL-002`：Go admission 完成 UUID 规范化、去重、tenant/project 归属校验；失效引用在 LLM resolver 与 WriterStarter 之前失败；后端未配置错误保持 503。
- `AUDIT-WL-003`：timeline 与 saved-path deep-read 投影 `state_changes`，经公开 payload 清洗后同时进入 orchestrator/composer prompt；candidate/rejected 仍不进入结果。
- `AUDIT-WEB-004`：start-run 失败时回滚本地 optimistic user turn 与 live-turn 集合。
- `AUDIT-WEB-005`：会话列表一次返回 `canon_event_count`，移除逐 session 事件请求；任一列表读取失败在 composer 显示可见错误。
- `AUDIT-OPS-006`：书架真实验收脚本改用必填 `MIROFISH_ACCEPTANCE_EMAIL` / `MIROFISH_ACCEPTANCE_PASSWORD`。

受影响验证：`apps/api/go test ./...`、`apps/pi-agent-runtime/npm test`（138 passed, 4 skipped）及 typecheck/build、`apps/web/npm test`（121 passed, 1 skipped）及 typecheck/build、`git diff --check` 均通过。
