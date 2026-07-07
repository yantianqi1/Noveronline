# 22. Midstream Handoff Summary

更新时间：`2026-07-05`

## 目的

本文是 SaaS 重构进行中的中途总结和新对话接手卡片。它不替代 `DEVELOPMENT_PLAN.md`、`18-legacy-coverage-matrix.md` 或 `tasks/refactor-saas-parallel-board.md`；继续开发仍必须以这些文件作为基线。

本文件已登记在 `DEVELOPMENT_PLAN.md` 的文档地图中。后续开启新对话时，建议把本文作为 `DEVELOPMENT_PLAN.md` 之后的第二入口，用来快速恢复当前进度、边界约束和下一步优先级。

## 工作区事实

- 主仓库：`/Users/yantianqi/Documents/Noveronline`
- 隔离 worktree：`/Users/yantianqi/Documents/Noveronline-saas-mainline`
- 目标分支：`codex/saas-mainline`
- 主仓库仍有大量未提交改动；SaaS 重构改动集中在隔离 worktree。不得回到主工作区开发、覆盖或混入主工作区改动。

开始任何新开发前必须重新运行：

```bash
git -C /Users/yantianqi/Documents/Noveronline status --short
git -C /Users/yantianqi/Documents/Noveronline-saas-mainline status --short
git -C /Users/yantianqi/Documents/Noveronline-saas-mainline status -sb
```

## 总体完成度估算

按产品真实闭环估算，当前 SaaS 重构约完成 **55%-60%**。

看板数字会显得更乐观，因为许多条目已经有 API、schema、read side、fail-closed worker shell 或 metadata-only 用户动作。但这些还不等价于完整产品：真实 live cluster E2E、真实 provider 调用、runtime 事件生产、浏览器上传、向量搜索、Character Console runtime、Auth/Billing/Ops 仍有大块待做。因此这里采用偏保守的产品闭环估算。

阶段状态：

| Phase | 当前判断 | 说明 |
|---|---:|---|
| Phase 0 | 100% | 文档、覆盖矩阵和隔离 worktree 基线已 verified。 |
| Phase 1 | 80%-90% | Writer-first contract、Pi Runtime skeleton、缺绑定显式失败、draft 保存和显式 adoption 已落地；真实 LLM-bound E2E 仍待验收。 |
| Phase 2 | 70%-80% | Writer read tools 已接入 assets、world rules、character profile、graph neighbors、worldline paths；picker/right rail 已有实现；live LLM reference E2E 和 proposal tools 仍 pending。 |
| Phase 3 | 70%-80% | Go API、Next shell、Postgres/RLS、Temporal/Python/Pi worker skeleton 已落地；完整 compose health、真实 Temporal handoff、Auth/tenant/project picker 仍 pending。 |
| Phase 4 | 75%-85% | LLM Facility schema/API/UI、binding、channel CRUD、model sync、trace/usage、secure key handoff、concurrency lease 已大体完成；live provider/cluster E2E、retry backend、quota/billing 聚合仍 pending。 |
| Phase 5 | 45%-60% | Seed/Assets/Graph 有大量 DB-backed skeleton 和部分真实持久化；PDF、browser direct upload、智能分段、ontology/entity/profile/finalize runner、vector/hybrid search、live provider E2E 仍 pending。 |
| Phase 6 | 35%-45% | Worldline metadata side、step admission Web/API、Python fail-closed workflow shell 和最小 LLM-backed candidate event producer 已推进；runtime-generated saved paths、prepare runtime、richer director tools、Character Console runtime 仍未完成。 |
| Phase 7 | 0%-10% | Legacy import report skeleton blocked，旧架构清理未开始。 |
| Phase 8 | 0%-10% | Ops/Billing/Security/Production hardening 仍主要停留在设计和少量底座。 |

## 已落地的关键能力

