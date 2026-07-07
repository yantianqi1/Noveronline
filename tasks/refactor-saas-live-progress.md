# MiroFish-Novel SaaS Refactor Live Progress

更新时间：`2026-07-07`

## 用途

本文是 SaaS 重构的实时任务进度记录。它不替代 `docs/refactor-saas/DEVELOPMENT_PLAN.md`、`docs/refactor-saas/22-midstream-handoff-summary.md` 或 `tasks/refactor-saas-parallel-board.md`：

- `DEVELOPMENT_PLAN.md` 是总纲和阶段顺序。
- `refactor-saas-parallel-board.md` 是任务分派和状态看板。
- 本文记录当前读数、每轮工作流水、验证结果和下一步。

后续每个开发切片开始、完成、阻塞或验证后，都必须更新本文对应条目。不得把 skeleton、fail-closed shell 或 metadata-only path 写成完整产品能力。

## 工作区基线

| 项 | 当前值 |
|---|---|
| 主仓库 | `/Users/yantianqi/Documents/Noveronline` |
| SaaS worktree | `/Users/yantianqi/Documents/Noveronline-saas-mainline` |
| 当前分支 | `codex/saas-mainline` |
| git dir | `/Users/yantianqi/Documents/Noveronline/.git/worktrees/Noveronline-saas-mainline` |
| common dir | `/Users/yantianqi/Documents/Noveronline/.git` |
| 开发边界 | 只在 SaaS worktree 开发，不覆盖主仓库未提交改动 |

## 实时更新规则

每轮开发按下面节奏更新：

1. 开始前：更新 `当前焦点`，写明目标 slice、约束和预期验证。
2. RED 后：在 `工作日志` 追加失败测试、失败原因和命令。
3. GREEN 后：追加实现摘要、聚焦验证命令和结果。
4. 广泛验证后：追加 broader verification 结果，包括失败或未运行原因。
5. 文档同步后：追加同步过的 docs/tasks 文件。
6. 结束前：更新 `下一步` 和 `开放风险`。

状态用词：

| 状态 | 含义 |
|---|---|
| verified | 已有实现并完成对应验收 |
| implemented | 已实现主要代码路径，但仍缺 live/E2E 或更广验收 |
| in_progress | 正在推进，存在明确 pending 子项 |
| blocked | 依赖缺失或必须等另一 slice |
| planned | 还未实质开工；必须在对应任务或矩阵行标注 owner/wave |

## 当前总览

按产品真实闭环估算，当前 SaaS 重构约完成 `55%-60%`。看板会显得更乐观，因为许多条目已经有 schema、API、read side、fail-closed worker shell 或 metadata-only 用户动作，但还不等价于完整产品。

| Phase | 产品闭环判断 | 当前状态 |
|---|---:|---|
| Phase 0 | 100% | 文档、覆盖矩阵和隔离 worktree 基线已 verified |
| Phase 1 | 80%-90% | Writer-first contract、Pi Runtime skeleton、缺绑定显式失败、draft 保存和显式 adoption 已落地；真实 LLM-bound E2E 待验收 |
| Phase 2 | 70%-80% | Writer read tools 已接入 assets、graph、worldline paths；picker/right rail 已有实现；live LLM reference E2E 和 proposal tools 待补 |
| Phase 3 | 70%-80% | Go API、Next shell、Postgres/RLS、Temporal/Python/Pi worker skeleton 已落地；W2-S1 `/v1/me` auth reader seam 和 W2-S2 DB-backed auth membership read side 已接入；完整 compose health、真实 Temporal handoff、project picker/RBAC enforcement 待补 |
| Phase 4 | 75%-85% | LLM Facility schema/API/UI、binding、channel CRUD、model sync、trace/usage、secure key handoff、concurrency lease 已大体完成；live provider/cluster E2E、retry backend、quota/billing 待补 |
| Phase 5 | 50%-65% | Seed/Assets/Graph 有大量 DB-backed skeleton 和部分真实持久化；可提取文本 PDF parse、Python source parse-status 完成/失败回写、opt-in Go API upload/complete -> Temporal cluster -> Python parse/segment live harness、MinIO/Postgres object/row/event readback、真实 Temporal worker event-writer handoff、Seed running/terminal run status handoff（含 parse/segment 早期失败）、`story_ontology` / `entity_resolution` / `graph_bond_generator` LLM Facility runner path，以及 Asset search 版本/collection metadata 已补；browser upload/complete、扫描/OCR PDF、完整智能分段、agent profile/finalize runner、vector/hybrid search、Seed live provider E2E 和 Graph candidate adoption 待补 |
| Phase 6 | 35%-45% | Worldline metadata side、step admission、最小 LLM-backed candidate event metadata producer 已推进；Character Console metadata skeleton 已落地并硬化；runtime、saved-path runtime producer、prepare runtime、richer director tools 待补 |
| Phase 7 | 0%-10% | Legacy import report skeleton blocked，旧架构清理未开始 |
| Phase 8 | 0%-10% | Ops/Billing/Security/Production hardening 仍主要停留在设计和少量底座 |

## 当前焦点

| 项 | 内容 |
|---|---|
| 当前主线 | Wave 2：SaaS Auth / Tenant / Project / RBAC |
| 最近完成重点 | Wave 0 governance calibration、W1-S1 explicit draft adoption、W1-S2 writer reviewer admission/read metadata、W1-S3 manuscript metadata/export manifest、W1-S4 Writer UI manuscript metadata panels、W1-S5 Writer replay cursor / raw payload UI hardening、W1-S6 Pi compose live/local provider opt-in smoke harness、W1-S7 Writer browser verification evidence documentation、W2-S1 `/v1/me` auth reader seam、W2-S2 DB-backed auth membership read side 均已通过对应验收记录 |
| 当前未完成重点 | Wave 1 真实 LLM-bound E2E 执行需 resolved provider env；真正内容导出 artifact service；Wave 2 tenant/project picker、RBAC enforcement、session/cookie/JWT transport |
| 本轮开发 slice | W2-S2 DB-backed auth membership read side：`/v1/me` 在 `DATABASE_URL` 配置时读取真实 active user/tenant/project membership summaries |
| 推荐下一步 | W2-S3 实现 Next tenant/project picker 消费 `/v1/me`，或 W2-S4 接入 RBAC enforcement；也可提供 resolved live/local provider handoff env 后回补 W1-S6 live smoke；当前 W2-S2 不声明完整 Auth/RBAC 或 project picker 完成 |

## Wave 2 W2-S2 DB-backed auth membership read side

Context:

- W2-S1 已新增 `/v1/me` fail-closed auth reader seam。
- 本 slice 将 cmd/api `DATABASE_URL` path 接到真实 SQL reader，让 current-user API 可读取既有 SaaS core tables 的 public membership summary。
- Scope 限定在 `apps/api/internal/auth/**` 与 `apps/api/cmd/api/**`；不改前端、不改 schema、不替换现有业务路由的 `X-Tenant-Id` 兼容路径、不实现完整 RBAC enforcement。

TDD / Review:

- Implementer subagent Turing 先跑 RED：`cd apps/api && go test ./internal/auth -count=1`，失败为 `undefined: SQLRows`、`undefined: NewSQLReader`、`undefined: SQLReaderConfig`。
- `auth.SQLReader` 新增 `SQLQueryer` / `SQLRows` / `SQLDBQueryer`，并实现 `Reader.GetCurrentUser`。
- SQL reader 读取 active `users` public columns、active `tenant_memberships` joined active `tenants`，以及 active tenant membership 可访问的 active `projects`；项目角色优先使用 `project_members.role`，否则继承 tenant membership role。
- Auth lookup 不使用 `X-Tenant-Id`，这是 current-user membership discovery 的受控跨租户查询，不是普通 tenant-scoped business read bypass。
- Missing/inactive user 返回 `AUTH_USER_NOT_FOUND`；普通 query/scan/rows/close failure 统一为 `AUTH_LOOKUP_FAILED` / `auth lookup failed`，不透传 driver 文本。
- 测试检查 SQL 不选择高风险字段名：`api_key`、`encrypted`、`credential_ref`、`object_key`、`content_text`、`body`、`draft`、`manuscript`、`prompt`、`response`。
- `cmd/api` 新增 `newAuthReader(databaseURL)`：无 DB 时 disabled fail-closed，有 DB 时 `auth.SQLReader`，并传入 `httpapi.Config.AuthReader`。
- Spec reviewer Zeno APPROVED：确认 `DATABASE_URL` wiring、`/v1/me` 不用 `X-Tenant-Id`、public active summaries、role fallback 和 sanitized auth errors。
- Quality reviewer Ohm APPROVED：确认 scope 窄、disabled reader 仍 fail closed、跨 tenant lookup 仅用于 current-user membership discovery、无生产 fake success。

Verification:

- `cd apps/api && go test ./internal/auth -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Auth|CurrentUser|Me' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -count=1` 通过。
- Coordinator broader：`cd apps/api && go test ./internal/httpapi -run 'Auth|CurrentUser|Me|Writer|Draft|Trace|LLM|Workflow' -count=1` 通过。
- Coordinator broader：`cd apps/api && go test ./internal/httpapi -count=1` 通过。
- `gofmt -l`、`git diff --check` 和触达 Go 文件尾随空白扫描通过。

Docs synced:

- `tasks/refactor-saas-live-progress.md`
- `tasks/refactor-saas-parallel-board.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/14-data-model.md`

Next:

- W2-S3：Next tenant/project picker 消费 `/v1/me` active membership summary，并逐步减少开发期硬编码 tenant/project route assumptions。
- W2-S4：RBAC enforcement，把 viewer/editor/admin/writer/analyst 权限接入关键 mutation/read gates；当前 W2-S2 只提供 membership read side。

## Wave 2 W2-S1 `/v1/me` auth reader seam

Context:

- Wave 1 browser verification 已记录；本机未配置 `MIROFISH_PI_WRITER_LIVE_RESOLVED_*`，因此不能诚实执行真实 provider E2E。
- Wave 2 入口先补最小 Auth API seam，让后续 DB-backed membership、tenant/project picker 和 RBAC enforcement 有可测试边界。
- Scope 限定在 `apps/api/internal/auth/**` 与 `apps/api/internal/httpapi/**`；不改前端、不改 schema、不替换现有业务路由的 `X-Tenant-Id` 兼容路径。

TDD / Review:

- Implementer subagent Rawls 先跑 RED：`cd apps/api && go test ./internal/httpapi -run 'Auth|CurrentUser|Me' -count=1`，失败原因是 `mirofish-novel/apps/api/internal/auth` 尚不存在。
- Rawls 新增 `auth.Reader`、public current-user/membership summary types、`DisabledReader`、`AppError` / `ErrorCode`，并把 `AuthReader` 注入 `httpapi.Config` / `Server`。
- `GET /v1/me` 只要求 trimmed `X-User-Id`，缺失时返回 `UNAUTHENTICATED` 且不调用 reader；不要求 `X-Tenant-Id`，也不从 header 伪造 tenant/project membership。
- 默认无 reader 时 fail closed 为 `AUTH_BACKEND_UNCONFIGURED` / HTTP 503；reader error 在 HTTP boundary 映射为稳定 public message，不回显 reader message 中的 prompt/body/content、API key、encrypted credential、`credential_ref`、object key、draft 或 manuscript。
- Spec reviewer Kant APPROVED：确认 exact `/v1/me` route、缺用户上下文先失败、不伪造 header-derived membership，并额外跑 `go test ./...`。
- Quality reviewer Gibbs APPROVED：确认 scope 窄、测试覆盖缺用户/disabled backend/injected reader/sanitized error、无生产 mock success，并确认 `go test ./... -count=1`、`git diff --check`、`gofmt -l` clean。

Verification:

- `cd apps/api && go test ./internal/auth ./internal/httpapi -run 'Auth|CurrentUser|Me' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Auth|CurrentUser|Me|Writer|Draft|Trace|LLM|Workflow' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -count=1` 通过。
- `cd apps/api && go test ./cmd/api -count=1` 通过。
- Reviewer 侧额外跑过 `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 和触达 Go 文件尾随空白扫描通过。

Docs synced:

- `tasks/refactor-saas-live-progress.md`
- `tasks/refactor-saas-parallel-board.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/14-data-model.md`

Next:

- W2-S2：DB-backed auth reader，读取 `users` / active `tenant_memberships` / active `projects` + project role summary，并在 app-role/RLS 或 service-role boundary 上保持稳定 public errors。
- W2-S3：Next tenant/project picker 消费 `/v1/me`，仍不在 UI 暴露 prompt/provider/raw/body/content/API key/credential/object key/draft/manuscript。
- W2-S4：RBAC enforcement，把 viewer/editor/admin/writer/analyst 权限接入关键 mutation/read gates。

## Wave 1 W1-S7 Writer browser verification evidence documentation

Context:

- Coordinator 已在 API `127.0.0.1:3888` 与 Next `127.0.0.1:3999` 下完成 Writer browser verification。
- 验证 URL：`/demo/projects/demo-project/writer?runId=run-browser-check&traceId=trace-browser-check&after_event_id=evt-browser-check`。
- 本 slice 仅记录证据并同步 board/coverage；不修改应用代码、不新增测试、不声明真实 provider E2E 或内容导出 artifact service 完成。

Browser evidence recorded:

- Desktop `1280x720`：页面 title 为 `MiroFish Novel`；可见 headings 包含 `Writer Workbench`、`Manuscript metadata`、`Export manifest`、`Recovered stream`、`Event stream`。
- Desktop fail-closed states：显式显示 `MANUSCRIPT_BACKEND_UNCONFIGURED`、`MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED`、`NOT_FOUND`、`AGENT_TRACE_BACKEND_UNCONFIGURED`。
- Desktop replay form：action 为 `/demo/projects/demo-project/writer`，method 为 `get`，并保留 `runId = run-browser-check`、`traceId = trace-browser-check`、`after_event_id = evt-browser-check`。
- Desktop no-leak scan：visible text 与 HTML 中均未出现 `api_key`、`encrypted_api_key`、`credential_ref`、`sk-`、`content_text`、`body_text`、`raw payload`、`JSON.stringify` 或 private draft/manuscript markers；无水平溢出。
- Mobile `390x844`：`Recovered stream` / replay button 可见，run/trace/cursor query metadata 保留；同一 forbidden-string scan 为空；无水平溢出。
- Browser console error logs：none。
- Browser session 已 reset/finalized after verification。

Docs synced:

- `tasks/refactor-saas-live-progress.md`
- `tasks/refactor-saas-parallel-board.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `docs/refactor-saas/11-writer-workbench.md`

Next:

- 继续推进真实 LLM-bound Writer E2E，需 resolved provider handoff env / live-local provider 执行证据。
- 真正 PDF/DOCX/TXT 或对象存储内容导出 artifact service 仍 pending；当前 export manifest 仍是 metadata-only / fail-closed browser evidence。

## Wave 1 W1-S6 Pi compose live/local provider opt-in smoke harness

Context:

- W1-S5 已提交 Writer replay UI / raw payload hardening。
- Wave 1 仍缺 live/local LLM-bound E2E 执行；本 slice 先补 tests-only opt-in smoke harness，让后续可用 resolved LLM Facility handoff env 真实调用 OpenAI-compatible provider。
- Scope 限定在 `apps/pi-agent-runtime/src/llm/**`；不改 production worker/env fallback、Go API、DB schema、Web UI 或 docs 之外的 runtime 行为。

TDD / Review:

- Implementer subagent Aristotle 新增 `apps/pi-agent-runtime/src/llm/pi-ai-compose.live.test.ts`，默认无 live env 时 skip，partial env 时 fail fast，完整 env 时调用 `createPiAIComposeDraft`。
- Coordinator 复跑 partial env RED：只设置 `MIROFISH_PI_WRITER_LIVE_RESOLVED_BASE_URL` 时测试失败并只列缺失 resolved handoff env names，不构造 provider request。
- Spec reviewer Ampere APPROVED：确认显式 resolved handoff env、无旧式 fallback、无 fake success、无 API key/prompt/raw response/generated content logging。
- Quality reviewer Dalton 初审要求不要信任 provider-controlled `error.name`；Coordinator 加入 malicious error-name regression，并将 provider failure type 限制为短 allowlisted identifier，否则回落 `Error`。Dalton re-review APPROVED。

Implementation:

- Required envs：`MIROFISH_PI_WRITER_LIVE_RESOLVED_BASE_URL`、`MIROFISH_PI_WRITER_LIVE_RESOLVED_API_KEY`、`MIROFISH_PI_WRITER_LIVE_RESOLVED_MODEL_ID`、`MIROFISH_PI_WRITER_LIVE_RESOLVED_CHANNEL_ID`。
- Optional envs：`MIROFISH_PI_WRITER_LIVE_MAX_TOKENS`、`MIROFISH_PI_WRITER_LIVE_TEMPERATURE`。
- Full live path builds a `ComposeDraftRequest` with `module_key = writer_composer`、`provider = openai-compatible`、explicit `apiKey` from the resolved handoff, and a short instruction; assertion only checks non-empty content and does not print the generated text.
- Provider failures are rethrown as stable redacted messages; API keys, prompt fragments, raw provider body, generated content, and provider-controlled error names are not echoed.

Verification so far:

- Default/no env: `cd apps/pi-agent-runtime && npm run test -- src/llm/pi-ai-compose.live.test.ts` 通过，live smoke skipped，39 passed / 1 skipped。
- Partial env RED: `cd apps/pi-agent-runtime && MIROFISH_PI_WRITER_LIVE_RESOLVED_BASE_URL=http://127.0.0.1:1 npm run test -- src/llm/pi-ai-compose.live.test.ts` 按预期失败于 missing resolved handoff env names。
- Combined Pi LLM tests: `cd apps/pi-agent-runtime && npm run test -- src/llm/pi-ai-compose.test.ts src/llm/pi-ai-compose.live.test.ts` 通过，38 passed / 1 skipped before sanitizer regression；后续 full acceptance 待跑。
- `cd apps/pi-agent-runtime && npm run typecheck` 通过。
- Wave 1 acceptance：`cd apps/api && go test ./internal/workflows ./internal/httpapi -run 'Writer|Draft|Trace|LLM|Workflow|Manuscript' -count=1` 通过。
- Wave 1 acceptance：`cd apps/pi-agent-runtime && npm run test && npm run typecheck` 通过，39 passed / 1 skipped。
- Focused live harness acceptance：`cd apps/pi-agent-runtime && npm run test -- src/llm/pi-ai-compose.test.ts src/llm/pi-ai-compose.live.test.ts` 通过，39 passed / 1 skipped。
- Wave 1 acceptance：`cd apps/web && npm run test -- --test-name-pattern='Writer|writer|replay|Recovered stream' && npm run typecheck` 通过，39 tests。
- `git diff --check` 通过。
- 当前未配置完整 live/local provider env，因此尚未执行真实 provider call；不能声明 live provider E2E completed。

## Wave 1 W1-S5 Writer replay cursor / raw payload UI hardening

Context:

- W1-S4 已提交并让 Writer page 加载 metadata-only manuscript/export manifest panels。
- Wave 1 剩余验收包含页面刷新后恢复 run/events/draft，以及 trace/replay browser verification；本 slice 先补 explicit replay cursor UI contract 和 public UI raw payload hardening。
- Scope 限定在 `apps/web` Writer page/shell/static tests；不改 Go API、Pi runtime、draft adoption、manuscript export 或 provider path。

TDD / Review:

- Implementer subagent Bohr 先补 `apps/web/tests/web-shell.test.mjs` RED/GREEN，证明 Writer shell 有 `after_event_id` replay cursor form，保留 run/trace query metadata，且 replay slice 不含 credential/body/draft/manuscript 字段。
- Spec reviewer Poincare 初审要求修正 Trace Events raw `JSON.stringify(event.payload)` 泄露风险，并要求在 run summary 失败时保留 query `runId` / `traceId`。Coordinator 将测试扩展到禁止 writer shell public render path 中的 raw event payload JSON，并新增 `selectedRunId` / `selectedTraceId` props。
- Quality reviewer Hooke 初审要求修正 trace 优先级：页面用 `selectedTraceId || runSummary.trace_id` 读取 trace events，shell/export/replay form 也必须同样 query trace 优先。Coordinator 先把测试改为 `selectedTraceId || traceId` RED，再修正 shell。
- Final reviewer Einstein 要求补强测试覆盖 `replayTraceId` assignment、display 和 export hidden field，Coordinator 补测后复跑通过；Einstein re-review APPROVED。

Implementation:

- `apps/web/app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx` 规范化 `after_event_id` / `afterEventId`，并将 query `runId` / `traceId` 作为 selected metadata 传入 shell。
- `apps/web/components/writer-workbench-shell.tsx` 在 Recovered stream 面板新增 GET replay cursor form，提交 `runId`、`traceId`、`after_event_id`；run summary 失败时仍保留 query metadata，trace 优先级与 page fetch 保持一致。
- Writer Events 和 Trace Events 不再渲染 arbitrary raw payload JSON，只显示 event type/order/id/time/redaction 与 payload metadata key count；typed tool result cards 继续使用 sanitized event payload 派生专用卡片。
- 不新增 fake success、adoption/export side effects、旧式 LLM env fallback 或 provider call。

Verification so far:

- RED: `cd apps/web && npm run test -- --test-name-pattern='Writer shell exposes recovered stream replay cursor'` 先失败于缺 selected run/trace props。
- GREEN: 同命令通过，39 passed。
- RED: quality 修正测试先失败于错误 `traceId || selectedTraceId` priority。
- GREEN: 同命令通过，39 passed。
- `cd apps/web && npm run test` 通过，39 passed。
- `cd apps/web && npm run typecheck` 通过。
- Wave 1 acceptance：`cd apps/api && go test ./internal/workflows ./internal/httpapi -run 'Writer|Draft|Trace|LLM|Workflow|Manuscript' -count=1` 通过。
- Wave 1 acceptance：`cd apps/pi-agent-runtime && npm run test && npm run typecheck` 通过，7 files / 38 tests。
- Wave 1 acceptance：`cd apps/web && npm run test -- --test-name-pattern='Writer|writer|replay|Recovered stream' && npm run typecheck` 通过，39 tests。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' 'apps/web/app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx' apps/web/components/writer-workbench-shell.tsx apps/web/tests/web-shell.test.mjs docs/refactor-saas/11-writer-workbench.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-live-progress.md tasks/refactor-saas-parallel-board.md` 无输出，目标文件尾随空白扫描通过。

## P6-002 Character Console 当前状态

已落地：

- `character_interaction_sessions` / `character_interaction_turns` metadata-only 表、RLS、索引、grants。
- Go `internal/characterconsole` DB-backed store/read side。
- HTTP endpoints：create/list/detail/append/list turns。
- `events` endpoint 作为 explicit pending/fail-closed contract；`chapter-drafts` endpoint 已推进为真实 Writer run admission，并要求至少一条 saved public turn summary。
- Next Character Console shell：metadata create、turn append、selected interaction replay、public turn replay、anchor/session/saved-path/graph-node/prepared-agent public metadata 选择器。
- SQL read side 和 HTTP response boundary 双层清洗 high-risk fields。
- query、scan、`rows.Err()`、rows close、transaction commit、coded error 和 JSON decode error 都稳定化，不公开 prompt/API key/credential/body/draft/manuscript。

仍 pending：

- 不生成 AI 回复。
- 不生成 runtime events。
- 不在 Character Console 内生成 chapter draft。
- 不写 Writer draft 或 manuscript；当前只 admission/queue 真实 Writer run。
- 不自动采用 worldline candidate 为 canon。

## 工作日志

### 2026-07-07 当前会话：Wave 1 W1-S1 explicit draft adoption

Context:

- Wave 0 governance calibration 已完成并单独提交。
- 根据 `tasks/refactor-saas-100-percent-subagent-development-plan.md`，Wave 1 从 Writer live closure 继续推进。
- 本 slice 聚焦 docs 已列出的 `POST /v1/drafts/{draftId}/adoptions`：candidate draft 只能通过显式作者动作进入 manuscript，不允许 Writer runtime 自动采用。

Scope:

- Implementer subagent 负责 Go API slice，写 scope 限定为 `apps/api/internal/workflows/`、`apps/api/internal/httpapi/` 和必要的 `apps/api/cmd/api/` DB wiring。
- Coordinator 不在同一代码 scope 并行编辑，避免冲突；只同步任务/文档和后续整体验证。
- 本 slice 不触碰 Pi runtime、Worldline、Web UI、migrations 或旧主仓库。

Planned TDD:

- RED：先补 workflows SQL draft adoption store 和 HTTP route tests，证明当前缺 `POST /v1/drafts/{draftId}/adoptions` / store。
- Implementation：新增 explicit adoption store、fail-closed disabled store、HTTP route，并在 DB 配置下接入 SQL store。
- GREEN：聚焦 `go test` 覆盖 writer adoption tests。
- Regression：跑相关 Writer/Workflow HTTP 和 cmd wiring tests，再由 spec reviewer 与 quality reviewer 审查。

RED:

- Implementer subagent 先运行 `cd apps/api && go test ./internal/workflows -run 'TestSQLDraftAdoptionStore' -count=1`，失败于缺 `NewSQLDraftAdoptionStore`、config 和 adoption types。
- Implementer subagent 先运行 `cd apps/api && go test ./internal/httpapi -run 'TestAdoptDraft' -count=1`，失败于缺 workflow adoption types 和 `DraftAdoptionStore` config field。

Implementation:

- 新增 `DraftAdoptionStore` / `DisabledDraftAdoptionStore` / `SQLDraftAdoptionStore`，默认无 backend 显式 `DRAFT_ADOPTION_BACKEND_UNCONFIGURED`。
- 新增 `POST /v1/drafts/{draftId}/adoptions`，只信任 `X-Tenant-Id` 和 route draft id，携带 actor/request context，公开响应只返回 adoption metadata。
- `cmd/api` 在 `DATABASE_URL` 配置时接入 DB-backed draft adoption store；无 DB 时保持 fail-closed disabled store。
- Coordinator 追加 hardening：candidate draft SQL selection 使用 `FOR UPDATE` 锁定 row，避免并发 adoption 在内部 manuscript insert 周围留下竞态；同时补 `cmd/api` store wiring tests。
- Quality reviewer 初审指出 3 个必须修正点：HTTP 边界不得透传 store 底层错误文本、SQL result scan 失败不得通过 read-side rows `Close()` 间接 commit、`scene_id` override 在 `manuscript_blocks` 无目标列前不得静默忽略。Coordinator 已修正为稳定公开错误 message、显式 `Commit()` / deferred `Rollback()` 的 write rows 协议，并在 HTTP 层拒绝 `scene_id` override。

GREEN:

- `cd apps/api && go test ./internal/workflows -run 'TestSQLDraftAdoptionStore' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestAdoptDraft' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Writer|Draft|Admission' -count=1` 通过。
- 修正后 focused regression：`cd apps/api && go test ./internal/workflows -count=1`、`cd apps/api && go test ./internal/httpapi -count=1`、`cd apps/api && go test ./cmd/api -count=1` 通过。
- Broader verification：`cd apps/api && go test ./... -count=1`、`git diff --check`、touched-file trailing whitespace scan 均通过。
- Review gate：quality reviewer Darwin re-review `APPROVED`；原 spec reviewer Singer 超时后关闭，replacement spec reviewer Banach `APPROVED`，并复跑 focused adoption/spec checks 与 `git diff --check`。

### 2026-07-07 当前会话：Wave 1 W1-S2 writer reviewer admission/read

Context:

- W1-S1 已提交：`32a304a feat: add explicit writer draft adoption`。
- Wave 1 剩余 gaps 里，`writer_reviewer` route 已在 `15-api-contracts.md` / `11-writer-workbench.md` 冻结，但 `apps/api` 尚无 `POST /v1/drafts/{draftId}/reviews` / `GET /v1/drafts/{draftId}/reviews` 实现。
- 本 slice 目标是 fail-closed、metadata-only 的 review admission/read path；不得生成 fake review issues，不得读取或公开 draft/manuscript 正文。

Planned TDD:

- RED：补 Go workflows / HTTP / cmd wiring tests，证明当前 review route/store/backend 不存在或 fail-closed contract 未实现。
- Implementation：通过 `writer_reviewer` LLM Facility binding 做 review admission，缺 binding / 缺 backend 显式失败；read side 只返回 public review metadata/issues。
- GREEN：聚焦 `go test` 覆盖 Review / Writer 路径，再由 spec reviewer 与 quality reviewer 审查。

RED:

- Implementer subagent 先运行 `cd apps/api && go test ./internal/workflows -run 'Review|Writer' -count=1`，失败于缺 `NewSQLDraftReviewStore`、`StartDraftReviewInput`、`WriterReviewWorkflowType`。
- Implementer subagent 先运行 `cd apps/api && go test ./internal/httpapi -run 'Review|Draft|Writer' -count=1`，失败于缺 draft review workflow types。
- Implementer subagent 先运行 `cd apps/api && go test ./cmd/api -run 'Review|Writer' -count=1`，失败于缺 `newDraftReviewStore`。

Implementation:

- 新增 `DraftReviewStore` / `DisabledDraftReviewStore` / `SQLDraftReviewStore`；无 DB/backend 显式 `WRITER_REVIEW_BACKEND_UNCONFIGURED`。
- 新增 `POST /v1/drafts/{draftId}/reviews`，只信任 `X-Tenant-Id` 和 route draft id，先解析 `writer_reviewer` LLM Facility binding；缺 binding 返回 `LLM_MODULE_UNBOUND`，不会 admission。
- 新增 `GET /v1/drafts/{draftId}/reviews`，只返回 review / issue public metadata。
- target Postgres baseline 新增 `draft_reviews` / `draft_review_issues`、索引和 tenant RLS；DB-backed POST 只写 `workflow_runs`、sanitized `workflow.queued` event 和 `draft_reviews.status = queued` metadata，不生成 fake issues、不采用 manuscript。
- Coordinator 追加 hardening：HTTP response boundary 对 review issue text/status/category 再清洗，防止替换 store 或未来 reader 返回 prompt/API key/`credential_ref`/draft/manuscript 类字符串。
- Spec reviewer 初审指出 3 个必须修正点：review admission 不能在缺 project scope 时解析 tenant/platform binding、public workflow event 不能包含 user note text、issue row 不能脱离同一 review/draft/project。Coordinator 已修正为 body `project_id` required before LLM resolution、queued event/persistence 不带 note、SQL read join 加 project/draft 条件，并在 schema 上为 `draft_review_issues` 添加 `(tenant_id, project_id, draft_id, review_id)` 复合外键。
- Quality reviewer 初审指出 review admission 不应把 `llm_resolution` / provider routing metadata 持久化到 `draft_reviews.options_jsonb`。Coordinator 已保留 `writer_reviewer` binding preflight，但移除 review store input 中的 `llm_resolution`，并在 SQL store 侧防御性剥离 provider/base URL/channel/model/settings 等 routing metadata。

GREEN:

- Implementer subagent：`cd apps/api && go test ./internal/workflows -run 'Review|Writer' -count=1`、`cd apps/api && go test ./internal/httpapi -run 'Review|Draft|Writer' -count=1`、`cd apps/api && go test ./cmd/api -run 'Review|Writer' -count=1`、`git diff --check` 通过。
- Coordinator focused regression：`cd apps/api && go test ./internal/workflows -run 'Review|Writer' -count=1`、`cd apps/api && go test ./internal/httpapi -run 'Review|Draft|Writer' -count=1`、`cd apps/api && go test ./cmd/api -run 'Review|Writer' -count=1` 通过。
- Broader verification：`cd apps/api && go test ./... -count=1`、`PYTHONUTF8=1 backend/.venv/bin/python -m pytest backend/tests/test_saas_phase3_rls_schema.py -q -k 'core_saas or writer or draft_review'`、`git diff --check`、touched-file trailing whitespace scan 均通过。
- Review gate：spec reviewer Kierkegaard re-review `APPROVED`；quality reviewer Russell re-review `APPROVED`。

### 2026-07-07 当前会话：refactor-saas-gpt55 Wave 1 subagent implementation

Context:

- 本轮按 `tasks/refactor-saas-gpt55-subagent-development-plan.md` 启动 4 个并行 subagent slice：Seed live E2E、Writer live LLM E2E hardening、Asset search/vector first slice、Story Graph bond runner。
- 开发只发生在 `/Users/yantianqi/Documents/Noveronline-saas-mainline`；未修改主仓库 `/Users/yantianqi/Documents/Noveronline` 的未提交工作区。

Implementation:

- A1 Seed：新增 opt-in Go API upload/complete -> Temporal cluster -> Python parse/segment live harness，并加强 public event/object readback assertions；默认缺 `MIROFISH_SEED_LIVE_*` env 时跳过，不声称完整 Seed pipeline。
- A2 Writer/Pi runtime：Writer admission/cancel 与 Pi runtime DB writes 使用 tenant-aware SQL path；writer/workflow events 先验证 parent rows，并把 provider/credential/query failure 收敛为稳定 public errors。
- A3 Assets：`POST /v1/assets/search` 去掉 public `body`，只返回 sanitized metadata；新增 asset version/collection baseline schema、tenant-aware RLS read path和 Web client/UI 类型更新。vector/hybrid search 仍 pending。
- A4 Story Graph：新增 LLM Facility-backed `graph_bond_generator` runner，schema-validate bonds/plot/conflict candidates，并只把 sanitized candidates 写为 lifecycle=`candidate` assets；不写 canon、不自动 adoption。

Verification:

- `cd apps/api && go test ./internal/sourcefiles ./internal/workflows ./internal/httpapi -run 'Seed|Upload|SourceFile|Temporal|Writer|LLM|Activity|Usage|Asset|Search|Vector|Collection|Version|StoryGraph|Graph|Bond' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过：`227 passed, 4 skipped`。
- `cd apps/pi-agent-runtime && npm run test && npm run typecheck` 通过：`38 tests` + typecheck。
- `cd apps/web && npm run test -- --test-name-pattern='Writer|writer|Asset|asset|Story Graph|graph'` 通过：`35 passed`。
- `backend/.venv/bin/python -m pytest backend/tests/test_saas_phase3_rls_schema.py backend/tests/test_saas_phase3_infra.py -q` 通过：`25 passed`。
- `docker compose --env-file infra/.env.example -f infra/docker-compose.yml config --quiet` 通过。
- `git diff --check` 通过。

Docs synced:

- 已同步 `tasks/refactor-saas-parallel-board.md`、`docs/refactor-saas/07-story-graph.md`、`docs/refactor-saas/13-agent-runtime.md`、`docs/refactor-saas/15-api-contracts.md` 和 `docs/refactor-saas/18-legacy-coverage-matrix.md`。

Next:

- Seed 仍需 browser upload/complete、扫描/OCR PDF、sequential/provider success、ontology/entity/profile/finalize full provider path 和 retry failed segments。
- Assets 仍需 vector/hybrid search、embedding persistence 和 live reindex/browser check。
- Graph 仍需 candidate viewer/adoption flow、React Flow canvas polish 和 cluster/browser E2E。

### 2026-07-07 当前会话：P5 Seed HTTP request-id privacy hardening

Context:

- Phase 5 当前主线仍是补 Go API upload/complete -> Temporal cluster -> Python parse/segment 的完整 live E2E。
- 继续检查 Go HTTP -> Seed starter -> admission/Temporal handoff 时，发现 `requestID(request)` 会直接保留客户端可控 `X-Request-Id`。
- `request_id` 是 public correlation metadata，但它会进入 error envelope、starter input、admission metadata 和 Temporal payload；如果 header 夹带 prompt/API key/`credential_ref`/object key/draft/manuscript，就会绕过 body/options sanitizer。

Scope:

- 目标：让 HTTP boundary 只保留短安全字符集且不含高风险键族的 request id；敏感、非法或过长 `X-Request-Id` 改用生成的 `req_...`。
- 边界：只收紧 HTTP correlation metadata；不改变 upload/complete、source validation、Seed admission CTE、Temporal worker、Python parse/segment 或完整 live E2E 状态。

RED:

- `cd apps/api && go test ./internal/httpapi -run 'Test(StartSeedRunSanitizesSensitiveRequestIDBeforeStarter|ErrorEnvelopeSanitizesSensitiveRequestIDHeader)' -count=1` 失败。
- 失败原因：Seed starter input 和公开 error envelope 都直接回显了包含 prompt/API key/`credential_ref`/object key/draft/manuscript 的 `X-Request-Id`。

Implementation:

- `requestID` 现在先调用 `safeRequestID`；只有长度不超过 128、字符属于 `A-Z` / `a-z` / digits / `-` / `_` / `.` / `:`，且归一化后不含高风险键族时才保留 header。
- 敏感、非法或过长 header 改由 `newRequestID` 生成 `req_...`，并继续保留随机生成失败时的 `req_unknown` fail-safe。

GREEN:

- `cd apps/api && go test ./internal/httpapi -run 'Test(StartSeedRunSanitizesSensitiveRequestIDBeforeStarter|ErrorEnvelopeSanitizesSensitiveRequestIDHeader)' -count=1` 通过。

Focused recheck:

- `cd apps/api && go test ./internal/httpapi -run 'Test(ErrorResponseIncludesRequestID|StartSeedRun|Seed|Upload|SourceFile|RequestID)' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -run 'TemporalSeedRunStarter|SeedAdmission|StartFailure' -count=1` 通过。

Broader verification:

- `cd apps/api && go test ./... -count=1` 通过。
- `cd /Users/yantianqi/Documents/Noveronline-saas-mainline && git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/api/internal/httpapi/server.go apps/api/internal/httpapi/server_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无输出，目标文件尾随空白扫描通过。