- Writer-first vertical slice 已建立：writer run API、Pi Writer Runtime skeleton、LLM Facility 缺绑定显式失败、draft revision 保存和显式 adoption 到 manuscript。
- Writer tools 已读真实数据源：`query_assets`、`query_world_rules`、`query_character_profile`、`query_graph_neighbors`、`query_worldline_paths`，并保留 tool trace / `full_result` 审计信息。
- Go control plane skeleton 已存在，覆盖标准错误 envelope、health、writer workflow admission、generic workflow read/replay/cancel/retry contracts。
- Next App Router shell 已覆盖 project routes：Writer、Guide、Overview、LLM Facility、Asset Library、Story Graph、Worldline、Character Console placeholder。
- Postgres baseline 已覆盖 core SaaS、workflow、writer、LLM、Seed/Canon、Assets/Search、Story Graph、Worldline 第一批表；tenant RLS 和 `mirofish_app` 访问模型已有核心隔离验证。
- LLM Facility 已具备 tenant/project binding resolver、module registry、channel CRUD、model sync、settings snapshot、activity/usage/trace read side、encrypted credential storage、secure key handoff 和 concurrency lease。
- Seed pipeline 已推进到 upload/source file admission、object verification、workflow admission、parse/segment/sequential-reading/runtime-facts/global aggregation、archive candidate persistence、asset/search projection 的 skeleton/部分 DB-backed 实现。
- Assets 已具备 sanitized list/detail/facets/search、create/update/delete、candidate adoption、bulk actions、reindex skeleton、ingestion/style extraction workflow skeleton、archive memory read/review side。
- Story Graph 已具备 schema、build admission、current snapshot/viewport/node/edge/evidence/layout/cluster read side、DB-backed builder skeleton、bond generation fail-closed workflow shell。
- Worldline 已具备 session/preparation admission/read side、timeline metadata read side、variable injection metadata write side、candidate/canon event metadata read side、explicit metadata-only event edit/adoption、metadata-only saved path producer、step admission Web/API、Python `worldline-interactive` workflow/activity shell，以及最小 LLM Facility-backed candidate event metadata producer。

## 主要未完成项

- 真实 live cluster E2E：Go API + Postgres + Temporal + Pi runtime/Python worker + provider 的完整链路仍需要系统验收。
- Writer：真实 LLM-bound draft generation、reviewer、dedup、book plan、chapters/scenes/manuscript API、one-click actions 仍 pending。
- LLM Facility：live provider model sync/E2E、realtime activity、billing aggregation、quota enforcement 仍 pending。
- Seed：browser/direct upload handoff、PDF parsing、完整智能分段、真实 ontology/entity resolution/agent profile/finalize runner、retry failed segments、vector embeddings 仍 pending。
- Assets/Search：asset versions/collections/embeddings、hybrid/vector search、live DB-backed bulk/reindex/browser memory-review check 仍 pending。
- Story Graph：React Flow canvas、semantic merge/layout hardening、real `graph_bond_generator` runner、candidate adoption flow、legacy graph import 仍 pending。
- Worldline：runtime-generated saved paths、prepare runtime、richer director tools、auto-evolution 和 live provider E2E 仍 pending；source loader 已有 DB-backed public metadata skeleton，但尚未做完整 live E2E。
- Character Console：除 route shell 外基本仍 planned，依赖 Worldline runtime。
- SaaS/Auth/Ops：注册登录、成员协作、tenant/user preferences、billing、backup/restore、incident playbook、production hardening 仍 pending。

## 最近完成的 Worldline slice