Docs synced:

- 已同步 `docs/refactor-saas/06-seed-pipeline.md`、`docs/refactor-saas/15-api-contracts.md`、`docs/refactor-saas/18-legacy-coverage-matrix.md` 和 `tasks/refactor-saas-parallel-board.md` 的 request-id privacy 边界说明。

Next:

- 继续补真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E；当前切片仍不声明 browser upload/complete、Temporal worker handoff 或 full Seed pipeline E2E 完成。

### 2026-07-07 当前会话：P5 Temporal Seed starter UUID preflight hardening

Context:

- 上一切片已让 DB-backed `SQLSeedAdmissionStore` 在执行 `::uuid` SQL 前拒绝非法 UUID context。
- 继续检查 Go -> Temporal handoff boundary 时，`TemporalSeedRunStarter` 自己仍只要求 tenant/project/upload 非空，并验证 source object/MIME/SHA/size；如果内部调用使用非 SQL admission store 或测试 store，非 UUID tenant/project/upload/source/actor 仍可能进入 Temporal payload。
- 正常 HTTP Seed start 仍由 `sourcefiles.ValidateSourceFile` 注入 DB-backed UUID source metadata；本切片是 starter 级第二道防线，防止内部调用绕过 source validation。

Scope:

- 目标：让 `TemporalSeedRunStarter` 在 admission store 写入、run id 分配和 Temporal start 前拒绝非 UUID-shaped tenant/project/upload/source id 以及非空 actor id。
- 边界：只收紧 Go starter 的 context preflight；不改变 HTTP Seed start response、SQL admission CTE、Temporal workflow payload shape、Python parse/segment runtime 或完整 live E2E 状态。
- 预期验证：先补 starter invalid UUID RED，再最小实现 validation，并迁移 starter 单测 fixture 为 UUID-shaped context。

RED:

- `cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterRejectsInvalidUUIDContextBeforeAdmission -count=1` 失败。
- 失败原因：`TemporalSeedRunStarter` 当前只校验必填非空和 source handoff metadata，非 UUID tenant/project/upload/source/actor 仍继续进入 admission/Temporal 路径。

Implementation:

- `TemporalSeedRunStarter.StartSeedRun` 现在会在 source metadata validation、admission store 写入、run id 分配和 Temporal `ExecuteWorkflow` 前调用 UUID preflight。
- 新增 `invalidSeedStartUUIDContext` / `invalidSeedStartContext`，复用 Seed admission 侧 UUID shape helper；非法 tenant/project/upload/source id 或非空 actor id 返回稳定 `VALIDATION_FAILED` / `seed workflow context is invalid`。
- starter 单测 fixture 已迁移为 UUID-shaped tenant/project/upload/source/actor context，避免缺 backend、缺 source metadata、Temporal start failure 等测试被新的 UUID preflight 抢先命中。

GREEN:

- `cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterRejectsInvalidUUIDContextBeforeAdmission -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -run 'TemporalSeedRunStarter|SeedAdmission|StartFailure' -count=1` 通过。

Focused recheck:

- `cd apps/api && go test ./internal/workflows -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun|Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。

Broader verification:

- `cd apps/api && go test ./... -count=1` 通过。
- `cd /Users/yantianqi/Documents/Noveronline-saas-mainline && git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/api/internal/workflows/seed.go apps/api/internal/workflows/seed_test.go apps/api/internal/workflows/seed_admission.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无输出，目标文件尾随空白扫描通过。

Docs synced:

- 已同步 `docs/refactor-saas/06-seed-pipeline.md`、`docs/refactor-saas/15-api-contracts.md`、`docs/refactor-saas/18-legacy-coverage-matrix.md` 和 `tasks/refactor-saas-parallel-board.md` 的 Seed starter UUID preflight 边界说明。

Next:

- 继续补真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E；当前切片仍不声明 browser upload/complete、Temporal worker handoff 或 full Seed pipeline E2E 完成。

### 2026-07-07 当前会话：P5 Seed admission UUID preflight hardening

Context:

- 总纲 Phase 5 仍要求上传 TXT/MD/PDF 可进入真实 Seed workflow，当前下一大缺口是 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E。
- 继续审查 Go control-plane -> Postgres admission 边界时，`SQLSeedAdmissionStore.AdmitSeedRun` 与 `RecordSeedRunStartFailure` 的 SQL 使用 `tenant_id/project_id/run_id/upload_id/source_file_id` 的 `::uuid` cast，但 store 级校验只检查非空。
- 如果内部调用绕过 HTTP/source validation 传入非 UUID id，当前路径会进入 SQL/driver cast failure 后再泛化为 workflow admission/start-failure error；本切片把该边界前移为稳定 validation failure。

Scope:

- 目标：让 Seed DB admission 与 start-failure compensation 在执行 SQL 前验证 UUID-shaped tenant/project/run/upload/source identifiers。
- 边界：只收紧 Go `SQLSeedAdmissionStore` 的 DB admission/compensation preflight；不改变 public HTTP response、Temporal payload shape、Python parse/segment runtime、source 状态机或完整 live E2E 状态。
- 预期验证：先补 invalid UUID RED，再最小实现 validation helper，运行 Seed workflow/http/cmd 和 `apps/api` 回归。

RED:

- `cd apps/api && go test ./internal/workflows -run 'TestSQLSeedAdmissionStoreRejectsInvalidUUIDContextBefore(Admission|StartFailure)SQL' -count=1` 失败。
- 失败原因：`AdmitSeedRun` 和 `RecordSeedRunStartFailure` 只验证必填非空，非 UUID tenant/project/run/upload/source id 仍进入 SQL path；测试期望在 SQL 前以 `VALIDATION_FAILED` fail closed。

Implementation:

- `SQLSeedAdmissionStore.AdmitSeedRun` 现在会在 admission SQL 前验证 tenant/project/run/upload/source id 以及非空 actor id 的 UUID shape。
- `SQLSeedAdmissionStore.RecordSeedRunStartFailure` 现在会在 start-failure compensation SQL 前验证 tenant/project/run/upload/source id 的 UUID shape。
- 非法内部 context 返回稳定 `VALIDATION_FAILED` / `seed admission context is invalid`，不执行 SQL、不推进 source row、不写 workflow rows/events，也不回显 prompt/API key/`credential_ref` 等不可信 id 文本。

GREEN:

- `cd apps/api && go test ./internal/workflows -run 'TestSQLSeedAdmissionStoreRejectsInvalidUUIDContextBefore(Admission|StartFailure)SQL' -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -run 'SeedAdmission|SQLSeedAdmission|TemporalSeedRunStarter|StartFailure|WorkflowStartFailure|RecordsFailedAdmission' -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -count=1` 通过。

Focused recheck:

- `cd apps/api && go test ./internal/workflows -run 'TestSQLSeedAdmissionStoreRejectsInvalidUUIDContextBefore(Admission|StartFailure)SQL|SeedAdmission|SQLSeedAdmission|TemporalSeedRunStarter|StartFailure|WorkflowStartFailure|RecordsFailedAdmission' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun|Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。

Broader verification:

- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过，无输出。
- `rg -n '[[:blank:]]$' apps/api/internal/workflows/seed_admission.go apps/api/internal/workflows/seed_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- Browser upload/complete、扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed start-failure source-file scope hardening

Context:

- 上一切片让 `SQLSeedAdmissionStore.AdmitSeedRun` 同时匹配 tenant/project、`upload_id`、`source_file_id` 和 `parse_status = uploaded` 后才推进 source row 并写 queued workflow。
- 继续沿同一控制面边界检查时，`RecordSeedRunStartFailure` 仍只携带 tenant/project/run/upload scope；如果 Temporal start 失败后的 source release 不带 source id，失败补偿边界会弱于 admission 边界。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 不修改。

Scope:

- 目标：让 Seed start-failure compensation 要求并使用同一个 `source_file_id` scope，确保 release source row、failed event public metadata 与已 admission 的 source handoff 一致。
- 边界：只收紧 Go DB compensation/source release；不改变 public response、Temporal start 语义、Python parse/segment runtime 或完整 live E2E 状态。
- 预期验证：先补 missing-source-id RED，再补 release query source-id RED，最小实现后跑 Seed workflow/http/cmd 和 `apps/api` 回归。

RED 1:

- `cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStoreRequiresSourceFileIDForWorkflowStartFailure -count=1` 失败。
- 失败原因：`RecordSeedRunStartFailure` 缺少 `source_file_id` scope 时仍执行补偿路径，没有先以 `VALIDATION_FAILED` fail closed。

GREEN 1:

- `SeedStartFailureInput` 新增 `SourceFileID`，`TemporalSeedRunStarter` 在 Temporal start failure compensation 中传递同一个 validated source id。
- `RecordSeedRunStartFailure` 的 context validation 现在要求 `source_file_id` 非空。
- `cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStoreRequiresSourceFileIDForWorkflowStartFailure -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -run 'StartFailure|WorkflowStartFailure|RecordsFailedAdmission' -count=1` 通过。

RED 2:

- `cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStoreRecordsWorkflowStartFailureAndReleasesSource -count=1` 失败。
- 失败原因：`RecordSeedRunStartFailure` 的 `source_update` CTE 仍只按 tenant/project/upload/status 释放 source row，没有 `file_id = source_file_id` 约束。

Implementation:

- `RecordSeedRunStartFailure` 的 source release CTE 现在同时匹配 tenant/project、`upload_id`、`source_file_id` 和 `parse_status = parsing`。
- Failed event payload 仍从实际释放的 DB row 派生 public `source_file_id`；source id 作为 SQL scope 参数使用，不进入 caller-provided failure JSON。
- 未改变 Temporal start public error、workflow failed status 语义、Python parse/segment runtime 或完整 live E2E 状态。

GREEN 2:

- `cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStoreRecordsWorkflowStartFailureAndReleasesSource -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -run 'StartFailure|WorkflowStartFailure|RecordsFailedAdmission' -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -run 'SeedAdmission|SQLSeedAdmission|TemporalSeedRunStarter|StartFailure|WorkflowStartFailure|RecordsFailedAdmission' -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -count=1` 通过。

Focused recheck:

- `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun|Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。

Broader verification:

- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过，无输出。
- `rg -n '[[:blank:]]$' apps/api/internal/workflows/seed.go apps/api/internal/workflows/seed_admission.go apps/api/internal/workflows/seed_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- Browser upload/complete、扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed admission source-file scope hardening

Context:

- Phase 5 当前主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- 现有 Go live harness 已覆盖 `CreateSourceFile -> object upload -> CompleteUpload -> ValidateSourceFile -> SQLSeedAdmissionStore.AdmitSeedRun`，但 `SQLSeedAdmissionStore` admission CTE 只用 tenant/project/upload/status 推进 source row，queued event 的 `source_file_id` 从 DB row 派生，而 `TemporalSeedRunStarter` payload 仍使用 caller-provided `SourceFileID`。
- 如果未来内部调用绕过 HTTP/source validation，传入匹配 upload 但不匹配的 source file id，DB public queued event 与 Python worker payload 可能在 source id 上分叉，parse/status writer 会围绕错误 source id 继续执行。

Scope:

- 目标：让 Seed DB admission 必须同时匹配 `upload_id` 和 `source_file_id`，并要求 admission input 带 source id，防止 queued row/event 与 Temporal payload source metadata 分叉。
- 边界：只收紧 DB admission/control-plane source scope；不改变 public response、object storage、Temporal start、Python parse/segment 行为或完整 live E2E 状态。
- 预期验证：先扩展 SQL admission 单测并确认 RED，再最小修改 admission validation/CTE，运行 focused/broader checks。

RED:

- `cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStoreScopesAdmissionToSourceFileID -count=1` 失败。
- 失败原因：`SQLSeedAdmissionStore` 的 `source_update` CTE 只按 tenant/project/upload/status 推进 source row，没有 `file_id = source_file_id` 约束，无法证明 DB queued event 与 Temporal payload 使用同一个 source file。

Implementation:

- `SQLSeedAdmissionStore.AdmitSeedRun` 现在要求 `SeedAdmissionInput.SourceFileID` 非空。
- Admission CTE 在推进 `source_files.parse_status = uploaded -> parsing` 时同时匹配 `upload_id` 与 `file_id`，只有同一个 source row 命中后才写 `workflow_runs` 和 `workflow.queued` event。
- Queued event payload 仍从 DB `source_update.file_id` 派生 `source_file_id`，不会把 caller-provided source id 写进 public event JSON。

GREEN:

- `cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStoreScopesAdmissionToSourceFileID -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -run 'SeedAdmission|SQLSeedAdmission|TemporalSeedRunStarter' -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -count=1` 通过。

Focused recheck:

- `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun|Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。

Broader verification:

- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过，无输出。
- `rg -n '[[:blank:]]$' apps/api/internal/workflows/seed_admission.go apps/api/internal/workflows/seed_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- Browser upload/complete、扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed Temporal payload camelCase option key hardening

Context:

- 上一切片已让 `TemporalSeedRunStarter` 将 hyphenated high-risk option keys 归一为 underscore 形式后清洗。
- 继续审查同一 Go -> Temporal payload boundary 时发现，`sourceMaterial`、`candidateEventBody`、`eventBody` 等 camelCase high-risk keys 会 lower 成 `sourcematerial` / `candidateeventbody` / `eventbody`，当前敏感键表未覆盖，仍可能进入 Temporal workflow history。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 不修改。

Scope:

- 目标：让 Seed starter `options` sanitizer 对 camelCase high-risk key 与 snake_case / hyphenated 形式等价处理。
- 边界：只收紧 Go -> Temporal payload privacy；不改变 safe options、admission、Temporal start、Python parse/segment runtime 或完整 E2E 状态。
- 预期验证：先扩展现有 starter payload sanitizer 单测并确认 RED，再最小实现 normalization/alias，运行 focused/broader checks。

RED:

- `cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterSanitizesOptionsBeforeTemporalPayload -count=1` 失败。
- 失败原因：`sourceMaterial`、`candidateBody`、`candidateEventBody`、`eventBody` 等 camelCase high-risk option keys 仍保留在 `TemporalSeedRunStarter` 传给 `SeedPipelineWorkflow` 的 `options` payload 中。

Implementation:

- `seedOptionKeySensitive` 现在把 key 先 lower/trim，再将 `-` 归一为 `_`，并用移除 `_` 的 compact 形式匹配敏感键族。
- `source_material` / `source-material` / `sourceMaterial`、`candidate_event_body` / `candidate-event-body` / `candidateEventBody` 等变体共享同一拒绝路径。
- 未改变 safe options、admission、Temporal start 或 Python worker payload schema。

GREEN:

- `cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterSanitizesOptionsBeforeTemporalPayload -count=1` 通过。

Focused recheck:

- `cd apps/api && go test ./internal/workflows -run 'Seed' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun|Seed' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|TemporalStarters|SourceFile' -count=1` 通过。

Broader verification:

- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过，无输出。
- `rg -n '[[:blank:]]$' apps/api/internal/workflows/seed.go apps/api/internal/workflows/seed_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- Browser upload/complete、扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed Temporal payload option key normalization hardening

Context:

- Phase 5 当前主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- `TemporalSeedRunStarter` 已在 Go -> Temporal payload 前递归清洗 `options`，但需要确认高风险 option key 的变体形式同样不能进入 Temporal workflow history。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 不修改。

Scope:

- 目标：让 Seed starter 的 `options` sanitizer 对 `api-key`、`credential-ref`、`raw-text`、`source-material`、`candidate-event-body` 等 hyphenated high-risk key 与 underscore 形式等价处理。
- 边界：只收紧 Go -> Temporal payload privacy；不改变 public API response、workflow admission、Temporal start 成功语义、Python parse/segment runtime 或完整 E2E 状态。
- 预期验证：先扩展现有 starter payload sanitizer 单测并确认 RED，再最小实现 key normalization，运行 focused/broader checks。

RED:

- `cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterSanitizesOptionsBeforeTemporalPayload -count=1` 失败。
- 失败原因：`TemporalSeedRunStarter` 当前仅按 lower/trim 后的 key 判断 high-risk options，`source-material`、`api-key`、`credential-ref`、`candidate-event-body`、`raw-text` 等 hyphenated 变体仍进入 Temporal workflow payload。

Implementation:

- `seedOptionKeySensitive` 在匹配 high-risk key 前先把 `-` 归一为 `_`，让 hyphenated 和 underscore 形式共享同一敏感键表。
- 未改变 safe options 保留策略、admission、Temporal start 或 Python worker payload schema。

GREEN:

- `cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterSanitizesOptionsBeforeTemporalPayload -count=1` 通过。

Focused recheck:

- `cd apps/api && go test ./internal/workflows -run 'Seed' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun|Seed' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|TemporalStarters|SourceFile' -count=1` 通过。

Broader verification:

- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过，无输出。
- `rg -n '[[:blank:]]$' apps/api/internal/workflows/seed.go apps/api/internal/workflows/seed_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- Browser upload/complete、扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 workflow event payload public metadata boundary hardening

Context:

- Seed `workflow.queued` / `workflow.failed` events 已写入 row-derived `source_file_id`，用于 queued -> parse/segment 的公开关联。
- HTTP workflow event 读取层会再次调用 `workflows.SanitizeWorkflowEventPayload`，需要明确保留安全 metadata，并防止 storage object key、raw text、hash 等高风险字段穿透到公网事件流。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 不修改。

Scope:

- 目标：让 workflow event payload sanitizer 保留 `source_file_id`，但移除 `object_key`、`source_object_key`、raw text/body/content、hash/SHA256、prompt、API key、credential、draft、manuscript 等字段。
- 边界：不改变 workflow event schema、cursor、SSE 格式、Temporal/Python runtime；不公开 object storage path、raw source/manuscript 或 LLM trace。
- 预期验证：先写 RED 覆盖 HTTP event response，再最小实现并运行 focused/broader checks。

RED:

- `cd apps/api && go test ./internal/httpapi -run TestGetWorkflowRunEventsReturnsEventsAfterQueryCursorAndSanitizesPayload -count=1` 失败。
- 失败原因：HTTP workflow event response 仍公开 `object_key`、`source_object_key`、`raw_text` 和 `source_sha256`；测试同时确认 `source_file_id` 是应保留的安全关联 metadata。
- 扩展同一测试覆盖 `artifact_object_key` / `segment_object_key` 后再次 RED，确认 artifact/segment object refs 也会透出。

Implementation:

- `workflows.SanitizeWorkflowEventPayload` 的敏感键集合扩展为剥离 source/artifact/segment object storage key、raw/source/input/output/body/content text、hash/checksum、prompt/response、API key、credential、draft 和 manuscript。
- `source_file_id` 保持为安全 public metadata，不加入敏感键集合。
- 未改变 workflow event schema、cursor、SSE 输出格式或任何 runtime/admission 行为。

GREEN:

- `cd apps/api && go test ./internal/httpapi -run TestGetWorkflowRunEventsReturnsEventsAfterQueryCursorAndSanitizesPayload -count=1` 通过。

Focused recheck:

- `cd apps/api && go test ./internal/workflows -run 'WorkflowEvent|Seed' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'WorkflowRunEvents|Seed' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Workflow' -count=1` 通过。

Broader verification:

- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过，无输出。
- `rg -n '[[:blank:]]$' apps/api/internal/workflows/workflow_events.go apps/api/internal/httpapi/server_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- Browser upload/complete、扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed start-failure event source-file id DB row authority

Context:

- `workflow.queued` event 已能携带 row-derived `source_file_id` public metadata。
- Temporal `ExecuteWorkflow` 如果在 DB admission 后失败，`SQLSeedAdmissionStore.RecordSeedRunStartFailure` 会把 queued run 标为 `failed`、追加 `workflow.failed`，并把 source row 从 `parsing` 释放回 `uploaded`；但 failure event 当前只有 `upload_id`，缺少同样 row-derived 的 `source_file_id` 关联元数据。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：让 Seed start-failure compensation 的 `workflow.failed` payload 在 source row 被释放时包含 row-derived `source_file_id`。
- 边界：只公开 source file id；不公开 object key、source path、raw text、prompt、API key、`credential_ref`、draft 或 manuscript；不改变 workflow admission、Temporal start、Python parse/segment 或完整 E2E 语义。

RED:

- `cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStoreRecordsWorkflowStartFailureAndReleasesSource -count=1` 失败。
- 失败原因：`RecordSeedRunStartFailure` 的 `source_update` 只 `RETURNING upload_id`，`workflow.failed` payload 只使用 `$8::jsonb`，没有从 released source row 派生 `source_file_id`。

Implementation:

- `SQLSeedAdmissionStore.RecordSeedRunStartFailure` 的 `source_update` CTE 改为 `RETURNING upload_id, file_id`。
- `workflow.failed` payload 在 `source_update.file_id` 非空时通过 `jsonb_build_object('source_file_id', source_update.file_id::text)` 加入 row-derived source file id；若 source row 没被释放，payload 仍保持稳定 failure metadata。
- 未改变 Temporal start failure code/message、source release 条件、workflow status 条件或 Python runtime。

GREEN:

- `cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStoreRecordsWorkflowStartFailureAndReleasesSource -count=1` 通过。

Focused recheck:

- `cd apps/api && go test ./internal/workflows -run 'Seed' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun|Seed' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|TemporalStarters|SourceFile' -count=1` 通过。

Broader verification:

- `cd apps/api && go test ./... -count=1` 通过。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，116 passed。
- `git diff --check` 通过，无输出。
- `rg -n '[[:blank:]]$' apps/api/internal/workflows/seed_admission.go apps/api/internal/workflows/seed_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- Browser upload/complete、扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed queued event source-file id DB row authority

Context:

- 上一切片让 Seed `workflow.queued` public event 携带 `upload_id` 与 `source_file_id`，补齐 queued -> parse/segment 的公开事件关联。
- 但当前 DB-backed `SQLSeedAdmissionStore` 会把 caller-supplied `SourceFileID` 放进 event payload；虽然正常 HTTP/Temporal starter path 会先验证 source metadata，DB admission 自身仍应以实际被 `UPDATE source_files ... RETURNING file_id` 推进到 `parsing` 的 row 作为 source-file id 真相源。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：让 SQL admission queued event 的 `source_file_id` 从 `source_update.file_id` 派生，而不是信任 `SeedAdmissionInput.SourceFileID`。
- 边界：保留 starter -> admission input 的 source metadata handoff 给非 SQL/test stores；DB event 只公开 row-derived `source_file_id`，不公开 object key、source path、raw text、prompt、API key、`credential_ref`、draft 或 manuscript；不改变 admission 状态机或 Temporal/Python runtime。

RED:

- `cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload -count=1` 失败。
- 失败原因：`SQLSeedAdmissionStore` 当前把 caller-supplied `SourceFileID` 放进 queued event JSON 参数，SQL query 也没有从 `source_update.file_id` 派生 `source_file_id`。

Implementation:

- `SQLSeedAdmissionStore.AdmitSeedRun` 的 JSON 参数不再包含 caller-supplied `SourceFileID`。
- `source_update` CTE 现在 `RETURNING upload_id, file_id`，最终 `workflow.queued` payload 通过 `jsonb_build_object('source_file_id', source_update.file_id::text)` 从实际推进到 `parsing` 的 source row 派生 source file id。
- admission 状态机、Temporal start、Python runtime 均未改变。

GREEN:

- `cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload -count=1` 通过。

Focused recheck:

- `cd apps/api && go test ./internal/workflows -run 'Seed' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun|Seed' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|TemporalStarters|SourceFile' -count=1` 通过。

Broader verification:

- `cd apps/api && go test ./... -count=1` 通过。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，116 passed。
- `git diff --check` 通过，无输出。
- `rg -n '[[:blank:]]$' apps/api/internal/workflows/seed.go apps/api/internal/workflows/seed_admission.go apps/api/internal/workflows/seed_test.go apps/api/internal/workflows/seed_live_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- Browser upload/complete、扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed queued event `source_file_id` public metadata handoff

Context:

- Phase 5 下一条主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- Go `TemporalSeedRunStarter` 的内部 Temporal payload 已携带 `source_file_id`，Python parse/segment events 也会公开 `source_file_id`；但 Go admission 的 `workflow.queued` event 目前只公开 `upload_id`，使 queued -> parse/segment 的公开事件链缺少 source file correlation metadata。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：让 Seed starter 把 validated `source_file_id` 交给 admission store，并让 DB-backed `workflow.queued` public event 包含 `source_file_id`。
- 边界：只公开 source file id 这种安全 metadata；不公开 object key、source path、raw text、prompt、API key、`credential_ref`、draft 或 manuscript；不启动 fake Temporal/Python runtime，不声明完整 Seed live E2E 完成。
- 预期验证：先写 RED Go 单测确认当前 admission input/event payload 缺失 `source_file_id`，再最小实现并运行 focused/broader checks。

RED:

- `cd apps/api && go test ./internal/workflows -run 'TestTemporalSeedRunStarterPersistsAdmissionBeforeStartingWorkflow|TestSQLSeedAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload' -count=1` 失败。
- 失败原因：`SeedAdmissionInput` 尚无 `SourceFileID` 字段，starter admission handoff 和 SQL queued event payload 都无法公开 source file correlation metadata。

Implementation:

- `SeedAdmissionInput` 新增 optional `SourceFileID`。
- `TemporalSeedRunStarter` 在 source handoff validation 后，将 trimmed `SourceFileID` 传入 admission store。
- `SQLSeedAdmissionStore.AdmitSeedRun` 在 `workflow.queued` public event payload 中写入非空 `source_file_id`，继续只保留 request/upload/trace/status 这类安全 metadata。
- opt-in Go live MinIO/Postgres admission harness 也传入并断言 queued event 包含 source file metadata。

GREEN:

- `cd apps/api && go test ./internal/workflows -run 'TestTemporalSeedRunStarterPersistsAdmissionBeforeStartingWorkflow|TestSQLSeedAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload' -count=1` 通过。

Focused recheck:

- `cd apps/api && go test ./internal/workflows -run 'Seed' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun|Seed' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|TemporalStarters|SourceFile' -count=1` 通过。

Broader verification:

- `cd apps/api && go test ./... -count=1` 通过。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，116 passed。
- `git diff --check` 通过，无输出。
- `rg -n '[[:blank:]]$' apps/api/internal/workflows/seed.go apps/api/internal/workflows/seed_admission.go apps/api/internal/workflows/seed_test.go apps/api/internal/workflows/seed_live_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- Browser upload/complete、扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed Temporal starter options handoff privacy hardening

Context:

- Phase 5 下一条主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- HTTP `POST /v1/projects/{projectId}/seed-runs` 已在进入 `SeedStarter` 前清洗 user options，但 `TemporalSeedRunStarter` 自身只浅拷贝 options；未来内部调用若绕过 HTTP handler，仍可能把 body-provided tenant/project、prompt、API key、`credential_ref`、raw text、draft 或 manuscript 放进 `SeedPipelineWorkflow` Temporal payload。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：在 Go `TemporalSeedRunStarter` 组装 Temporal payload 前递归清洗 `options`，形成 HTTP handler 之后的第二道 handoff 隐私边界。
- 边界：保留 safe public analysis options，例如 language、analysis depth、chapter detection；不改变 source metadata handoff、admission、object upload/complete、Python parse/segment 或 LLM stages；不声明完整 Seed live E2E 完成。

RED:

- `cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterSanitizesOptionsBeforeTemporalPayload -count=1` 失败。
- 失败原因：Temporal payload options 仍包含 `tenant_id`、`project_id`、prompt、`api_key`、`credential_ref`、`encrypted_api_key`、body/raw text 和 manuscript。

Implementation:

- `TemporalSeedRunStarter` 的 `cloneSeedOptions` 改为递归 sanitizer。
- 新增 Seed starter-local high-risk key filter，移除 tenant/project authority 字段、credential/API key、prompt/response/body/content/raw/source/material/candidate/event text、draft 和 manuscript。
- 数组和嵌套 map 递归清洗；安全 public metadata 继续传给 Python worker。

GREEN:

- `cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterSanitizesOptionsBeforeTemporalPayload -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -run 'Seed' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun|Seed' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|TemporalStarters|SourceFile' -count=1` 通过。

Broader verification:

- `cd apps/api && go test ./... -count=1` 通过。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，116 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，216 passed / 3 skipped。
- `git diff --check` 通过，无输出。
- `rg -n '[[:blank:]]$' apps/api/internal/workflows/seed.go apps/api/internal/workflows/seed_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- Browser upload/complete、扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed story_ontology DB-backed snapshot writer + env wiring

Context:

- 上一切片已新增可注入 `LLMFacilityOntologyRunner` 和 `OntologySnapshotWriter` contract，但 `_ontology_runner_from_env()` 仍未自动装配，target schema 也没有 `seed_ontology_snapshots`。
- Phase 5 验收要求 Seed 结果进入结构化知识层；本轮把 `story_ontology` 从 injected skeleton 推进到 DB-backed private snapshot persistence 与默认 runtime env wiring。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：新增 `seed_ontology_snapshots` target schema/RLS/index，新增 `PostgresOntologySnapshotWriter`，并让 `_ontology_runner_from_env()` 在 `DATABASE_URL` + LLM credential key 可用时装配 DB-backed `LLMFacilityOntologyRunner`。
- 边界：不生成 mock ontology；不公开 ontology body、prompt/response、API key、encrypted credential、`credential_ref`、raw text、draft 或 manuscript；不声明 Seed live provider E2E、entity resolution/profile/finalize runner 完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'postgres_ontology_snapshot_writer_upserts_sanitized_private_snapshot or ontology_runner_from_env_builds_db_backed_llm_facility_runner'` 失败，2 failed / 114 deselected。
- 失败原因：`mirofish_agents.temporal.seed` 尚无 `PostgresOntologySnapshotWriter`，且 `_ontology_runner_from_env()` 不接受 `http_request` / `connect` 注入，仍固定返回 unconfigured。
- `backend/.venv/bin/python -m pytest backend/tests/test_saas_phase3_rls_schema.py -q -k 'core_saas_schema_declares_minimum_phase3_tables or tenant_business_tables_have_tenant_id_and_timestamps or seed_canon_structured_tables or rls_is_enabled_for_tenant_scoped_tables'` 失败，3 failed / 15 deselected。
- 失败原因：target schema 尚无 `seed_ontology_snapshots` 表、tenant/project columns、RLS policy 和 index。

Implementation:

- target schema 新增 `seed_ontology_snapshots`，包含 tenant/project/run/module scope、私有 `ontology_jsonb`、类型 counts、metadata、唯一键、run/project 索引、RLS policy 和 app-role grant。
- 新增 `PostgresOntologySnapshotWriter`：写入前设置 `app_set_tenant_context`，清洗 prompt/API key/`credential_ref`/raw content 等高风险字段，upsert 私有 ontology JSON/counts，SQL/commit failure rollback 并返回稳定 `ONTOLOGY_SNAPSHOT_WRITE_FAILED`。
- `_ontology_runner_from_env()` 现在可在 `DATABASE_URL` 可用时装配 DB-backed `LLMFacilityOntologyRunner`，复用 LLM Facility `PostgresModuleBindingResolver`、`PostgresCredentialProvider`、显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 和 OpenAI-compatible JSON client。
- public result / workflow event 仍只公开 `ontology_snapshot_id`、model 和类型 counts；不公开 ontology body、prompt/response、API key、encrypted credential、`credential_ref`、raw text、draft 或 manuscript。
- 当前切片不声明 Seed live provider E2E，也不实现 entity resolution/profile/finalize runner。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'postgres_ontology_snapshot_writer_upserts_sanitized_private_snapshot or ontology_runner_from_env_builds_db_backed_llm_facility_runner'` 通过，2 passed / 114 deselected。
- `backend/.venv/bin/python -m pytest backend/tests/test_saas_phase3_rls_schema.py -q -k 'core_saas_schema_declares_minimum_phase3_tables or tenant_business_tables_have_tenant_id_and_timestamps or seed_canon_structured_tables or rls_is_enabled_for_tenant_scoped_tables'` 通过，3 passed / 15 deselected。

Focused recheck:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'postgres_ontology_snapshot_writer_upserts_sanitized_private_snapshot or ontology_runner_from_env_builds_db_backed_llm_facility_runner or llm_facility_ontology_runner_persists_schema_valid_snapshot_without_public_body_or_credentials or story_ontology_activity_records_sanitized_metadata_from_runner or story_ontology_activity_fails_closed_without_runner'` 通过，5 passed / 111 deselected。
- `backend/.venv/bin/python -m pytest backend/tests/test_saas_phase3_rls_schema.py -q -k 'core_saas_schema_declares_minimum_phase3_tables or tenant_business_tables_have_tenant_id_and_timestamps or seed_canon_structured_tables or rls_is_enabled_for_tenant_scoped_tables'` 通过，3 passed / 15 deselected。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，216 passed / 3 skipped。
- `backend/.venv/bin/python -m pytest backend/tests/test_saas_phase3_rls_schema.py -q` 通过，18 passed。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过，无输出。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py backend/tests/test_saas_phase3_rls_schema.py infra/postgres/migrations/0001_core_saas.sql docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/14-data-model.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续补真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- 扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed story_ontology LLM Facility runner skeleton with persistence

Context:

- Phase 5 验收要求 Seed 结果进入结构化知识层，ontology 是 sequential/global aggregation 后进入 entity resolution/profile 的关键 stage。
- 当前 `ontology_activity` 已有 fail-closed shell、runner protocol、sanitized completed event contract，但 `_ontology_runner_from_env()` 仍固定 `None`，覆盖矩阵明确标记真实 ontology runner / schema validation / persistence pending。
- 本轮要推进一个真实 runner skeleton：走 LLM Facility module binding、显式 credential、JSON-capable provider、schema validation，并通过 writer 持久化私有 ontology snapshot 后才返回 public snapshot metadata。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：新增 `LLMFacilityOntologyRunner` 和 ontology snapshot writer contract；schema-valid provider 输出必须写入 writer 后才返回 completed public metadata。
- 边界：不生成 mock ontology；不把 ontology body、prompt/response、API key、`credential_ref`、raw text、draft 或 manuscript 放进 public result/event；不声明完整 ontology/entity/profile/finalize pipeline 或 live provider E2E 已完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'llm_facility_ontology_runner_persists_schema_valid_snapshot_without_public_body_or_credentials'` 失败，1 failed / 113 deselected。
- 失败原因：`mirofish_agents.temporal.seed` 还没有 `LLMFacilityOntologyRunner`，`story_ontology` 只有 injected runner contract 与 fail-closed activity shell。

Implementation:

- 新增 `OntologySnapshotWriter` contract 与可注入的 `LLMFacilityOntologyRunner`。
- runner 只支持 `story_ontology` module key，先解析 LLM Facility module binding、校验 JSON-capable resolution、用显式 credential 调用 OpenAI-compatible JSON client，再校验 `seed_ontology.entity_types` / `relationship_types` / `world_rule_types` array schema。
- schema-valid ontology 会先清洗 `prompt` / `credential_ref` 等高风险字段，并写入 snapshot writer；只有 writer 返回 snapshot id 后，runner 才返回 completed public metadata。
- public result 只包含 `ontology_snapshot_id`、`model_id` 和类型 counts；不公开 ontology body、prompt、response、API key、`credential_ref`、raw text、draft 或 manuscript。
- 当前切片不自动装配 `_ontology_runner_from_env()`，不声明 live provider E2E、Postgres ontology snapshot writer、entity resolution/profile/finalize 已完成。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'llm_facility_ontology_runner_persists_schema_valid_snapshot_without_public_body_or_credentials'` 通过，1 passed / 113 deselected。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'llm_facility_ontology_runner_persists_schema_valid_snapshot_without_public_body_or_credentials or story_ontology_activity_records_sanitized_metadata_from_runner or story_ontology_activity_fails_closed_without_runner or seed_workflow_locally_can_continue_global_aggregation_into_fail_closed_ontology'` 通过，4 passed / 110 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，114 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，214 passed / 3 skipped。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续补真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- `story_ontology` 默认 env wiring、Postgres ontology snapshot writer、Seed live provider E2E、entity resolution/profile/finalize runner、扫描/OCR PDF、完整智能分段和 retry failed segments 仍 pending。

### 2026-07-07 当前会话：P5 Seed sequential-reading object-store env-resolution hardening

Context:

- Phase 5 下一主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment/sequential-reading 的真实 live E2E。
- `sequential_reading_activity` 的默认 `LLMFacilitySequentialReader` 需要通过 object store 读取 segment text，再通过 LLM Facility module binding 调用 JSON-capable provider。
- 当前检查发现 `_sequential_reader_from_env()` 在装配默认 reader 时会调用 `_object_store_from_env()`；如果 object store factory/env resolution 抛出普通异常，activity 只捕获 `LLMFacilityError`，可能让底层 exception 变成未结构化 crash，并泄露 prompt/API key/`credential_ref`/segment object key/draft/manuscript。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：`sequential_reading_activity` 默认 reader 装配阶段的 object store env-resolution failure 返回稳定 `OBJECT_STORAGE_BACKEND_MISCONFIGURED` / `object storage backend is misconfigured`。
- 失败路径必须写 sanitized sequential-reading failed event，并在 workflow status writer 可用时标记 admitted Seed run failed。
- 边界：不改变显式注入 reader 路径、不伪造 reading notes、不调用 LLM、不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment/sequential-reading live E2E 已完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'sequential_reading_activity_sanitizes_object_store_env_resolution_exception'` 失败，1 failed / 112 deselected。
- 失败原因：`_sequential_reader_from_env()` 默认 reader 装配时直接调用 `_object_store_from_env()`，普通 object store factory/env `RuntimeError` 会原样冒出，异常文本可夹带 prompt、API key、`credential_ref`、segment object key、draft 或 manuscript。