- Go API/domain/cmd 已实现 `POST /v1/worldline-sessions/{sessionId}/steps` disabled/DB-backed admission。
- Next `/worldline` 已实现 `startWorldlineStep` API client、`startWorldlineStepAction`、Step session 表单、`stepMode` 控件和 explicit success/error query status。
- Python Agent Runtime 新增 `worldline-interactive` 队列，注册 `WorldlineStepWorkflow` / `worldline_step_activity`。
- Python activity 要求 `workflow_type = worldline_step`、`module_key = worldline_director`、`worldline_director:run` permission 和 tenant/project/run/trace/session context。
- 默认无真实 runner 时以 `WORLDLINE_STEP_RUNNER_UNCONFIGURED` fail closed，只写 sanitized `worldline.stage.failed` event 和 failed workflow status；不调用 LLM、不生成 candidate event、timeline、saved path、canon、draft 或 manuscript。
- DB/key/provider 配置后，默认 `LLMFacilityWorldlineStepRunner` 会解析 `worldline_director`、解密 credential、调用 JSON provider、schema-validate `candidate_events`，并通过 `PostgresWorldlineCandidateEventWriter` 只写 public `worldline_events.status = candidate` metadata；成功路径还会写 sanitized `worldline.stage.completed` workflow event 并更新 admitted run public status。
- `PostgresWorldlineCandidateEventWriter` 现在会通过 `worldline_sessions` 按 tenant/project/session 校验已 admission session 后才写 candidate event；缺失或跨租户/项目 session 以 `WORLDLINE_SESSION_NOT_FOUND` fail closed，并显式 rollback candidate-event transaction，避免 runtime 产生 orphan candidate events 或留下 partial batch。
- `PostgresWorldlineCandidateEventWriter` 现在要求 `source_run_id` 是有效 UUID；非法 run id 以 `VALIDATION_FAILED` fail closed，避免 candidate event 静默写入 NULL source run 而无法与同一 run 的 Activity/Usage telemetry 关联。
- `LLMFacilityWorldlineStepRunner` 现在也会在 binding resolution、credential decrypt、provider call、telemetry write 和 candidate write 之前验证 `context.run_id` 是有效 UUID；非法 run id 以 `VALIDATION_FAILED` fail closed，不产生 provider/telemetry/candidate 调用，确保后续 `source_run_id`、Activity 和 Usage 都能围绕同一 admitted run 关联。
- `LLMFacilityWorldlineStepRunner` 现在会写 LLM telemetry：provider response 先通过 `candidate_events` schema validation，成功后才记录 completed `llm_activity`，provider response 带 usage 时记录 `usage_events.usage_type = llm_tokens`；provider/schema/credential 失败记录 failed `llm_activity` 且不写 usage，不写 candidate event。
- Worldline telemetry 写入失败现在以 `LLM_TELEMETRY_WRITE_FAILED` fail closed，不写 candidate event，不二次尝试 failed telemetry 后把异常抛出 runtime。
- Worldline telemetry 兼容只返回 `usage.total_tokens` 的 OpenAI-compatible provider：`usage_events.quantity` 会使用 total token count，`llm_activity.prompt_tokens` / `completion_tokens` 在缺少 breakdown 时保持空值；公开 telemetry metadata 仍不包含 API key、prompt/source text 或 `credential_ref`。
- Go LLM Facility Activity read side 现在会在 SQL reader 和 HTTP response boundary 两层递归清洗 Activity error payload，即使历史、外部 runtime 或替换 reader 写入了 `api_key`、`credential_ref`、`prompt`、`source_text` 等高风险字段，公开 Activity API 也只返回安全错误摘要；无法解析的 error payload 不再透传原始字符串。
- Python DB-backed LLM Facility resolver/provider 查询失败现在也会稳定化：`PostgresModuleBindingResolver` 底层 query exception 只返回 `LLM_BINDING_QUERY_FAILED` / `LLM module binding query failed`，`PostgresCredentialProvider` 底层 query exception 只返回 `LLM_CREDENTIAL_QUERY_FAILED` / `LLM credential query failed`，不把 driver 异常中的 prompt、API key、`credential_ref` 透出到 Seed/Assets/Worldline runner result。
- Python shared LLM Facility resolution validation 现在要求 `provider` 非空：Seed sequential reader 与 Worldline director runner 在缺 provider 的 binding 上以 `LLM_PROVIDER_ERROR` / `resolved LLM module is missing provider` fail closed，并在 credential decrypt、provider call、telemetry completed、candidate persistence 前停止。
- Worldline `PostgresLLMTelemetryWriter` 现在也会在写入 `llm_activity.error_jsonb` 前递归清洗 failed activity error payload，移除 `api_key`、`credential_ref`、`prompt` 等高风险 key；读侧双层清洗继续保留，形成写入侧和公开 API 双防线。
- Worldline `PostgresLLMTelemetryWriter` 现在提供 completed-call 原子写入路径；`LLMFacilityWorldlineStepRunner` 在 provider `candidate_events` schema validation 成功后，会把 completed `llm_activity` 与可选 token `usage_events` 放入同一 DB transaction/commit。telemetry 写入失败仍以 `LLM_TELEMETRY_WRITE_FAILED` fail closed，不写 candidate event，也不泄露 prompt/source text/API key/`credential_ref`。
- Worldline completed telemetry transaction 现在在中途写入失败时显式 rollback：例如 completed `llm_activity` 已执行 insert、随后 `usage_events` insert 失败时，runner 返回稳定 `LLM_TELEMETRY_WRITE_FAILED`，不写 candidate event，也不公开 DB/provider exception 中的 prompt/API key。
- Worldline completed/failed telemetry writer 的普通异常现在也会被稳定收敛：即使是注入式 writer、非 Postgres writer 或 driver wrapper 抛出普通 exception，runner 也只返回 `LLM_TELEMETRY_WRITE_FAILED` / 稳定 public message，不透传 prompt/API key/`credential_ref`，且 completed telemetry 未完成时不会写 candidate event。
- Worldline 单条 telemetry insert 失败现在也会显式 rollback：`PostgresLLMTelemetryWriter.record_llm_activity` 和 `record_usage_event` 在各自 DB/driver 异常路径都会 rollback connection，再返回稳定 `LLM_TELEMETRY_WRITE_FAILED`，不泄露异常中的 prompt/API key/`credential_ref`，也不留下未清理事务。
- Worldline workflow event/status persistence 失败现在也会显式 rollback：`PostgresWorkflowEventWriter` 和 `PostgresWorkflowRunStatusWriter` 在 `workflow_events` insert 或 `workflow_runs` status update 的 DB/driver 异常路径返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `WORKFLOW_STATUS_WRITE_FAILED` runtime error，不把异常里的 prompt/API key/`credential_ref` 透出。
- Worldline workflow event admission parent 未命中现在会在 commit 前 rollback：`PostgresWorkflowEventWriter` 通过 tenant/project/run scoped `workflow_runs.workflow_type = worldline_step` admission row 驱动 `workflow_events` insert；缺失父行时返回稳定 `WORKFLOW_RUN_NOT_FOUND`，不会创建 orphan workflow event。
- Worldline status admission parent 未命中现在会在 commit 前 rollback：`PostgresWorkflowRunStatusWriter` 更新 `workflow_runs.workflow_type = worldline_step` 未命中时返回稳定 `WORKFLOW_RUN_NOT_FOUND`，不会把缺失 admission 父行的 no-op update 当作成功状态回写。
- Worldline candidate metadata persistence failure 现在不会污染 LLM Activity：当 provider/schema/completed telemetry 已成功，而 candidate writer 因 session/admission/scope 失败返回 `WORLDLINE_SESSION_NOT_FOUND` 等明确错误时，runner 返回该错误，但不追加 failed `llm_activity`，避免同一 `run_id` 的 provider call 同时显示 completed/failed。
- Worldline unexpected candidate writer exception 现在会被稳定收敛：当 completed telemetry 已成功，而 candidate writer 抛出非 `LLMFacilityError` 的普通异常时，runner 返回 `WORLDLINE_CANDIDATE_EVENT_WRITE_FAILED` / `worldline candidate event write failed`，不误报为 `LLM_PROVIDER_ERROR`，也不追加 failed `llm_activity` 或透出 prompt/API key/`credential_ref`。
- Worldline candidate writer 普通 DB/driver insert exception 现在会 rollback 并返回稳定 `WORLDLINE_CANDIDATE_EVENT_WRITE_FAILED` / `worldline candidate event write failed`，不把异常消息中的 prompt/API key/`credential_ref` 泄露到 runner result、workflow status 或公开错误。
- `worldline_step_activity` 现在会保留 runner 直接抛出的 `LLMFacilityError` code/message，例如 `LLM_MODULE_UNBOUND`，并写入 failed result、`worldline.stage.failed` 和 failed workflow status；不会把这些明确失败泛化为 `WORLDLINE_STEP_FAILED` 或写 completed event/status。
- `LLMFacilityWorldlineStepRunner` 对普通 provider/SDK exception 不再公开原始异常文本，只返回稳定 `LLM_PROVIDER_ERROR` / `worldline provider call failed`，避免异常消息泄露 API key、prompt 或 source material；该失败路径不会写 candidate event。
- Worldline DB-backed success-chain 现在有 integration-like 覆盖：`test_worldline_step_activity_runs_db_backed_success_chain_under_same_run_id` 用记录型 fake DB 串起 DB-backed binding resolver、AES-GCM credential decrypt、JSON provider、atomic completed telemetry/usage、candidate `worldline_events.status = candidate` persistence、sanitized completed workflow event/status，并验证同一 `run_id`、operation order、无 rollback 和无 prompt/candidate body/API key/`credential_ref` 泄露。`AgentContext.to_trace_payload()` 现在保留 `actor_user_id`，使 runtime result 与审计上下文一致。
- Worldline DB-backed source loader skeleton 现在已接入：`PostgresWorldlineSourceLoader` 在 `DATABASE_URL` 配置下默认注入 `LLMFacilityWorldlineStepRunner`，只读取 tenant/project scoped enabled `assets` title/summary/type/category metadata 和 tenant/project/session scoped `worldline_events` candidate/canon title/summary/kind/status metadata；不选择 `content_text`、event body、prompt、credential、draft/manuscript 字段，DB 异常稳定为 `WORLDLINE_SOURCE_LOAD_FAILED`。

最近验证：

```bash
cd apps/api && go test ./internal/worldline -run 'Step'
cd apps/api && go test ./internal/httpapi -run 'WorldlineStep'
cd apps/api && go test ./cmd/api -run 'WorldlineStep'
cd apps/api && go test ./...
cd apps/web && npm run test -- --test-name-pattern='Worldline route|worldline API client|worldline saved path'
cd apps/web && npm run test
cd apps/web && npm run typecheck
cd apps/web && npm run build
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q
cd apps/agent-runtime && .venv/bin/python -m pytest tests -q
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_sequential_reader.py -q -k 'sanitizes_query_exception_message'
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_sequential_reader.py -q -k 'rejects_resolution_without_provider_before_credential_call or calls_provider_with_explicit_key'
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_sequential_reader.py -q
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k 'rejects_resolution_without_provider_before_credential_call or persists_candidate_events_without_public_body'
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k rejects_non_uuid_run_id_before_provider_call
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k writes_postgres_completed_activity_and_usage_atomically
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k rolls_back_postgres_completed_telemetry_when_usage_insert_fails
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k sanitizes_unexpected_completed_telemetry_exception
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k 'telemetry_write_fails or unexpected_completed_telemetry_exception or records_failed_activity_without_usage'
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k does_not_record_failed_llm_activity_after_candidate_write_failure
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k sanitizes_unexpected_candidate_write_exception
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k sanitizes_db_exception_message
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k rolls_back_when_session_scope_missing
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k 'telemetry_writer_rolls_back_when_activity_insert_fails or telemetry_writer_rolls_back_when_usage_insert_fails'
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k 'workflow_event_writer_rolls_back_and_sanitizes_error or workflow_status_writer_rolls_back_and_sanitizes_error'
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k workflow_event_writer_rolls_back_when_admission_parent_missing
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k workflow_status_writer_rolls_back_when_admission_parent_missing
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q -k db_backed_success_chain
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_agent_context.py -q
git diff --check
```