Implementation:

- `_sequential_reader_from_env()` 现在只在 object store 解析点捕获 env/factory 异常，并转换为稳定 `LLMFacilityError("OBJECT_STORAGE_BACKEND_MISCONFIGURED", "object storage backend is misconfigured")`。
- `sequential_reading_activity` 复用既有 `LLMFacilityError` path 写 sanitized sequential-reading failed event，并在 workflow status writer 可用时标记 admitted Seed run failed。
- `_public_llm_error_message` 新增 `OBJECT_STORAGE_BACKEND_MISCONFIGURED` 映射，避免 workflow status message 被泛化为 `sequential reading failed`。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'sequential_reading_activity_sanitizes_object_store_env_resolution_exception'` 通过，1 passed / 112 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'sequential_reading_activity_sanitizes_object_store_env_resolution_exception or sequential_reading_activity_uses_default_llm_reader_when_available or sequential_reader_from_env_builds_db_backed_llm_facility_reader or sequential_reading_activity_fails_closed_without_llm_reader or sequential_reading_activity_sanitizes_workflow_event_writer_env_resolution_exception or sequential_reading_activity_sanitizes_workflow_status_writer_env_resolution_exception or sequential_reading_activity_marks_workflow_failed_on_terminal_failure'` 通过，5 passed / 108 deselected。

Broader verification:

- 文档同步后重新验证：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'sequential_reading_activity_sanitizes_object_store_env_resolution_exception'` 通过，1 passed / 112 deselected。
- 文档同步后重新验证：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'sequential_reading_activity_sanitizes_object_store_env_resolution_exception or sequential_reading_activity_uses_default_llm_reader_when_available or sequential_reader_from_env_builds_db_backed_llm_facility_reader or sequential_reading_activity_fails_closed_without_llm_reader or sequential_reading_activity_sanitizes_workflow_event_writer_env_resolution_exception or sequential_reading_activity_sanitizes_workflow_status_writer_env_resolution_exception or sequential_reading_activity_marks_workflow_failed_on_terminal_failure'` 通过，5 passed / 108 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，113 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，213 passed / 3 skipped。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

### 2026-07-07 当前会话：P5 Seed object-store env-resolution hardening

Context:

- Phase 5 下一主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment 的真实 live E2E。
- `parse_file_activity` 和 `segment_text_activity` 都依赖 object store factory / env resolution 来读取 source 或 extracted artifact，并写回 extracted artifact / segment object。
- 当前检查发现这两个 activity 只把 object store env-resolution 的 `ValueError` 收敛为稳定 `OBJECT_STORAGE_BACKEND_MISCONFIGURED`；如果 factory 抛出其他异常，activity 可能未结构化 crash，并把 prompt/API key/`credential_ref`/object key/draft/manuscript 等敏感片段带到公共错误面。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：`parse_file_activity` 和 `segment_text_activity` 的 object store env-resolution failure 都返回稳定 `OBJECT_STORAGE_BACKEND_MISCONFIGURED` / `object storage backend is misconfigured`。
- 失败路径必须写 sanitized parse/segment failed event，并在 workflow status writer 可用时标记 admitted Seed run failed；parse 路径还应尝试把 source row 标为 `failed`。
- 边界：不改变 object storage success path、不伪造 parse/segment success、不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 已完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_object_store_env_resolution_exception'` 失败，1 failed / 110 deselected。
- 失败原因：`parse_file_activity` 只捕获 object store env-resolution 的 `ValueError`，普通 factory/env `RuntimeError` 会原样冒出，异常文本可夹带 prompt、API key、`credential_ref`、object key、draft 或 manuscript。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'segment_text_activity_sanitizes_object_store_env_resolution_exception'` 失败，1 failed / 111 deselected。
- 失败原因：`segment_text_activity` 也只捕获 object store env-resolution 的 `ValueError`，普通 factory/env `RuntimeError` 会原样冒出，异常文本可夹带 prompt、API key、`credential_ref`、object key、draft 或 manuscript。

Implementation:

- `parse_file_activity` 的 object store env-resolution 失败现在统一走稳定 `OBJECT_STORAGE_BACKEND_MISCONFIGURED` / `object storage backend is misconfigured`。
- 该路径会尝试把 source row 标为 `failed`，写 sanitized `seed.stage.failed` parse event，并在 workflow status writer 可用时标记 admitted Seed run failed。
- `segment_text_activity` 的 object store env-resolution 失败现在也统一走稳定 `OBJECT_STORAGE_BACKEND_MISCONFIGURED` / `object storage backend is misconfigured`。
- 该路径会写 sanitized `seed.stage.failed` segment event，并在 workflow status writer 可用时标记 admitted Seed run failed；不会读取 extracted artifact 或写 segment object。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_object_store_env_resolution_exception'` 通过，1 passed / 110 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'segment_text_activity_sanitizes_object_store_env_resolution_exception'` 通过，1 passed / 111 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_object_store_env_resolution_exception or segment_text_activity_sanitizes_object_store_env_resolution_exception or parse_file_activity_sanitizes_untrusted_object_storage_errors_in_result or segment_text_activity_sanitizes_untrusted_object_storage_errors_in_result or parse_file_activity_sanitizes_text_artifact_writer_env_resolution_exception or segment_text_activity_sanitizes_text_segment_writer_env_resolution_exception or parse_file_activity_marks_workflow_failed_on_terminal_parse_failure or segment_text_activity_marks_workflow_failed_on_terminal_segment_failure'` 通过，8 passed / 104 deselected。

Broader verification:

- 文档同步后重新验证：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_object_store_env_resolution_exception or segment_text_activity_sanitizes_object_store_env_resolution_exception'` 通过，2 passed / 110 deselected。
- 文档同步后重新验证：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_object_store_env_resolution_exception or segment_text_activity_sanitizes_object_store_env_resolution_exception or parse_file_activity_sanitizes_untrusted_object_storage_errors_in_result or segment_text_activity_sanitizes_untrusted_object_storage_errors_in_result or parse_file_activity_sanitizes_text_artifact_writer_env_resolution_exception or segment_text_activity_sanitizes_text_segment_writer_env_resolution_exception or parse_file_activity_marks_workflow_failed_on_terminal_parse_failure or segment_text_activity_marks_workflow_failed_on_terminal_segment_failure'` 通过，8 passed / 104 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，112 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，212 passed / 3 skipped。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

### 2026-07-07 当前会话：P5 Seed segment text-segment writer env-resolution hardening

Context:

- Phase 5 下一主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment 的真实 live E2E。
- Python `segment_text_activity` 需要读取 parse 阶段的 extracted text artifact，生成 segment object references，并用 DB-backed text segment writer 记录 `text_segments`，供 sequential reading 继续消费。
- 当前检查发现 `segment_text_activity` 在真实 worker path 解析 DB-backed text segment writer 时，如果 writer factory / env resolution 抛出异常，会在读取 artifact 前直接冒出未结构化 exception；这可能泄露 prompt/API key/`credential_ref`/object key/draft/manuscript，也会绕过 stable segment failed event 和 workflow failed status handoff。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：`segment_text_activity` 的 text segment writer env-resolution failure 返回稳定 `TEXT_SEGMENT_WRITE_FAILED` / `text segment write failed`，写 sanitized segment failed event，并通过 workflow status writer 标记 admitted Seed run failed。
- 边界：不改变 Go admission、parse success path、segment success semantics，不伪造 segment persistence，不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 已完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'segment_text_activity_sanitizes_text_segment_writer_env_resolution_exception'` 失败，1 failed / 109 deselected。
- 失败原因：`segment_text_activity` 当前直接调用 `_text_segment_writer_from_env()`，writer factory/env exception 会未结构化冒出，异常文本可夹带 prompt、API key、`credential_ref`、object key、draft 或 manuscript。

Implementation:

- `segment_text_activity` 现在安全解析 text segment writer。
- text segment writer env-resolution failure 会返回稳定 `TEXT_SEGMENT_WRITE_FAILED` / `text segment write failed`，写 sanitized `seed.stage.failed` segment event，并在 workflow status writer 可用时标记 admitted Seed run failed。
- 该路径不会读取 extracted artifact 或写 segment object，也不会公开底层 writer factory exception。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'segment_text_activity_sanitizes_text_segment_writer_env_resolution_exception'` 通过，1 passed / 109 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'segment_text_activity_sanitizes_text_segment_writer_env_resolution_exception or segment_text_activity_sanitizes_workflow_status_writer_env_resolution_exception or segment_text_activity_marks_workflow_failed_on_terminal_segment_failure or segment_text_activity_sanitizes_workflow_event_writer_env_resolution_exception or segment_text_activity_sanitizes_untrusted_object_storage_errors_in_result or temporal_seed_workflow_uses_env_workflow_event_writer'` 通过，7 passed / 103 deselected。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，110 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，210 passed / 3 skipped。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py tasks/refactor-saas-live-progress.md` 无匹配。
- 文档同步后重新验证：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'segment_text_activity_sanitizes_text_segment_writer_env_resolution_exception'` 通过，1 passed / 109 deselected。
- 文档同步后重新验证：`git diff --check` 通过。
- 文档同步后重新验证：`rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

### 2026-07-07 当前会话：P5 Seed parse text-artifact writer env-resolution hardening

Context:

- Phase 5 下一主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment 的真实 live E2E。
- Python `parse_file_activity` 需要把真实 source object 解析出的 extracted text 写入 object storage，并用 DB-backed text artifact writer 记录 `project_text_artifacts` 引用，供 `segment_text_activity` 继续读取。
- 当前检查发现 `parse_file_activity` 在真实 worker path 解析 DB-backed text artifact writer 时，如果 writer factory / env resolution 抛出异常，会在 source object read 前直接冒出未结构化 exception；这可能泄露 prompt/API key/`credential_ref`/object key/draft/manuscript，也会绕过 source parse failed 状态和 workflow failed status handoff。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：`parse_file_activity` 的 text artifact writer env-resolution failure 返回稳定 `TEXT_ARTIFACT_WRITE_FAILED` / `text artifact write failed`，写 sanitized parse failed event，尝试把 source row 标为 `failed`，并通过 workflow status writer 标记 admitted Seed run failed。
- 边界：不改变 Go admission、object storage、successful parse/segment semantics，不伪造 extracted artifact，不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 已完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_text_artifact_writer_env_resolution_exception'` 失败，1 failed / 108 deselected。
- 失败原因：`parse_file_activity` 当前直接调用 `_text_artifact_writer_from_env()`，writer factory/env exception 会未结构化冒出，异常文本可夹带 prompt、API key、`credential_ref`、object key、draft 或 manuscript。

Implementation:

- `parse_file_activity` 现在安全解析 text artifact writer。
- text artifact writer env-resolution failure 会复用 parse terminal failed helper，返回稳定 `TEXT_ARTIFACT_WRITE_FAILED` / `text artifact write failed`，尝试把 source row 标为 `failed`，写 sanitized `seed.stage.failed` parse event，并在 workflow status writer 可用时标记 admitted Seed run failed。
- 该路径不会读取 source object 或写 extracted artifact，也不会公开底层 writer factory exception。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_text_artifact_writer_env_resolution_exception'` 通过，1 passed / 108 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_text_artifact_writer_env_resolution_exception or parse_file_activity_sanitizes_source_status_writer_env_resolution_exception or parse_file_activity_sanitizes_workflow_status_writer_env_resolution_exception or parse_file_activity_marks_workflow_failed_on_terminal_parse_failure or parse_file_activity_fails_closed_when_source_object_integrity_mismatches or parse_file_activity_sanitizes_untrusted_object_storage_errors_in_result or temporal_seed_workflow_uses_env_workflow_event_writer'` 通过，7 passed / 102 deselected。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，109 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，209 passed / 3 skipped。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py tasks/refactor-saas-live-progress.md` 无匹配。
- 文档同步后重新验证：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_text_artifact_writer_env_resolution_exception'` 通过，1 passed / 108 deselected。
- 文档同步后重新验证：`git diff --check` 通过。
- 文档同步后重新验证：`rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

### 2026-07-07 当前会话：P5 Seed parse source-status writer env-resolution hardening

Context:

- Phase 5 下一主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment 的真实 live E2E。
- Go admission 已把 uploaded source row 推进到 `parsing`，Python `parse_file_activity` 需要在 success/failure path 稳定更新 source parse status 并同步 workflow event/status。
- 当前检查发现 `parse_file_activity` 在真实 worker path 解析 DB-backed source parse-status writer 时，如果 writer factory / env resolution 抛出异常，会在 parse 前直接冒出未结构化 exception；这可能泄露 prompt/API key/`credential_ref`/object key/draft/manuscript，也会绕过 stable workflow failed status handoff。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：`parse_file_activity` 的 source parse-status writer env-resolution failure 返回稳定 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED` / `source file parse status update failed`，写 sanitized parse failed event，并通过 workflow status writer 标记 admitted Seed run failed。
- 边界：不改变 Go admission、object storage、successful parse/segment semantics，不伪造 parse success，不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 已完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_source_status_writer_env_resolution_exception'` 失败，1 failed / 107 deselected。
- 失败原因：`parse_file_activity` 当前直接调用 `_source_file_status_writer_from_env()`，writer factory/env exception 会未结构化冒出，异常文本可夹带 prompt、API key、`credential_ref`、object key、draft 或 manuscript。

Implementation:

- `parse_file_activity` 现在先稳定解析 workflow status writer，再解析 source parse-status writer。
- source parse-status writer env-resolution failure 会写 sanitized `seed.stage.failed` parse event，并返回稳定 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED` / `source file parse status update failed`。
- 如果 workflow status writer 可用，该路径会把 admitted Seed `workflow_runs` 标为 `failed`；公开 result/event/status 不包含底层 writer factory exception。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_source_status_writer_env_resolution_exception'` 通过，1 passed / 107 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_source_status_writer_env_resolution_exception or parse_file_activity_sanitizes_workflow_status_writer_env_resolution_exception or parse_file_activity_marks_workflow_failed_on_terminal_parse_failure or parse_file_activity_fails_closed_when_source_object_integrity_mismatches or temporal_seed_workflow_uses_env_workflow_event_writer'` 通过，5 passed / 103 deselected。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，108 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，208 passed / 3 skipped。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py tasks/refactor-saas-live-progress.md` 无匹配。
- 文档同步后重新验证：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_source_status_writer_env_resolution_exception'` 通过，1 passed / 107 deselected。
- 文档同步后重新验证：`git diff --check` 通过。
- 文档同步后重新验证：`rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

### 2026-07-07 当前会话：P5 Seed parse/segment terminal workflow status handoff

Context:

- Phase 5 下一主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment 的真实 live E2E。
- Go admission / `seed_pipeline_activity` 已能把 admitted Seed run 标为 `queued -> running`；`sequential_reading_activity` terminal failure 和 `finalize_seed_activity` success/failure 已有 workflow status handoff。
- 当前检查发现 parse/segment 早期失败路径虽然会写 sanitized `seed.stage.failed` event 和 source parse failed，但没有同步把已 running 的 `workflow_runs` 标为 failed，真实 E2E 会让 Overview/Seed read side 看到 stuck running。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：`parse_file_activity` 与 `segment_text_activity` 在 terminal failure 时，如果 workflow status writer 可用，写入稳定 public failed status，并在 activity result 中返回 `workflow_status_persisted`。
- 边界：不改变 Go admission、Temporal start、object storage、parse/segment success path、source parse status 更新语义；不伪造 parse/segment success，不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 已完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'marks_workflow_failed_on_terminal_parse_failure or marks_workflow_failed_on_terminal_segment_failure'` 失败，2 failed / 103 deselected。
- 失败原因：`parse_file_activity` 与 `segment_text_activity` 当前不接受 `workflow_status_writer`，terminal parse/segment failure 无法把已 running 的 Seed workflow row 标为 failed。
- 追加 RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'workflow_status_writer_env_resolution_exception'` 失败，2 failed / 105 deselected；新增 env status writer 解析点会裸抛可夹带 prompt/API key/`credential_ref`/object key/draft/manuscript 的异常。

Implementation:

- `parse_file_activity` 与 `segment_text_activity` 新增可选 `workflow_status_writer`，真实 worker path 会从 `DATABASE_URL` 自行解析，local runner 会复用同一个显式 status writer。
- parse/segment terminal failed helper 现在在写 sanitized `seed.stage.failed` event 后，尝试以稳定 public code/message 标记 admitted Seed `workflow_runs` failed，并在 result 中返回 `workflow_status_persisted`。
- workflow status writer env-resolution failure 会收敛为稳定 `WORKFLOW_STATUS_WRITE_FAILED` / `seed workflow status write failed`，不公开底层 factory exception。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'marks_workflow_failed_on_terminal_parse_failure or marks_workflow_failed_on_terminal_segment_failure'` 通过，2 passed / 103 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'workflow_status_writer_env_resolution_exception'` 通过，2 passed / 105 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'marks_workflow_failed_on_terminal_parse_failure or marks_workflow_failed_on_terminal_segment_failure or workflow_status_writer_env_resolution_exception or parse_file_activity_fails_closed_when_source_object_integrity_mismatches or segment_text_activity_sanitizes_untrusted_object_storage_errors_in_result or workflow_status_writer_for_chained_stages or temporal_seed_workflow_uses_env_workflow_event_writer'` 通过，8 passed / 99 deselected。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，107 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，207 passed / 3 skipped。
- `cd apps/api && go test ./internal/workflows -run 'Seed|WorkflowEvent' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `cd /Users/yantianqi/Documents/Noveronline-saas-mainline && git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py backend/tests/test_saas_phase3_rls_schema.py infra/postgres/migrations/0001_core_saas.sql docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/14-data-model.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md tasks/refactor-saas-gpt55-subagent-development-plan.md` 无输出，目标文件尾随空白扫描通过。
- 文档同步后重新验证：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，107 passed。
- 文档同步后重新验证：`cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，207 passed / 3 skipped。
- 文档同步后重新验证：`cd apps/api && go test ./... -count=1` 通过。
- 文档同步后重新验证：`git diff --check` 通过。
- 文档同步后重新验证：`rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 无匹配。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 Go API upload/complete -> Temporal cluster -> Python parse/segment E2E。
- Browser upload/complete、sequential-reading provider/live LLM、扫描/OCR PDF、更完整语义分段、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed later-stage workflow event writer env-resolution redaction

Context:

- Phase 5 下一主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment 的真实 live E2E。
- `parse_file_activity`、`segment_text_activity` 和 `sequential_reading_activity` 的 workflow event writer 环境解析失败已经稳定化；继续检查发现后续 `persist_runtime_facts_activity`、`global_aggregation_activity`、`ontology_activity`、`entity_resolution_activity`、`agent_profile_activity`、`archive_candidate_activity`、`index_assets_activity`、`finalize_seed_activity` 仍会直接解析 workflow event writer。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：后续 Seed stages 在 workflow event writer 环境解析失败时，公开 failed result 返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，不回显底层 exception。
- 边界：不改变 LLM Facility binding、runner/writer 缺失 fail-closed、status writer、event payload 或 completed stage 语义；不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'seed_later_stage_activities_sanitize_workflow_event_writer_env_resolution_exception'` 失败，8 failed / 95 deselected。
- 失败覆盖 `persist_runtime_facts`、`global_aggregation`、`story_ontology`、`entity_resolution`、`agent_profiles`、`archive_candidates`、`index_assets`、`finalize`，当前 `_workflow_event_writer_from_env` 抛出的异常会直接冒出，异常文本可夹带 prompt、API key、`credential_ref`、object key、draft 或 manuscript。

Implementation:

- Added shared workflow event writer resolution failure result helper.
- Wrapped the 8 later Seed stage writer resolution points with stable `WORKFLOW_EVENT_WRITE_FAILED` public result.
- Public failed results preserve only stage/module public metadata and do not include writer factory exception text.

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'seed_later_stage_activities_sanitize_workflow_event_writer_env_resolution_exception'` 通过，8 passed / 95 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'seed_later_stage_activities_sanitize_workflow_event_writer_env_resolution_exception or persist_runtime_facts_activity_writes_structured_canon_without_public_evidence or global_aggregation_activity_fails_closed_without_aggregator or story_ontology_activity_fails_closed_without_runner or entity_resolution_activity_fails_closed_without_runner or agent_profile_activity_fails_closed_without_runner or archive_candidate_activity_fails_closed_without_runner or index_assets_activity_fails_closed_without_indexer or finalize_seed_activity_fails_closed_without_updater'` 通过，16 passed / 87 deselected。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，103 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，203 passed / 3 skipped。
- `cd apps/api && go test ./internal/workflows -run 'Seed|WorkflowEvent' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进 Go API upload/complete -> Temporal cluster -> Python worker parse/segment 的真实 live E2E。
- Browser upload/complete、sequential-reading provider/live LLM、扫描/OCR PDF、更完整语义分段、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：W1-S3 manuscript metadata/export manifest

Context:

- Wave 0 已 verified；W1-S1 explicit draft adoption 和 W1-S2 writer review admission/read metadata 已提交。
- 本轮继续 Wave 1 Writer live closure 的剩余 manuscript/export control-plane gap；仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发。

Scope:

- 目标：新增 `GET /v1/projects/{projectId}/manuscript` 和 `GET /v1/projects/{projectId}/manuscript/export` metadata-only public path。
- 边界：不返回 draft/manuscript 正文、不读取 `content_text`、不生成 fake PDF/DOCX/TXT、不开启旧 LLM env fallback、不声明 live LLM-bound E2E 完成。

RED:

- `cd apps/api && go test ./internal/workflows -run 'Manuscript' -count=1` 失败于缺少 manuscript reader/types。
- `cd apps/api && go test ./internal/httpapi -run 'Manuscript' -count=1` 失败于缺少 HTTP manuscript API types/routes。
- `cd apps/api && go test ./cmd/api -run 'Manuscript|Draft' -count=1` 失败于缺少 `newManuscriptReader`。
- Spec review 后追加 RED：injected metadata/id value 可泄露 private manuscript/prompt，且 `format=pdf/docx/txt` 与 `exported_at` 会暗示 fake content export。

GREEN:

- 新增 `SQLManuscriptReader` / `DisabledManuscriptReader`，DB-backed path 在 tenant context 下只选择 `manuscript_blocks` public metadata，query/scan/rows/close failure 收敛为 `MANUSCRIPT_QUERY_FAILED` 或 `MANUSCRIPT_EXPORT_QUERY_FAILED`。
- 新增 HTTP routes：`GET /v1/projects/{projectId}/manuscript` 和 `/manuscript/export`；无 backend 分别 fail closed 为 `MANUSCRIPT_BACKEND_UNCONFIGURED` / `MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED`。
- HTTP response boundary 对 replacement store 返回的 metadata、ids、status、timestamps、manifest fields 做二次清洗；content-looking formats 全部规范化为 `metadata_manifest`，metadata-only manifest 不设置 `exported_at`。
- `cd apps/api && go test ./internal/workflows ./internal/httpapi -run 'Manuscript|Writer|Draft' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Manuscript|Draft' -count=1` 通过。

Reviews:

- Spec reviewer 首轮要求修复 value-level leakage 和 fake export implication；实现修复后 spec re-review approved。
- Quality reviewer approved；补充提醒 staging 时包含 untracked `apps/api/internal/workflows/writer_manuscript_reader.go`。

Broader verification:

- `cd apps/api && go test ./internal/workflows ./internal/httpapi -run 'Writer|Draft|Trace|LLM|Workflow|Manuscript' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Manuscript|Draft' -count=1` 通过。
- `cd apps/pi-agent-runtime && npm run test && npm run typecheck` 通过，7 files / 38 tests。
- `cd apps/web && npm run test -- --test-name-pattern='Writer|writer'` 通过，35 tests。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/api/internal/workflows/writer.go apps/api/internal/workflows/writer_manuscript_reader.go apps/api/internal/workflows/writer_test.go apps/api/internal/httpapi/server.go apps/api/internal/httpapi/server_test.go apps/api/cmd/api/main.go apps/api/cmd/api/main_test.go docs/refactor-saas/11-writer-workbench.md docs/refactor-saas/14-data-model.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/11-writer-workbench.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- W1 剩余重点转向真实 LLM-bound writer E2E、trace/replay browser verification 和真正内容导出 artifact service。

### 2026-07-07 当前会话：W1-S4 Writer UI manuscript metadata panels

Context:

- W1-S3 已提交 metadata-only manuscript / export manifest Go API。
- 本轮继续 Wave 1 Writer UI Agent，接入 Next Writer client/page/shell，不触碰 Go API 或真正内容导出。

Scope:

- 目标：`apps/web` typed API client 新增 `getProjectManuscript` / `getProjectManuscriptExportManifest`，Writer page 并行加载 summaries，Writer shell 渲染 manuscript metadata 和 export manifest panels。
- 边界：只展示 public metadata 和显式 backend/query errors；不显示 draft/manuscript 正文、`content_text`、prompt/provider response、API key、encrypted credential、`credential_ref`、object key、`exported_at` 或 PDF/DOCX/TXT 内容导出语义。

RED:

- `cd apps/web && npm run test -- --test-name-pattern='Writer|writer|manuscript|Manuscript'` 失败，缺 manuscript client types/routes、Writer page load 和 shell panels。
- Spec review 后追加 RED：Character Console no-`draft_id` guard 被 `source_draft_id` 全局放宽，需改为 scoped slice。
- Quality review 后追加 RED：web manifest type/UI/tests 暴露 backend 不提供的 `block_ids`，且 manuscript client assertions 未 scoped 到新函数。

GREEN:

- Web client 新增 metadata-only manuscript/export manifest types、routes、decoders，使用 `contextHeaders(input)` 和现有 failure decode path。
- Writer page 将 manuscript/export manifest 与 assets/graph/worldline picker data 一起加载并传给 shell。
- Writer shell 新增 `Manuscript metadata` 与 `Export manifest` panels，显示 block id、chapter/source draft id、order、status、word count、timestamps、manifest format/status/counts/generated metadata 和 explicit backend errors。
- Tests 改为 manuscript-specific source slices；Character Console guard 恢复为 scoped strict no-`draft_id`；移除未契合 backend contract 的 `block_ids` type/UI。
- `cd apps/web && npm run test -- --test-name-pattern='Writer|writer|manuscript|Manuscript'` 通过，38 tests。
- `cd apps/web && npm run typecheck` 通过。
- `cd apps/web && npm run test` 通过，38 tests。

Reviews:

- Spec reviewer 首轮要求 scoped Character Console guard；修复后 spec re-review approved。
- Quality reviewer 首轮要求移除 `block_ids` 并 scope manuscript tests；修复后 quality re-review approved。

Broader verification:

- `cd apps/api && go test ./internal/workflows ./internal/httpapi -run 'Writer|Draft|Trace|LLM|Workflow|Manuscript' -count=1` 通过。
- `cd apps/pi-agent-runtime && npm run test && npm run typecheck` 通过，7 files / 38 tests。
- `cd apps/web && npm run test -- --test-name-pattern='Writer|writer|manuscript|Manuscript'` 通过，38 tests。
- `cd apps/web && npm run typecheck` 通过。
- `cd apps/web && npm run test` 通过，38 tests。
- `git diff --check` 通过。

Docs synced:

- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- W1 剩余重点仍是真实 LLM-bound writer E2E、trace/replay browser verification 和真正内容导出 artifact service。

### 2026-07-07 当前会话：Wave 0 governance and acceptance matrix calibration

Scope:

- 文档/治理-only：不修改产品代码，不声明任何新增 runtime 能力完成。
- 对齐 `17-migration-roadmap.md` 到 `DEVELOPMENT_PLAN.md` 的 Phase 0..8。
- 给 coverage matrix 剩余 `planned` 状态补 owner/wave，校准 P6-003 reviewer/dedup 与覆盖矩阵关系。

RED:

- `rg -n "planned|Phase 11|Phase 12|blocked \\|.*verified" docs/refactor-saas tasks` 发现 `17-migration-roadmap.md` 仍有超出 Phase 0..8 的旧后续阶段标题，coverage matrix 多个裸 `planned`，以及 P6-003 `blocked` 行的 verification 文案声称 reviewer/dedup workflows verified。
- `git diff --check` 基线通过。

GREEN:

- 重新运行同一 acceptance search 后，不再出现超出 Phase 0..8 的实际 roadmap 标题，也不再出现 `blocked | ... verified`；coverage matrix 剩余 `planned` 均带 owner/wave，命令文本和状态规则行仅作为治理说明保留。
- `git diff --check` 通过。

Review:

- Spec Reviewer approved Wave 0：Phase 0..8 编号一致，P6-003 不再把 blocked 状态写成 reviewer/dedup verified，hard constraints 未被弱化。
- Quality Reviewer 先要求补 provenance 和 owner：`23-a4-story-graph-runner-fix-handoff.md` 现在明确是历史/外部 handoff note，不是 Wave 0 product-complete 证据，且未记录精确 commit SHA；coverage matrix 的 `project` 行已增加 Wave 2 auth/dev session 与 tenant/project list/create owner。
- Quality Reviewer 复审通过；Wave 0 仍只声明治理校准完成，不声明任何 Story Graph runner 或产品 runtime 新能力完成。

Next:

- Wave 1 继续 Writer live closure；后续实现 wave 不得把 skeleton、fail-closed shell 或 metadata-only path 当作产品闭环。

### 2026-07-07 当前会话：P5 Seed entity_resolution LLM Facility runner skeleton + DB-backed snapshot writer/env wiring

Context:

- 当前 Phase 5 主线仍是补 Seed live object upload -> pipeline E2E，但 `story_ontology` 已具备 LLM Facility runner 和 DB-backed snapshot writer，后续 `entity_resolution` 仍停在 fail-closed shell。
- 本轮继续沿 Seed semantic runner 链路推进，不实现 fake entity merge，不声明 live provider E2E 或完整 Seed pipeline 完成。

Scope:

- 目标：新增 `entity_resolution` 的可注入 LLM Facility runner、私有 snapshot writer contract、DB-backed `seed_entity_resolution_snapshots` target schema/RLS/index/grant，以及 `_entity_resolution_runner_from_env()` 默认装配路径。
- 公开 result / workflow event 只允许 `resolution_snapshot_id`、`model_id`、merged/alias/conflict counts；不返回 resolution body、prompt/response、API key、`credential_ref`、raw text、draft 或 manuscript。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'llm_facility_entity_resolution_runner_persists_schema_valid_snapshot_without_public_body_or_credentials'` 首次因测试 helper 缺失失败；补 `_entity_resolution()` helper 后重新 RED，失败于缺 `LLMFacilityEntityResolutionRunner`。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'postgres_entity_resolution_snapshot_writer_upserts_sanitized_private_snapshot or entity_resolution_runner_from_env_builds_db_backed_llm_facility_runner'` 失败，缺 `PostgresEntityResolutionSnapshotWriter` 且 `_entity_resolution_runner_from_env()` 不接受 live dependency injection。
- `cd backend && env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 .venv/bin/python -m pytest tests/test_saas_phase3_rls_schema.py -q -k 'seed_canon_structured_tables or core_saas_schema_declares_minimum_phase3_tables or tenant_business_tables_have_tenant_id_and_timestamps or rls_is_enabled_for_tenant_scoped_tables'` 失败，target schema 缺 `seed_entity_resolution_snapshots`。

GREEN:

- 新增 `EntityResolutionSnapshotWriter` protocol 和 `LLMFacilityEntityResolutionRunner`，runner 解析 `entity_resolution` module binding、校验 JSON-capable resolution、使用显式 credential 调用 JSON client、schema-validate `merged_entities` / `aliases` / `conflicts`，并在 writer 持久化私有 snapshot 后只返回 public counts。
- 新增 `PostgresEntityResolutionSnapshotWriter`，先设置 app-role tenant context，再 upsert `seed_entity_resolution_snapshots.resolution_jsonb` 和 counts；SQL/commit failure rollback 后稳定为 `ENTITY_RESOLUTION_SNAPSHOT_WRITE_FAILED`。
- `_entity_resolution_runner_from_env()` 现在可在 `DATABASE_URL` 和显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 可用时装配 DB-backed LLM Facility runner。
- target schema 新增 `seed_entity_resolution_snapshots` 表、run/project index、app-role grant 和 tenant RLS policy。

Focused verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'llm_facility_entity_resolution_runner_persists_schema_valid_snapshot_without_public_body_or_credentials or postgres_entity_resolution_snapshot_writer_upserts_sanitized_private_snapshot or entity_resolution_runner_from_env_builds_db_backed_llm_facility_runner'` 通过，3 passed / 116 deselected。
- `cd backend && env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 .venv/bin/python -m pytest tests/test_saas_phase3_rls_schema.py -q -k 'seed_canon_structured_tables or core_saas_schema_declares_minimum_phase3_tables or tenant_business_tables_have_tenant_id_and_timestamps or rls_is_enabled_for_tenant_scoped_tables'` 通过，3 passed / 15 deselected。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，119 passed。
- `cd backend && env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 .venv/bin/python -m pytest tests/test_saas_phase3_rls_schema.py -q` 通过，18 passed。
- `cd apps/api && go test ./internal/workflows -run 'Seed|WorkflowEvent' -count=1` 通过。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_story_graph_workflow.py -q -k 'llm_facility_graph_bond_runner_persists_schema_valid_candidate_metadata_without_public_secrets'` 通过，1 passed / 12 deselected；用于复核一次未复现的 full-suite Story Graph privacy assertion。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_story_graph_workflow.py -q` 通过，13 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，221 passed / 4 skipped。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 后续代码切片可继续补 `character_agent_profile` DB-backed runner/writer/env wiring，或回到 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E。

### 2026-07-07 当前会话：GPT-5.5 subagent development plan

Context:

- 用户要求整理当前未完成任务进度，并设计一个全部使用 `gpt-5.5` 主模型的 subagent 开发计划，用于加速后续开发。
- 本轮只做 coordination/documentation，不声明新的产品代码能力完成。
- 主仓库 `/Users/yantianqi/Documents/Noveronline` 已确认存在大量未提交改动，本轮没有修改主仓库。
- SaaS worktree `/Users/yantianqi/Documents/Noveronline-saas-mainline` 当前分支仍为 `codex/saas-mainline`。

Scope:

- 汇总当前整体进度：产品真实闭环约 `55%-60%`。
- 按 Phase 1-8 梳理未完成重点，保留 Phase 5 Seed live E2E 作为当前主线。
- 新增 GPT-5.5 子智能体派工文档，明确模型配置、Wave 0-3 启动顺序、每个 worker 的目标、可写范围、禁止触碰范围、TDD 起点、验证命令和交接格式。

Docs added:

- `tasks/refactor-saas-gpt55-subagent-development-plan.md`

Verification:

- `rg -n "55%-60%|Wave 1|A1 Seed Live E2E|gpt-5.5|子智能体统一规则|建议首批启动顺序" tasks/refactor-saas-gpt55-subagent-development-plan.md` 通过，核心锚点可检索。
- `rg -n "GPT-5.5 subagent development plan|tasks/refactor-saas-gpt55-subagent-development-plan.md|55%-60%|Wave 1" tasks/refactor-saas-live-progress.md` 通过，实时记录锚点可检索。
- `git diff --check` 通过。
- `rg -n "[[:blank:]]$" tasks/refactor-saas-gpt55-subagent-development-plan.md tasks/refactor-saas-live-progress.md` 无输出，目标文件尾随空白扫描通过。

Next:

- 可按新文档的 Wave 1 启动 A1 Seed Live E2E、A2 Writer Live LLM E2E、A3 Asset Search/Vector、A4 Story Graph Runner 四个 `gpt-5.5` worker。
- Coordinator 继续负责 integration、broader verification 和看板/覆盖矩阵更新。

### 2026-07-07 当前会话：P5 Seed sequential-reading workflow event writer env-resolution redaction

Context:

- Phase 5 下一主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment 的真实 live E2E。
- `seed_pipeline_activity`、`parse_file_activity` 和 `segment_text_activity` 的 workflow event writer 环境解析失败已经稳定化；当前检查发现 `sequential_reading_activity` 仍会在 `_resolved_workflow_event_writer` 环境解析失败时未结构化抛错。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：`sequential_reading_activity` 在 workflow event writer 环境解析失败时，公开 failed result 返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，不回显底层 exception。
- 边界：不改变 LLM Facility binding、reading notes writer、segment object handoff 或 sequential success/fail-closed 语义；不生成 fake reading notes，不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'sequential_reading_activity_sanitizes_workflow_event_writer_env_resolution_exception'` 失败，当前 `_workflow_event_writer_from_env` 抛出的异常会直接从 `sequential_reading_activity` 冒出，异常文本可夹带 prompt、API key、`credential_ref`、object key、draft 或 manuscript。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'sequential_reading_activity_sanitizes_workflow_event_writer_env_resolution_exception'` 通过，1 passed / 94 deselected。

Implementation:

- `sequential_reading_activity` 在 segment references 通过基础校验和 sanitization 后，先解析 workflow event writer。
- workflow event writer 环境解析失败时返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，并只附带 `stage = sequential_reading` 与 `module_key = sequential_reading` public metadata。
- 该切片只收紧 sequential worker 入口失败边界，不改变 LLM Facility binding、reading notes writer、provider、status writer 或 sequential completed/failed event 语义。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'sequential_reading_activity_sanitizes_workflow_event_writer_env_resolution_exception or sequential_reading_activity_fails_closed_without_llm_reader or sequential_reading_activity_uses_default_llm_reader_when_available or temporal_seed_workflow_uses_env_workflow_event_writer'` 通过，4 passed / 91 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，95 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，195 passed / 3 skipped。
- `cd apps/api && go test ./internal/workflows -run 'Seed|WorkflowEvent' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进 Go API upload/complete -> Temporal cluster -> Python worker parse/segment 的真实 live E2E。
- Browser upload/complete、sequential-reading provider/live LLM、扫描/OCR PDF、更完整语义分段、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed segment workflow event writer env-resolution redaction

Context:

- Phase 5 下一主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment 的真实 live E2E。
- `seed_pipeline_activity` 与 `parse_file_activity` 的 workflow event writer 环境解析失败已经稳定化；当前检查发现下一段 `segment_text_activity` 仍会在 `_resolved_workflow_event_writer` 环境解析失败时未结构化抛错，或被误归类为 object storage misconfiguration。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：`segment_text_activity` 在 workflow event writer 环境解析失败时，公开 failed result 返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，不回显底层 exception。
- 边界：不改变 segment success 语义、不伪造 object storage/text segment writer 成功、不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'segment_text_activity_sanitizes_workflow_event_writer_env_resolution_exception'` 失败，当前 `_workflow_event_writer_from_env` 抛出的异常会直接从 `segment_text_activity` 冒出，异常文本可夹带 prompt、API key、`credential_ref`、object key、draft 或 manuscript。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'segment_text_activity_sanitizes_workflow_event_writer_env_resolution_exception_before_artifact_validation'` 失败，unsupported artifact 分支在 artifact type validation 前同样直接冒出 writer env exception。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'segment_text_activity_sanitizes_workflow_event_writer_env_resolution_exception'` 通过，2 passed / 92 deselected。