已知说明：`apps/web npm run build` 通过但本地仍可能出现 Next SWC 平台包 warning，这是当前本地依赖环境 warning，不代表构建失败。

## 下一步建议

推荐下一小步继续收口 **P6-001 Worldline live step execution hardening**，但范围要窄：

1. 先不要做 Character Console runtime；它依赖 Worldline 真实事件生产。
2. integration-like DB-backed success-chain 覆盖已补；下一步补 live provider E2E 或真实 Postgres integration，证明 `worldline_director` binding、credential decrypt、provider JSON、单事务 telemetry write/rollback、`workflow_events` completed event/status 和 `worldline_events` candidate metadata persistence 能在真实 DB/provider 环境下工作。
3. 验证 LLM Facility Activity/Usage read side 能用同一个 `run_id` 查询到 Worldline `worldline_director` activity 和 token usage。
4. 引入已授权 source loader / director tools 时，输入只使用 tenant/project/session/run context 和 public step mode/options；不得把 raw source text、prompt 或 credential 放进公开 payload。
5. 候选事件只能写 `worldline_events.status = candidate` 和 sanitized `workflow_events`；candidate -> canon、saved path、writer draft 都必须继续是明确用户动作。
6. 完成后同步 `13-agent-runtime.md`、`14-data-model.md`、`15-api-contracts.md`、`18-legacy-coverage-matrix.md` 和 `tasks/refactor-saas-parallel-board.md`，并跑 Go/Python/Web 聚焦和必要全量验证。

备选下一步：

- 补 LLM/Writer live cluster E2E，证明 Phase 4 secure key + concurrency + provider path 在真实 Temporal/Postgres 下可运行。
- 收口 P5 Seed live object upload/parse/segment/index E2E。
- 做 Story Graph React Flow canvas 和 live DB-backed graph build browser check。

## 新对话启动提示词

可复制下面这段作为新对话开场：

```text
/goal 继续开发 MiroFish-Novel SaaS 重构。必须只在隔离 worktree `/Users/yantianqi/Documents/Noveronline-saas-mainline` 工作，不要回到主仓库 `/Users/yantianqi/Documents/Noveronline` 开发或覆盖主工作区改动。

开始前必须：
1. 在 `/Users/yantianqi/Documents/Noveronline` 运行 `git status --short`，确认主工作区仍有大量未提交改动。
2. 在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 运行 `git status --short` 和 `git status -sb`，确认当前重构改动位于隔离 worktree，分支应为 `codex/saas-mainline`。
3. 阅读并以这些文件为基线：
   - `docs/refactor-saas/DEVELOPMENT_PLAN.md`
   - `docs/refactor-saas/22-midstream-handoff-summary.md`
   - `docs/refactor-saas/21-pi-writer-agent-runtime.md`
   - `docs/refactor-saas/11-writer-workbench.md`
   - `docs/refactor-saas/12-llm-facility.md`
   - `docs/refactor-saas/13-agent-runtime.md`
   - `docs/refactor-saas/14-data-model.md`
   - `docs/refactor-saas/15-api-contracts.md`
   - `docs/refactor-saas/18-legacy-coverage-matrix.md`
   - `tasks/refactor-saas-parallel-board.md`

当前进度：整体约 55%-60%。Phase 0 verified；Phase 1-3 基本落地；Phase 4 LLM Facility 大体实现但 live provider/cluster E2E 仍 pending；Phase 5 Seed/Assets/Graph 已有大量 DB-backed skeleton 和部分真实持久化；Phase 6 Worldline metadata side、step admission Web/API、Python `worldline-interactive` workflow/activity shell、最小 LLM-backed candidate event metadata producer 已完成，Character Console runtime 仍 blocked。

硬约束：
- 不新增 mock 成功、静默 fallback、伪数据路径或吞错路径。
- 不使用旧式环境变量 LLM fallback；所有 LLM 调用必须走 LLM Facility 模块绑定。
- 不使用 `pi-coding-agent` CLI 作为产品后端；使用 `@earendil-works/pi-agent-core` 和 `@earendil-works/pi-ai` SDK。
- Pi Writer Runtime 只替代 Writer Agent 通用 agent loop，不迁移 Seed/Graph/Asset/Worldline 的 Python 领域逻辑。
- 所有新 runtime/API/tool 调用必须携带 tenant_id/project_id/run_id 或相应 session/run context。
- 工具调用必须有权限检查、trace、错误状态和可审计记录。
- draft 到 manuscript、candidate 到 canon 必须是明确用户动作；Agent 不得默认自动采用。
- Worldline 保持单世界/current-world，不恢复旧多分支主模型。
- 每完成一个明确子任务，更新 `tasks/refactor-saas-parallel-board.md` 和 `docs/refactor-saas/18-legacy-coverage-matrix.md`；涉及 API/data/runtime contract 时同步 `15-api-contracts.md` / `14-data-model.md` / `13-agent-runtime.md`。
- 行为变更按 TDD 做：先写失败测试，确认 red，再实现，最后跑聚焦和必要全量验证。

建议下一步优先推进 P6-001 Worldline live step execution hardening。在现有 `POST /v1/worldline-sessions/{sessionId}/steps` admission、Next Step session UI、Python `WorldlineStepWorkflow` / `worldline_step_activity`、`LLMFacilityWorldlineStepRunner` 和 Worldline LLM telemetry write path 之上，补更贴近真实 DB/provider 的 integration 或 live E2E，证明 `worldline_director` binding、credential decrypt、provider JSON、单事务 telemetry write/rollback、ordinary telemetry writer exception stabilization、sanitized `workflow_events` completed event/status、`worldline_events.status = candidate` persistence 能同链路工作，并能通过 LLM Facility Activity/Usage read side 查询。`PostgresWorkflowEventWriter` 已要求 admitted `workflow_runs.workflow_type = worldline_step` parent row，下一步测试要保留这个 invariant，不能创建 orphan workflow event。缺绑定/缺 credential/缺 provider/schema invalid 都必须显式失败；成功时仍只写 schema-valid candidate metadata，不自动采用 canon、不保存 path、不写 writer draft/manuscript。完成后同步文档和看板，并跑 Go/Python/Web 聚焦测试、必要全量验证和 `git diff --check` 后再汇报。
```