Implementation:

- `segment_text_activity` 在 source/artifact id 基础校验后先解析 workflow event writer；解析失败时返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`。
- 公开 failed result 只附带 `stage = segment_text` 和 `source_file_id` public metadata，不回显 writer factory exception，也不把 writer env failure 误归类为 object storage misconfiguration。
- 该切片只收紧 segment worker 入口失败边界，不改变 segment success、object storage read/write、text segment writer 或 public stage event 语义。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'segment_text_activity_sanitizes_workflow_event_writer_env_resolution_exception or segment_text_activity_writes_real_segments_without_returning_raw_text or segment_text_activity_splits_long_unheaded_text_into_paragraph_windows or temporal_seed_workflow_uses_env_workflow_event_writer'` 通过，5 passed / 89 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，94 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，194 passed / 3 skipped。
- `cd apps/api && go test ./internal/workflows -run 'Seed|WorkflowEvent' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进 Go API upload/complete -> Temporal cluster -> Python worker parse/segment 的真实 live E2E。
- Browser upload/complete、sequential-reading provider/live LLM、扫描/OCR PDF、更完整语义分段、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed parse workflow event writer env-resolution redaction

Context:

- Phase 5 下一主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment 的真实 live E2E。
- `seed_pipeline_activity` 的 event writer 环境解析失败已经稳定化；当前检查发现更靠近 parse stage 的 `parse_file_activity` 仍会在 `_resolved_workflow_event_writer` 环境解析失败时未结构化抛错。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：`parse_file_activity` 在 workflow event writer 环境解析失败时，公开 failed result 返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，不回显底层 exception。
- 边界：不改变 parse success 语义、不伪造 object storage/artifact/status writer 成功、不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_workflow_event_writer_env_resolution_exception'` 失败，当前 `_workflow_event_writer_from_env` 抛出的异常会直接从 `parse_file_activity` 冒出，异常文本可夹带 prompt、API key、`credential_ref`、object key、draft 或 manuscript。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_sanitizes_workflow_event_writer_env_resolution_exception'` 通过，1 passed / 91 deselected。

Implementation:

- `parse_file_activity` 在校验 `source_file_id` / `source_object_key` 后先规范化 `source_file_id`，再解析 workflow event writer。
- workflow event writer 环境解析失败时返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，并只附带 `stage = parse_file` 与 `source_file_id` public metadata。
- 该切片只收紧 parse worker 入口失败边界，不改变 parse success、object storage、artifact writer、source status writer 或 workflow event completed/failed 语义。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，92 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，192 passed / 3 skipped。
- `cd apps/api && go test ./internal/workflows -run 'Seed|WorkflowEvent' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进 Go API upload/complete -> Temporal cluster -> Python worker parse/segment 的真实 live E2E。
- Browser upload/complete、sequential-reading provider/live LLM、扫描/OCR PDF、更完整语义分段、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed workflow event writer env-resolution redaction

Context:

- Phase 5 下一主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment 的真实 live E2E。
- 当前检查发现 `seed_pipeline_activity` 在未显式注入 workflow event writer 时，会先调用环境解析；如果 `DATABASE_URL` / runtime package / DB writer factory 在解析阶段抛出异常，activity 会在 pending event 写入前未结构化失败。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：Seed worker 的 workflow event writer 环境解析失败时，公开 failed result 仍返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，不回显底层 exception。
- 边界：不改变 Seed success 控制流、不伪造 parse/segment/sequential/finalize 成功、不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'env_resolution_exception'` 失败，当前 `_workflow_event_writer_from_env` 抛出的异常直接冒出，公开失败会夹带 prompt、API key、`credential_ref`、object key、draft 或 manuscript。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'workflow_event_writer_exception or env_resolution_exception'` 通过，2 passed / 89 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，91 passed。

Implementation:

- `seed_pipeline_activity` 现在把 workflow event writer 环境解析和 pending `seed.stage.pending` 写入放进同一个稳定失败边界。
- 环境解析失败或写入失败都返回 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，不让底层 exception 文本进入 activity result。
- 该切片只收紧真实 worker handoff 的失败边界，不改变 queued 控制语义、不启动 fake parse/segment/sequential/finalize success。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，191 passed / 3 skipped。
- `cd apps/api && go test ./internal/workflows -run 'Seed|WorkflowEvent' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进 Go API upload/complete -> Temporal cluster -> Python worker parse/segment 的真实 live E2E。
- Browser upload/complete、sequential-reading provider/live LLM、扫描/OCR PDF、更完整语义分段、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed workflow event write error redaction

Context:

- Phase 5 下一主线仍是 Go API upload/complete -> Temporal cluster -> Python parse/segment 的真实 live E2E。
- 当前检查发现 `seed_pipeline_activity` 在记录 pending workflow event 失败时会把 event writer 的 `str(exc)` 放进 failed result；真实 worker path 中该异常可能夹带 prompt、API key、`credential_ref`、object key、source path、draft 或 manuscript。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：Seed worker 接受 run 但 pending workflow event 写入失败时，公开 failed result 只返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，不回显底层 writer exception。
- 边界：不改变 Seed success 控制流、不伪造 parse/segment/sequential/finalize 成功、不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'sanitizes_workflow_event_writer_exception'` 失败，当前 `seed_pipeline_activity` 把 workflow event writer exception 原文放进 `error.message`，其中可包含 prompt、API key、`credential_ref`、object key、draft 或 manuscript。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'sanitizes_workflow_event_writer_exception'` 通过，1 passed / 89 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，90 passed。

Implementation:

- `seed_pipeline_activity` 的 pending `seed.stage.pending` event 写入失败路径不再使用 `str(exc)` 作为公开 error message。
- 公开 failed result 固定为 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`。
- 该切片只收紧 worker handoff 失败边界，不改变 queued 控制语义、不启动 fake parse/segment/sequential/finalize success。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，190 passed / 3 skipped。
- `cd apps/api && go test ./internal/workflows -run 'Seed|WorkflowEvent' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进 Go API upload/complete -> Temporal cluster -> Python worker parse/segment 的真实 live E2E。
- Browser upload/complete、sequential-reading provider/live LLM、扫描/OCR PDF、更完整语义分段、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-06

Context:

- 对照总纲、交接总结、覆盖矩阵和看板完成一次只读进度盘点。
- 确认主仓库 `/Users/yantianqi/Documents/Noveronline` 很脏，不作为开发位置。
- 确认 SaaS worktree `/Users/yantianqi/Documents/Noveronline-saas-mainline` 在 `codex/saas-mainline`，是 linked worktree。
- 确认主仓库总纲与 SaaS worktree 总纲内容不一致；开发事实以 SaaS worktree 文档为准。

Progress:

- 创建本实时进度记录文档。
- 当前总览同步为产品闭环 `55%-60%`。
- P6-002 Character Console 标记为 metadata skeleton 已落地并硬化，runtime 仍 pending。

Verification:

- 本轮为文档维护，无代码测试。
- `test -s tasks/refactor-saas-live-progress.md` 通过，确认文档已创建且非空。
- `rg -n "当前总览|当前焦点|P6-002 Character Console|工作日志|实时更新规则|下一步" tasks/refactor-saas-live-progress.md` 通过，核心章节可检索。
- `rg -n "refactor-saas-live-progress" tasks/refactor-saas-parallel-board.md` 通过，看板入口已登记。
- `rg -n '[[:blank:]]$' tasks/refactor-saas-live-progress.md tasks/refactor-saas-parallel-board.md` 未发现尾随空白。
- `git diff --check` 通过。

Active slice:

- P6-002 Character Console metadata-only status mutation。
- 目标：新增 tenant-scoped interaction status update，让作者能显式把 interaction 标记为 `active` / `saved` / `archived`。
- 边界：只改 public metadata status；不启动 runtime、不生成 AI reply、不生成 chapter draft、不写 Writer draft/manuscript、不采用 worldline canon。
- 计划验证：先补 Go store / HTTP RED 测试，再实现最小 SQL store、disabled-store 和 HTTP route，最后跑 Character Console 聚焦测试与必要 broader verification。

Progress:

- Go `characterconsole.Store` 新增 `UpdateInteractionStatus`，disabled store 继续 fail closed。
- DB-backed `SQLStore.UpdateInteractionStatus` 通过 tenant-scoped `UPDATE character_interaction_sessions ... RETURNING` 修改 `status/updated_at`，只接受 `active` / `saved` / `archived`。
- Go HTTP 新增 `PATCH /v1/character-interactions/{interactionId}`，使用 `X-Tenant-Id` / path interaction id / header actor/request context，不信任 body tenant。
- Next typed API client、server action 和 Character Console shell 新增 Save interaction / Archive interaction / Restore active metadata-only 表单。

TDD:

- RED：`cd apps/api && go test ./internal/characterconsole -run 'TestSQLStoreRejectsInvalidInteractionStatusMutationBeforeSQL|TestSQLStoreUpdatesInteractionStatusAsMetadataOnly' -count=1` 失败，缺 `UpdateInteractionStatus` 和 `UpdateInteractionStatusInput`。
- RED：`cd apps/api && go test ./internal/httpapi -run TestUpdateCharacterInteractionStatusUsesTenantScopeAndSanitizesResponse -count=1` 失败，缺 `characterconsole.UpdateInteractionStatusInput`。
- GREEN：以上两条 Go 聚焦测试通过。
- RED：`cd apps/web && npm run test -- --test-name-pattern='Character Console route exposes|character console API client'` 失败，缺 `updateCharacterInteractionStatusAction` 和 `UpdateCharacterInteractionStatusInput`。
- GREEN：同一 Web 测试命令通过，34/34 pass。

Verification:

- `cd apps/api && go test ./internal/characterconsole -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Character|Interaction' -count=1` 通过。
- `cd apps/web && npm run test` 通过，34/34 pass。
- `cd apps/api && go test ./... -count=1` 通过。
- `cd apps/web && npm run typecheck` 通过。
- `git diff --check` 通过。

Docs synced:

- `docs/refactor-saas/10-character-console.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Verification:

- `cd apps/api && go test ./internal/httpapi -run TestCreateUploadValidationErrorDoesNotEchoSensitiveUnknownField -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestCreateUpload|TestCompleteUpload|TestListSourceFiles' -count=1` 通过。
- `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Upload|SourceFile|Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Upload|SourceFile|Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Next:

- P5 可继续推进 live object upload / parse / segment / index E2E。
- P6 可继续推进 Worldline live provider/cluster E2E 或真实 Character Console runtime admission；runtime 未实现前继续 fail closed。

Follow-up active slice:

GREEN:

- `cd apps/api && go test ./internal/httpapi -run TestPhase5ValidationErrorsDoNotEchoDecoderDetails -count=1` 通过；Phase 5 request decode failure 现在只返回稳定 `VALIDATION_FAILED` message 和空 details，不再公开 decoder string、unknown field 名称或 Go request struct field 名称。

Docs synced:

- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Verification:

- `cd apps/api && go test ./internal/httpapi -run TestPhase5ValidationErrorsDoNotEchoDecoderDetails -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Asset|Archive|StoryGraph|Graph|Style|Ingestion|Reindex' -count=1` 通过。
- `cd apps/api && go test ./internal/assets -count=1` 通过。
- `cd apps/api && go test ./internal/storygraph -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Asset|Archive|StoryGraph|Graph|Style|Ingestion|Reindex' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Next:

- P5 可继续推进 live object upload / parse / segment / index E2E、hybrid/vector search 或 Asset/Graph live provider E2E。
- P6 可继续推进外部 provider/cluster E2E、prepare runtime、richer director tools 或真实 Character Console runtime admission；runtime 未实现前继续 fail closed。
- P5-001 Source file store error-boundary hardening。
- 目标：DB-backed `sourcefiles.SQLStore` 和 object verifier 普通异常不把底层 driver/storage 文本透出到 store caller / HTTP response，避免 prompt、API key、`credential_ref`、object key 或 source path 泄露。
- 边界：保留现有业务 code、`NOT_FOUND`、`SOURCE_FILE_NOT_UPLOADED` 和 object verifier 已结构化 `AppError`；只稳定普通 query/scan/rows/storage exception message。
- RED：`cd apps/api && go test ./internal/sourcefiles -run TestSQLStoreSanitizesUnexpectedErrorMessages -count=1` 失败，create/complete/object lookup/list/list rows/validate/object verification 路径都会回显 `prompt=hidden api_key=sk-hidden credential_ref=... object_key=...`。
- GREEN：同一测试通过；普通 create/complete/query/storage exception 现在返回稳定 source-file public message，不再透传底层文本。

Docs synced:

- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Verification:

- `cd apps/api && go test ./internal/sourcefiles -run TestSQLStoreSanitizesUnexpectedErrorMessages -count=1` 通过。
- `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Upload|SourceFile|Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Upload|SourceFile|Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Next:

- P5 可继续推进 live object upload / parse / segment / index E2E，或继续补 source-file HTTP error boundary 对替换 store coded/raw errors 的稳定化。
- P6 可继续推进 Worldline live provider/cluster E2E 或真实 Character Console runtime admission；runtime 未实现前继续 fail closed。

Follow-up active slice:

- P5-001 Source file HTTP error-boundary hardening。
- 目标：`POST /v1/projects/{projectId}/uploads`、`POST /v1/uploads/{uploadId}/complete`、`GET /v1/projects/{projectId}/source-files` 的 HTTP 边界不信任替换 store / injected store 的 error message。
- 边界：保留现有 source file error code 与 HTTP status 映射；只把 public message 稳定化，不改变 source file admission、complete、list 或 Seed validation 业务语义。
- RED：`cd apps/api && go test ./internal/httpapi -run TestSourceFileRoutesSanitizeStoreErrorMessagesAtHTTPBoundary -count=1` 失败，三个 route 都把替换 store message 中的 `prompt=hidden api_key=sk-hidden credential_ref=... object_key=...` 写入公开 response。

## 开放风险

| 风险 | 影响 | 当前处理 |
|---|---|---|
| live cluster E2E 尚未完成 | 无法证明 Go API + Postgres + Temporal + runtime + provider 全链路可交付 | 作为 P4/P6/P5 的下一批验收重点 |
| Character Console runtime 仍 pending | 角色控制还不能真实对话或行动；interaction handoff 只能排队真实 Writer run，不能代表 draft 已生成 | 保持 fail-closed，不做 fake AI reply、fake draft id 或 fake convert success |
| Seed/Assets/Graph 多处仍是 skeleton | 主链上传到结构化资产还未完整闭环；readiness snapshot 已写入但还没有 Go read API/dashboard | 优先补 readiness read side，再推进 live upload/parse/segment/index E2E |
| Auth/Billing/Ops 未实质完成 | SaaS 生产化不可交付 | Phase 7/8 前不得宣称产品完成 |

## 下一步

1. P5：补 project readiness snapshot Go read API，使用 header tenant + path project scope，公开响应只返回 snapshot id、run id、counts 和 timestamps。
2. P5：推进 Seed live object upload/complete/parse/segment/index E2E。
3. P6-001：补 Worldline live step execution hardening 或真实 provider/Postgres E2E。
4. P6-002：在 Worldline 事件生产链路稳定后，设计真实 Character Console runtime admission。
5. P4：补 LLM Facility live provider/cluster E2E、quota/billing 聚合和 retry backend。

### 2026-07-06 继续

Active slice:

- P6-002 Character Console -> Writer draft admission bridge。
- 目标：把 `POST /v1/character-interactions/{interactionId}/chapter-drafts` 从 pure pending 推进为显式启动真实 Writer run 的 admission。
- 边界：只读取 tenant-scoped interaction 和 public turn summaries，调用现有 WriterStarter / LLM Facility writer path；不在 Character Console endpoint 内伪造章节草稿、不生成 fake AI reply、不写 manuscript、不采用 worldline canon。
- 计划验证：先改 HTTP RED 测试，确认当前 pending endpoint 失败；再实现最小 route；最后跑 Character/Interaction 聚焦测试、cmd wiring 相关测试、Web client/typecheck 如涉及。

TDD:

- RED：`cd apps/api && go test ./internal/httpapi -run 'TestConvertCharacterInteractionToChapterDraft|TestCharacterInteractionEventsRemainExplicitlyPending' -count=1` 失败，`chapter-drafts` 仍返回 `CHARACTER_CONSOLE_RUNTIME_PENDING`，未进入 Writer run admission。
- GREEN：同一 Go HTTP 聚焦测试通过；后端现在验证 tenant-scoped interaction、解析 `writer_composer` LLM binding、读取 public turn summaries，并通过 `WriterStarter` admission 返回 `run_id/trace_id/workflow_type/status`，不返回 fake `draft_id`。
- RED：`cd apps/web && npm run test -- --test-name-pattern='Character Console route exposes|character console API client'` 失败，Web 仍使用 `draft_id` 和旧 chapter draft created 文案，尚未匹配 Writer run queued admission response。
- GREEN：同一 Web 测试命令通过，34/34 pass；typed client 解码 `run_id/trace_id/workflow_type/status`，server action 和 shell 改为 Writer run queued 文案，不把 admission 说成已生成 draft。

Verification:

- `cd apps/api && go test ./internal/httpapi -run 'TestConvertCharacterInteractionToChapterDraft|TestCharacterInteractionEventsRemainExplicitlyPending' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./internal/characterconsole -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `cd apps/web && npm run test` 通过，34/34 pass。
- `cd apps/web && npm run typecheck` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白；补充覆盖当前 worktree 中 `apps/`、`docs/refactor-saas/`、`tasks/` 仍是 untracked tree 的状态。

Docs synced:

- `docs/refactor-saas/10-character-console.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Follow-up active slice:

- P6-001 Worldline validation error-boundary hardening。
- 目标：Worldline session/step/preparation/adoption/mutation/variable/saved-path 的 JSON decode validation failure 不回显 decoder 原始详情，避免 unknown field 名称如 `api_key` 或 Go struct field 名称进入公开 error details。
- 边界：只收紧 HTTP validation error envelope；不改变 Worldline admission、candidate event、saved path、canon adoption、runtime 或 Character Console 语义。
- RED：`cd apps/api && go test ./internal/httpapi -run TestWorldlineValidationErrorsDoNotEchoDecoderDetails -count=1` 失败，7 个 route 的 response 都包含 `details.error`；session/step/preparation 泄露 `json: unknown field "api_key"`，adoption/mutation/variable/saved-path 泄露 Go decoder type/struct field 文本。
- GREEN：同一聚焦测试通过；Worldline request decode failure 现在只返回稳定 `VALIDATION_FAILED` message 和空 details，不再公开 decoder string、unknown field 名称或 Go request struct field 名称。

Verification:

- `cd apps/api && go test ./internal/httpapi -run TestWorldlineValidationErrorsDoNotEchoDecoderDetails -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Worldline' -count=1` 通过。
- `cd apps/api && go test ./internal/worldline -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Worldline' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Worldline|SourceFile|Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Worldline|SourceFile|Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/09-worldline.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P6 可继续推进外部 provider/cluster E2E、prepare runtime、richer director tools 或真实 Character Console runtime admission；runtime 未实现前继续 fail closed。
- P5 可继续推进 live object upload / parse / segment / index E2E。

Follow-up active slice:

- P4-002 LLM Facility / Trace validation error-boundary hardening。
- 目标：LLM module binding upsert、LLM channel create/update、trace export 的 JSON decode validation failure 不回显 decoder 原始详情，避免 unknown field 名称如 `api_key`、`prompt`、`credential_ref`、draft/manuscript 进入公开 error details。
- 边界：只收紧 HTTP validation error envelope；不改变 LLM channel credential encryption、module binding validation、model sync、trace full-access permission、trace export audit、runtime provider invocation 或 telemetry semantics。
- RED：`cd apps/api && go test ./internal/httpapi -run TestLLMFacilityAndTraceValidationErrorsDoNotEchoDecoderDetails -count=1` 失败，4 个 route 的 response 都包含 `details.error`；module binding / trace export 泄露 `json: unknown field "api_key"`，channel create/update 泄露 `json: unknown field "prompt"`。
- GREEN：同一聚焦测试通过；LLM Facility / Trace request decode failure 现在只返回稳定 `VALIDATION_FAILED` message 和空 details，不再公开 decoder string、unknown field 名称或 Go request struct field 名称。

Docs synced:

- `docs/refactor-saas/12-llm-facility.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Verification:

- `cd apps/api && go test ./internal/httpapi -run TestLLMFacilityAndTraceValidationErrorsDoNotEchoDecoderDetails -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'LLM|Trace' -count=1` 通过。
- `cd apps/api && go test ./internal/llm -count=1` 通过。
- `cd apps/api && go test ./internal/traces -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'LLM|Trace' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Next:

- P4 可继续推进 live provider/cluster E2E、quota/billing 聚合和 real retry backend。
- P5 可继续推进 live object upload / parse / segment / index E2E、hybrid/vector search 或 Asset/Graph live provider E2E。
- P6 可继续推进外部 provider/cluster E2E、prepare runtime、richer director tools 或真实 Character Console runtime admission；runtime 未实现前继续 fail closed。

Follow-up active slice:

- P5-002 Assets / Story Graph validation error-boundary hardening。
- 目标：asset create/search/bulk/adoption/patch、archive memory review、asset ingestion、style extraction、asset reindex、story graph build/bond generation 的 JSON decode validation failure 不回显 decoder 原始详情，避免 unknown field 名称如 `api_key` 进入公开 error details。
- 边界：只收紧 HTTP validation error envelope；不改变 asset mutation/search/review/workflow admission、Story Graph build/bond admission、runtime、LLM provider 或 persistence 语义。
- RED：`cd apps/api && go test ./internal/httpapi -run TestPhase5ValidationErrorsDoNotEchoDecoderDetails -count=1` 失败，11 个 route 的 response 都包含 `details.error` 和 `json: unknown field "api_key"`。

Follow-up active slice:

- P6-001 Worldline validation error-boundary hardening。
- 目标：Worldline session/step/preparation/adoption/mutation/variable/saved-path 的 JSON decode validation failure 不回显 decoder 原始详情，避免 unknown field 名称如 `api_key` 或 Go struct field 名称进入公开 error details。
- 边界：只收紧 HTTP validation error envelope；不改变 Worldline admission、candidate event、saved path、canon adoption、runtime 或 Character Console 语义。
- RED：`cd apps/api && go test ./internal/httpapi -run TestWorldlineValidationErrorsDoNotEchoDecoderDetails -count=1` 失败，7 个 route 的 response 都包含 `details.error`；session/step/preparation 泄露 `json: unknown field "api_key"`，adoption/mutation/variable/saved-path 泄露 Go decoder type/struct field 文本。

Follow-up active slice:

- P5-001 Source file HTTP error-boundary hardening。
- 目标：upload create、upload complete、source file list 和 Seed start source validation 的 HTTP 边界不信任替换 store / injected store 的 error message。
- 边界：保留 source file code 与现有 HTTP status 映射；只稳定 public message，不改变 source file admission、complete、list、Seed source validation 或 object storage verification 业务语义。
- RED：`cd apps/api && go test ./internal/httpapi -run 'TestSourceFileRoutesSanitizeStoreErrorMessagesAtHTTPBoundary|TestStartSeedRunSanitizesSourceFileValidationErrorAtHTTPBoundary' -count=1` 失败，create/complete/list/Seed validation response 都回显 `prompt=hidden api_key=sk-hidden credential_ref=... object_key=...`。
- GREEN：同一测试通过；source file HTTP routes 现在通过专用 error writer 按 code 输出固定 public message。

Docs synced:

- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Verification:

- `cd apps/api && go test ./internal/httpapi -run 'TestSourceFileRoutesSanitizeStoreErrorMessagesAtHTTPBoundary|TestStartSeedRunSanitizesSourceFileValidationErrorAtHTTPBoundary' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestCreateUpload|TestCompleteUpload|TestListSourceFiles|TestStartSeedRun' -count=1` 通过。
- `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Upload|SourceFile|Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Upload|SourceFile|Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Next:

- P5 可继续推进 live object upload / parse / segment / index E2E，或继续检查 Assets/Story Graph/Worldline 公开错误边界是否还有替换 store message 泄漏。
- P6 可继续推进 Worldline live provider/cluster E2E 或真实 Character Console runtime admission；runtime 未实现前继续 fail closed。

Follow-up active slice:

- P5-001 Upload admission validation error hardening。
- 目标：`POST /v1/projects/{projectId}/uploads` 的 JSON decode validation failure 不回显 decoder 原始错误，避免 unknown field 名称如 `api_key`、`prompt`、`credential_ref`、draft/manuscript 出现在公开 error details。
- 边界：只收紧 upload admission validation error；不改变 upload metadata admission、object storage verification、complete upload、Seed workflow admission 或任何 parse/segment/runtime 行为。
- RED：`cd apps/api && go test ./internal/httpapi -run TestCreateUploadValidationErrorDoesNotEchoSensitiveUnknownField -count=1` 失败，公开 response details 包含 `json: unknown field "api_key"`。
- GREEN：同一测试通过；handler 现在返回稳定 `VALIDATION_FAILED` / `invalid upload payload`，details 为空。

Docs synced:

- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Follow-up active slice:

- P1/P4 Writer start options authority/privacy hardening。
- 目标：普通 `POST /v1/projects/{projectId}/writer-runs` 在进入 `WriterStarter` 前清洗用户提交的 `options`，避免 body-provided `tenant_id` / `project_id`、prompt/body/source/candidate/draft/manuscript 或 credential 字段进入 runtime handoff。
- 边界：不移除服务端解析后补入的 internal `llm_resolution.credential_ref`，不改变 Writer runtime provider handoff，不伪造 draft，不写 manuscript；只收紧 HTTP handoff 边界。
- RED：`cd apps/api && go test ./internal/httpapi -run TestStartWriterRunSanitizesUntrustedOptionsBeforeStarter -count=1` 失败，`WriterStarter` input options 仍包含 `tenant_id`、`project_id`、`prompt`、`body_text`、`source_material`、嵌套 `api_key` 和 `candidate_body`。
- GREEN：同一测试通过；handler 现在先递归清洗用户 options，再补入可信 `module_key` 与服务端解析出的 `llm_resolution`。

Verification:

- `cd apps/api && go test ./internal/httpapi -run TestStartWriterRunSanitizesUntrustedOptionsBeforeStarter -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestStartWriterRun' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/api/internal/httpapi/server.go apps/api/internal/httpapi/server_test.go docs/refactor-saas/14-data-model.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Follow-up active slice:

- P1/P4 Writer start validation error hardening。
- 目标：普通 `POST /v1/projects/{projectId}/writer-runs` 的 JSON decode validation failure 不回显 decoder 原始错误，避免 unknown field 名称如 `api_key`、`prompt`、`credential_ref`、draft/manuscript 出现在公开 error details。
- 边界：只收紧 Writer start validation error；不改变 LLM binding resolution、WriterStarter admission、runtime payload 或 draft/manuscript 行为。
- RED：`cd apps/api && go test ./internal/httpapi -run TestStartWriterRunValidationErrorDoesNotEchoSensitiveUnknownField -count=1` 失败，公开 response details 包含 `json: unknown field "api_key"`。
- GREEN：同一测试通过；handler 现在返回稳定 `VALIDATION_FAILED` / `invalid writer run payload`，details 为空。

Verification:

- `cd apps/api && go test ./internal/httpapi -run TestStartWriterRunValidationErrorDoesNotEchoSensitiveUnknownField -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestStartWriterRun' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。

Docs synced:

- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Follow-up active slice:

- P5-001 Seed run options authority/privacy hardening。
- 目标：`POST /v1/projects/{projectId}/seed-runs` 在进入 `SeedStarter` 前递归清洗 body `options`，避免 body-provided `tenant_id` / `project_id`、prompt/body/source/candidate/draft/manuscript 或 credential 字段进入 Seed workflow handoff。
- 边界：保留 `upload_id` 经过 source file scope validation 后进入 workflow；保留安全 public analysis options；不改变 object storage metadata handoff、workflow admission、parse/segment/LLM runner 行为。
- RED：`cd apps/api && go test ./internal/httpapi -run TestStartSeedRunCarriesTenantProjectUploadActorAndRequestContext -count=1` 失败，`SeedStarter` input options 仍包含 `tenant_id`、`project_id`、`prompt`、`source_material`、`draft`、嵌套 `api_key` 和 `credential_ref`。
- GREEN：同一测试通过；handler 现在使用通用 workflow options sanitizer，Seed/Writer start 共用同一类 high-risk key 清理规则。

Verification:

- `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRunCarriesTenantProjectUploadActorAndRequestContext|TestStartWriterRunSanitizesUntrustedOptionsBeforeStarter' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。

Docs synced:

- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Follow-up active slice:

- P5-001 Seed run validation error hardening。
- 目标：`POST /v1/projects/{projectId}/seed-runs` 的 JSON decode validation failure 不回显 decoder 原始错误，避免 unknown field 名称如 `api_key`、`prompt`、`credential_ref`、draft/manuscript 出现在公开 error details。
- 边界：只收紧 Seed run start validation error；不改变 source upload validation、workflow admission、Seed runtime payload 或任何 parse/segment/LLM runner 行为。
- RED：`cd apps/api && go test ./internal/httpapi -run TestStartSeedRunValidationErrorDoesNotEchoSensitiveUnknownField -count=1` 失败，公开 response details 包含 `json: unknown field "api_key"`。
- GREEN：同一测试通过；handler 现在返回稳定 `VALIDATION_FAILED` / `invalid seed run payload`，details 为空。

Verification:

- `cd apps/api && go test ./internal/httpapi -run TestStartSeedRunValidationErrorDoesNotEchoSensitiveUnknownField -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。

Docs synced:

- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Follow-up active slice:

- P1/P4 Writer admission options privacy hardening。
- 目标：DB-backed Writer admission 持久化 `writer_runs.options_jsonb` 前递归清理 prompt/body/content/draft/manuscript/source/raw/candidate/event 等 high-risk option keys，不只清理 credential-like keys。
- 边界：不改变 Writer runtime payload，不伪造 draft，不影响 internal `credential_ref` 传给 worker 的路径；只收紧 admission store 的持久化隐私边界。
- RED：`cd apps/api && go test ./internal/workflows -run TestSQLWriterAdmissionStorePersistsWorkflowAndWriterRowsWithoutCredentialRefs -count=1` 失败，`writer_runs.options_jsonb` SQL args 仍包含 `prompt` / `body_text` / `draft` / `source_material` / `candidate_body`。
- GREEN：同一测试通过，`sanitizeWriterAdmissionValue` 现在递归移除 credential、prompt/response/body/content、source/material/raw、candidate/event body、draft/manuscript keys，同时保留 `module_key` 和 public turn summary metadata。

Verification:

- `cd apps/api && go test ./internal/workflows -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `cd apps/web && npm run test` 通过，34/34 pass。
- `cd apps/web && npm run typecheck` 通过。

Docs synced:

- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Follow-up active slice:

- P6-002 Character Console Writer handoff guardrail。
- 目标：没有任何 saved public turn 的 interaction 不能排队 Writer run，避免空材料转章节被误认为真实 draft handoff。
- RED：`cd apps/api && go test ./internal/httpapi -run TestConvertCharacterInteractionToChapterDraftRequiresPublicTurns -count=1` 失败，当前 endpoint 对空 turns 仍返回 202 queued。
- GREEN：同一测试通过；handler 现在先读取 sanitized public turns，空列表返回 `409 CHARACTER_INTERACTION_TURNS_REQUIRED`，且不解析 LLM binding、不调用 `WriterStarter`。

Verification:

- `cd apps/api && go test ./internal/httpapi -run 'TestConvertCharacterInteractionToChapterDraft|TestCharacterInteractionEventsRemainExplicitlyPending' -count=1` 通过。
- `cd apps/api && go test ./internal/characterconsole -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `cd apps/web && npm run test` 通过，34/34 pass。
- `cd apps/web && npm run typecheck` 通过。

Docs synced:

- `docs/refactor-saas/10-character-console.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Follow-up active slice:

- P6-002 Character Console Writer handoff material guardrail。
- 目标：有 turn row 但没有任何 public turn summary material 时，也不能排队 Writer run，避免空白回合被当作真实转换素材。
- 边界：只检查已经保存的 public turn metadata；不读取 raw text、不生成 AI reply、不写 draft/manuscript、不启动 Character Console runtime。
- RED：`cd apps/api && go test ./internal/httpapi -run TestConvertCharacterInteractionToChapterDraftRequiresPublicTurnSummaryMaterial -count=1` 失败，空白 summary 的 turn 仍返回 202 queued。
- GREEN：同一聚焦行为随相邻 handoff 用例通过；handler 现在会先过滤出有非空 public summary 的 turns，空 material 以 `409 CHARACTER_INTERACTION_TURNS_REQUIRED` fail closed，且不调用 `WriterStarter`。

Verification:

- `cd apps/api && go test ./internal/httpapi -run 'TestConvertCharacterInteractionToChapterDraft|TestCharacterInteractionEventsRemainExplicitlyPending' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./internal/characterconsole -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `cd apps/web && npm run test` 通过，34/34 pass。
- `cd apps/web && npm run typecheck` 通过。

Docs synced:

- `docs/refactor-saas/10-character-console.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Follow-up active slice:

- P6-001 Worldline validation error-boundary hardening。
- 目标：Worldline session/step/preparation/adoption/mutation/variable/saved-path 的 JSON decode validation failure 不回显 decoder 原始详情，避免 unknown field 名称如 `api_key` 或 Go struct field 名称进入公开 error details。
- 边界：只收紧 HTTP validation error envelope；不改变 Worldline admission、candidate event、saved path、canon adoption、runtime 或 Character Console 语义。
- RED：`cd apps/api && go test ./internal/httpapi -run TestWorldlineValidationErrorsDoNotEchoDecoderDetails -count=1` 失败，7 个 route 的 response 都包含 `details.error`；session/step/preparation 泄露 `json: unknown field "api_key"`，adoption/mutation/variable/saved-path 泄露 Go decoder type/struct field 文本。
- GREEN：同一聚焦测试通过；Worldline request decode failure 现在只返回稳定 `VALIDATION_FAILED` message 和空 details，不再公开 decoder string、unknown field 名称或 Go request struct field 名称。

Verification:

- `cd apps/api && go test ./internal/httpapi -run TestWorldlineValidationErrorsDoNotEchoDecoderDetails -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Worldline' -count=1` 通过。
- `cd apps/api && go test ./internal/worldline -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Worldline' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Worldline|SourceFile|Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Worldline|SourceFile|Seed|Writer|Workflow|Character|Interaction' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/09-worldline.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P6 可继续推进外部 provider/cluster E2E、prepare runtime、richer director tools 或真实 Character Console runtime admission；runtime 未实现前继续 fail closed。
- P5 可继续推进 live object upload / parse / segment / index E2E。

Follow-up active slice:

- P4-002 LLM Facility HTTP error-message boundary hardening。
- 目标：LLM resolver、module binding store、catalog/settings reader、channel store、model syncer 和 telemetry reader 的 HTTP error response 不回显不可信 store/driver/provider message，避免 prompt/API key/`credential_ref`/draft/manuscript 泄露。
- 边界：只收紧 Go HTTP public error message；不改变 LLM binding/channel/catalog/settings/model sync/telemetry business semantics、status code mapping、provider invocation 或 runtime payload。
- RED：`cd apps/api && go test ./internal/httpapi -run TestLLMFacilityRoutesSanitizeStoreErrorMessagesAtHTTPBoundary -count=1` 失败，11 个 route 都回显 `driver exploded prompt=hidden api_key=sk-hidden credential_ref=cred-hidden draft=private manuscript=private`。
- GREEN：同一聚焦测试通过；LLM HTTP error boundary 现在按 error code 输出固定 public message，不再公开 resolver/store/driver/provider exception text。

Docs synced:

- `docs/refactor-saas/12-llm-facility.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Verification:

- `cd apps/api && go test ./internal/httpapi -run TestLLMFacilityRoutesSanitizeStoreErrorMessagesAtHTTPBoundary -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'LLM|Trace' -count=1` 通过。
- `cd apps/api && go test ./internal/llm -count=1` 通过。
- `cd apps/api && go test ./internal/traces -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'LLM|Trace' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `gofmt -l apps/api/internal/httpapi/server.go apps/api/internal/httpapi/server_test.go` 无输出。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Follow-up active slice:

- P5-001 Source file app-role RLS tenant-context hardening。
- 目标：DB-backed `sourcefiles.SQLStore` 在真实 app-role/Postgres RLS 路径下读写 `source_files` 前设置 tenant context，覆盖 upload admission、object metadata lookup、upload complete、source-file list 和 Seed source validation。
- 边界：只收紧 Go source file DB path 的 tenant-context/transaction handling；不改变 upload metadata contract、object storage verification、Seed workflow payload、parse/segment/LLM runner 行为，也不伪造 browser upload 或 Seed 成功。
- RED：`cd apps/api && go test ./internal/sourcefiles -run 'TestSQLStore(UsesTenantContextQueryerForReadAndWritePaths|ReturnsRowsCloseErrorsAsStableQueryFailures|AbortsTenantContextRowsOnScanFailure)' -count=1` 失败：所有路径 tenant context call 为 0，rows close/commit error 和 scan abort 期望未满足。
- GREEN：同一聚焦测试通过；`sourcefiles.SQLDBQueryer` 现在在 tenant-scoped transaction 中调用 `app_set_tenant_context`，store 在 queryer 支持时走 tenant-aware path，rows close/commit error 稳定为 source-file public error，scan failure 会 abort tenant-scoped rows/transaction。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Verification:

- `cd apps/api && go test ./internal/sourcefiles -run 'TestSQLStore(UsesTenantContextQueryerForReadAndWritePaths|ReturnsRowsCloseErrorsAsStableQueryFailures|AbortsTenantContextRowsOnScanFailure)' -count=1` 通过。
- `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Upload|SourceFile|Seed' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Upload|SourceFile|Seed' -count=1` 通过。
- `gofmt -l apps/api/internal/sourcefiles/source_files.go apps/api/internal/sourcefiles/source_files_test.go` 无输出。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Follow-up active slice:

- P5-001 Source file object integrity verification。
- 目标：配置 object verifier 时，`POST /v1/uploads/{uploadId}/complete` 不能只因对象存在就标记 `uploaded`；对象大小和 sha256 证据必须与 admission metadata 匹配。
- 边界：只加固 MinIO/S3-compatible `StatObject` metadata verification；不实现 browser direct upload、不读取/返回 raw file content、不生成 Seed parse/segment 成功、不改 Seed workflow payload public boundary。
- RED：`cd apps/api && go test ./internal/sourcefiles -run 'TestMinIOObjectVerifier(RejectsMismatchedObjectSize|RejectsMismatchedSHA256Metadata|AcceptsMatchingObjectMetadata)' -count=1` 失败；大小不匹配和 sha256 metadata 不匹配时当前 verifier 仍返回 nil。
- GREEN：同一聚焦测试通过；MinIO object verifier 现在会比较 `ObjectInfo.Size`，并要求 `ChecksumSHA256` / user metadata / object metadata 中的 sha256 证据与 admission `sha256` 匹配，失败时返回稳定 `SOURCE_FILE_STORAGE_VERIFY_FAILED`，不公开 object key 或 hash。
- Package check：`cd apps/api && go test ./internal/sourcefiles -count=1` 通过。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Verification:

- `cd apps/api && go test ./internal/sourcefiles -run 'TestMinIOObjectVerifier(RejectsMismatchedObjectSize|RejectsMismatchedSHA256Metadata|AcceptsMatchingObjectMetadata)' -count=1` 通过。
- `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Upload|SourceFile|Seed' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Upload|SourceFile|Seed' -count=1` 通过。
- `gofmt -l apps/api/internal/sourcefiles/object_verifier.go apps/api/internal/sourcefiles/object_verifier_test.go` 无输出。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Next:

- P5 继续推进 browser/direct upload handoff 或 live object upload -> parse -> segment E2E，让新 size/hash verifier 在真实对象上传链路里被验收。

Follow-up active slice:

- P5-001 Source file object checksum request hardening。
- 目标：`CompleteUpload` 的 MinIO/S3-compatible verifier 要在 `StatObject` 时显式请求 checksum metadata，避免真实 S3-compatible backend 因未开启 checksum mode 而无法返回 `ChecksumSHA256`。
- 边界：只设置 `StatObjectOptions.Checksum`；不改变 public upload API、不返回 presigned URL、不读取 raw file content、不伪造 Seed 成功。
- RED：`cd apps/api && go test ./internal/sourcefiles -run TestMinIOObjectVerifierRequestsChecksumMetadata -count=1` 失败，recorded `StatObjectOptions.Checksum=false`。
- GREEN：同一聚焦测试通过；object verifier 现在以 `minio.StatObjectOptions{Checksum: true}` 调用 `StatObject`，让真实 S3-compatible backend 有机会返回 checksum metadata 参与 admission sha256 校验。
- Package check：`cd apps/api && go test ./internal/sourcefiles -count=1` 通过。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Verification:

- `cd apps/api && go test ./internal/sourcefiles -run TestMinIOObjectVerifierRequestsChecksumMetadata -count=1` 通过。
- `cd apps/api && go test ./internal/sourcefiles -run 'TestMinIOObjectVerifier(RequestsChecksumMetadata|RejectsMismatchedObjectSize|RejectsMismatchedSHA256Metadata|AcceptsMatchingObjectMetadata)' -count=1` 通过。
- `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Upload|SourceFile|Seed' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Upload|SourceFile|Seed' -count=1` 通过。
- `gofmt -l apps/api/internal/sourcefiles/object_verifier.go apps/api/internal/sourcefiles/object_verifier_test.go` 无输出。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Next:

- P5 继续推进 browser/direct upload handoff 或 live object upload -> parse -> segment E2E；当前 verifier 已能在 complete 前请求并校验 checksum metadata。

Follow-up active slice:

- P5-001 Source file server-side object upload handoff。
- 目标：在 metadata admission 与 complete verification 之间补真实对象写入入口，让客户端可以把 TXT/MD/PDF bytes 交给 API，API 内部写入 MinIO/S3-compatible storage，而不暴露 object key、presigned URL 或 object credentials。
- 边界：只新增后端 `PUT /v1/uploads/{uploadId}/object`、SQL metadata lookup、MinIO object writer 和 cmd wiring；不实现 browser file picker UI、不自动 complete、不启动 Seed workflow、不读取/返回 raw content、不生成 fake parse/segment 成功。
- RED：`cd apps/api && go test ./internal/sourcefiles -run 'Test(SQLStoreGetsUploadObjectMetadataWithTenantScope|MinIOObjectWriter)' -count=1` 失败，缺 `GetUploadObject`、`ObjectWriteInput` 和 `minioObjectWriter`。
- RED：`cd apps/api && go test ./internal/httpapi -run 'TestUploadSourceObject' -count=1` 失败，缺 `SourceFileObjectWriter` config、object upload route 和 sourcefiles object metadata types。
- RED：`cd apps/api && go test ./cmd/api -run 'ObjectWriter|ObjectVerifier' -count=1` 失败，缺 `newObjectWriterFromEnv`。
- GREEN：上述聚焦测试通过；`PUT /v1/uploads/{uploadId}/object` 现在先检查 object writer 配置，再通过 tenant/upload scoped store lookup 获取内部 object metadata，object writer spool body 到临时文件并校验 exact size/SHA-256，匹配后才 `PutObject` 并写 `sha256` metadata。公开 response 只包含 `upload_id` 和 `status=stored`。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Verification:

- `cd apps/api && go test ./internal/sourcefiles -run 'Test(SQLStoreGetsUploadObjectMetadataWithTenantScope|MinIOObjectWriter)' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'TestUploadSourceObject' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'ObjectWriter|ObjectVerifier' -count=1` 通过。
- `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Upload|SourceFile|Seed' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Upload|SourceFile|Seed|ObjectWriter|ObjectVerifier' -count=1` 通过。
- `gofmt -l ...touched Go files...` 无输出。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Next:

- P5 继续补 browser UI file picker / web API client 对 `PUT /v1/uploads/{uploadId}/object` 的调用，并做 live object upload -> complete -> parse/segment E2E。

Follow-up active slice:

- P5-001 browser file picker / Web API client object upload handoff。
- 目标：把 Next `/overview` 的浏览器文件选择表单接到 `PUT /v1/uploads/{uploadId}/object`，让 metadata admission 与 complete verification 之间可以通过 Web shell 上传真实 TXT/MD/PDF bytes。
- 边界：只新增 typed Web API client、Overview server action 和 UI file input；不自动 complete、不启动 Seed workflow、不读取/显示 raw content、不返回 object key/presigned URL/credentials、不生成 fake parse/segment 成功。
- RED：`cd apps/web && npm run test -- --test-name-pattern="Overview|source file|Seed"` 失败，Next page 缺 `uploadSourceFileObject` / `uploadSourceObjectAction`，Web API client 缺 `UploadSourceFileObjectInput` / `SourceFileObjectUploadSummary` / `PUT /object`，Overview shell 缺 `Upload object` 文件表单。
- GREEN：同一聚焦测试通过，34/34 pass；`apps/web/lib/api.ts` 现在提供 `uploadSourceFileObject`，只发送 tenant/user headers、path upload id 和 selected `Blob` body，解析公开 `upload_id/status`；Overview server action 读取 `FormData` 文件并回显 sanitized status；shell 新增 Upload object 表单。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Verification:

- `cd apps/web && npm run test -- --test-name-pattern="Overview|source file|Seed"` 通过，34/34 pass。
- `cd apps/web && npm run test` 通过，34/34 pass。
- `cd apps/web && npm run typecheck` 通过。
- `cd apps/web && npm run build` 通过；Next 输出了现有 `@next/swc-darwin-arm64` native package load warning，但自动 fallback 并完成 production build。
- `cd apps/web && npm run dev -- --hostname 127.0.0.1 --port 3999` 已启动；`curl -s http://127.0.0.1:3999/demo/projects/demo-project/overview` 可渲染 `Upload object` file input/form。当前未同步启动 Go API，source/Seed 列表显示 fail-closed/invalid API response 状态。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Next:

- P5 继续做 live object upload -> complete -> parse/segment E2E；Web handoff 已接上，但还没有声明真实 MinIO/Postgres/Python parse/segment 闭环 verified。

Follow-up active slice:

- P5-001 Python Seed parse/segment object-storage failure result hardening。
- 目标：`parse_file_activity` / `segment_text_activity` 在 source/artifact object read/write、UTF-8 decode 或 segment persistence 失败时，公开 `result.error.message` 只返回稳定 public message，不透传底层 storage/driver exception 中的 prompt、API key、`credential_ref`、object key、raw manuscript/draft 文本。
- 边界：只收紧 Python Seed activity failed result/error boundary；不改变成功 parse/segment 输出、不实现 PDF parsing、不启动 Seed LLM runner、不伪造 parse/segment 成功。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "sanitizes_untrusted_object_storage_errors"` 失败；parse source read 和 segment artifact read 的 `error.message` 仍回显 `prompt=hidden api_key=sk-hidden credential_ref=... object_key=... source_text=private raw manuscript ...`。
- GREEN：同一聚焦测试通过，2 passed；Python Seed parse/segment 的 object read/write/decode 和 segment persistence 失败结果现在只返回固定 public message，segment object write exception 也会结构化为 `TEXT_SEGMENT_WRITE_FAILED`，不再裸抛底层异常。

Verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "sanitizes_untrusted_object_storage_errors"` 通过，2 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，62 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_sequential_reader.py -q` 通过，13 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，160 passed, 1 skipped。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 继续推进 live object upload -> complete -> parse/segment/index E2E；当前只声明 Python Seed failed result/error boundary hardening verified，不声明真实 MinIO/Postgres/Temporal/Python 全链路已完成。

Follow-up active slice:

- P5-001 Python Seed parse/segment DB writer app-role tenant-context hardening。
- 目标：为真实 Postgres/app-role parse/segment E2E 铺路，`PostgresWorkflowEventWriter`、`PostgresTextArtifactWriter`、`PostgresTextSegmentWriter` 在写 `workflow_events`、`project_text_artifacts`、`text_segments` 前必须设置 `app_set_tenant_context(tenant_id, project_id, false)`，否则 RLS live path 不能可靠写入。
- 边界：只收紧 Python Seed parse/segment 相关 DB writer 的 tenant context；不改变 Go upload API、不启动 fake Seed success、不实现 PDF 或 LLM stages。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_workflow_event_writer_inserts_sanitized_workflow_event or postgres_text_artifact_writer_upserts_sanitized_artifact_reference or postgres_text_segment_writer_upserts_sanitized_segments"` 失败；三条 writer 测试都显示第一条 SQL 是业务 insert，而不是 `SELECT app_set_tenant_context(...)`。
- GREEN：同一聚焦测试通过，3 passed；三个 writer 现在在业务 insert/upsert 前设置 `app_set_tenant_context(%s::uuid, %s::uuid, false)`。

Verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_workflow_event_writer_inserts_sanitized_workflow_event or postgres_text_artifact_writer_upserts_sanitized_artifact_reference or postgres_text_segment_writer_upserts_sanitized_segments"` 通过，3 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，62 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_sequential_reader.py -q` 通过，13 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，160 passed, 1 skipped。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment/index E2E；当前只声明 Python Seed DB writer app-role tenant-context hardening verified，不声明完整上传解析分段闭环已完成。

Follow-up active slice:

- P5-001 Python Seed parse/segment DB writer rollback hardening。
- 目标：为真实 Postgres/app-role parse/segment E2E 铺路，`PostgresWorkflowEventWriter`、`PostgresTextArtifactWriter`、`PostgresTextSegmentWriter` 在业务 SQL execute 或 commit failure 时必须显式 rollback 当前 connection，并继续抛出原错误，避免 RLS live path 留下未回滚的 partial transaction。
- 边界：只收紧 Python Seed parse/segment 相关 DB writer 的失败事务处理；不改变 Go upload API、不吞错、不启动 fake Seed success、不实现 PDF 或 LLM stages。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "seed_parse_segment_postgres_writers_roll_back_on_database_failure"` 失败；workflow event writer 的 failure path 中 `rolled_back` 仍为 false。
- GREEN：同一聚焦测试通过，1 passed；三个 writer 现在在 SQL/commit failure 时 rollback，且继续抛出原错误，由 activity 层保持稳定 failed result/event。

Verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "seed_parse_segment_postgres_writers_roll_back_on_database_failure"` 通过，1 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，63 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_sequential_reader.py -q` 通过，13 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，161 passed, 1 skipped。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment/index E2E；当前只声明 Python Seed parse/segment DB writer rollback hardening verified，不声明完整上传解析分段闭环已完成。

Follow-up active slice:

- P5-001 Python Seed sequential-reading notes writer app-role/rollback hardening。
- 目标：为 parse/segment 后续的真实 sequential reading persistence 铺路，`PostgresReadingNotesWriter` 在写 `reading_passes` / `reading_segment_notes` 前必须设置 `app_set_tenant_context(tenant_id, project_id, false)`；业务 SQL execute 或 commit failure 必须 rollback 当前 connection 并继续抛错，避免 RLS live path 误报成功或留下 partial transaction。
- 边界：只收紧 Python Seed sequential-reading notes public metadata writer；不启动 fake LLM reader、不生成 mock reading notes、不改变 Go upload API、不实现完整 Seed LLM provider E2E。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_reading_notes_writer_upserts_sanitized_pass_and_notes or postgres_reading_notes_writer_rolls_back_on_database_failure"` 失败；成功路径只有两条业务 SQL、缺少 tenant context，失败路径 `rolled_back` 仍为 false。
- GREEN：同一聚焦测试通过，2 passed；reading notes writer 现在先设置 tenant context，失败时 rollback 后继续抛错，由 activity 层保持稳定 failed result/event。

Verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_reading_notes_writer_upserts_sanitized_pass_and_notes or postgres_reading_notes_writer_rolls_back_on_database_failure"` 通过，2 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，64 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_sequential_reader.py -q` 通过，13 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，162 passed, 1 skipped。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading/index E2E；当前只声明 Python Seed reading notes writer app-role/rollback hardening verified，不声明完整上传解析分段或 Seed LLM live provider 闭环已完成。

Follow-up active slice:

- P5-001 Python Seed runtime facts canon writer app-role/rollback hardening。
- 目标：为 sequential reading 后续的真实 structured canon persistence 铺路，`PostgresRuntimeFactsWriter` 在读取 `reading_segment_notes` 或写 Seed/Canon target tables 前必须设置 `app_set_tenant_context(tenant_id, project_id, false)`；业务 SQL execute 或 commit failure 必须 rollback 当前 connection 并继续抛错，避免 RLS live path 误报成功或留下 partial transaction。
- 边界：只收紧 Python Seed runtime facts structured canon writer；不启动 fake Seed success、不伪造 canon facts、不改变 Go upload API、不实现完整 Seed live E2E。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_runtime_facts_writer_sets_tenant_context_before_canon_writes or postgres_runtime_facts_writer_rolls_back_on_database_failure"` 失败；空 facts 路径没有执行 tenant context，带 segment summary 的 failure 未触发 rollback。
- GREEN：同一聚焦测试通过，2 passed；runtime facts writer 现在先设置 tenant context，失败时 rollback 后继续抛错，由 `persist_runtime_facts_activity` 保持稳定 failed result/event。

Verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_runtime_facts_writer_sets_tenant_context_before_canon_writes or postgres_runtime_facts_writer_rolls_back_on_database_failure"` 通过，2 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，66 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_sequential_reader.py -q` 通过，13 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，164 passed, 1 skipped。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts/index E2E；当前只声明 Python Seed runtime facts canon writer app-role/rollback hardening verified，不声明完整上传解析分段、Seed LLM live provider 或 structured canon 全链路闭环已完成。

Follow-up active slice:

- P5-001 Python Seed asset indexer app-role/rollback hardening。
- 目标：为 runtime facts 后续的真实 index assets persistence 铺路，`PostgresSeedAssetIndexer` 在把 Seed canon facts 投射到 `assets` / `global_search_index` 前必须设置 `app_set_tenant_context(tenant_id, project_id, false)`；业务 SQL execute 或 commit failure 必须 rollback 当前 connection 并继续抛错，避免 RLS live path 误报成功或留下 partial transaction。
- 边界：只收紧 Python Seed asset/search projection writer；不启动 fake Seed success、不伪造 embeddings、不改变 Go upload API、不实现完整 Seed live E2E。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_seed_asset_indexer_projects_canon_into_assets_and_search or postgres_seed_asset_indexer_rolls_back_on_database_failure"` 失败；成功路径没有执行 tenant context，业务 SQL failure 后 `rolled_back` 仍为 false。
- GREEN：同一聚焦测试通过，2 passed；asset indexer 现在先设置 tenant context，失败时 rollback 后继续抛错，由 `index_assets_activity` 保持稳定 failed result/event。

Verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_seed_asset_indexer_projects_canon_into_assets_and_search or postgres_seed_asset_indexer_rolls_back_on_database_failure"` 通过，2 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，67 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_sequential_reader.py -q` 通过，13 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，165 passed, 1 skipped。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts/index E2E；当前只声明 Python Seed asset indexer app-role/rollback hardening verified，不声明完整上传解析分段、Seed LLM live provider、vector embeddings 或 search/index UI 闭环已完成。

### 2026-07-07

Follow-up active slice:

- P5-001 Python Seed seed analysis snapshot writer app-role/rollback hardening。
- 目标：为 global aggregation 后续的真实 seed analysis snapshot persistence 铺路，`PostgresSeedAnalysisWriter` 在写私有 `seed_analysis_snapshots` 前必须设置 `app_set_tenant_context(tenant_id, project_id, false)`；业务 SQL execute 或 commit failure 必须 rollback 当前 connection 并继续抛错，避免 RLS live path 误报成功或留下 partial transaction。
- 边界：只收紧 Python Seed global aggregation snapshot writer；不启动 fake Seed success、不公开 seed analysis body、不改变 Go upload API、不实现完整 Seed live E2E。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_seed_analysis_writer_upserts_sanitized_private_snapshot or postgres_seed_analysis_writer_rolls_back_on_database_failure"` 失败；成功路径没有执行 tenant context，`fail_on_execute=2` 未触发业务 SQL failure，commit failure 后未 rollback。
- GREEN：同一聚焦测试通过，2 passed；seed analysis writer 现在先设置 tenant context，失败时 rollback 后继续抛错，由 `global_aggregation_activity` 保持稳定 failed result/event。

Verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_seed_analysis_writer_upserts_sanitized_private_snapshot or postgres_seed_analysis_writer_rolls_back_on_database_failure"` 通过，2 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，68 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_sequential_reader.py -q` 通过，13 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，166 passed, 1 skipped。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts -> global-aggregation -> index E2E；当前只声明 Python Seed seed analysis snapshot writer app-role/rollback hardening verified，不声明完整上传解析分段、Seed LLM live provider、seed analysis live provider 或 search/index UI 闭环已完成。

Follow-up active slice:

- P5-001 Python Seed global aggregation aggregate source app-role/error-boundary hardening。
- 目标：为 global aggregation 的真实 DB-backed read side 铺路，`PostgresSeedAggregateSource` 在读取 `segment_summaries` 和 structured fact counts 前必须设置 app-role tenant context；普通 DB/driver query exception 必须稳定为 public `SEED_AGGREGATE_SOURCE_QUERY_FAILED`，避免 RLS live path 失败时泄露 prompt/API key/`credential_ref` 或 raw text。
- 边界：只收紧 Python Seed aggregate source read side；不启动 fake Seed success、不生成 fake seed analysis、不改变 Go upload API、不实现完整 Seed live E2E。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_global_aggregator.py -q -k "postgres_seed_aggregate_source_loads_public_summaries_and_counts_without_evidence or postgres_seed_aggregate_source_sanitizes_query_failures"` 失败；成功路径第一条 SQL 直接读取 `segment_summaries`，普通 query failure 仍返回旧 `SEED_AGGREGATE_SOURCE_FAILED` 并回显 `prompt=hidden api_key=... credential_ref=... raw novel text`。
- GREEN：同一聚焦测试通过，2 passed；aggregate source 现在先设置 app-role tenant context，普通 query exception 稳定为 `SEED_AGGREGATE_SOURCE_QUERY_FAILED` / `seed aggregate source query failed`。

Verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_global_aggregator.py -q -k "postgres_seed_aggregate_source_loads_public_summaries_and_counts_without_evidence or postgres_seed_aggregate_source_sanitizes_query_failures"` 通过，2 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_global_aggregator.py -q` 通过，5 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，68 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_sequential_reader.py -q` 通过，13 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，167 passed, 1 skipped。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts -> global-aggregation -> index E2E；当前只声明 Python Seed aggregate source app-role/error-boundary hardening verified，不声明完整上传解析分段、Seed LLM live provider、seed analysis live provider 或 search/index UI 闭环已完成。

Follow-up active slice:

- P5-001 Python Seed archive candidate writer app-role/rollback/error-boundary hardening。
- 目标：为真实 `narrative_archives` archive candidate persistence 铺路，`PostgresArchiveCandidateWriter` 在写 candidate `assets` / `archive_memories` / `archive_memory_events` 前必须设置 `app_set_tenant_context(tenant_id, project_id, false)`；业务 SQL execute 或 commit failure 必须 rollback 当前 connection，并把普通 DB/driver exception 稳定为 public `ARCHIVE_CANDIDATE_WRITE_FAILED`，避免 RLS live path 误报成功、留下 partial transaction，或泄露 prompt/API key/`credential_ref` / raw text。
- 边界：只收紧 Python Seed archive candidate DB writer；不启动 fake archive runner、不生成 mock archive candidates、不自动采用 candidate 为 canon、不实现完整 Seed live E2E。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_archive_candidate_writer_persists_candidate_archive_assets_and_memories_without_public_body_or_credentials or postgres_archive_candidate_writer_rolls_back_and_sanitizes_database_failures"` 失败；成功路径第一条 SQL 直接 `INSERT INTO assets`，没有 tenant context；失败路径因缺 tenant context 未触发预期业务 SQL failure，也没有 rollback / stable error boundary。
- GREEN：同一聚焦测试通过，2 passed；archive candidate writer 现在先设置 tenant context，业务 SQL / commit failure 时 rollback，并把普通 DB/driver exception 稳定为 `ARCHIVE_CANDIDATE_WRITE_FAILED` / `archive candidate write failed`。

Verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_archive_candidate_writer_persists_candidate_archive_assets_and_memories_without_public_body_or_credentials or postgres_archive_candidate_writer_rolls_back_and_sanitizes_database_failures"` 通过，2 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，69 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_global_aggregator.py -q` 通过，5 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_sequential_reader.py -q` 通过，13 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，168 passed, 1 skipped。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts -> global-aggregation -> archive-candidates -> index E2E；当前只声明 Python Seed archive candidate writer app-role/rollback/error-boundary hardening verified，不声明完整 Seed LLM live provider、archive candidate live provider 或 search/index UI 闭环已完成。

Follow-up active slice:

- P5-001 Python Seed project readiness snapshot DB-backed updater。
- 目标：为 `finalize_seed_activity` 接入真实 DB-backed readiness persistence，新增 `project_readiness_snapshots` schema/RLS，并在 `DATABASE_URL` 配置时默认装配 updater，从同一 tenant/project/run 的 seed assets/entities/relationships/world rules 计数生成 readiness snapshot metadata。
- 边界：不伪造 project ready；不生成 readiness report body；不公开 prompt/API key/`credential_ref`、raw text、draft 或 manuscript；不声明完整 live Seed E2E。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_project_readiness_updater_records_snapshot_counts_without_report_body or postgres_project_readiness_updater_rolls_back_and_sanitizes_database_failures"` 失败，缺 `PostgresProjectReadinessUpdater`；`cd backend && .venv/bin/python -m pytest tests/test_saas_phase3_rls_schema.py -q -k "minimum_phase3_tables or runtime_fact_schema_supports_structured_seed_outputs or all_tenant_scoped_tables_enable_rls"` 失败，缺 `project_readiness_snapshots` schema/RLS。
- GREEN：同一 runtime 聚焦测试通过，2 passed；schema/RLS 聚焦测试通过，1 passed。`project_readiness_snapshots` schema/RLS 已加入 baseline，`PostgresProjectReadinessUpdater` 现在设置 tenant context、从 seed assets/entities/relationships/world rules 计数 upsert readiness snapshot，业务 SQL/commit failure 会 rollback 并稳定为 `PROJECT_READINESS_UPDATE_FAILED` / `project readiness update failed`；`DATABASE_URL` 配置时 `finalize_seed_activity` 默认装配该 updater。

Verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k "postgres_project_readiness_updater_records_snapshot_counts_without_report_body or postgres_project_readiness_updater_rolls_back_and_sanitizes_database_failures"` 通过，2 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，71 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_global_aggregator.py -q` 通过，5 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_sequential_reader.py -q` 通过，13 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，170 passed, 1 skipped。
- `cd backend && .venv/bin/python -m pytest tests/test_saas_phase3_rls_schema.py -q` 通过，17 passed。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts -> global-aggregation -> archive-candidates -> index-assets -> finalize E2E；当前只声明 project readiness snapshot metadata persistence verified，不声明 project readiness dashboard、Seed LLM live provider 或完整 live Seed pipeline E2E 已完成。

### 2026-07-07 进度记录维护

Context:

- 用户要求创建任务进度记录文档，并在开发过程中实时更新。
- 确认 `tasks/refactor-saas-live-progress.md` 已存在，且 `tasks/refactor-saas-parallel-board.md` 已把它登记为实时进度流水入口。
- 确认主仓库 `/Users/yantianqi/Documents/Noveronline` 仍有大量未提交改动，不作为 SaaS 开发位置。
- 确认 SaaS worktree `/Users/yantianqi/Documents/Noveronline-saas-mainline` 位于 `codex/saas-mainline`，git dir 为 `/Users/yantianqi/Documents/Noveronline/.git/worktrees/Noveronline-saas-mainline`，common dir 为 `/Users/yantianqi/Documents/Noveronline/.git`。

Progress:

- 刷新 `当前焦点`：最近完成重点改为 project readiness snapshot DB-backed updater。
- 把本轮 slice 标记为进度文档维护，不把它混同为业务能力完成。
- 更新 `开放风险` 和 `下一步`，明确 readiness snapshot 已能写入，但 Go read API/dashboard 仍 pending。
- 下一开发建议收窄为 tenant/project-scoped project readiness snapshot read API，然后再推进完整 live Seed pipeline E2E。

Verification:

- 本轮为文档维护，无代码测试。
- `test -s tasks/refactor-saas-live-progress.md` 通过，确认实时进度文档存在且非空。
- `rg -n "当前焦点|进度记录维护|readiness read side|project readiness snapshot Go read API|开放风险|下一步" tasks/refactor-saas-live-progress.md` 通过，核心章节和本轮记录可检索。
- `rg -n '[[:blank:]]$' tasks/refactor-saas-live-progress.md` 未发现尾随空白。
- `git diff --check` 通过。

Next:

- 若继续开发，按 TDD 做 P5 project readiness snapshot Go read API；响应不得公开 readiness report body、prompt、API key、`credential_ref`、raw text、draft 或 manuscript。

Follow-up active slice:

- P5 project readiness snapshot tenant/project-scoped Go read API。
- 目标：为 Python `finalize_seed_activity` 写入的 `project_readiness_snapshots` 增加 Go public read side，使 Overview/dashboard 后续能读取最新 readiness snapshot metadata。
- 边界：只读 latest public snapshot metadata；不生成 project ready 假状态、不生成 readiness report body、不实现 dashboard UI、不推进完整 live Seed E2E。
- 公开响应只能包含 snapshot id、project id、run id、ready asset/entity/relationship/world-rule counts 和 timestamps；不得返回 prompt、API key、`credential_ref`、raw text、draft、manuscript、readiness report body 或任意 private payload。
- 计划验证：先写 domain reader / HTTP route / cmd wiring RED 测试；再实现 disabled reader、SQL reader、HTTP `GET /v1/projects/{projectId}/readiness`、cmd `DATABASE_URL` wiring；最后跑聚焦 Go tests、必要 broader verification、`git diff --check` 和尾随空白扫描。
- RED：`cd apps/api && go test ./internal/projectreadiness -count=1` 失败，缺 `NewSQLReader` / `SQLReaderConfig` / `GetLatestSnapshotInput` / `SQLRows` 等生产类型。
- RED：`cd apps/api && go test ./internal/httpapi -run 'ProjectReadiness' -count=1` 失败，`internal/projectreadiness` 还没有 non-test Go files。
- RED：`cd apps/api && go test ./cmd/api -run 'ProjectReadiness' -count=1` 失败，`internal/projectreadiness` 还没有 non-test Go files。
- GREEN：新增 `apps/api/internal/projectreadiness` disabled reader / SQL reader；SQL reader 使用 tenant-scoped queryer 设置 app-role tenant context，只读取 latest `project_readiness_snapshots` public columns，普通 query/scan/rows error 稳定为 `PROJECT_READINESS_QUERY_FAILED`。
- GREEN：Go HTTP 新增 `GET /v1/projects/{projectId}/readiness`，只使用 `X-Tenant-Id` 与 path project id，公开响应只返回 readiness snapshot metadata，并在 HTTP boundary 固定 `PROJECT_READINESS_*` public error message。
- GREEN：Go cmd 在 `DATABASE_URL` 配置时 wiring `projectreadiness.SQLReader`，无 DB 时使用 `PROJECT_READINESS_BACKEND_UNCONFIGURED` fail-closed disabled reader。
- 聚焦验证：`cd apps/api && go test ./internal/projectreadiness -count=1` 通过。
- 聚焦验证：`cd apps/api && go test ./internal/httpapi -run 'ProjectReadiness' -count=1` 通过。
- 聚焦验证：`cd apps/api && go test ./cmd/api -run 'ProjectReadiness' -count=1` 通过。

Verification:

- `cd apps/api && go test ./internal/projectreadiness -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'ProjectReadiness|Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'ProjectReadiness|Seed' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/05-overview-dashboard.md`
- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 可继续把 `GET /v1/projects/{projectId}/readiness` 接入 Next Overview readiness dashboard UI；触碰 UI 前必须加载 UI/UX skill 并做对应 Web 测试。
- P5 也可继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts -> global-aggregation -> archive-candidates -> index-assets -> finalize E2E；当前只声明 readiness snapshot Go read API verified，不声明 dashboard UI 或完整 live Seed pipeline E2E 已完成。

### 2026-07-07 继续：实时进度记录确认

Context:

- 用户要求创作任务进度记录文档，并在开发过程中实时更新。
- 复核 `/goal` pasted text、`DEVELOPMENT_PLAN.md`、worktree 状态和看板入口，确认 SaaS 开发仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 进行。
- 主仓库 `/Users/yantianqi/Documents/Noveronline` 仍有大量未提交 UI/文档改动，本轮不触碰。

Progress:

- 确认 `tasks/refactor-saas-live-progress.md` 已作为实时任务流水文档存在，且看板 `tasks/refactor-saas-parallel-board.md` 已登记它为实时进度入口。
- 将顶部 `当前焦点` 的本轮 slice 校准为进度记录维护，并把下一可开工项明确为 P5 Overview readiness dashboard UI handoff。
- 本轮只做文档状态维护，不声明新增业务能力、不声明 readiness dashboard UI 或完整 live Seed pipeline E2E 已完成。

Verification:

- 本轮为文档维护，无代码测试。
- `test -s tasks/refactor-saas-live-progress.md` 通过，确认实时进度文档存在且非空。
- `rg -n "当前焦点|实时进度记录确认|Overview readiness dashboard UI|实时进度入口|下一可开工" tasks/refactor-saas-live-progress.md` 通过，核心章节、本轮记录和下一步可检索。
- `rg -n "refactor-saas-live-progress|实时进度流水" tasks/refactor-saas-parallel-board.md` 通过，看板入口仍在。
- `rg -n '[[:blank:]]$' tasks/refactor-saas-live-progress.md tasks/refactor-saas-parallel-board.md` 未发现尾随空白。
- `git diff --check` 通过。

Next:

- 下一个开发切片开始前，先在本文追加 active slice，写明目标、边界和 RED/GREEN/broader verification 计划。

Follow-up active slice:

- P5 Overview readiness dashboard UI handoff。
- 目标：把已完成的 `GET /v1/projects/{projectId}/readiness` 接入 Next Overview route/API client/shell，在 Overview 中展示最新 readiness snapshot public counts。
- 边界：只展示 snapshot id、run id、ready asset/entity/relationship/world-rule counts 和 timestamps；不生成假 ready 状态、不读取或显示 readiness report body、raw text、prompt、API key、`credential_ref`、draft、manuscript；不声明完整 live Seed pipeline E2E。
- UI 约束：沿用现有 SaaS operational shell，紧凑数据优先，显式 fail-closed error state；不做 landing/hero，不新增装饰性图形或一色系主题。
- RED/GREEN 计划：先补 `apps/web/tests/web-shell.test.mjs`，要求 API client 暴露 typed readiness reader、Overview route 调用 reader 并传入 shell、shell 渲染 readiness counts/error；确认 RED 后实现最小 client/route/shell，再跑 Web 聚焦测试、typecheck、必要 Go readiness tests、`git diff --check` 和尾随空白扫描。
- RED：`cd apps/web && npm run test -- --test-name-pattern='Overview|source file, Seed, and readiness'` 失败，缺 `getProjectReadinessSnapshot`、`ProjectReadinessSummary`、`ProjectReadinessSnapshot`、`/v1/projects/${input.projectId}/readiness` endpoint client、Overview route prop wiring 和 shell `Project readiness` 面板。
- GREEN：同一聚焦 Web 测试通过，34/34 pass；Web API client 现在解码 readiness snapshot public metadata，Overview route 使用 tenant/project scoped apiContext 调用 reader，`OverviewSeedShell` 新增 Project readiness 面板和 header status pill。

Verification:

- `cd apps/web && npm run test -- --test-name-pattern='Overview|source file, Seed, and readiness'` 通过，34/34 pass。
- `cd apps/web && npm run test` 通过，34/34 pass。
- `cd apps/web && npm run typecheck` 通过。
- `cd apps/web && npm run build` 通过；Next build 仍打印本地 `@next/swc-darwin-arm64` native package load warning，但 fallback 编译完成并 exit 0。
- `cd apps/web && npm run dev -- -p 4000` 启动成功；Next dev server 同样打印本地 SWC native package load warning，但随后显示 `Ready`。
- `curl -I http://localhost:4000/demo/projects/demo-project/overview` 返回 `HTTP/1.1 200 OK`，dev server log 显示 Overview route compiled and responded 200。
- `cd apps/api && go test ./internal/projectreadiness -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'ProjectReadiness' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'ProjectReadiness' -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/web/lib/api.ts apps/web/components/overview-seed-shell.tsx 'apps/web/app/(app)/[tenantSlug]/projects/[projectId]/overview/page.tsx' apps/web/tests/web-shell.test.mjs tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/05-overview-dashboard.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts -> global-aggregation -> archive-candidates -> index-assets -> finalize E2E。
- 或补完整 Project Health rollup endpoint，将 readiness、Seed run、LLM binding、graph/assets/worldline/writer 状态聚合到单一 overview contract；仍需 TDD 且不得返回私密正文、prompt、credential 或 fake ready 状态。

Follow-up active slice:

- P5 Project Overview aggregate read API。
- 目标：实现 `GET /v1/projects/{projectId}/overview` 的 Go public rollup read side，为 `ProjectHealthHeader` / 完整 Project Health rollup 提供后端 contract。
- 边界：只返回 tenant/project scoped public metadata：project id、derived status、active workflow id/type/status、source/seed run counts、latest readiness snapshot counts/timestamps；不返回 source object key、raw/parsed text、readiness report body、prompt、response、API key、encrypted credential、`credential_ref`、draft 或 manuscript；不声明 live Seed E2E 完成。
- 设计：新增 `apps/api/internal/projectoverview` disabled reader / SQL reader；SQL reader 在真实 DB 上设置 app-role tenant context，聚合 `source_files`、`workflow_runs` 和 latest `project_readiness_snapshots` public columns；HTTP route 使用 `X-Tenant-Id` + path project id，不信任 body；`cmd/api` 按 `DATABASE_URL` wiring SQL reader，否则 fail closed。
- RED/GREEN 计划：先补 domain reader / HTTP route / cmd wiring RED 测试，再实现最小 reader、route、error boundary 和 cmd factory；最后跑 projectoverview/httpapi/cmd 聚焦测试、必要 broader verification、`git diff --check` 和尾随空白扫描。
- RED：`cd apps/api && go test ./internal/projectoverview -count=1` 失败，缺 `NewSQLReader` / `SQLReaderConfig` / `GetProjectOverviewInput` / `NewDisabledReader` / `ErrorCode` / `SQLRows` 等生产类型。
- RED：`cd apps/api && go test ./internal/httpapi -run 'ProjectOverview' -count=1` 失败，`internal/projectoverview` 还没有 non-test Go files。
- RED：`cd apps/api && go test ./cmd/api -run 'ProjectOverview' -count=1` 失败，`internal/projectoverview` 还没有 non-test Go files。
- GREEN：新增 `apps/api/internal/projectoverview` disabled reader / SQL reader；SQL reader 使用 tenant-scoped queryer 设置 app-role tenant context，聚合 `source_files`、`workflow_runs` 和 latest `project_readiness_snapshots` public columns，普通 query/scan/rows/close error 稳定为 `PROJECT_OVERVIEW_QUERY_FAILED`。
- GREEN：Go HTTP 新增 `GET /v1/projects/{projectId}/overview`，只使用 `X-Tenant-Id` 与 path project id，公开响应只返回 overview public rollup，并在 HTTP boundary 固定 `PROJECT_OVERVIEW_*` public error message。
- GREEN：Go cmd 在 `DATABASE_URL` 配置时 wiring `projectoverview.SQLReader`，无 DB 时使用 `PROJECT_OVERVIEW_BACKEND_UNCONFIGURED` fail-closed disabled reader。
- 聚焦验证：`cd apps/api && go test ./internal/projectoverview -count=1` 通过。
- 聚焦验证：`cd apps/api && go test ./internal/httpapi -run 'ProjectOverview' -count=1` 通过。
- 聚焦验证：`cd apps/api && go test ./cmd/api -run 'ProjectOverview' -count=1` 通过。

Verification:

- `cd apps/api && go test ./internal/projectoverview -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'ProjectOverview|ProjectReadiness|Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'ProjectOverview|ProjectReadiness|Seed' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。

Docs synced:

- `docs/refactor-saas/05-overview-dashboard.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 可继续把 Next Overview Project Health header 从 readiness-specific panel 扩展到 `GET /v1/projects/{projectId}/overview` aggregate contract。
- P5 也可继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts -> global-aggregation -> archive-candidates -> index-assets -> finalize E2E；当前只声明 Project Overview aggregate read API verified，不声明完整 live Seed pipeline E2E 已完成。

Follow-up active slice:

- P5 Overview Project Health aggregate UI handoff。
- 目标：把已完成的 `GET /v1/projects/{projectId}/overview` 接入 Next Overview route/API client/header，使 Overview 顶部 Project Health 使用 aggregate public rollup，而不是只用 readiness-specific count pill。
- 边界：只展示 project id、derived status、source/seed counts、active workflow id/type/status、readiness snapshot/run ids、ready counts 和 timestamp；不展示 source object key、raw/parsed text、readiness report body、prompt/response、API key、encrypted credential、`credential_ref`、draft 或 manuscript；不声明 live Seed E2E、跨模块 health rollup 或 Project Health 全量完成。
- UI 约束：沿用现有 SaaS operational shell、data-dense dashboard、status pills 和 compact panels；不做 landing/hero，不新增装饰性图形、不引入新一色系主题；错误状态必须显式 fail closed。
- RED/GREEN 计划：先补 `apps/web/tests/web-shell.test.mjs`，要求 typed `ProjectOverviewSummary` / `getProjectOverview`、route 调用并传给 `OverviewSeedShell`、header/Project Health 渲染 status/counts/active workflow/error；确认 RED 后实现最小 client/route/shell，再跑 Web 聚焦测试、Web 全量测试、typecheck、build、必要 Go overview tests、`git diff --check` 和尾随空白扫描。
- RED：`cd apps/web && npm run test -- --test-name-pattern='Overview|source file, Seed, readiness, and overview'` 失败，route 缺 `getProjectOverview` / `projectOverview={projectOverview}`，API client 缺 `ProjectOverviewRecord` / `ProjectOverviewSummary` / `/overview` reader，shell 缺 `Project health` / aggregate status/counts/error rendering。
- GREEN：同一聚焦 Web 测试通过，34/34 pass；Web API client 现在解码 `GET /v1/projects/{projectId}/overview` public rollup，Overview route 使用 tenant/project scoped apiContext 调用 reader，`OverviewSeedShell` 顶部 status pills 和 `Project health` panel 渲染 project status、source/seed counts、active workflow metadata、readiness ids/counts/timestamp 或 `PROJECT_OVERVIEW_BACKEND_UNCONFIGURED` 等显式错误。

Verification:

- `cd apps/web && npm run test -- --test-name-pattern='Overview|source file, Seed, readiness, and overview'` 通过，34/34 pass。
- `cd apps/web && npm run test` 通过，34/34 pass。
- `cd apps/web && npm run typecheck` 通过。
- `cd apps/web && npm run build` 通过；Next build 仍打印本地 `@next/swc-darwin-arm64` native package load warning，但 fallback 编译完成并 exit 0。
- `cd apps/api && go test ./internal/projectoverview -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'ProjectOverview|ProjectReadiness' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'ProjectOverview|ProjectReadiness' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `rg -n '[[:blank:]]$' ...` 检查本轮触碰文件无尾随空白。
- `git diff --check` 通过。

Docs synced:

- `docs/refactor-saas/05-overview-dashboard.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- Cross-module public count rollup 已在后续 slice 追加；下一步仍是 live provider/cluster diagnostics 或真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts -> global-aggregation -> archive-candidates -> index-assets -> finalize E2E。
- 当前只声明 Overview aggregate UI handoff verified，不声明完整 live Seed pipeline E2E 已完成。

Follow-up active slice:

- P5 Overview Project Health cross-module public rollup。
- 目标：在既有 `GET /v1/projects/{projectId}/overview` 中补齐 assets、graph、worldline、Character Console、Writer、LLM public count metadata，并让 Next `/overview` Project Health panel 展示这些 counts。
- 边界：只聚合 enabled asset count、最新 graph node/edge counts、worldline session/event counts、character interaction count、writer run count、LLM activity count 和 `usage_events.usage_type = llm_tokens` token sum；不读取或公开 asset content、graph evidence snippet、worldline/character body、writer instruction/options/draft/manuscript、prompt/response、API key、encrypted credential 或 `credential_ref`；不声明 live provider/cluster diagnostics 或 live Seed E2E 已完成。
- UI 约束：沿用现有 data-dense operational panel 和 status pills；不新增 landing/hero、装饰图或新色系；错误状态继续 fail closed。
- RED：`cd apps/api && go test ./internal/projectoverview -run TestSQLReaderGetsProjectOverviewWithTenantContextAndPublicColumns -count=1` 失败，`Overview` 缺 `AssetCount` / `GraphNodeCount` / `WorldlineSessionCount` / `WriterRunCount` / `LLMActivityCount` 等字段。
- RED：`cd apps/api && go test ./internal/httpapi -run TestGetProjectOverviewUsesTenantProjectScopeAndReturnsPublicRollup -count=1` 失败，HTTP response struct 缺 cross-module public count fields。
- RED：`cd apps/web && npm run test -- --test-name-pattern='Overview|source file, Seed, readiness, and overview'` 失败，typed API client 和 `OverviewSeedShell` 缺 cross-module count 解码与展示。
- GREEN：上述三条聚焦测试均通过；SQL reader 现在聚合 cross-module public counts，Web API client 解码新增字段，`Project health` panel 展示 Asset records、Graph nodes/edges、Worldline sessions/events、Character interactions、Writer runs、LLM calls/tokens。

Verification:

- `cd apps/api && go test ./internal/projectoverview -run TestSQLReaderGetsProjectOverviewWithTenantContextAndPublicColumns -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run TestGetProjectOverviewUsesTenantProjectScopeAndReturnsPublicRollup -count=1` 通过。
- `cd apps/web && npm run test -- --test-name-pattern='Overview|source file, Seed, readiness, and overview'` 通过，34/34 pass。
- `cd apps/api && go test ./internal/projectoverview -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'ProjectOverview|ProjectReadiness' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'ProjectOverview|ProjectReadiness' -count=1` 通过。
- `cd apps/web && npm run test` 通过，34/34 pass。
- `cd apps/web && npm run typecheck` 通过。
- `cd apps/web && npm run build` 通过；Next build 仍打印本地 `@next/swc-darwin-arm64` native package load warning，但 fallback 编译完成并 exit 0。
- `cd apps/api && go test ./... -count=1` 通过。
- `rg -n '[[:blank:]]$' ...` 检查本轮触碰文件无尾随空白。
- `git diff --check` 通过。

Docs synced:

- `docs/refactor-saas/05-overview-dashboard.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 可继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts -> global-aggregation -> archive-candidates -> index-assets -> finalize E2E。
- Project Health 后续可继续补 live provider/cluster diagnostics，例如真实 provider binding 状态、recent failed workflow summary 或 live dependency health；当前只声明 cross-module public count rollup，不声明完整 health diagnostics 已完成。

Follow-up active slice:

- P5 Overview Project Health LLM configuration diagnostics。
- 目标：在既有 `GET /v1/projects/{projectId}/overview` 中补充 LLM Facility 配置健康 public counts，并让 Next `/overview` Project Health panel 展示这些 counts。
- 边界：只聚合 enabled LLM channel count、指向 enabled channel 且存在 model 的 valid bound module count，以及核心创作 module missing count；不返回 channel/model/provider/base URL 详情、不读取或公开 prompt/response、API key、encrypted credential、`credential_ref`、draft 或 manuscript；不声明 provider connectivity、cluster health、live Seed E2E 已完成。
- 核心创作 modules：`writer_composer`、`writer_reviewer`、`sequential_reading`、`anchor_point_summary`、`narrative_archives`、`asset_ingestion`、`style_extractor`、`graph_bond_generator`、`worldline_director`。
- UI 约束：沿用现有 data-dense operational panel 和 status pills；只新增可扫描的 counts，不新增 landing/hero、装饰图或新色系；错误状态继续 fail closed。
- RED：`cd apps/api && go test ./internal/projectoverview -run TestSQLReaderGetsProjectOverviewWithTenantContextAndPublicColumns -count=1` 失败，`Overview` 缺 `LLMEnabledChannelCount` / `LLMBoundModuleCount` / `LLMMissingCoreModuleCount`。
- RED：`cd apps/api && go test ./internal/httpapi -run TestGetProjectOverviewUsesTenantProjectScopeAndReturnsPublicRollup -count=1` 失败，HTTP response struct 缺 LLM configuration public count fields。
- RED：`cd apps/web && npm run test -- --test-name-pattern='Overview|source file, Seed, readiness, and overview'` 失败，typed API client 和 `OverviewSeedShell` 缺 LLM configuration count 解码与展示。
- GREEN：上述三条聚焦测试均通过；SQL reader 现在聚合 enabled channels、valid bound modules 和 missing core modules，Web API client 解码新增字段，`Project health` panel 展示 LLM enabled channels、LLM bound modules、LLM missing core modules。

Verification:

- `cd apps/api && go test ./internal/projectoverview -run TestSQLReaderGetsProjectOverviewWithTenantContextAndPublicColumns -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run TestGetProjectOverviewUsesTenantProjectScopeAndReturnsPublicRollup -count=1` 通过。
- `cd apps/web && npm run test -- --test-name-pattern='Overview|source file, Seed, readiness, and overview'` 通过，34/34 pass。
- `cd apps/api && go test ./internal/projectoverview -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'ProjectOverview|ProjectReadiness' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'ProjectOverview|ProjectReadiness' -count=1` 通过。
- `cd apps/web && npm run test` 通过，34/34 pass。
- `cd apps/web && npm run typecheck` 通过。
- `cd apps/web && npm run build` 通过；Next build 仍打印本地 `@next/swc-darwin-arm64` native package load warning，但 fallback 编译完成并 exit 0。
- `cd apps/api && go test ./... -count=1` 通过。
- `rg -n '[[:blank:]]$' ...` 检查本轮触碰文件无尾随空白。
- `git diff --check` 通过。

Docs synced:

- `docs/refactor-saas/05-overview-dashboard.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- P5 可继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts -> global-aggregation -> archive-candidates -> index-assets -> finalize E2E。
- Project Health 可继续补 provider connectivity check、cluster dependency health、recent failed workflow summary；当前只声明 LLM configuration count diagnostics，不声明 provider/live cluster health 已完成。

Follow-up active slice:

- P5 Overview Project Health recent failed workflow diagnostics。
- 目标：在既有 `GET /v1/projects/{projectId}/overview` 中补充最新 failed workflow 的 public summary，并让 Next `/overview` Project Health panel 展示最近失败 workflow、错误 code 和更新时间。
- 边界：只读取当前 tenant/project 下 `workflow_runs.status = failed` 的 `run_id`、`workflow_type`、`error_code`、`updated_at`；不选择或公开 `workflow_runs.error_message`、prompt/response、body/content/raw text、API key、encrypted credential、`credential_ref`、draft 或 manuscript；不声明 provider connectivity、cluster health、live Seed E2E 或完整 failure drilldown 已完成。
- UI 约束：沿用现有 data-dense operational panel；只在 `Project health` `<dl>` 中新增紧凑字段，不新增 landing/hero、装饰图或新色系；错误状态继续 fail closed。
- RED：`cd apps/api && go test ./internal/projectoverview -run TestSQLReaderGetsProjectOverviewWithTenantContextAndPublicColumns -count=1` 失败，`Overview` 缺 `LatestFailedWorkflowRunID` / `LatestFailedWorkflowType` / `LatestFailedWorkflowErrorCode` / `LatestFailedWorkflowUpdatedAt`。
- RED：`cd apps/api && go test ./internal/httpapi -run TestGetProjectOverviewUsesTenantProjectScopeAndReturnsPublicRollup -count=1` 失败，HTTP response struct/body 缺 latest failed workflow public fields。
- RED：`cd apps/web && npm run test -- --test-name-pattern='Overview|source file, Seed, readiness, and overview'` 失败，typed API client 和 `OverviewSeedShell` 缺 latest failed workflow 解码与展示。
- GREEN：上述三条聚焦测试均通过；SQL reader 现在聚合 latest failed workflow public summary，且 query/test 明确禁止 `error_message`；Web API client 解码新增字段，`Project health` panel 展示 Latest failed workflow / Failure code / Failure updated。
- Verification：
  - `cd apps/api && go test ./internal/projectoverview -run TestSQLReaderGetsProjectOverviewWithTenantContextAndPublicColumns -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run TestGetProjectOverviewUsesTenantProjectScopeAndReturnsPublicRollup -count=1` 通过。
  - `cd apps/web && npm run test -- --test-name-pattern='Overview|source file, Seed, readiness, and overview'` 通过，34/34 pass。
  - `cd apps/api && go test ./internal/projectoverview -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run 'ProjectOverview|ProjectReadiness' -count=1` 通过。
  - `cd apps/api && go test ./cmd/api -run 'ProjectOverview|ProjectReadiness' -count=1` 通过。
  - `cd apps/web && npm run test` 通过，34/34 pass。
  - `cd apps/web && npm run typecheck` 通过。
  - `cd apps/api && go test ./... -count=1` 通过。
  - `cd apps/web && npm run build` 通过；Next build 仍打印本地 `@next/swc-darwin-arm64` native package load warning，但 fallback 编译完成并 exit 0。
  - `rg -n '[[:blank:]]$' ...` 检查本轮触碰文件无尾随空白。
  - `git diff --check` 通过。
- Docs synced：
  - `docs/refactor-saas/05-overview-dashboard.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - P5 可继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts -> global-aggregation -> archive-candidates -> index-assets -> finalize E2E。
  - Project Health 可继续补 provider connectivity check 或 cluster dependency health；当前只声明 latest failed workflow public summary，不声明 provider/live cluster health 或完整 failure drilldown 已完成。

Follow-up active slice:

- P5 Overview Project Health LLM model sync health diagnostics。
- 目标：在既有 `GET /v1/projects/{projectId}/overview` 中补充 enabled LLM channel model-sync public health counts，并让 Next `/overview` Project Health panel 展示同步成功/失败/未同步数量和最新同步时间。
- 边界：只读取 enabled `llm_channels.last_sync_status` / `last_sync_at` 并聚合 ok / failed / pending counts 与 latest sync timestamp；不选择或公开 provider/base URL/API key/encrypted credential/`credential_ref`、prompt/response、body/content/raw text、draft 或 manuscript；不发起 live provider connectivity call，不声明 cluster health、live Seed E2E 或完整 failure drilldown 已完成。
- UI 约束：沿用现有 data-dense operational panel 和 status pills；只新增可扫描的 public counts 与 `LLM latest sync`，不新增 landing/hero、装饰图或新色系；错误状态继续 fail closed。
- RED：`cd apps/api && go test ./internal/projectoverview -run TestSQLReaderGetsProjectOverviewWithTenantContextAndPublicColumns -count=1` 失败，`Overview` 缺 `LLMSyncOKChannelCount` / `LLMSyncFailedChannelCount` / `LLMSyncPendingChannelCount` / `LLMLatestSyncAt`。
- RED：`cd apps/api && go test ./internal/httpapi -run TestGetProjectOverviewUsesTenantProjectScopeAndReturnsPublicRollup -count=1` 失败，HTTP response struct/body 缺 LLM model sync health public fields。
- RED：`cd apps/web && npm run test -- --test-name-pattern='Overview|source file, Seed, readiness, and overview'` 失败，typed API client 和 `OverviewSeedShell` 缺 LLM sync health 解码与展示。
- GREEN：上述三条聚焦测试均通过；SQL reader 现在聚合 `llm_model_sync_health`，query/test 明确禁止 `base_url` / `encrypted_api_key` 等私密渠道字段；Web API client 解码新增字段，`Project health` panel 展示 LLM sync ok/failed/pending channels 和 LLM latest sync。
- Verification：
  - `cd apps/api && go test ./internal/projectoverview -run TestSQLReaderGetsProjectOverviewWithTenantContextAndPublicColumns -count=1` 先按预期 RED，缺 `LLMSyncOKChannelCount` / `LLMSyncFailedChannelCount` / `LLMSyncPendingChannelCount` / `LLMLatestSyncAt`。
  - `cd apps/api && go test ./internal/httpapi -run TestGetProjectOverviewUsesTenantProjectScopeAndReturnsPublicRollup -count=1` 先按预期 RED，HTTP response struct/body 缺 LLM model sync health fields。
  - `cd apps/web && npm run test -- --test-name-pattern='Overview|source file, Seed, readiness, and overview'` 先按预期 RED，client/shell 缺 LLM sync health fields/labels。
  - `cd apps/api && go test ./internal/projectoverview -run TestSQLReaderGetsProjectOverviewWithTenantContextAndPublicColumns -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run TestGetProjectOverviewUsesTenantProjectScopeAndReturnsPublicRollup -count=1` 通过。
  - `cd apps/web && npm run test -- --test-name-pattern='Overview|source file, Seed, readiness, and overview'` 通过，34/34 pass。
  - `cd apps/api && go test ./internal/projectoverview -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run 'ProjectOverview|ProjectReadiness' -count=1` 通过。
  - `cd apps/api && go test ./cmd/api -run 'ProjectOverview|ProjectReadiness' -count=1` 通过。
  - `cd apps/web && npm run test` 通过，34/34 pass。
  - `cd apps/web && npm run typecheck` 通过。
  - `cd apps/api && go test ./... -count=1` 通过。
  - `cd apps/web && npm run build` 通过；Next build 仍打印本地 `@next/swc-darwin-arm64` native package load warning，但 fallback 编译完成并 exit 0。
- Docs synced：
  - `docs/refactor-saas/05-overview-dashboard.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - P5 可继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts -> global-aggregation -> archive-candidates -> index-assets -> finalize E2E。
  - Project Health 可继续补 live provider connectivity call 或 cluster dependency health；当前只声明 LLM model sync metadata health，不声明 live provider/cluster health 或完整 failure drilldown 已完成。

Follow-up active slice:

- P5 Python Seed parse_file PDF text extraction support。
- 目标：让 Python `parse_file_activity` 支持 `application/pdf` 源文件，把可提取文本的 PDF 写成标准 `extracted_text` artifact object reference，并保持 public result / workflow event 不暴露 raw PDF bytes、解析后正文、object credential、prompt、API key、`credential_ref`、draft 或 manuscript。
- 边界：不实现 OCR/扫描件，不声明 live MinIO/Postgres/Temporal/Python object upload -> complete -> parse E2E，不改变 segment/LLM/canon/finalize 语义，不生成 mock parse success。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'extracts_pdf_text'` 失败，`application/pdf` 仍返回 unsupported MIME。
- GREEN：同一测试通过；`parse_file_activity` 现在通过 `pypdf` 读取可提取文本 PDF，artifact writer 记录 `application/pdf` metadata，公开 result/event 仍不含正文。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'unextractable_pdf'` 失败，损坏 PDF 抛出 `pypdf.errors.PdfStreamError`，activity 未结构化失败。
- GREEN：同一测试通过；`PyPdfError` 现在稳定收敛为 `FILE_PARSE_DECODE_FAILED` / `source object text extraction failed`，不写 artifact、不泄露 PDF bytes。
- Verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity or segment_text_activity or workflow_locally_chains_uploaded_text_source or extracts_pdf_text or unextractable_pdf'` 通过，11 passed / 62 deselected。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，73 passed。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，172 passed / 1 skipped。
  - `cd apps/agent-runtime && uv lock --check` 通过。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进 live object upload -> complete -> parse/segment E2E，把已支持的 TXT/MD/PDF parse path 放进真实 MinIO/Postgres/Temporal/Python 链路验收。
  - 扫描/OCR PDF、完整智能分段和 Seed LLM live provider E2E 仍 pending。

Follow-up active slice:

- P5 Source upload MIME admission allowlist。
- 目标：让 Go upload metadata admission 与 Python `parse_file_activity` 支持范围对齐，只允许 TXT/Markdown/PDF 源进入 `source_files` pending rows，避免 unsupported MIME 先入库、后续才在 worker parse 阶段失败。
- 边界：只收紧 metadata admission；不改变 object upload/complete verifier、Seed workflow payload、Python parse/segment 成功语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- 支持 MIME：`text/plain`、`text/markdown`、`text/x-markdown`、`application/x-markdown`、`application/pdf`；匹配前去掉 `; charset=...` 等 MIME 参数。
- RED：`cd apps/api && go test ./internal/sourcefiles -run TestSQLStoreRejectsUnsupportedSourceMimeBeforeInsert -count=1` 失败，`application/json` 仍可进入 DB insert path 并返回 nil error。
- RED：`cd apps/api && go test ./internal/httpapi -run TestCreateUploadRejectsUnsupportedSourceMimeBeforeStore -count=1` 失败，HTTP 对 `application/json` 返回 201 created。
- GREEN：上述两条聚焦测试均通过；HTTP 现在在调用 store 前返回 `400 VALIDATION_FAILED` / `invalid source MIME type`，SQL store 在 insert 前拒绝 unsupported MIME。
- Focused verification：
  - `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run 'TestCreateUpload|TestUploadSourceObject|TestCompleteUpload|TestListSourceFiles|TestStartSeedRun' -count=1` 通过。
  - `cd apps/api && go test ./internal/workflows -run 'Seed' -count=1` 通过。
- Broader verification：
  - `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run 'Upload|SourceFile|Seed|Workflow' -count=1` 通过。
  - `cd apps/api && go test ./cmd/api -run 'Upload|SourceFile|Seed|Workflow' -count=1` 通过。
  - `cd apps/api && go test ./... -count=1` 通过。
  - `gofmt -l apps/api/internal/sourcefiles/source_files.go apps/api/internal/sourcefiles/source_files_test.go apps/api/internal/httpapi/server.go apps/api/internal/httpapi/server_test.go` 无输出。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`

### 2026-07-07 最新 checkpoint：P5 Seed admission tenant-context SQL write hardening

Context:

- 最新已验证切片是 `P5 Seed admission tenant-context SQL write hardening`。
- 顶部 `当前焦点`、`docs/refactor-saas/18-legacy-coverage-matrix.md` 和 `tasks/refactor-saas-parallel-board.md` 已同步到该切片。
- SaaS worktree 仍是 `/Users/yantianqi/Documents/Noveronline-saas-mainline` / `codex/saas-mainline`；主仓库 `/Users/yantianqi/Documents/Noveronline` 仍有大量未提交改动，本轮没有在主仓库开发。

Implementation:

- `SQLSeedAdmissionStore.AdmitSeedRun` 和 `RecordSeedRunStartFailure` 现在通过共享 `execAdmissionSQL` 使用 tenant-context-aware execer。
- 真实 `sqlDBWriterAdmissionExecer.ExecTenantContext` 会在同一 transaction 中执行 `app_set_tenant_context(tenant_id, project_id, false)`，再写 RLS-protected `source_files`、`workflow_runs` 和 `workflow_events`。

Verification:

- RED 已确认：`cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStoreUsesTenantContextExecerForAdmissionAndStartFailure -count=1` 曾失败，原因是 admission 仍走 plain `ExecContext`。
- GREEN：`cd apps/api && go test ./internal/workflows -run 'TestSQLSeedAdmissionStoreUsesTenantContextExecerForAdmissionAndStartFailure|TestSQLSeedAdmissionStoreRecordsWorkflowStartFailureAndReleasesSource|TestSQLSeedAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload' -count=1` 通过。
- Broader：`cd apps/api && go test ./internal/workflows -count=1` 通过。
- Broader：`cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- Broader：`cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- Broader：`cd apps/api && go test ./... -count=1` 通过。
- Hygiene：`cd apps/api && gofmt -l internal/workflows/writer_admission.go internal/workflows/seed_admission.go internal/workflows/seed_test.go` 无输出。
- Hygiene：`git diff --check` 通过。
- Hygiene：`rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Next:

- 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts/index E2E。
- 扫描/OCR PDF、更完整语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 最新 checkpoint：P5 Seed live Postgres app-role parse/segment E2E harness

Context:

- 本轮新增 Seed live Postgres/app-role parse -> segment 验收入口，继续逼近 Phase 5 的 live object upload -> pipeline E2E。
- 该入口是 opt-in live harness：默认没有 `MIROFISH_SEED_LIVE_DATABASE_URL` 时跳过，不伪造 live DB 成功。
- SaaS worktree 仍是 `/Users/yantianqi/Documents/Noveronline-saas-mainline` / `codex/saas-mainline`；主仓库 `/Users/yantianqi/Documents/Noveronline` 仍只做状态检查，没有开发改动。

Implementation:

- 新增 `apps/agent-runtime/tests/test_seed_live_e2e.py`。
- live harness 会应用 target Postgres migration、创建 `mirofish_seed_live_app` app-role login、准备 tenant/project/queued Seed run 和 `source_files.parse_status = parsing` source row。
- harness 通过 app-role `DATABASE_URL` 跑 `run_seed_workflow_locally` parse -> segment，验证 `source_files` 变 `parsed`，`project_text_artifacts`、`text_segments` 和 public `workflow_events` 落库。
- public workflow event 断言不包含 object key、source path、raw text、prompt、API key、`credential_ref`、draft 或 manuscript。
- `test_seed_workflow.py` 的本地 parse/segment 串联测试同步加强：注入 `RecordingSourceFileStatusWriter` 并断言 local workflow 会把 source row 推进到 `parsed`。

Verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_live_e2e.py -q` 通过当前默认环境，结果为 1 skipped（需要 `MIROFISH_SEED_LIVE_DATABASE_URL` 才执行 live DB）。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'locally_chains_uploaded_text_source_into_parse_and_segment_activities or local_events_do_not_expose_object_storage_keys'` 通过，2 passed / 78 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，80 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，179 passed / 2 skipped。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/tests/test_seed_live_e2e.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 在可用 live Postgres 环境中设置 `MIROFISH_SEED_LIVE_DATABASE_URL` 跑新 harness，拿到真实 executed 结果。
- 继续补真实 MinIO object storage、Go API upload/complete、Temporal worker handoff 到 Python parse/segment 的 live E2E。
- 扫描/OCR PDF、更完整语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：任务进度记录文档维护

Context:

- 用户要求创建任务进度记录文档，并在开发过程中实时更新。
- 复核本文已存在于 `tasks/refactor-saas-live-progress.md`，且 `tasks/refactor-saas-parallel-board.md` 已把它登记为实时进度流水入口。
- 复核 `/goal` pasted text、SaaS worktree 状态和 `DEVELOPMENT_PLAN.md`，确认开发仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 进行。
- 主仓库 `/Users/yantianqi/Documents/Noveronline` 仍有大量未提交 UI/文档改动，本轮未在主仓库开发。

Progress:

- 将顶部 `当前焦点` 从较早的 Seed Temporal starter handoff checkpoint 校准到最新尾部 checkpoint：`P5 Seed live Postgres app-role parse/segment E2E harness`。
- 明确本轮 slice 是文档维护，不声明新的代码能力完成。
- 保留实时更新规则：每个开发切片开始、RED、GREEN、广泛验证、文档同步和交接前都必须更新本文。

Verification:

- `test -s tasks/refactor-saas-live-progress.md` 通过，确认实时进度文档存在且非空。
- `rg -n "当前焦点|任务进度记录文档维护（verified）|任务进度记录文档维护收口|P5 Seed live Postgres app-role parse/segment E2E harness|下一代码切片" tasks/refactor-saas-live-progress.md` 通过，核心章节和本轮记录可检索。
- `rg -n "refactor-saas-live-progress|实时进度流水" tasks/refactor-saas-parallel-board.md` 通过，看板入口仍在。
- `rg -n '[[:blank:]]$' tasks/refactor-saas-live-progress.md tasks/refactor-saas-parallel-board.md` 未发现尾随空白。
- `git diff --check` 通过。

Next:

- 下一代码切片继续推进 Seed live object upload -> complete -> Temporal/Python parse/segment E2E。

### 2026-07-07 当前会话：P5 Seed Temporal starter source handoff format validation

Context:

- Phase 5 下一缺口仍是 live object upload -> complete -> Temporal/Python parse/segment E2E。
- Go upload/sourcefile path 已有 TXT/Markdown/PDF MIME allowlist，Python `parse_file_activity` 已依赖可选 `source_size_bytes` / `source_sha256` 做 object integrity guard。
- 当前 Go `TemporalSeedRunStarter` 只验证 source MIME/SHA metadata 非空；内部调用如果绕过 sourcefile store，仍可能 admission/start unsupported MIME 或 malformed SHA payload。

Scope:

- 只收紧 Go Temporal starter 的内部 handoff validation。
- 不改变公网 upload/complete/Seed start 语义，不改变 Temporal payload 字段，不改 Python parse/segment/runtime 行为。
- validation error 仍使用稳定 `VALIDATION_FAILED` / `seed source metadata is incomplete`，不公开 MIME、SHA、object key、hash、prompt、API key、`credential_ref`、draft 或 manuscript。

Plan:

- RED：补 Go starter 测试，unsupported MIME 和 malformed SHA-256 都必须在 admission store / Temporal client 前 fail closed。
- GREEN：实现最小 MIME allowlist 与 64 位 hex SHA-256 validation。
- Verification：跑 focused workflows tests、Seed HTTP/cmd 聚焦测试、`go test ./...`、`git diff --check` 和尾随空白扫描。

TDD:

- RED：`cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterRejectsInvalidSourceHandoffBeforeAdmission -count=1` 失败；unsupported MIME 和 malformed SHA-256 都继续走到 Temporal start，并返回 `WORKFLOW_FAILED`。
- GREEN：同一聚焦测试通过；`TemporalSeedRunStarter` 现在在 admission/run id allocation/Temporal start 前要求 source MIME 属于 TXT/Markdown/PDF allowlist，并要求 `source_sha256` 为 64 位 hex。

Verification:

- `cd apps/api && go test ./internal/workflows -run 'TestTemporalSeedRunStarterRejectsInvalidSourceHandoffBeforeAdmission|TestTemporalSeedRunStarterRequiresSourceMetadataBeforeAdmission|TestTemporalSeedRunStarterStartsSeedWorkflowWithoutWaitingForCompletion|TestTemporalSeedRunStarterPersistsAdmissionBeforeStartingWorkflow|TestTemporalSeedRunStarterDoesNotStartWorkflowWhenAdmissionFails|TestTemporalSeedRunStarterSanitizesWorkflowStartErrors' -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `cd apps/api && gofmt -l internal/workflows/seed.go internal/workflows/seed_test.go` 无输出。
- `rg -n "Seed Temporal starter source handoff format validation|source handoff metadata|unsupported source MIME|malformed SHA|64 位 hex|seed source metadata is incomplete" ...docs/tasks...` 通过，文档同步点可检索。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- `git diff --check` 通过。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 Temporal worker handoff、browser upload/complete、Python parse/segment 联动、sequential-reading/provider 和 full Seed pipeline E2E。

### 2026-07-07 当前会话：P5 Seed live Go upload/complete/admission app-role harness

Context:

- 本轮继续从总纲 Phase 5 推进真实 Seed 链路，目标是让 Go API/control-plane 的 source upload metadata、MinIO object write/verify、complete upload 和 Seed admission 在 live Postgres app-role/RLS + live MinIO 下同链路验收。
- SaaS worktree 仍是 `/Users/yantianqi/Documents/Noveronline-saas-mainline` / `codex/saas-mainline`；主仓库 `/Users/yantianqi/Documents/Noveronline` 仍有大量未提交改动，本轮只做状态检查，不在主仓库开发。
- 该 harness 是 opt-in live test：缺少 `MIROFISH_SEED_LIVE_DATABASE_URL` 或 MinIO 环境变量时跳过，不伪造 live 成功。

RED / debugging:

- 新增 `apps/api/internal/workflows/seed_live_test.go`，覆盖 `CreateSourceFile -> GetUploadObject -> MinIO WriteObject -> CompleteUpload -> ValidateSourceFile -> AdmitSeedRun`。
- RED 已确认：`cd apps/api && MIROFISH_SEED_LIVE_DATABASE_URL=... MIROFISH_SEED_LIVE_OBJECT_STORAGE_*=... go test ./internal/workflows -run TestLiveSeedGoUploadCompleteAndAdmissionUseMinIOAndAppRole -count=5` 出现不稳定失败，错误集中在 `SOURCE_FILE_QUERY_FAILED` / `SOURCE_FILE_CREATE_FAILED` / `SOURCE_FILE_COMPLETE_FAILED`。
- 诊断确认相同 row 在 direct app-role SQL lookup 与独立 `sourcefiles.NewSQLDBQueryer(...).QueryTenantContext` lookup 中可见；失败路径里 `rows.Scan` 与 `rows.Close` 为 nil，但 close/commit 后二次读取 `rows.Err()` 返回 driver `context canceled`。
- 聚焦 RED：`cd apps/api && go test ./internal/sourcefiles -run TestSQLStoreDoesNotTreatTenantRowsErrAfterSuccessfulCloseAsQueryFailure -count=1` 失败，当前 `scanRow` 把 successful close 后的 `rows.Err() = context canceled` 包装为 `SOURCE_FILE_QUERY_FAILED`。

Implementation:

- `sourcefiles.SQLStore.scanRow` 现在在 tenant-scoped single-row scan 中先检查 `rows.Err()`，再执行 `rows.Close()`/transaction commit；不再在 successful close/commit 后二次读取 driver row error。
- 真实 close/commit failure 仍按原规则收敛为 stable source-file public error；scan failure 仍 abort tenant rows/transaction。
- 清理 `seed_live_test.go` 中的临时诊断 queryer/log helper，只保留 opt-in live harness。

Focused verification:

- RED 已确认：`cd apps/api && go test ./internal/sourcefiles -run TestSQLStoreDoesNotTreatTenantRowsErrAfterSuccessfulCloseAsQueryFailure -count=1` 失败。
- GREEN：`cd apps/api && go test ./internal/sourcefiles -run 'TestSQLStoreDoesNotTreatTenantRowsErrAfterSuccessfulCloseAsQueryFailure|TestSQLStoreReturnsRowsCloseErrorsAsStableQueryFailures|TestSQLStoreAbortsTenantContextRowsOnScanFailure' -count=1` 通过。
- GREEN：`cd apps/api && MIROFISH_SEED_LIVE_DATABASE_URL=... MIROFISH_SEED_LIVE_OBJECT_STORAGE_*=... go test ./internal/workflows -run TestLiveSeedGoUploadCompleteAndAdmissionUseMinIOAndAppRole -count=5` 通过。
- GREEN：`cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
- GREEN：`cd apps/api && go test ./internal/workflows -run 'TestLiveSeedGoUploadCompleteAndAdmissionUseMinIOAndAppRole|Seed|WorkflowEvent|WorkflowRun' -count=1` 通过。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Broader verification:

- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `cd apps/agent-runtime && MIROFISH_SEED_LIVE_DATABASE_URL=... MIROFISH_SEED_LIVE_OBJECT_STORAGE_*=... .venv/bin/python -m pytest tests/test_seed_live_e2e.py -q` 通过，2 passed。
- `cd apps/api && gofmt -l internal/sourcefiles/source_files.go internal/sourcefiles/source_files_test.go internal/workflows/seed_live_test.go` 无输出。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Next:

- 继续推进 Temporal worker handoff、browser upload/complete、Go admission -> Python parse/segment 联动、sequential-reading/provider 和完整 Seed pipeline E2E。
- 扫描/OCR PDF、更完整语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed Python parse source object size/SHA guard

Context:

- Go Seed starter 的 Temporal payload 已包含内部 `source_size_bytes` 和 `source_sha256`，Go upload complete 也会在 admission 前验证 MinIO object metadata。
- 为推进 Go admission -> Python worker handoff 的真实链路，本切片在 Python `parse_file_activity` 读取 source object 后复核 actual bytes，防止 admission 后对象被外部篡改仍进入 parse/segment。
- 边界：只收紧 Python parse worker 的 source object integrity guard；不改变 Go upload/complete/admission、Temporal workflow id/task queue、segmentation、sequential-reading、LLM/canon/finalize 语义，也不声明完整 Seed E2E 已完成。

Plan:

- RED：新增 `parse_file_activity` size/SHA mismatch 测试，要求稳定失败且 public result/event 不泄露 object key、raw text、expected hash 或 actual hash。
- GREEN：实现最小 object bytes integrity check，失败时尝试把 source row 标为 `failed`，公开错误使用固定 code/message。
- Verification：跑聚焦 Python seed tests、完整 `tests/test_seed_workflow.py`、live MinIO/Postgres parse/segment harness、必要 Go regression 和 hygiene。

TDD:

- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k source_object_integrity_mismatches` 先因 indentation collection error 暴露测试插入缩进问题；修正测试缩进后再次运行，预期失败为 `assert 'completed' == 'failed'`，证明当前 `parse_file_activity` 未校验 Go handoff size/SHA。
- GREEN：`parse_file_activity` 读取 source bytes 后、解析文本前新增可选 `source_size_bytes` / `source_sha256` 校验；字段缺省兼容旧 payload，字段存在但类型、格式或值不匹配时返回稳定 `SOURCE_FILE_OBJECT_INTEGRITY_MISMATCH` / `source object integrity check failed`，并走既有 source parse-status failed + sanitized failed event path。

Verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k source_object_integrity_mismatches` 通过，1 passed / 81 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'source_object_integrity_mismatches or parse_file_activity_writes_extracted_text_artifact_without_returning_raw_text or workflow_locally_chains_uploaded_text_source'` 通过，3 passed / 79 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，82 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，181 passed / 3 skipped。
- `cd apps/agent-runtime && MIROFISH_SEED_LIVE_DATABASE_URL='postgresql://mirofish:mirofish_dev_password@127.0.0.1:54329/mirofish' MIROFISH_SEED_LIVE_OBJECT_STORAGE_ENDPOINT='127.0.0.1:9000' MIROFISH_SEED_LIVE_OBJECT_STORAGE_BUCKET='mirofish-uploads' MIROFISH_SEED_LIVE_OBJECT_STORAGE_ACCESS_KEY='mirofish' MIROFISH_SEED_LIVE_OBJECT_STORAGE_SECRET_KEY='mirofish_dev_password' MIROFISH_SEED_LIVE_OBJECT_STORAGE_USE_SSL='false' .venv/bin/python -m pytest tests/test_seed_live_e2e.py -q` 通过，2 passed。
- `cd apps/api && go test ./internal/workflows -run 'Seed|WorkflowEvent|WorkflowRun|LiveSeed' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced so far:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

### 2026-07-07 当前会话：P5 Seed Temporal starter source metadata handoff validation

Context:

- Go HTTP Seed start 已通过 `sourcefiles.ValidateSourceFile` 注入 `source_file_id/source_object_key/source_mime_type/source_size_bytes/source_sha256` 给 `TemporalSeedRunStarter`。
- Python `parse_file_activity` 已开始依赖 `source_size_bytes/source_sha256` 做 object integrity guard；因此 Go starter 不应 admission/start 一个缺 source metadata 的 source-less workflow shell。
- 边界：只在 Go Temporal Seed starter admission 前做 source metadata handoff validation；不改变 HTTP source-file validation、object upload/complete、Python parse/segment、Temporal worker runtime 或 LLM stages。

Plan:

- RED：新增 Go starter 测试，缺 `source_object_key` 时应 `VALIDATION_FAILED`，且不调用 admission store / Temporal client。
- GREEN：实现最小 source handoff metadata validation，要求 `source_file_id/source_object_key/source_mime_type/source_sha256` 非空且 `source_size_bytes` 非负。
- Verification：跑 focused workflows test、Seed workflow broader、Seed HTTP/cmd 相关测试、`go test ./...`、`git diff --check` 和尾随空白扫描。

TDD:

- RED：`cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterRequiresSourceMetadataBeforeAdmission -count=1` 失败，当前缺 source object key 时仍走到 Temporal start；输出为 `expected source metadata validation failure, got WORKFLOW_FAILED (<nil>)`。
- GREEN：`TemporalSeedRunStarter` 在 admission/run id allocation/Temporal start 前新增 source handoff metadata validation；缺必需 source metadata 或 `source_size_bytes < 0` 时返回稳定 `VALIDATION_FAILED` / `seed source metadata is incomplete`，且不调用 admission store / Temporal client。原有 admission/start failure-path tests 补齐 valid source fixture 后继续覆盖下游错误边界；validation test 同时断言 public message 不含 object key 字段名、object path 或 hash 字段。

Verification:

- `cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterRequiresSourceMetadataBeforeAdmission -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced so far:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

### 2026-07-07 当前会话：任务进度记录文档维护

Context:

- 用户要求创建任务进度记录文档，并实时更新进度。
- 复核本文已作为 SaaS 重构实时进度流水存在于 `tasks/refactor-saas-live-progress.md`。
- 复核 `tasks/refactor-saas-parallel-board.md` 已登记本文为每个开发切片开始、RED/GREEN、广泛验证、文档同步和交接前必须同步更新的入口。
- 复核 `/goal` pasted text、`DEVELOPMENT_PLAN.md` 和 linked worktree 状态：后续开发仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` / `codex/saas-mainline` 进行；主仓库 `/Users/yantianqi/Documents/Noveronline` 保持只读检查。

Progress:

- 顶部 `当前焦点` 临时校准为 `任务进度记录文档维护（in_progress，校验中）`。
- 保留真实产品闭环估算 `55%-60%` 和 Phase 5/Phase 6 pending 边界，不把 opt-in harness、metadata skeleton 或 fail-closed shell 写成完整产品能力。

Verification:

- `test -s tasks/refactor-saas-live-progress.md` 通过，确认实时进度文档存在且非空。
- `rg -n "当前焦点|任务进度记录文档维护|in_progress，校验中|DEVELOPMENT_PLAN.md|实时更新规则|下一代码切片" tasks/refactor-saas-live-progress.md` 通过，核心章节和本轮记录可检索。
- `rg -n "refactor-saas-live-progress|实时进度流水" tasks/refactor-saas-parallel-board.md` 通过，看板入口仍在。
- `rg -n '[[:blank:]]$' tasks/refactor-saas-live-progress.md tasks/refactor-saas-parallel-board.md` 未发现尾随空白。
- `git diff --check` 通过。

Next:

- 本轮文档校验通过后，将顶部 `本轮开发 slice` 改为 verified。
- 下一代码切片继续围绕 P5 Seed live/Postgres/MinIO/Temporal/Python E2E gap 推进；若没有 live DB，则优先做 Seed workflow event write failure sanitization 的 TDD 小切片。

### 2026-07-07 当前会话：P5 Seed live Postgres existing-table upsert index hardening

Context:

- `127.0.0.1:54329` 本地 Postgres 可连；`MIROFISH_SEED_LIVE_DATABASE_URL` 环境变量默认未设置。
- 使用 compose 默认连接串执行 `apps/agent-runtime/tests/test_seed_live_e2e.py` 后，live harness 从 skipped 进入真实执行但失败。
- 诊断复现显示 `run_seed_workflow_locally` 返回 `TEXT_ARTIFACT_WRITE_FAILED`，只落了 `seed.stage.pending` event，`source_files.parse_status` 被标记为 `failed`，`project_text_artifacts` / `text_segments` 未落库。
- 直接调用 `PostgresTextArtifactWriter` 捕获到底层 root cause：`psycopg.errors.InvalidColumnReference: there is no unique or exclusion constraint matching the ON CONFLICT specification`。
- 根因：既有 live DB 中 `project_text_artifacts` 是旧表形态；target migration 使用 `CREATE TABLE IF NOT EXISTS`，不会为既有表补 `ON CONFLICT` 所需唯一约束。同类风险也存在 `text_segments`。

Active slice:

- 目标：让 target Postgres migration 对既有 `project_text_artifacts` / `text_segments` 表补齐 parse/segment upsert unique index，使 live app-role parse -> segment harness 可在已存在 schema 上执行。
- 边界：只修 schema migration 的兼容 backfill；不改变 Seed activity payload、object storage handoff、public event sanitizer、LLM/canon/finalize 语义；不声明真实 MinIO/Temporal/browser upload E2E 已完成。

TDD:

- RED：`cd backend && env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 .venv/bin/python -m pytest tests/test_saas_phase3_rls_schema.py -q -k seed_parse_segment_upsert_indexes_are_backfilled_for_existing_tables` 失败，migration 缺 `idx_project_text_artifacts_upsert_unique` 和 `idx_text_segments_upsert_unique`。
- GREEN：同一 schema 测试通过；migration 现在会在既有表缺少 matching unique index 时补 `project_text_artifacts` / `text_segments` upsert index。
- Follow-up RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k seed_workflow_locally_reuses_env_workflow_event_writer_for_chained_stages` 失败，只记录到第一条 `seed.stage.pending`，说明 local runner 后续 parse/segment stages 没复用 env workflow event writer。
- GREEN：同一 local runner 测试通过；`run_seed_workflow_locally` 现在解析一次 env workflow event writer，并复用到 admission、parse、segment 和后续 stages。

Implementation:

- `infra/postgres/migrations/0001_core_saas.sql` 新增 existing-table backfill DO block：缺 matching unique index 时创建 `idx_project_text_artifacts_upsert_unique` 和 `idx_text_segments_upsert_unique`。
- `run_seed_workflow_locally` 现在在入口解析 `workflow_event_writer` / `_workflow_event_writer_from_env()`，并把同一个 writer 传入 parse/segment/sequential/runtime/canon/finalize chain。
- `apps/agent-runtime/tests/test_seed_workflow.py` 新增 env workflow event writer 复用回归测试。
- `backend/tests/test_saas_phase3_rls_schema.py` 新增 migration upsert-index backfill schema test。

Verification:

- `cd backend && env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONUTF8=1 .venv/bin/python -m pytest tests/test_saas_phase3_rls_schema.py -q` 通过，18 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'seed_workflow_locally_reuses_env_workflow_event_writer_for_chained_stages or locally_chains_uploaded_text_source_into_parse_and_segment_activities or local_events_do_not_expose_object_storage_keys'` 通过，3 passed / 78 deselected。
- `cd apps/agent-runtime && MIROFISH_SEED_LIVE_DATABASE_URL='postgresql://mirofish:mirofish_dev_password@127.0.0.1:54329/mirofish' .venv/bin/python -m pytest tests/test_seed_live_e2e.py -q` 通过，1 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，81 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，180 passed / 2 skipped。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续补真实 MinIO object storage、Go API upload/complete、Temporal worker handoff 到 Python parse/segment 的 live E2E。
- 本轮只证明本地 Postgres/app-role parse -> segment metadata 和 public events 可执行；不声明 browser upload、MinIO object store、Temporal worker handoff、sequential-reading provider 或完整 Seed pipeline E2E 已完成。

### 2026-07-07 当前会话：P5 Seed live MinIO/Postgres app-role parse/segment harness

Context:

- 本地 Docker/Compose 可用；`mirofish-saas-postgres-1` 已健康运行在 `127.0.0.1:54329`。
- 本轮启动了 `infra/docker-compose.yml` 中的 `minio` / `minio-init`，MinIO health endpoint `http://127.0.0.1:9000/minio/health/ready` 返回 ready。
- 直接使用 Python `S3CompatibleObjectStore` 对 `mirofish-uploads` bucket 做真实 PUT/GET 探测，返回 `hello minio`。

Active slice:

- 目标：把 Seed live harness 从 in-memory object store 推进到真实 MinIO/S3-compatible object store，证明 Python parse -> segment 在 app-role Postgres path 下能从真实 object store 读 source，并把 extracted artifact / segment objects 写回真实 object store。
- 边界：只扩展 live harness 和验证；不实现 Go API upload/complete、Temporal worker handoff、browser upload、sequential-reading provider 或完整 Seed pipeline E2E。

TDD:

- RED：`cd apps/agent-runtime && MIROFISH_SEED_LIVE_DATABASE_URL='postgresql://mirofish:mirofish_dev_password@127.0.0.1:54329/mirofish' MIROFISH_SEED_LIVE_OBJECT_STORAGE_ENDPOINT='127.0.0.1:9000' MIROFISH_SEED_LIVE_OBJECT_STORAGE_BUCKET='mirofish-uploads' MIROFISH_SEED_LIVE_OBJECT_STORAGE_ACCESS_KEY='mirofish' MIROFISH_SEED_LIVE_OBJECT_STORAGE_SECRET_KEY='mirofish_dev_password' MIROFISH_SEED_LIVE_OBJECT_STORAGE_USE_SSL='false' .venv/bin/python -m pytest tests/test_seed_live_e2e.py -q -k minio` 失败，缺 `_live_object_store` helper。
- GREEN：同一 MinIO live test 通过，1 passed / 1 deselected；新增 helper 按 `MIROFISH_SEED_LIVE_OBJECT_STORAGE_*` 读取真实 S3-compatible object store 配置，测试会先把 source bytes 写入 MinIO，再让 parse/segment 从 MinIO 读 source、写 extracted artifact 和 segment objects。

Implementation:

- `apps/agent-runtime/tests/test_seed_live_e2e.py` 新增 opt-in MinIO/Postgres live test。
- MinIO live test 使用真实 `S3CompatibleObjectStore`，验证 extracted artifact object bytes 和 segment object bytes 可从 MinIO 读回。
- 公开 workflow event 仍断言不包含 source/extracted/segment object key、raw text、API key、`credential_ref`、draft 或 manuscript。

Verification:

- `cd apps/agent-runtime && MIROFISH_SEED_LIVE_DATABASE_URL='postgresql://mirofish:mirofish_dev_password@127.0.0.1:54329/mirofish' MIROFISH_SEED_LIVE_OBJECT_STORAGE_ENDPOINT='127.0.0.1:9000' MIROFISH_SEED_LIVE_OBJECT_STORAGE_BUCKET='mirofish-uploads' MIROFISH_SEED_LIVE_OBJECT_STORAGE_ACCESS_KEY='mirofish' MIROFISH_SEED_LIVE_OBJECT_STORAGE_SECRET_KEY='mirofish_dev_password' MIROFISH_SEED_LIVE_OBJECT_STORAGE_USE_SSL='false' .venv/bin/python -m pytest tests/test_seed_live_e2e.py -q` 通过，2 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，81 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，180 passed / 3 skipped。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/tests/test_seed_live_e2e.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 推进 Go API upload/complete -> Temporal/Python parse/segment live E2E，把浏览器上传、server-side object writer/verifier、Seed admission 和 worker handoff 串成真实链路。
- 本 slice 仍不声明 Go API upload/complete、Temporal worker handoff、browser upload、sequential-reading/provider 或完整 Seed pipeline E2E 已完成。

### 2026-07-07 继续：P5 Seed admission tenant-context SQL write hardening

Context:

- 当前开发仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` linked worktree / `codex/saas-mainline` 分支进行。
- 主仓库 `/Users/yantianqi/Documents/Noveronline` 仍有大量未提交 UI/文档改动，本轮没有在主仓库开发。
- 本 slice 接在 Seed Temporal start failure compensation 之后，补齐 Go DB-backed admission 写路径的 app-role/RLS tenant context。

目标:

- `SQLSeedAdmissionStore.AdmitSeedRun` 和 `RecordSeedRunStartFailure` 写 `source_files`、`workflow_runs`、`workflow_events` 时，在 execer 支持 tenant context 的情况下先设置可信 tenant/project session context。
- 真实 `sqlDBWriterAdmissionExecer` 在同一 transaction 中调用 `app_set_tenant_context(tenant_id, project_id, false)` 后再执行 admission 或 start-failure compensation SQL。

边界:

- 不改变 upload、complete、Temporal payload、Python parse/segment、sequential-reading、LLM/canon/finalize 语义。
- 不声明完整 live object upload/complete/parse/segment/index E2E 已完成。
- 继续不公开 prompt、response、body/content raw text、API key、encrypted credential、`credential_ref`、object key、source path、draft 或 manuscript。

TDD:

- RED：`cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStoreUsesTenantContextExecerForAdmissionAndStartFailure -count=1` 失败，recording tenant execer 显示 Seed admission 仍走 plain `ExecContext`。
- GREEN：`cd apps/api && go test ./internal/workflows -run 'TestSQLSeedAdmissionStoreUsesTenantContextExecerForAdmissionAndStartFailure|TestSQLSeedAdmissionStoreRecordsWorkflowStartFailureAndReleasesSource|TestSQLSeedAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload' -count=1` 通过；共享 admission SQL execer 现在支持 `ExecTenantContext`，Seed admission 与 start-failure compensation 都传入可信 tenant/project scope。

Verification:

- `cd apps/api && go test ./internal/workflows -run 'TestSQLSeedAdmissionStoreUsesTenantContextExecerForAdmissionAndStartFailure|TestSQLSeedAdmissionStoreRecordsWorkflowStartFailureAndReleasesSource|TestSQLSeedAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload' -count=1` 通过。
- `cd apps/api && go test ./internal/workflows -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts/index E2E。
- 扫描/OCR PDF、更完整语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

Follow-up active slice:

- P5 Seed Temporal start failure compensation。
- 目标：admission 成功但 Temporal `ExecuteWorkflow` 启动失败时，不能留下 orphan `workflow_runs.status = queued` 或 `source_files.parse_status = parsing`；应记录稳定 failed workflow metadata，并把 source row 从 `parsing` 释放回 `uploaded` 以便后续真实重试。
- 边界：只处理 Go Seed Temporal start failure 后的 DB 状态一致性；不改变 upload admission、object verifier、Temporal payload、Python parse/segment、sequential-reading、LLM/canon/finalize 语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- 公开失败 metadata 不得返回 prompt、response、body/content raw text、API key、encrypted credential、`credential_ref`、draft/manuscript、source object key、artifact object key 或 source path。
- RED：`cd apps/api && go test ./internal/workflows -run 'TestTemporalSeedRunStarterRecordsFailedAdmissionWhenWorkflowStartFails|TestSQLSeedAdmissionStoreRecordsWorkflowStartFailureAndReleasesSource' -count=1` 失败，生产代码缺 `SeedStartFailureInput` / `RecordSeedRunStartFailure`，说明 start failure 后还没有真实 admission compensation path。
- GREEN：`cd apps/api && go test ./internal/workflows -run 'TestTemporalSeedRunStarterRecordsFailedAdmissionWhenWorkflowStartFails|TestSQLSeedAdmissionStoreRecordsWorkflowStartFailureAndReleasesSource|TestTemporalSeedRunStarterSanitizesWorkflowStartErrors' -count=1` 通过；`TemporalSeedRunStarter` 现在在 Temporal start failure 后调用 admission store 记录 failed run，`SQLSeedAdmissionStore` 会把 admitted queued run 标为 `failed`、追加 sanitized `workflow.failed` event，并把同 tenant/project/upload 的 `source_files.parse_status` 从 `parsing` 释放回 `uploaded`。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Broader verification：
  - `cd apps/api && go test ./internal/workflows -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
  - `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier' -count=1` 通过。
  - `cd apps/api && go test ./... -count=1` 通过。
  - `cd apps/api && gofmt -l internal/workflows/seed.go internal/workflows/seed_admission.go internal/workflows/seed_test.go` 无输出。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' apps/api/internal/workflows/seed.go apps/api/internal/workflows/seed_admission.go apps/api/internal/workflows/seed_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/14-data-model.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 Seed Temporal start failure compensation verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、更完整的语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

Follow-up active slice:

- P5 Seed admission tenant-context SQL write hardening。
- 目标：`SQLSeedAdmissionStore.AdmitSeedRun` 和 `RecordSeedRunStartFailure` 触碰 RLS-protected `source_files`、`workflow_runs`、`workflow_events` 时，在 execer 支持 tenant context 的情况下必须先设置 app-role tenant/project context，而不是只依赖 SQL `WHERE tenant_id/project_id`。
- 边界：只收紧 Go Seed admission / start-failure compensation 的 SQL write execution context；不改变 upload admission、object verifier、Temporal payload、Python parse/segment、sequential-reading、LLM/canon/finalize 语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- RED：`cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStoreUsesTenantContextExecerForAdmissionAndStartFailure -count=1` 失败，recording tenant execer 显示 Seed admission 仍走 plain `ExecContext`。
- GREEN：`cd apps/api && go test ./internal/workflows -run 'TestSQLSeedAdmissionStoreUsesTenantContextExecerForAdmissionAndStartFailure|TestSQLSeedAdmissionStoreRecordsWorkflowStartFailureAndReleasesSource|TestSQLSeedAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload' -count=1` 通过；共享 admission SQL execer 现在支持 `ExecTenantContext`，`SQLSeedAdmissionStore` 在 admission 和 start-failure compensation 时会传入可信 tenant/project scope，真实 SQL DB execer 在同一 transaction 中调用 `app_set_tenant_context(tenant_id, project_id, false)` 后再执行写入。
- Broader verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，80 passed。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，179 passed, 1 skipped。
  - `cd apps/agent-runtime && uv lock --check` 通过。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 Seed public workflow event object-key redaction verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、更完整的语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

Follow-up active slice:

- P5 Seed Temporal start error-message hardening。
- 目标：`TemporalSeedRunStarter` 在 admission 成功但 Temporal `ExecuteWorkflow` 启动失败时返回稳定 `WORKFLOW_FAILED` public message，不回显 Temporal/client exception 文本。
- 边界：不改变内部 workflow payload、source metadata handoff、admission store、Temporal workflow id、upload/complete/parse/segment、Python worker 或 LLM/canon/finalize 语义；不声明完整 live Seed pipeline E2E 已完成。
- 公开错误不得返回 prompt、response、body/content raw text、API key、encrypted credential、`credential_ref`、draft/manuscript、source object key、artifact object key 或 source path。
- 计划验证：先补 `apps/api/internal/workflows/seed_test.go` RED，确认 `ExecuteWorkflow` 普通 error 中的敏感文本会泄漏；再做最小 message 固定化；最后跑 workflows focused/broader、Seed HTTP/cmd 相关测试、`go test ./...`、`git diff --check` 和尾随空白扫描。
- RED：`cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterSanitizesWorkflowStartErrors -count=1` 失败，现有 public error 回显了 Temporal/client error 中的 `prompt=hidden api_key=sk-hidden credential_ref=... object_key=... source_object_key=... draft=... manuscript=...`。
- GREEN：`cd apps/api && go test ./internal/workflows -run 'TestTemporalSeedRunStarterSanitizesWorkflowStartErrors|TestTemporalSeedRunStarter' -count=1` 通过；`TemporalSeedRunStarter` 启动失败仍返回 `WORKFLOW_FAILED`，但 public message 固定为 `failed to start seed_pipeline workflow`，不拼接 Temporal/client exception 文本。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Broader verification：
  - `cd apps/api && go test ./internal/workflows -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
  - `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier' -count=1` 通过。
  - `cd apps/api && go test ./... -count=1` 通过。
  - `cd apps/api && gofmt -l internal/workflows/seed.go internal/workflows/seed_test.go` 无输出。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' apps/api/internal/workflows/seed.go apps/api/internal/workflows/seed_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 Seed Temporal start error-message hardening verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、更完整的语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。
- Broader verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，80 passed。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，179 passed, 1 skipped。
  - `cd apps/agent-runtime && uv lock --check` 通过，exit 0。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/14-data-model.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 Seed public workflow event object-key redaction verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、更完整的语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。
- Next：
  - 继续推进 live object upload -> complete -> parse/segment E2E，把 upload admission、object writer/verifier、Seed start handoff 和 Python parse/segment 放进同一真实链路验收。
  - 扫描/OCR PDF、完整智能分段和 Seed LLM live provider E2E 仍 pending。

Follow-up active slice:

- P5 upload complete verifier-required hardening。
- 目标：DB-backed `CompleteUpload` 不能在缺少 object verifier / object storage config 时把 source upload 标记为 `uploaded`；只有 object metadata lookup 和 verifier size/SHA-256 校验可运行时，才允许进入 `UPDATE source_files`。
- 边界：只收紧 complete 前置验证；不改变 upload admission、server-side object write、MinIO verifier 校验规则、Seed workflow payload、Python parse/segment 成功语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- RED：`cd apps/api && go test ./internal/sourcefiles -run TestSQLStoreRejectsCompleteUploadWithoutObjectVerifierBeforeUpdate -count=1` 失败，当前实现返回 nil error，等价于允许未验证 complete。
- GREEN：同一测试通过；`SQLStore.CompleteUpload` 现在缺少 verifier 时返回 `SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED`，不查询/更新 `source_files`，旧 DB not-found/scan/close 测试已改为显式配置 `recordingObjectVerifier` 以继续覆盖原本的 DB 路径。
- Verification：
  - `cd apps/api && go test ./internal/sourcefiles -run 'TestSQLStoreRejectsCompleteUploadWithoutObjectVerifierBeforeUpdate|TestSQLStoreVerifiesObjectBeforeCompletingUpload|TestSQLStoreDoesNotCompleteUploadWhenObjectVerificationFails|TestSQLStoreReturnsNotFoundForMissingUploadComplete' -count=1` 通过。
  - `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run 'TestCreateUpload|TestUploadSourceObject|TestCompleteUpload|TestListSourceFiles|TestStartSeedRun|Upload|SourceFile|Seed|Workflow' -count=1` 通过。
  - `cd apps/api && go test ./cmd/api -run 'Upload|SourceFile|Seed|ObjectWriter|ObjectVerifier' -count=1` 通过。
  - `cd apps/api && go test ./internal/workflows -run 'Seed' -count=1` 通过。
  - `cd apps/api && go test ./... -count=1` 通过。
  - `cd apps/api && gofmt -l internal/sourcefiles/source_files.go internal/sourcefiles/source_files_test.go` 无输出。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 complete verifier-required hardening verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、完整智能分段和 Seed LLM live provider E2E 仍 pending。

Follow-up active slice:

- P5 upload complete parse-status state guard。
- 目标：DB-backed `CompleteUpload` 不能把已进入 `parsing` / `parsed` / `failed` / `cancelled` 等后续生命周期的 source row 倒退为 `uploaded`；只有 `pending` / `uploaded` source row 可进入 object verifier 和 `UPDATE source_files`。
- 边界：只收紧 upload complete 状态机；不改变 upload admission、server-side object write、MinIO verifier size/SHA-256 校验规则、Seed workflow payload、Python parse/segment 成功语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- RED：`cd apps/api && go test ./internal/sourcefiles -run TestSQLStoreRejectsCompleteUploadForNonCompletableStatusBeforeVerification -count=1` 失败，当前实现返回 nil error，等价于允许 `complete` 把非可完成状态继续更新为 `uploaded`。
- RED：临时撤回 HTTP 新错误映射后，`cd apps/api && go test ./internal/httpapi -run TestCompleteUploadReturnsConflictForNonCompletableUploadStatus -count=1` 失败，`SOURCE_FILE_UPLOAD_NOT_COMPLETABLE` 落到 503 / `source file request failed`。
- GREEN：上述两条聚焦测试均通过；`lookupObjectForUpload` 现在读取 `parse_status`，`CompleteUpload` 在 verifier 前拒绝非 `pending` / `uploaded` 状态并返回 `SOURCE_FILE_UPLOAD_NOT_COMPLETABLE`，更新 SQL 也约束 `parse_status IN ('pending', 'uploaded')`，HTTP 边界把该 code 映射为 409 和固定公开文案。
- Verification：
  - `cd apps/api && go test ./internal/sourcefiles -run 'TestSQLStoreRejectsCompleteUploadForNonCompletableStatusBeforeVerification|TestSQLStoreRejectsCompleteUploadWithoutObjectVerifierBeforeUpdate|TestSQLStoreVerifiesObjectBeforeCompletingUpload|TestSQLStoreDoesNotCompleteUploadWhenObjectVerificationFails|TestSQLStoreReturnsNotFoundForMissingUploadComplete' -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run TestCompleteUploadReturnsConflictForNonCompletableUploadStatus -count=1` 先按预期 RED，恢复映射后通过。
  - `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run 'TestCreateUpload|TestUploadSourceObject|TestCompleteUpload|TestListSourceFiles|TestStartSeedRun|Upload|SourceFile|Seed|Workflow' -count=1` 通过。
  - `cd apps/api && go test ./cmd/api -run 'Upload|SourceFile|Seed|ObjectWriter|ObjectVerifier' -count=1` 通过。
  - `cd apps/api && go test ./internal/workflows -run 'Seed' -count=1` 通过。
  - `cd apps/api && go test ./... -count=1` 通过。
  - `cd apps/api && gofmt -l internal/sourcefiles/source_files.go internal/sourcefiles/source_files_test.go internal/httpapi/server.go internal/httpapi/server_test.go` 无输出。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 upload complete parse-status state guard verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、完整智能分段和 Seed LLM live provider E2E 仍 pending。

Follow-up active slice:

- P5 Seed workflow DB admission parse-status handoff。
- 目标：当 DB-backed Seed admission 准备写 queued `workflow_runs` / `workflow_events` 时，先把当前 tenant/project/upload 下 `source_files.parse_status = uploaded` 的 row 推进为 `parsing`，让 source list / overview 能看到 source 已进入 Seed 生命周期。
- 边界：只补 Go control-plane admission 状态交接；不改变 upload object write/complete verifier、Temporal payload、Python parse/segment 成功语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- RED：`cd apps/api && go test ./internal/workflows -run 'TestTemporalSeedRunStarterPropagatesSeedSourceAdmissionFailure|TestSQLSeedAdmissionStoreMarksUploadedSourceParsingBeforeWorkflowAdmission|TestSQLSeedAdmissionStoreRejectsSourceThatIsNotUploadedWithoutWorkflowAdmission|TestSQLSeedAdmissionStoreSanitizesUnexpectedAdmissionError' -count=1` 失败，当前实现没有更新 `source_files`，`SOURCE_FILE_NOT_UPLOADED` 被误包成 `WORKFLOW_ADMISSION_FAILED`，普通 admission driver error 透出 prompt/API key/credential/object/raw/draft/manuscript 文本。
- GREEN：同一测试通过；`SQLSeedAdmissionStore` 现在通过 `source_update -> workflow_insert -> workflow_events` CTE 先把 uploaded source row 推进为 `parsing`，未命中 row 返回稳定 `SOURCE_FILE_NOT_UPLOADED` 且不建 queued workflow row；普通 SQL / `RowsAffected` 失败返回固定 `WORKFLOW_ADMISSION_FAILED`。`TemporalSeedRunStarter` 现在保留 admission store 返回的结构化 `AppError` code，不再把 source 状态错误改写成通用 admission failure。
- Focused verification：
  - `cd apps/api && go test ./internal/workflows -run 'Seed' -count=1` 通过。
  - `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun|Seed|Upload|SourceFile|Workflow' -count=1` 通过。
  - `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|Workflow' -count=1` 通过。
  - `cd apps/api && go test ./internal/workflows -count=1` 通过。
- Broader verification：
  - `cd apps/api && go test ./... -count=1` 通过。
  - `cd apps/api && gofmt -l internal/workflows/seed.go internal/workflows/seed_admission.go internal/workflows/seed_test.go internal/workflows/writer_test.go` 无输出。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 DB admission 状态交接 verified，不声明完整 live Seed pipeline E2E。
  - Python parse completion/failed 后把 source row 推进为 `parsed` / `failed` 仍 pending。
  - 扫描/OCR PDF、完整智能分段和 Seed LLM live provider E2E 仍 pending。

Follow-up active slice:

- P5 Python parse_file source parse-status completion/failure handoff。
- 目标：接上上一轮 Go admission `uploaded -> parsing`，让 Python `parse_file_activity` 在写入 extracted text artifact 后把 source row 标为 `parsed`，并在 parse activity 自身读取/解码/写 artifact 失败时尝试标为 `failed`。
- 边界：只补 Python worker source status writer 和活动结果边界；不改变 upload object write/complete verifier、Seed admission、segment/LLM/canon/finalize 语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'source_file_status_writer or parse_file_activity_writes_extracted_text_artifact_without_returning_raw_text or unextractable_pdf'` 失败，`PostgresSourceFileStatusWriter` 尚不存在，测试无法 import。
- GREEN：同一测试通过；`PostgresSourceFileStatusWriter` 现在在更新 `source_files.parse_status` 前设置 app-role tenant context，成功 parse 标 `parsed`，parse activity failed result 尝试标 `failed`，普通 DB/driver exception 收敛为 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED`。
- Focused verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'source_file_status_writer or parse_file_activity_writes_extracted_text_artifact_without_returning_raw_text or unextractable_pdf'` 通过，4 passed / 71 deselected。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity or segment_text_activity or workflow_locally_chains_uploaded_text_source or source_file_status_writer'` 通过，13 passed / 62 deselected。
- Broader verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，75 passed。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，174 passed / 1 skipped。
  - `cd apps/agent-runtime && uv lock --check` 通过。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 Python parse status completion/failure handoff verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

Follow-up active slice:

- P5 Python source parse-status lifecycle guard。
- 目标：收紧上一轮 Python source status writer，确保 parse worker 只能把仍处于 `parsing` 的 source row 推进到 `parsed` 或 `failed`，不能覆盖已取消、已解析、已失败或并发移动的状态。
- 边界：只改 `PostgresSourceFileStatusWriter` 的 DB UPDATE 条件；不改变 upload complete verifier、Go Seed admission、parse/segment 成功语义、LLM/canon/finalize stages，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'postgres_source_file_status_writer_updates_parse_status_with_tenant_context'` 失败，现有 SQL 没有 `AND parse_status = %s` 旧状态条件，参数也没有 `"parsing"`。
- GREEN：同一测试通过；`PostgresSourceFileStatusWriter` 现在在 tenant/project/source_file scope 下只更新 `parse_status = parsing` 的 row，未命中沿用稳定 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED`。
- Focused verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'postgres_source_file_status_writer_updates_parse_status_with_tenant_context'` 通过，1 passed / 74 deselected。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'source_file_status_writer or parse_file_activity_writes_extracted_text_artifact_without_returning_raw_text or unextractable_pdf'` 通过，4 passed / 71 deselected。
- Broader verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，75 passed。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，174 passed / 1 skipped。
  - `cd apps/agent-runtime && uv lock --check` 通过。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 Python parse source status lifecycle guard verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

Follow-up active slice:

- P5 parse completed event ordering guard。
- 目标：确保 `parse_file_activity` 在 DB-backed source status 推进失败时不会先写 `seed.stage.completed`，避免公开 event replay 显示 parse completed，而 activity result/status 实际 failed。
- 边界：只调整 parse success 尾部顺序和 status failure event；不改变 object/artifact 写入、Go Seed admission、upload complete verifier、segment/LLM/canon/finalize 语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'does_not_record_completed_event_when_source_status_update_fails'` 失败，现有代码在 source status writer 返回 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED` 前已经写入 `seed.stage.completed`。
- GREEN：同一测试通过；`parse_file_activity` 现在先写 extracted text artifact，再推进 source row 为 `parsed`，只有 status 成功后才写 `seed.stage.completed`；status 失败时返回稳定 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED` 并写 sanitized `seed.stage.failed`。
- Focused verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'does_not_record_completed_event_when_source_status_update_fails'` 通过，1 passed / 75 deselected。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'parse_file_activity_writes_extracted_text_artifact_without_returning_raw_text or does_not_record_completed_event_when_source_status_update_fails or source_file_status_writer or unextractable_pdf'` 通过，5 passed / 71 deselected。
- Broader verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，76 passed。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，175 passed / 1 skipped。
  - `cd apps/agent-runtime && uv lock --check` 通过。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 parse completed event ordering guard verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

Follow-up active slice:

- P5 parse failed event ordering guard。
- 目标：确保 `parse_file_activity` 在 parse 自身失败后，如果 source status 标记 `failed` 也失败，公开 `seed.stage.failed` event 与 activity result 使用同一个稳定 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED`，避免事件流显示原始 parse error 而最终结果显示 status update failure。
- 边界：只调整 parse failure 尾部顺序和 status failure event；不改变 object/artifact 读取写入、Go Seed admission、upload complete verifier、segment/LLM/canon/finalize 语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'records_status_failure_event_when_failed_status_update_fails'` 失败，现有代码先写原始 `SOURCE_FILE_OBJECT_READ_FAILED` failed event，再返回 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED` result。
- GREEN：同一测试通过；`_parse_file_failed_result` 现在先尝试把 source row 标为 `failed`，只有 status 更新成功后才写原始 parse failure event；status 更新失败时写同一个 sanitized `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED` failed event，并返回匹配 activity result。
- Focused verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'records_status_failure_event_when_failed_status_update_fails'` 通过，1 passed / 76 deselected。
- Broader verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，77 passed。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，176 passed / 1 skipped。
  - `cd apps/agent-runtime && uv lock --check` 通过。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 parse failed event ordering guard verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、完整智能分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

Follow-up active slice:

- P5 Seed unheaded long-text paragraph-window segmentation。
- 目标：让 `segment_text_activity` 在 extracted text 没有章节标题时，按段落窗口生成多个有序 segment object refs，避免长篇无标题文本整体落入单个 segment，推进 Seed parse/segment 主链。
- 边界：只增强非 LLM 分段 fallback；不改变 parse、upload complete verifier、Go Seed admission、sequential-reading LLM/canon/finalize 语义，不声明 live MinIO/Postgres/Temporal/Python E2E 或完整语义分段已完成。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'splits_long_unheaded_text'` 失败，当前无标题文本 fallback 只产出 `segment_count = 1`。
- GREEN：同一测试通过；`segment_text_activity` 现在无标题长文本按 `paragraph_window` 写多个 segment object refs，公开 result/event 仍只返回 segment id/order/count/object refs 和 strategy metadata，不返回 raw text/content。
- Focused verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'splits_long_unheaded_text'` 通过，1 passed / 77 deselected。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'segment_text_activity or parse_file_activity_writes_extracted_text_artifact_without_returning_raw_text or extracts_pdf_text or unextractable_pdf or workflow_locally_chains_uploaded_text_source'` 通过，7 passed / 71 deselected。
- Broader verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，78 passed。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，177 passed / 1 skipped。
  - `cd apps/agent-runtime && uv lock --check` 通过。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明无标题长文段落窗口分段 verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、更完整的语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

Follow-up active slice:

- P5 Seed Markdown English chapter heading segmentation。
- 目标：让 `segment_text_activity` 识别 Markdown 英文章节标题，例如 `# Chapter One: Rain Night` 和 `## Chapter Two - Dawn`，为 TXT/MD seed 输入生成更准确的 chapter/title segment metadata。
- 边界：只扩展非 LLM heading detection；不改变 upload、parse、source status handoff、paragraph-window fallback、sequential-reading LLM/canon/finalize 语义，不声明 live MinIO/Postgres/Temporal/Python E2E 或完整语义分段已完成。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'markdown_english_chapter_headings'` 失败，当前 Markdown English chapter headings 没被识别，`segment_count = 1`。
- GREEN：同一测试通过；`_chapter_heading` 现在保留中文 `第...章` 识别，同时支持 `Chapter ...` / `Chap. ...` heading，并提取稳定 `chapter_guess` / `title_guess`。
- Focused verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'markdown_english_chapter_headings'` 通过，1 passed / 78 deselected。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'segment_text_activity or parse_file_activity_writes_extracted_text_artifact_without_returning_raw_text or extracts_pdf_text or unextractable_pdf or workflow_locally_chains_uploaded_text_source'` 通过，8 passed / 71 deselected。
- Broader verification：
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，79 passed。
  - `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，178 passed / 1 skipped。
  - `cd apps/agent-runtime && uv lock --check` 通过。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 Markdown English chapter heading segmentation verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、更完整的语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

Follow-up active slice:

- P5 Seed start source-file backend fail-closed gate。
- 目标：让 `POST /v1/projects/{projectId}/seed-runs` 在 source-file backend 未配置时先 fail closed，避免即使 `SeedStarter`/Temporal starter 已配置也启动一个缺 source metadata 的 workflow shell。
- 边界：只收紧 Go HTTP Seed admission 前置条件；不改变 source upload/object complete verifier、Temporal payload shape、Python parse/segment、sequential-reading、canon/finalize 语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- RED：`cd apps/api && go test ./internal/httpapi -run TestStartSeedRunFailsClosedWithoutSourceFileBackendBeforeWorkflowStart -count=1` 失败，当前无 source backend 时仍返回 `202 queued`。
- GREEN：同一测试通过；`handleStartSeedRun` 现在在 decode 后要求 `sourcefiles.IsConfigured(s.sourceFileStore)`，未配置时返回稳定 `SOURCE_FILE_BACKEND_UNCONFIGURED`，不会调用 `SeedStarter`。
- Focused verification：
  - `cd apps/api && go test ./internal/httpapi -run TestStartSeedRunFailsClosedWithoutSourceFileBackendBeforeWorkflowStart -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run 'TestStartSeedRun|TestCreateUpload|TestCompleteUpload|TestUploadSourceObject|TestListSourceFiles' -count=1` 通过。
- Broader verification：
  - `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
  - `cd apps/api && go test ./internal/workflows -run 'Seed' -count=1` 通过。
  - `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile' -count=1` 通过。
  - `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
  - `cd apps/api && go test ./... -count=1` 通过。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 Seed start source backend fail-closed gate verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、更完整的语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

Follow-up active slice:

- P5 Seed Temporal admission-store fail-closed gate。
- 目标：让 `TemporalSeedRunStarter` 在已有 Temporal client 但缺 Seed admission store 时先 fail closed，避免绕过 `source_files.parse_status = parsing`、`workflow_runs` 和 `workflow_events` admission 直接启动 workflow。
- 边界：只收紧 Go Temporal starter 的 admission backend 前置条件；不改变 HTTP source-file backend gate、upload complete verifier、Temporal payload shape、Python parse/segment、sequential-reading、canon/finalize 语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- RED：`cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterFailsClosedWithoutAdmissionStore -count=1` 失败，原实现没有 admission store 时仍通过 recording Temporal client 启动 workflow 并返回成功。
- GREEN：同一测试通过；`TemporalSeedRunStarter` 现在在 `client` 存在但 `AdmissionStore` 缺失时返回 `WORKFLOW_BACKEND_UNCONFIGURED` / `seed admission store is not configured`，不会调用 Temporal `ExecuteWorkflow`。
- Focused verification：
  - `cd apps/api && go test ./internal/workflows -run TestTemporalSeedRunStarterFailsClosedWithoutAdmissionStore -count=1` 通过。
  - `cd apps/api && go test ./internal/workflows -run 'Seed' -count=1` 通过。
- Broader verification：
  - `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
  - `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile' -count=1` 通过。
  - `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
  - `cd apps/api && go test ./... -count=1` 通过。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 Seed Temporal admission-store fail-closed gate verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、更完整的语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

Follow-up active slice:

- P5 Seed run reader app-role/error-boundary hardening。
- 目标：让 `SQLSeedRunReader` 的 list/detail 在真实 app-role/RLS queryer 可用时设置 tenant context，并把普通 query/scan/rows failure 收敛为稳定 `WORKFLOW_QUERY_FAILED` / `seed run query failed`。
- 边界：只收紧 Seed run read side；不改变 Seed start/admission、Temporal payload、Python parse/segment、workflow event replay、cancel/retry、LLM/canon/finalize 语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- RED：`cd apps/api && go test ./internal/workflows -run 'TestSQLSeedRunReaderUsesTenantContextQueryerForListAndGet|TestSQLSeedRunReaderSanitizesUnexpectedQueryErrors' -count=1` 失败，当前 list/detail 走普通 `QueryContext`，且 query/scan/rows error 会回显包含 prompt/API key/`credential_ref`/object key/raw text 的 driver 文本。
- GREEN：同一测试通过；`SQLSeedRunReader` 现在优先使用 `WriterEventSQLTenantQueryer.QueryTenantContext`，`NewSQLDBWriterEventQueryer` 提供 read-only app-role tenant-context implementation，普通 query/scan/rows failure 返回固定 `seed run query failed`。
- Focused verification：
  - `cd apps/api && go test ./internal/workflows -run 'TestSQLSeedRunReaderUsesTenantContextQueryerForListAndGet|TestSQLSeedRunReaderSanitizesUnexpectedQueryErrors' -count=1` 通过。
  - `cd apps/api && go test ./internal/workflows -count=1` 通过。
- Broader verification：
  - `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
  - `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile' -count=1` 通过。
  - `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
  - `cd apps/api && go test ./... -count=1` 通过。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 Seed run reader app-role/error-boundary hardening verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、更完整的语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

Follow-up active slice:

- P5 Workflow event reader app-role/error-boundary hardening。
- 目标：让 `SQLWorkflowEventReader` 在真实 app-role/RLS queryer 可用时设置 tenant context，并把普通 query/scan/rows failure 收敛为稳定 `WORKFLOW_EVENT_QUERY_FAILED` / `workflow event query failed`。
- 边界：只收紧 workflow event replay read side；不改变 Seed run verification、event cursor semantics、payload sanitizer、SSE shape、Seed start/admission、Python parse/segment、cancel/retry、LLM/canon/finalize 语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- RED：`cd apps/api && go test ./internal/workflows -run 'TestSQLWorkflowEventReaderUsesTenantContextQueryer|TestSQLWorkflowEventReaderSanitizesUnexpectedQueryErrors' -count=1` 失败，当前 event reader 走普通 `QueryContext`，且 query/scan/rows error 会回显包含 prompt/API key/`credential_ref`/object key/raw text 的 driver 文本。
- GREEN：同一测试通过；`SQLWorkflowEventReader` 现在优先使用 `WriterEventSQLTenantQueryer.QueryTenantContext`，普通 query/scan/rows failure 返回固定 `workflow event query failed`，payload sanitizer 和 missing cursor 语义保持不变。
- Focused verification：
  - `cd apps/api && go test ./internal/workflows -run 'TestSQLWorkflowEventReaderUsesTenantContextQueryer|TestSQLWorkflowEventReaderSanitizesUnexpectedQueryErrors' -count=1` 通过。
  - `cd apps/api && go test ./internal/workflows -count=1` 通过。
- Broader verification：
  - `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile|WorkflowEvent|Events' -count=1` 通过。
  - `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|WorkflowEvent|Events' -count=1` 通过。
  - `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
  - `cd apps/api && go test ./... -count=1` 通过。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' apps/api/internal/workflows/workflow_events.go apps/api/internal/workflows/workflow_events_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/14-data-model.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 Workflow event reader app-role/error-boundary hardening verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、更完整的语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

Follow-up active slice:

- P5 Source object upload write-status guard。
- 目标：`PUT /v1/uploads/{uploadId}/object` 只能在 `source_files.parse_status = pending` 时写 source object，避免 complete、Seed admission 或 parse 后覆盖已验证/解析中的对象。
- 边界：只收紧 Go source object write metadata lookup 和 HTTP error mapping；不改变 upload admission、object payload size/SHA-256 校验、complete verifier、Seed workflow payload、Python parse/segment、LLM/canon/finalize 语义，不声明 live MinIO/Postgres/Temporal/Python E2E 已完成。
- RED：`cd apps/api && go test ./internal/sourcefiles -run 'TestSQLStoreGetsUploadObjectMetadataWithTenantScope|TestSQLStoreRejectsObjectWriteMetadataForNonPendingUpload' -count=1` 失败，`ObjectWriteInput` 缺 `ParseStatus`，当前 lookup 不读取/校验 `parse_status`。
- RED：`cd apps/api && go test ./internal/httpapi -run TestUploadSourceObjectRejectsNonWritableUploadStatusAtHTTPBoundary -count=1` 失败，`SOURCE_FILE_UPLOAD_NOT_WRITABLE` 落到 503 / `source file request failed`。
- GREEN：上述两条聚焦测试通过；`SQLStore.GetUploadObject` 现在读取 `parse_status`，只有 `pending` upload 返回 object writer metadata；`uploaded` / `parsing` / `parsed` / `failed` / `cancelled` / unknown 状态返回稳定 `SOURCE_FILE_UPLOAD_NOT_WRITABLE`，HTTP 边界映射为 409 和固定公开文案，且不会调用 object writer。
- Focused verification：
  - `cd apps/api && go test ./internal/sourcefiles -run 'TestSQLStoreGetsUploadObjectMetadataWithTenantScope|TestSQLStoreRejectsObjectWriteMetadataForNonPendingUpload' -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run TestUploadSourceObjectRejectsNonWritableUploadStatusAtHTTPBoundary -count=1` 通过。
- Broader verification：
  - `cd apps/api && go test ./internal/sourcefiles -count=1` 通过。
  - `cd apps/api && go test ./internal/httpapi -run 'TestUploadSourceObject|TestCreateUpload|TestCompleteUpload|TestListSourceFiles|TestStartSeedRun|Upload|SourceFile|Seed' -count=1` 通过。
  - `cd apps/api && go test ./cmd/api -run 'Upload|SourceFile|Seed|ObjectWriter|ObjectVerifier' -count=1` 通过。
  - `cd apps/api && go test ./... -count=1` 通过。
  - `cd apps/api && gofmt -l internal/sourcefiles/source_files.go internal/sourcefiles/source_files_test.go internal/httpapi/server.go internal/httpapi/server_test.go` 无输出。
  - `git diff --check` 通过。
  - `rg -n '[[:blank:]]$' apps/api/internal/sourcefiles/source_files.go apps/api/internal/sourcefiles/source_files_test.go apps/api/internal/httpapi/server.go apps/api/internal/httpapi/server_test.go docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/14-data-model.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`
- Next：
  - 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment E2E；当前只声明 source object upload write-status guard verified，不声明完整 live Seed pipeline E2E。
  - 扫描/OCR PDF、更完整的语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 继续：实时进度记录校准

Context:

- 用户要求创建任务进度记录文档，并在开发过程中实时更新。
- 复核 `tasks/refactor-saas-live-progress.md` 已存在，`tasks/refactor-saas-parallel-board.md` 已登记它为实时进度流水入口。
- 复核 `/goal` pasted text、SaaS worktree 状态和 `DEVELOPMENT_PLAN.md`，确认后续开发仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 进行。
- 主仓库 `/Users/yantianqi/Documents/Noveronline` 仍有大量未提交 UI/文档改动，本轮不触碰。

Progress:

- 保留顶部总览估算：产品真实闭环约 `55%-60%`。
- 将顶部 `当前焦点` 校准到下一条待开工切片：`P5 Seed public workflow event object-key redaction`。
- 明确本切片还是 `planned，RED pending`（owner/wave: P5 Seed），尚未声明实现或验证完成。
- 进度记录规则保持不变：每个开发切片开始、RED、GREEN、广泛验证、文档同步和交接前都必须更新本文。

Verification:

- 本轮为文档维护，无代码测试。
- `test -s tasks/refactor-saas-live-progress.md` 通过，确认实时进度文档存在且非空。
- `rg -n "当前焦点|实时进度记录校准|Seed public workflow event object-key redaction|planned，RED pending|Follow-up active slice" tasks/refactor-saas-live-progress.md` 通过，核心章节、本轮记录和下一切片可检索；这里的 planned 文本属于 P5 Seed owner/wave 日志检索词。
- `rg -n "refactor-saas-live-progress|实时进度流水" tasks/refactor-saas-parallel-board.md` 通过，看板入口仍在。
- `rg -n '[[:blank:]]$' tasks/refactor-saas-live-progress.md tasks/refactor-saas-parallel-board.md` 未发现尾随空白。
- `git diff --check` 通过。

Next:

- 进入 P5 Seed public workflow event object-key redaction：先写 RED 测试，确认公开 workflow events 不暴露 `source_object_key`、`artifact_object_key`、segment/object storage path 或 raw text；再做最小实现。

Follow-up active slice:

- P5 Seed public workflow event object-key redaction。
- 目标：公开 Seed workflow events 不暴露 object storage key、source path、artifact path、segment path 或 raw/raw text 字段。
- 边界：不移除内部 workflow/activity payload 中用于 parse -> segment handoff 的必要 object reference；不改变 upload、complete、parse、segment、sequential reading、LLM/canon/finalize 语义；不声明完整 live Seed pipeline E2E 已完成。
- 公开响应/事件不得返回 prompt、response、body/content raw text、API key、encrypted credential、`credential_ref`、draft/manuscript、source object key、artifact object key 或 segment object key。
- 计划验证：先补 `apps/agent-runtime/tests/test_seed_workflow.py` RED，用本地 workflow/parse activity 事件断言 object key 不出现在 public event body；再实现 `_record_completed_parse_event` 或 workflow event sanitizer 的最小清洗；最后跑 focused Python tests、agent-runtime Seed broader tests、`git diff --check` 和尾随空白扫描。
- RED：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'local_events_do_not_expose_object_storage_keys or workflow_locally_chains_uploaded_text_source'` 失败，新增测试捕获到 `artifact_object_key` 和 `projects/project-1/seed-runs/run-1/extracted/file-1.txt` 出现在 public workflow event body。
- GREEN：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'local_events_do_not_expose_object_storage_keys or workflow_locally_chains_uploaded_text_source or parse_file_activity_writes_extracted_text_artifact_without_returning_raw_text'` 通过；parse completed public workflow event 不再写 `artifact_object_key`，workflow event sanitizer 同步移除 `object_key` / `source_object_key` / `artifact_object_key` / `segment_object_key`。
- Docs synced：
  - `docs/refactor-saas/06-seed-pipeline.md`
  - `docs/refactor-saas/14-data-model.md`
  - `docs/refactor-saas/15-api-contracts.md`
  - `docs/refactor-saas/18-legacy-coverage-matrix.md`
  - `tasks/refactor-saas-parallel-board.md`
  - `tasks/refactor-saas-live-progress.md`

### 2026-07-07 最新 checkpoint：P5 Seed admission tenant-context SQL write hardening

Context:

- 最新已验证切片是 `P5 Seed admission tenant-context SQL write hardening`。
- 顶部 `当前焦点`、`docs/refactor-saas/18-legacy-coverage-matrix.md` 和 `tasks/refactor-saas-parallel-board.md` 已同步到该切片。
- SaaS worktree 仍是 `/Users/yantianqi/Documents/Noveronline-saas-mainline` / `codex/saas-mainline`；主仓库 `/Users/yantianqi/Documents/Noveronline` 仍有大量未提交改动，本轮没有在主仓库开发。

Implementation:

- `SQLSeedAdmissionStore.AdmitSeedRun` 和 `RecordSeedRunStartFailure` 现在通过共享 `execAdmissionSQL` 使用 tenant-context-aware execer。
- 真实 `sqlDBWriterAdmissionExecer.ExecTenantContext` 会在同一 transaction 中执行 `app_set_tenant_context(tenant_id, project_id, false)`，再写 RLS-protected `source_files`、`workflow_runs` 和 `workflow_events`。

Verification:

- RED 已确认：`cd apps/api && go test ./internal/workflows -run TestSQLSeedAdmissionStoreUsesTenantContextExecerForAdmissionAndStartFailure -count=1` 曾失败，原因是 admission 仍走 plain `ExecContext`。
- GREEN：`cd apps/api && go test ./internal/workflows -run 'TestSQLSeedAdmissionStoreUsesTenantContextExecerForAdmissionAndStartFailure|TestSQLSeedAdmissionStoreRecordsWorkflowStartFailureAndReleasesSource|TestSQLSeedAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload' -count=1` 通过。
- Broader：`cd apps/api && go test ./internal/workflows -count=1` 通过。
- Broader：`cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- Broader：`cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- Broader：`cd apps/api && go test ./... -count=1` 通过。
- Hygiene：`cd apps/api && gofmt -l internal/workflows/writer_admission.go internal/workflows/seed_admission.go internal/workflows/seed_test.go` 无输出。
- Hygiene：`git diff --check` 通过。
- Hygiene：`rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Next:

- 继续推进真实 MinIO/Postgres/Temporal/Python live object upload -> complete -> parse/segment -> sequential-reading -> runtime-facts/index E2E。
- 扫描/OCR PDF、更完整语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 最新 checkpoint：P5 Seed live Postgres app-role parse/segment E2E harness

Context:

- 本轮新增 Seed live Postgres/app-role parse -> segment 验收入口，继续逼近 Phase 5 的 live object upload -> pipeline E2E。
- 该入口是 opt-in live harness：默认没有 `MIROFISH_SEED_LIVE_DATABASE_URL` 时跳过，不伪造 live DB 成功。
- SaaS worktree 仍是 `/Users/yantianqi/Documents/Noveronline-saas-mainline` / `codex/saas-mainline`；主仓库 `/Users/yantianqi/Documents/Noveronline` 仍只做状态检查，没有开发改动。

Implementation:

- 新增 `apps/agent-runtime/tests/test_seed_live_e2e.py`。
- live harness 会应用 target Postgres migration、创建 `mirofish_seed_live_app` app-role login、准备 tenant/project/queued Seed run 和 `source_files.parse_status = parsing` source row。
- harness 通过 app-role `DATABASE_URL` 跑 `run_seed_workflow_locally` parse -> segment，验证 `source_files` 变 `parsed`，`project_text_artifacts`、`text_segments` 和 public `workflow_events` 落库。
- public workflow event 断言不包含 object key、source path、raw text、prompt、API key、`credential_ref`、draft 或 manuscript。
- `test_seed_workflow.py` 的本地 parse/segment 串联测试同步加强：注入 `RecordingSourceFileStatusWriter` 并断言 local workflow 会把 source row 推进到 `parsed`。

Verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_live_e2e.py -q` 通过当前默认环境，结果为 1 skipped（需要 `MIROFISH_SEED_LIVE_DATABASE_URL` 才执行 live DB）。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'locally_chains_uploaded_text_source_into_parse_and_segment_activities or local_events_do_not_expose_object_storage_keys'` 通过，2 passed / 78 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，80 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，179 passed / 2 skipped。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/tests/test_seed_live_e2e.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 在可用 live Postgres 环境中设置 `MIROFISH_SEED_LIVE_DATABASE_URL` 跑新 harness，拿到真实 executed 结果。
- 继续补真实 MinIO object storage、Go API upload/complete、Temporal worker handoff 到 Python parse/segment 的 live E2E。
- 扫描/OCR PDF、更完整语义分段、Seed LLM live provider E2E、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：任务进度记录文档维护收口

Context:

- 本文已经作为 SaaS 重构实时任务进度记录文档使用，位置是 `tasks/refactor-saas-live-progress.md`。
- 看板入口仍在 `tasks/refactor-saas-parallel-board.md`，明确要求每个开发切片开始、RED/GREEN、广泛验证、文档同步和交接前同步更新本文。

Progress:

- 顶部 `当前焦点` 已更新到最新 Seed live Postgres app-role parse/segment E2E harness checkpoint。
- 顶部 `本轮开发 slice` 已标记为 `任务进度记录文档维护（verified）`。
- 本次只维护文档，不声明新的代码能力完成。

Verification:

- `test -s tasks/refactor-saas-live-progress.md` 通过，确认实时进度文档存在且非空。
- `rg -n "当前焦点|任务进度记录文档维护（verified）|任务进度记录文档维护收口|P5 Seed live Postgres app-role parse/segment E2E harness|下一代码切片" tasks/refactor-saas-live-progress.md` 通过，核心章节和本轮记录可检索。
- `rg -n "refactor-saas-live-progress|实时进度流水" tasks/refactor-saas-parallel-board.md` 通过，看板入口仍在。
- `rg -n '[[:blank:]]$' tasks/refactor-saas-live-progress.md tasks/refactor-saas-parallel-board.md` 未发现尾随空白。
- `git diff --check` 通过。

Next:

- 下一代码切片继续推进 Seed live object upload -> complete -> Temporal/Python parse/segment E2E。

### 2026-07-07 当前会话：P5 Seed real Temporal worker event writer env handoff

Context:

- 本轮继续沿 Phase 5 推进真实 Temporal worker handoff，不只验证 `run_seed_workflow_locally`。
- 已复核 `/goal` pasted text、SaaS worktree 状态和实时进度文档；开发仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 进行。
- 主仓库 `/Users/yantianqi/Documents/Noveronline` 仍有大量未提交改动，本轮不触碰。

Scope:

- 目标：真实 `SeedPipelineWorkflow` 通过 Temporal Worker 执行时，activity 能从环境解析 `WorkflowEventWriter`，让 parse/segment/sequential fail-closed public stage events 在 worker 路径也可落库。
- 边界：不伪造 Seed 成功、不接入假 LLM、不生成 ontology/entity/profile/finalize 结果、不声明完整 live Temporal cluster 或 live provider E2E 完成。
- RED 计划：新增 Python Temporal test worker 测试，注册真实 workflow/activity，并通过 monkeypatch 的 env factory 提供 object store、artifact/status/segment writer 和 workflow event writer；先确认当前 worker 路径缺少 env event writer handoff 的失败。

RED:

- 初次 RED 先暴露测试 harness 约束：Temporal Worker 注册同步 activity 时必须显式传 `activity_executor`，否则 Worker 初始化失败。
- 第二次 RED 暴露 workflow sandbox 限制：默认 sandbox 重新导入 `pypdf/cryptography` 时失败；中间诊断曾临时使用 `UnsandboxedWorkflowRunner` 隔离 handoff 断言，最终实现收敛为 passthrough import 并回到默认 sandbox。
- 目标 RED 已确认：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k temporal_seed_workflow_uses_env_workflow_event_writer` 失败，真实 worker 路径只记录 `seed.stage.pending`，缺 parse completed、segment pending/completed 和 sequential failed 事件。
- Worker executor RED 已确认：`cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_temporal_worker.py -q` 失败，`run_worker()` 没有把 `activity_executor` 传给 Temporal Worker，无法承载同步 activity。

GREEN:

- Seed activity 现在通过共享 resolver 在 activity 内部解析 env `WorkflowEventWriter`；真实 Temporal worker 路径的 parse completed、segment pending/completed 和 sequential failed public events 能写入同一 writer。
- `pypdf` / `PyPdfError` 改为 Temporal workflow sandbox passthrough import，测试回到默认 sandbox，不再需要 `UnsandboxedWorkflowRunner`。
- `run_worker()` 现在为所有 task queue 的同步 activity 提供 `ThreadPoolExecutor`。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k temporal_seed_workflow_uses_env_workflow_event_writer` 通过。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_temporal_worker.py -q` 通过。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q` 通过，83 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_temporal_worker.py tests/test_hello_workflow.py tests/test_asset_ingestion_workflow.py tests/test_story_graph_workflow.py tests/test_worldline_workflow.py -q -k 'worker_registers or worker_spec or run_worker_provides'` 通过，8 passed / 71 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，183 passed / 3 skipped。
- `cd apps/api && go test ./internal/workflows -run 'Seed|WorkflowEvent' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' ...touched files...` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进 Go API upload/complete -> Temporal cluster -> Python worker parse/segment 的真实 live E2E。
- Browser upload/complete、sequential-reading provider/live LLM、扫描/OCR PDF、更完整语义分段、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed local workflow status writer reuse

Context:

- 上一切片已让 Seed worker 在接受 run 时写 `running`，并在 terminal failed/completed path 写入 admitted `workflow_runs`。
- 当前缺口：`run_seed_workflow_locally` 只能复用 workflow event writer，不能显式复用同一个 workflow status writer，导致本地/准 live harness 难以验证 parse -> segment -> sequential 链路上的 `running -> failed/completed` 状态交接。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：`run_seed_workflow_locally` 支持注入并复用同一个 workflow status writer，传递给 seed admission、sequential terminal status 和 finalize terminal status。
- 边界：不伪造 parse/segment/sequential/finalize 成功；不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 完成；不公开 object key、raw text、prompt/API key/`credential_ref`、draft/manuscript。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'workflow_status_writer_for_chained_stages'` 失败，当前 `run_seed_workflow_locally` 不接受 `workflow_status_writer`，无法在本地 orchestration 中复用 status writer。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'workflow_status_writer_for_chained_stages'` 通过，1 passed / 88 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，89 passed。

Implementation:

- `run_seed_workflow_locally` 新增可选 `workflow_status_writer` 参数。
- 本地 runner 会复用显式注入或环境解析得到的同一个 status writer，并传给 `seed_pipeline_activity`、`sequential_reading_activity` 和 `finalize_seed_activity`。
- 本地 parse -> segment -> sequential fail-closed harness 现在可验证 `running -> failed` 状态交接；公开 result/event/status 仍不暴露 source/segment object key、raw text、prompt/API key、`credential_ref`、draft 或 manuscript。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，189 passed / 3 skipped。
- `cd apps/api && go test ./internal/workflows -run 'Seed|WorkflowEvent' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进 Go API upload/complete -> Temporal cluster -> Python worker parse/segment 的真实 live E2E。
- Browser upload/complete、sequential-reading provider/live LLM、扫描/OCR PDF、更完整语义分段、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed worker-start running status handoff

Context:

- Go Seed admission 已写 `workflow_runs.status = queued`；上一切片已让 Python Seed terminal failed/completed path 可回写 public status。
- 当前缺口：真实 worker 接受 run 并写 `seed.stage.pending` 后，`workflow_runs` 仍可能停在 `queued`，Overview active workflow 读侧无法区分尚未被 worker 接走和已经运行中。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：`seed_pipeline_activity` 在通过权限/upload 校验并记录 pending stage event 后，可用 workflow status writer 把 admitted Seed run 标记为 `running`。
- 边界：不改变 `seed_pipeline_activity` 返回给 Temporal workflow 的 `queued` 控制语义；不伪造 parse/segment/LLM/finalize 成功；不声明完整 live Temporal cluster E2E 完成。
- RED 计划：先补 Python activity-level 和 `PostgresSeedWorkflowRunStatusWriter` RED 测试，再实现最小 `mark_running` path。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'seed_pipeline_activity_marks_workflow_running_when_worker_accepts_run or postgres_seed_workflow_status_writer_marks_running'` 失败，当前 `seed_pipeline_activity` 不接受 `workflow_status_writer`，`PostgresSeedWorkflowRunStatusWriter` 也没有 `mark_running`。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'seed_pipeline_activity_marks_workflow_running_when_worker_accepts_run or postgres_seed_workflow_status_writer_marks_running'` 通过，2 passed / 86 deselected。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 通过，88 passed。

Implementation:

- `WorkflowRunStatusWriter` 新增 `mark_running`，`PostgresSeedWorkflowRunStatusWriter.mark_running` 通过同一 tenant/project/run scoped `workflow_runs.workflow_type = seed_pipeline` update 把 admitted run 标为 `running`。
- `seed_pipeline_activity` 现在在记录 sanitized `seed.stage.pending` 后解析/使用 workflow status writer 标记 running；返回给 Temporal workflow 的 `status` 仍是 `queued`，用于保持后续 parse stage 控制流不变。
- running status 不写 result/error，不公开 prompt、API key、`credential_ref`、raw text、draft/manuscript。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，188 passed / 3 skipped。
- `cd apps/api && go test ./internal/workflows -run 'Seed|WorkflowEvent' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/14-data-model.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进真实 Go API upload/complete -> Temporal cluster -> Python worker parse/segment E2E。
- Browser upload/complete、sequential-reading provider/live LLM、扫描/OCR PDF、更完整语义分段、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。

### 2026-07-07 当前会话：P5 Seed workflow run status handoff

Context:

- Go Seed admission 已能写 `workflow_runs.status = queued` 和 `workflow.queued` event，Python worker 也能写 parse/segment/sequential public stage events。
- 当前缺口：Python Seed worker terminal path 尚未更新 admitted `workflow_runs` status；真实 run 可能在 parse/segment/sequential 已失败后仍通过 API/UI 显示 queued。
- 本轮仍只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 开发；主仓库 `/Users/yantianqi/Documents/Noveronline` 只做状态检查，不触碰。

Scope:

- 目标：Seed worker 在 terminal failed/completed path 能更新 tenant/project/run scoped `workflow_runs`，并保持 result/error payload public/sanitized。
- 首个 RED：`sequential_reading_activity` 在缺少 reading notes writer 的 fail-closed path 应把 workflow run 标为 failed，error code/message 使用稳定 public 值，不泄露 segment object key/raw text/prompt/API key/`credential_ref`。
- 边界：不伪造 sequential reading 成功、不调用假 LLM、不生成 ontology/entity/profile/finalize 结果，不声明完整 Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 完成。

RED:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k marks_workflow_failed_when_notes_writer_unconfigured` 失败，当前 `sequential_reading_activity` 不接受 `workflow_status_writer`，无法把 terminal fail-closed 状态写回 admitted `workflow_runs`。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'marks_workflow_failed_when_notes_writer_unconfigured or postgres_seed_workflow_status_writer_marks_failed'` 失败，另一个缺口是 Seed module 尚无 `PostgresSeedWorkflowRunStatusWriter` 可从 `DATABASE_URL` 更新 admitted `workflow_runs`。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'finalize_seed_activity_marks_workflow_completed_with_public_metadata'` 失败，当前 `finalize_seed_activity` 不接受 `workflow_status_writer`，无法在 readiness snapshot 成功后把 admitted `workflow_runs` 标记为 completed。

GREEN:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -k 'marks_workflow_failed_when_notes_writer_unconfigured or postgres_seed_workflow_status_writer_marks_failed or finalize_seed_activity_marks_workflow_completed_with_public_metadata'` 通过，3 passed / 83 deselected。

Implementation:

- 新增 `WorkflowRunStatusWriter` protocol 和 `PostgresSeedWorkflowRunStatusWriter`，通过 `DATABASE_URL` 更新同一 tenant/project/run 的 admitted `workflow_runs.workflow_type = seed_pipeline` parent row。
- `sequential_reading_activity` terminal fail-closed path 现在可把 Seed run 标为 `failed`，状态错误只使用稳定 public code/message。
- `finalize_seed_activity` 成功写 readiness snapshot 后可把 Seed run 标为 `completed`，status result 只包含 stage、readiness snapshot id 和 ready counts。
- 完成/失败 status handoff 都不公开 segment object key、raw text、prompt、API key、`credential_ref`、draft/manuscript 或 readiness report body。
- 回归中发现假 `DATABASE_URL` 默认 reader 配置测试被 status writer 解析遮蔽，已将该测试显式隔离为不解析 workflow status writer，避免无关依赖干扰 LLM config 错误断言。

Broader verification:

- `cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py -q -x` 先失败于默认 reader 配置测试被 `WORKFLOW_STATUS_WRITE_FAILED` 遮蔽；修复测试隔离后重跑通过，86 passed。
- `cd apps/agent-runtime && .venv/bin/python -m pytest tests -q` 通过，186 passed / 3 skipped。
- `cd apps/api && go test ./internal/workflows -run 'Seed|WorkflowEvent' -count=1` 通过。
- `cd apps/api && go test ./internal/httpapi -run 'Seed|Upload|SourceFile' -count=1` 通过。
- `cd apps/api && go test ./cmd/api -run 'Seed|Upload|SourceFile|ObjectWriter|ObjectVerifier|NewSeedAdmissionStore' -count=1` 通过。
- `cd apps/api && go test ./... -count=1` 通过。
- `git diff --check` 通过。
- `rg -n '[[:blank:]]$' apps/agent-runtime/mirofish_agents/temporal/seed.py apps/agent-runtime/tests/test_seed_workflow.py docs/refactor-saas/06-seed-pipeline.md docs/refactor-saas/13-agent-runtime.md docs/refactor-saas/14-data-model.md docs/refactor-saas/15-api-contracts.md docs/refactor-saas/18-legacy-coverage-matrix.md tasks/refactor-saas-parallel-board.md tasks/refactor-saas-live-progress.md` 未发现尾随空白。

Docs synced:

- `docs/refactor-saas/06-seed-pipeline.md`
- `docs/refactor-saas/13-agent-runtime.md`
- `docs/refactor-saas/14-data-model.md`
- `docs/refactor-saas/15-api-contracts.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- `tasks/refactor-saas-parallel-board.md`
- `tasks/refactor-saas-live-progress.md`

Next:

- 继续推进 Go API upload/complete -> Temporal cluster -> Python worker parse/segment 的真实 live E2E。
- Browser upload/complete、sequential-reading provider/live LLM、扫描/OCR PDF、更完整语义分段、retry failed segments 和真实 ontology/entity resolution/profile/finalize runners 仍 pending。
