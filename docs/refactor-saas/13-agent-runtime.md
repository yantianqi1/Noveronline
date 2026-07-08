# 13. Agent Runtime

更新时间：`2026-07-09`

## 模块定位

Agent Runtime 是所有智能体能力的执行层。它不直接面向公网，而是通过 workflow/worker 执行 Go Control Plane 提交的任务。

当前实现顺序采用双 runtime：

- **Pi Writer Runtime**：第一阶段负责 Writer Agent loop、tool calling、流式正文和 draft 保存。
- **Python Agent Runtime**：继续负责 seed、graph、asset ingestion、worldline 等 Python 领域逻辑。

旧系统里 Agent 逻辑分散在：

- seed services。
- graph builder。
- asset ingestion agent。
- worldline services。
- writer_agent。
- llm_router。
- step trace。

新系统要把它们整理为统一运行规范，保留旧能力并增强可观测、可恢复和可审计。Writer loop 不再从零自研，详见 `21-pi-writer-agent-runtime.md`。

## 运行形态

```text
Go API starts workflow
  -> Temporal or compatibility runner queues work
  -> Pi Writer Runtime or Python Agent Worker picks activity
  -> Runtime loads tenant/project/run context
  -> LLM Facility adapter resolves module binding
  -> Agent executes prompt/tool loop or domain activity
  -> Trace events persisted
  -> Result written to Postgres/Object Storage
```

Python worker 和 Pi Writer Runtime 都不直接接收公网请求。

Python Temporal worker 注册的 Seed / Asset / Graph / Worldline activity 当前是同步函数，worker 入口必须为 Temporal `Worker` 提供 `ThreadPoolExecutor`；否则真实 worker 在启动时会拒绝同步 activity。Seed workflow 文件中的 `pypdf` import 仅供 activity PDF extraction 使用，必须作为 Temporal sandbox passthrough import，避免 workflow sandbox 重新导入 `pypdf/cryptography` 时失败。Seed activity 的 workflow event writer 和 workflow run status writer 也必须在 activity 内部从环境解析，不能只依赖 local runner 显式注入；真实 Temporal worker 只传 payload，parse/segment/sequential 等 stage event 持久化以及 running/terminal `workflow_runs` 状态回写需要 activity 自行解析 `DATABASE_URL` backed writer。本地 `run_seed_workflow_locally` harness 可显式注入同一个 workflow status writer 并复用于 seed admission、sequential terminal failure 和 finalize terminal success，用于验证 `running -> failed/completed` 状态交接，但这不替代真实 worker 的环境解析要求。

Seed worker 的 workflow event persistence 失败也属于 public runtime 边界。`seed_pipeline_activity` 解析 workflow event writer 或写 `seed.stage.pending` 失败时必须返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，不得把 workflow event writer factory / writer exception 中可能夹带的 prompt、API key、`credential_ref`、object key、source path、draft 或 manuscript 透出到 activity result、workflow status 或 API read side。

同一边界适用于后续 Seed stages。`parse_file_activity`、`segment_text_activity`、`sequential_reading_activity`、`persist_runtime_facts_activity`、`global_aggregation_activity`、`ontology_activity`、`entity_resolution_activity`、`agent_profile_activity`、`archive_candidate_activity`、`index_assets_activity` 和 `finalize_seed_activity` 在解析 workflow event writer 失败时必须返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，公开 result 只保留 stage/source-file/module public metadata，不能让 writer factory exception 变成未结构化 activity crash、被误归类为 object storage/LLM/runtime/index/finalize failure，或泄露 prompt、API key、`credential_ref`、object key、source path、draft/manuscript。

Seed `parse_file_activity` 和 `segment_text_activity` 的 terminal failure 也必须通过 workflow run status writer 回写 admitted `seed_pipeline` run 的 failed 状态，避免早期 parse/segment 失败后 `workflow_runs` 停留在 `running`。真实 worker path 可从 `DATABASE_URL` 装配 status writer；装配或写入失败必须返回稳定 `WORKFLOW_STATUS_WRITE_FAILED` / `seed workflow status write failed`，不得把 status writer factory / DB exception 中可能夹带的 prompt、API key、`credential_ref`、object key、draft 或 manuscript 写入 activity result、workflow event 或 API read side。

Seed parse source-status writer env-resolution failure 也属于 public runtime 边界。`parse_file_activity` 解析 DB-backed source parse-status writer 时如果遇到环境或 writer factory 异常，必须返回稳定 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED` / `source file parse status update failed`，写 sanitized `seed.stage.failed` parse event，并在 workflow status writer 可用时把 admitted run 标为 `failed`；不得把底层 exception 文本透出到 activity result、workflow event/status 或 API read side。

Seed parse text-artifact writer env-resolution failure 同样必须 fail closed。`parse_file_activity` 解析 DB-backed text artifact writer 时如果遇到环境或 writer factory 异常，必须返回稳定 `TEXT_ARTIFACT_WRITE_FAILED` / `text artifact write failed`，尝试把 source row 标为 `failed`，写 sanitized parse failed event，并在 workflow status writer 可用时把 admitted run 标为 `failed`；不得读取 source object、写 extracted artifact 或把底层 exception 文本透出到公共面。

Seed segment text-segment writer env-resolution failure 同样必须 fail closed。`segment_text_activity` 解析 DB-backed text segment writer 时如果遇到环境或 writer factory 异常，必须返回稳定 `TEXT_SEGMENT_WRITE_FAILED` / `text segment write failed`，写 sanitized segment failed event，并在 workflow status writer 可用时把 admitted run 标为 `failed`；不得读取 extracted artifact、写 segment object 或把底层 exception 文本透出到公共面。

Seed parse/segment object-store env-resolution failure 同样属于 public runtime 边界。`parse_file_activity` 与 `segment_text_activity` 解析 MinIO/S3-compatible object store 时如果遇到环境或 factory 普通异常，必须返回稳定 `OBJECT_STORAGE_BACKEND_MISCONFIGURED` / `object storage backend is misconfigured`；parse 路径还要尝试把 source row 标为 `failed`，两个路径都必须写 sanitized failed stage event，并在 workflow status writer 可用时把 admitted run 标为 `failed`。不得读取 source/extracted artifact、写 extracted artifact/segment object，或把底层 exception、object credential、object key、prompt、API key、`credential_ref`、draft/manuscript 透出到 activity result、workflow event/status 或 API read side。

Seed sequential-reading 默认 reader 的 object-store env-resolution failure 也必须 fail closed。`sequential_reading_activity` 在装配 DB-backed `LLMFacilitySequentialReader` 时，如果 segment text object store 环境或 factory 普通异常，会返回稳定 `OBJECT_STORAGE_BACKEND_MISCONFIGURED` / `object storage backend is misconfigured`，写 sanitized sequential-reading failed event，并在 workflow status writer 可用时把 admitted run 标为 `failed`。该路径不得调用 LLM、不得写 reading notes，也不得把底层 exception、segment object key、prompt/API key、`credential_ref`、draft/manuscript 透出到 activity result、workflow event/status 或 API read side。

当前 Phase 5 skeleton 已新增 Python `asset-light` task queue 的 `AssetIngestionWorkflow` / `asset_ingestion_activity`。Go control plane 在配置 `TEMPORAL_ADDRESS` 与 `DATABASE_URL` 时会先写 tenant/project scoped `workflow_runs` 和 sanitized `workflow.queued` event，再启动 Temporal `AssetIngestionWorkflow`；admission 失败必须返回 `WORKFLOW_ADMISSION_FAILED` 且不得启动 worker。该 activity 要求 `AgentContext` 携带 `tenant_id`、`project_id`、`run_id`、`trace_id`、`workflow_type = asset_ingestion`、`module_key = asset_ingestion` 和 `asset_ingestion:run` permission；缺少 runner 时以 `ASSET_INGESTION_RUNNER_UNCONFIGURED` fail-closed，并只写 sanitized `asset.stage.failed` workflow event。配置 `DATABASE_URL` 与显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 时，默认 runner 会解析 `asset_ingestion` LLM Facility module binding、解密 tenant-scoped channel credential、调用 JSON-capable OpenAI-compatible provider，并将 schema-valid candidates 通过 `PostgresAssetCandidateWriter` upsert 到 `assets.lifecycle = candidate`。公开 result/event 只暴露 candidate batch/count/type metadata 和可选 model id，不公开素材正文、prompt、candidate body、credential 或 API key；candidate 采用为 canon/material 仍必须走后续明确用户动作。

同一 `asset-light` 队列也注册 `StyleExtractionWorkflow` / `style_extraction_activity`。该 activity 要求 `workflow_type = style_extraction`、`module_key = style_extractor`、`style_extractor:run` permission，以及 tenant/project/run/trace context；缺少 runner 时以 `STYLE_EXTRACTION_RUNNER_UNCONFIGURED` fail-closed。配置 `DATABASE_URL` 与显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 时，默认 runner 会解析 `style_extractor` module binding、解密 credential、调用 JSON-capable provider、schema-validate `style_profile`，并通过 `PostgresAssetCandidateWriter(source_kind = style_extraction)` 写入 lifecycle=`candidate` 的 `style_profile` asset。若请求只提供 `source_asset_id`，默认 runner 通过 tenant/project/source asset scoped `PostgresStyleSourceMaterialLoader` 私下读取 enabled `assets.content_text`；缺失、跨租户/项目或空内容以 `STYLE_SOURCE_MATERIAL_UNAVAILABLE` fail-closed。公开 result/event 只暴露 batch/count/type/model metadata，不公开素材正文、source asset content、prompt、提取 body、credential 或 API key。

同一 `asset-light` 队列也注册 `AssetReindexWorkflow` / `asset_reindex_activity`。Go control plane 在配置 `TEMPORAL_ADDRESS` 与 `DATABASE_URL` 时先写 tenant/project scoped `workflow_runs` 和 sanitized `workflow.queued` event，再启动 Temporal `AssetReindexWorkflow`；admission 失败必须返回 `WORKFLOW_ADMISSION_FAILED` 且不得启动 worker。该 activity 要求 `workflow_type = asset_reindex`、`module_key = asset_reindex`、`asset_reindex:run` permission，以及 tenant/project/run/trace context；缺少 DB-backed reindexer 时以 `ASSET_REINDEXER_UNCONFIGURED` fail-closed。配置 `DATABASE_URL` 时，默认 `PostgresAssetReindexer` 执行 project/keyword reindex，从 tenant/project-scoped `assets` 重建 `global_search_index` 的 `asset` 文档。公开 result/event 只暴露 `reindex_batch_id`、asset/search document counts 和 `embedding_count = 0`，不公开 `content_text`、search body、embedding chunk、prompt、credential 或 API key。

Seed `seed-heavy` 队列中的 `parse_file_activity` 现在会在读取 source object bytes 后、文本/PDF extraction 前，使用 Go control plane handoff payload 中可选的 `source_size_bytes` / `source_sha256` 复核对象内容。字段缺省时兼容旧 payload；字段存在但类型、格式、size 或 SHA-256 不匹配时以 `SOURCE_FILE_OBJECT_INTEGRITY_MISMATCH` / `source object integrity check failed` fail closed，并走 source parse-status failed 与 sanitized `seed.stage.failed` event path。公开 result/event 不返回 expected/actual hash、source object key、raw text、prompt、API key、`credential_ref`、draft 或 manuscript。

Go `TemporalSeedRunStarter` 在启动 `SeedPipelineWorkflow` 前会递归清洗 user options，移除 body-provided tenant/project authority、prompt/response/body/content/raw/source/material/candidate/event text、API key、credential refs、draft 和 manuscript；Python worker 只能把保留下来的 safe public analysis options 当作配置参考。HTTP Seed start handler 仍执行前置 options 清洗，starter 级清洗是内部 Go -> Temporal -> Python handoff 的第二道防线，防止绕过 HTTP 边界的调用把私密正文或 credential material 带入 runtime payload。

Seed `seed-heavy` 队列中的 `archive_candidate_activity` 现在可在配置 `DATABASE_URL` 与显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 时装配 `LLMFacilityArchiveCandidateRunner`。该 runner 解析 `narrative_archives` module binding、解密 tenant-scoped credential、调用 JSON-capable OpenAI-compatible provider、schema-validate archive entity / memory candidates，并通过 `PostgresArchiveCandidateWriter` 写入 candidate `archive_entity` assets、candidate `archive_memories` 和 `memory.candidate.generated` events。writer 在写入前设置 app-role tenant context，业务 SQL/commit failure 会 rollback 并稳定为 `ARCHIVE_CANDIDATE_WRITE_FAILED` / `archive candidate write failed`。缺少 runner、binding、credential key 或 schema-valid 输出时 fail closed，不生成 mock archive candidates；公开 result/event 只暴露 batch/count/model metadata，不公开 archive candidate body、memory body、profile/seed analysis body、prompt/response 或 credential。

Seed `archive_candidate_activity` 现在还有 opt-in Postgres/local-provider harness 入口。配置 `MIROFISH_SEED_LIVE_DATABASE_URL` 时，`apps/agent-runtime/tests/test_seed_live_e2e.py` 会准备 workflow admission、encrypted LLM channel credential、model 和 `narrative_archives` binding，启动本地 OpenAI-compatible JSON provider，并通过 app-role `DATABASE_URL` 执行该 activity。harness 已在本机 live Postgres 执行通过，并验证 provider path、Authorization、tenant/project/run/module headers、candidate asset/memory/event persistence 和 sanitized `seed.stage.completed` public event。该覆盖不代表完整 browser/provider Seed pipeline、OCR PDF、retry 或 vector/hybrid search 完成。

Seed `seed-heavy` 队列中的 `sequential_reading` stage 现在有 opt-in live Postgres/MinIO/local-provider success-chain 覆盖。`LLMFacilitySequentialReader` 通过 LLM Facility 解析 `sequential_reading` binding、要求 resolved provider 非空、解密显式 credential、从 MinIO/S3-compatible segment object refs 读取 segment text，并调用 JSON-capable OpenAI-compatible provider。返回的 reading pass id 必须是 deterministic UUIDv5，基于 tenant/project/run 和 `seed-sequential-reading-pass` 生成，匹配 target `reading_passes.pass_id UUID` schema 并保持 retry idempotency。live harness 会用 app-role Postgres 写入/读回 `reading_passes` 与 `reading_segment_notes`，验证 provider request 和 sanitized `seed.stage.completed` public event；公开 result/event 不得包含 segment object key、raw segment text、prompt/provider response、API key、`credential_ref`、draft 或 manuscript。该覆盖不代表完整 browser/provider Seed pipeline 或 full Seed product closure 完成。

Seed `seed-heavy` 队列中的 `global_aggregation` / `anchor_point_summary` stage 现在有 DB-backed `LLMFacilityGlobalAggregator` 装配路径和 opt-in live Postgres/local-provider harness 入口。`PostgresSeedAggregateSource` 只读取 public `segment_summaries.summary` 和 scoped fact counts；`entities` / `relationships` 必须按真实 target schema 的 `source_run_id` 匹配当前 seed run，不能查询旧 `run_id` 列。aggregate input 会递归剔除 prompt/provider/raw/body/content/API key/credential refs/object keys/raw/source text/evidence/draft/manuscript 等高风险字段后才进入 provider request。`PostgresSeedAnalysisWriter` 写入私有 `seed_analysis_snapshots.analysis_jsonb` 前也会做 seed-analysis-specific 清洗，避免 provider output 中的 raw/source/content/body/material text、quote/evidence variants、provider response 或 credential material 落库；公开 activity result 和 `seed.stage.completed` event 只暴露 module/model/count/snapshot id metadata。失败路径的 public result 和 failed event 使用同一 allow-listed stable code/message；unknown aggregator/provider codes collapse to `LLM_PROVIDER_ERROR`，不得透传 provider/aggregator raw exception 或 untrusted `error.code`。当前默认环境只验证 explicit skip 和 focused unit regression；live DB execution of the new harness 仍 pending，不能据此声明完整 browser/provider Seed pipeline 完成。

Seed `seed-heavy` 队列中的 `story_ontology` stage 现在有 DB-backed `LLMFacilityOntologyRunner` 装配路径和 opt-in live Postgres/local-provider success-chain 覆盖。该 runner 只接受 `story_ontology` module key，解析 LLM Facility binding、校验 JSON-capable resolution，并要求 resolved `provider` 非空后才使用显式 credential 调用 JSON client；缺 provider 必须在 credential lookup/provider call 前以 `LLM_PROVIDER_ERROR` fail closed。runner 校验 `seed_ontology.entity_types` / `relationship_types` / `world_rule_types` 数组，并通过 `PostgresOntologySnapshotWriter` 写入私有 `seed_ontology_snapshots` 后才返回 completed public metadata。writer 先设置 app-role tenant context，清洗 prompt/API key/`credential_ref`/raw content/provider raw body 等高风险字段，DB/commit failure 会 rollback 并稳定为 `ONTOLOGY_SNAPSHOT_WRITE_FAILED` / `ontology snapshot write failed`。live harness 会用 app-role Postgres 准备 workflow admission 和 LLM Facility rows，启动本地 OpenAI-compatible JSON provider，重复执行 `ontology_activity` 验证同一 run/module 的 snapshot upsert 幂等、provider request headers/body 和 sanitized `seed.stage.completed` public events。公开 result/event 只暴露 `ontology_snapshot_id`、model 和类型 counts，不公开 ontology body、prompt/response、API key、`credential_ref`、raw text、draft 或 manuscript。完整 browser/provider Seed pipeline 仍 pending.

Seed `seed-heavy` 队列中的 `entity_resolution` stage 现在有 DB-backed `LLMFacilityEntityResolutionRunner` 装配路径和 opt-in live Postgres/local-provider success-chain 覆盖。该 runner 只接受 `entity_resolution` module key，解析 LLM Facility binding、校验 JSON-capable resolution，并要求 resolved `provider` 非空后才使用显式 credential 调用 JSON client；缺 provider 必须在 credential lookup/provider call 前以 `LLM_PROVIDER_ERROR` fail closed。runner 校验 `entity_resolution.merged_entities` / `aliases` / `conflicts` 数组，并通过 `PostgresEntityResolutionSnapshotWriter` 写入私有 `seed_entity_resolution_snapshots` 后才返回 completed public metadata。writer 先设置 app-role tenant context，清洗 prompt/API key/`credential_ref`/raw content/provider raw body 等高风险字段，DB/commit failure 会 rollback 并稳定为 `ENTITY_RESOLUTION_SNAPSHOT_WRITE_FAILED` / `entity resolution snapshot write failed`。live harness 会用 app-role Postgres 准备 workflow admission 和 LLM Facility rows，启动本地 OpenAI-compatible JSON provider，重复执行 `entity_resolution_activity` 验证同一 run/module 的 snapshot upsert 幂等、provider request headers/body 和 sanitized `seed.stage.completed` public events。公开 result/event 只暴露 `resolution_snapshot_id`、model 和 merged/alias/conflict counts，不公开 resolution body、prompt/response、API key、`credential_ref`、object key、raw text、draft 或 manuscript。完整 browser/provider Seed pipeline 仍 pending。

Seed `seed-heavy` 队列中的 `character_agent_profile` stage 现在有 DB-backed `LLMFacilityAgentProfileRunner` 装配路径。该 runner 只接受 `character_agent_profile` module key，并且必须先通过 `AgentProfileContextLoader` 读取 tenant/project/run scoped Seed context；缺 loader、空 context 或 loader 失败都会在 binding resolution、credential decrypt 和 provider call 前 fail closed。DB-backed loader 会设置 app-role tenant context，只读取 `seed_entity_resolution_snapshots` public metadata / allow-listed resolution arrays，以及 `entities`、`relationships`、`segment_summaries` 的 public summary fields；provider message 只注入 white-listed `source_context`，不注入 raw text、prompt、object key、provider metadata、credential material、draft 或 manuscript。随后 runner 解析 LLM Facility binding、校验 JSON-capable resolution，并要求 resolved `provider` 非空后才使用显式 credential 调用 JSON client；缺 provider 必须在 credential lookup/provider call 前以 `LLM_PROVIDER_ERROR` fail closed。runner 校验 `agent_profiles.profiles` / `memory_seeds` / `relationship_views` 数组，并通过 `PostgresAgentProfileSnapshotWriter` 写入私有 `seed_agent_profile_snapshots` 后才返回 completed public metadata。writer 先设置 app-role tenant context，清洗 prompt/API key/`credential_ref`/raw/source/content text、provider/raw body fields、object key、draft/manuscript 等高风险字段，DB/commit failure 会 rollback 并稳定为 `AGENT_PROFILE_SNAPSHOT_WRITE_FAILED` / `agent profile snapshot write failed`。公开 result/event 只暴露 `profile_snapshot_id`、model 和 profile/memory-seed/relationship-view counts，不公开 public/private profile body、prompt/response、API key、`credential_ref`、raw text、draft 或 manuscript。Postgres/local-provider harness 已在本机 live Postgres 上执行通过，覆盖 DB-backed context loader、credential decrypt、provider request、snapshot persistence 和 sanitized workflow event；完整 Seed browser/provider pipeline 仍 pending。

Seed `seed-heavy` 队列中的 `finalize_seed_activity` 现在可在配置 `DATABASE_URL` 时装配 `PostgresProjectReadinessUpdater`。该 updater 在 app-role/RLS context 下读取同一 tenant/project/run 的 Seed asset projection 与 structured canon counts，upsert `project_readiness_snapshots`，并只返回 `project_readiness_snapshot_id` 与 ready asset/entity/relationship/world-rule counts。缺少 updater 时仍以 `PROJECT_READINESS_UPDATER_UNCONFIGURED` fail closed，不伪造 project ready；DB/commit failure 会 rollback 并稳定为 `PROJECT_READINESS_UPDATE_FAILED` / `project readiness update failed`，不公开 readiness report body、prompt、raw text 或 credential。配置 workflow status writer 时，`seed_pipeline_activity` 会在 worker 接受 run 后把 admitted Seed `workflow_runs` 标为 `running`；finalize 成功还会标为 `completed`，result 仅包含 readiness public metadata；terminal failure path 也用稳定 public error 标记 `failed`，不会把底层 writer exception 或私密正文写入 status。`apps/agent-runtime/tests/test_seed_live_e2e.py` 的 opt-in finalize Postgres harness 已在本机 live Postgres 执行通过，验证 readiness snapshot、completed workflow status 和 sanitized completed event；该执行还暴露并修复了 psycopg 默认 tuple `RETURNING` row parsing。该覆盖不代表 full-chain readiness 或完整 Seed browser/provider pipeline 完成。

## 包结构

```text
apps/agent-runtime/
  mirofish_agents/
    common/
      context.py
      errors.py
      json_repair.py
      tracing.py
      schemas.py
    llm/
      router.py
      clients.py
      module_registry.py
      usage.py
    seed/
      workflows.py
      activities.py
      segmenter.py
      sequential_reader.py
      ontology.py
      profile_generator.py
    graph/
      workflows.py
      builder.py
      layout.py
      bond_generator.py
    assets/
      workflows.py
      ingestion_agent.py
      style_extractor.py
    worldline/
      workflows.py
      prepare.py
      director.py
      agents.py
      memory.py
    character_console/
      workflows.py
      interaction.py
      rewrite.py
    writer/
      workflows.py
      retrieval_planner.py
      orchestrator.py
      agent_loop.py
      tools.py
      composer.py
      reviewer.py
      dedup.py
    temporal/
      worker.py
      task_queues.py
```

Writer-first Pi runtime 的包结构见 `21-pi-writer-agent-runtime.md`。

## Context

所有 Agent 调用必须使用 `AgentContext`：

```python
class AgentContext(BaseModel):
    tenant_id: str
    project_id: str | None = None
    run_id: str
    workflow_type: str
    actor_user_id: str | None = None
    module_key: str | None = None
    trace_id: str
    permissions: dict = {}
```

禁止：

- 从环境变量猜 project。
- Worker 自己枚举所有 tenant。
- LLM 调用缺少 module_key。

`AgentContext.to_trace_payload()` 必须保留 `tenant_id`、`project_id`、`run_id`、`workflow_type`、`actor_user_id`、`trace_id` 和 `module_key`。这些字段是 runtime result、workflow event/status、trace 和审计链路的最小公共上下文；公开 payload 仍不得包含 prompt、source text、API key、`credential_ref` 或正文草稿。

## LLM Router

职责：

- 调 Go API 或读取安全缓存获得 module binding。
- 选择 channel/model。
- 执行并发控制。
- 调用 OpenAI-compatible Chat Completions 或 Responses API 兼容层。
- 记录 usage。
- 写 trace。

缺少绑定时必须抛出显式错误：

```text
LLM_MODULE_UNBOUND: writer_reviewer
```

DB-backed module binding resolver 和 credential provider 的 query failure 属于隐私边界。底层 driver/SQL 异常文本不得进入公开 `LLMFacilityError.message`，因为异常可能夹带 `api_key`、`encrypted_api_key`、`credential_ref`、prompt 或 source text。`PostgresModuleBindingResolver` 的普通 query exception 必须返回稳定 `LLM_BINDING_QUERY_FAILED` / `LLM module binding query failed`；`PostgresCredentialProvider` 的普通 query exception 必须返回稳定 `LLM_CREDENTIAL_QUERY_FAILED` / `LLM credential query failed`。内部 exception chaining 可保留给 worker 日志/调试，但 public runner result、workflow event/status、LLM Activity 和 API response 不得透出底层异常文本。

LLM Facility resolution 结果必须包含可用 `provider`。Python shared `LLMFacilitySequentialReader` 和 Worldline `LLMFacilityWorldlineStepRunner` 会把空 provider 视为无效 binding，并在 credential decrypt、provider call、candidate/event persistence 之前以 `LLM_PROVIDER_ERROR` / `resolved LLM module is missing provider` fail closed。该校验与 `channel_id`、`model_id`、`base_url`、`credential_ref` 同级，避免 runtime 在无法审计 provider identity 的情况下继续调用模型或写候选数据。

DB-backed Python LLM Facility resolver/credential provider、Seed parse/segment/sequential-reading/runtime-facts/global-aggregation/entity-resolution/agent-profile/archive-candidates/index-assets/finalize 的 Postgres workflow event / text artifact / text segment / reading notes / canon writers / aggregate source / seed analysis writer / entity resolution snapshot writer / agent profile snapshot writer / archive candidate writer / asset indexer / readiness updater，以及 Worldline Postgres source loader、candidate writer、telemetry writer、workflow event writer 和 workflow status writer，在使用 app-role / RLS connection 前必须设置 tenant context：`app_set_tenant_context(tenant_id, project_id_or_null, false)`。Seed public metadata、canon writers、seed analysis writer、entity resolution snapshot writer、agent profile snapshot writer、archive candidate writer、asset indexer 和 readiness updater 在 SQL/commit failure 时还必须 rollback 当前 connection，并继续 fail closed，不把 DB failure 当作成功 persistence；Seed aggregate source 普通 query failure 也必须稳定为 public `SEED_AGGREGATE_SOURCE_QUERY_FAILED`，entity resolution snapshot writer 普通 DB/driver failure 必须稳定为 public `ENTITY_RESOLUTION_SNAPSHOT_WRITE_FAILED`，agent profile snapshot writer 普通 DB/driver failure 必须稳定为 public `AGENT_PROFILE_SNAPSHOT_WRITE_FAILED`，archive candidate writer 普通 DB/driver failure 必须稳定为 public `ARCHIVE_CANDIDATE_WRITE_FAILED`，readiness updater 普通 DB/driver failure 必须稳定为 public `PROJECT_READINESS_UPDATE_FAILED`，不得公开 driver exception 文本。Go LLM Activity/Usage SQL read side 在真实 `*sql.DB` 上也必须用 read-only transaction 设置同一 tenant context 后再查询。这样 runtime 与 API read side 可以在 `mirofish_app` / app-role 权限下通过 RLS，而不是依赖 owner connection 或绕过策略。

## Trace 模型

统一 trace 覆盖旧 step trace、writer prompt snapshot、tool trace、LLM activity。

```text
agent_traces
  tenant_id
  trace_id
  run_id
  project_id
  module_key
  agent_name
  status
  started_at
  completed_at

agent_trace_events
  tenant_id
  trace_id
  event_id
  event_order
  event_type
  payload_json
  redaction_level
  created_at
```

event_type：

- prompt_snapshot。
- llm_call_started。
- llm_call_completed。
- llm_json_repair。
- tool_call。
- tool_result。
- schema_validation。
- artifact_written。
- error。

读取规则：

- 默认 `GET /v1/projects/{projectId}/agent-traces/{traceId}/events` 必须先通过 membership-backed project read RBAC，只返回 `public` / `summary` payload；`full` payload 在 SQL reader 层替换为空对象。
- `include_full=true` 必须先通过 project read、resolved-project `trace_full_access` RBAC 和既有 full trace checker，否则返回稳定 auth/full-trace error，不调用 trace reader。`trace_full_access` 只看 matching active project role `project_owner`、`owner`、`admin` 或 `editor`，raw tenant role alone 不授权。
- `POST /v1/projects/{projectId}/agent-traces/{traceId}/export` 必须先通过 project read RBAC，再检查是否请求 full export；`include_full=true` 同样必须先通过 resolved-project full trace RBAC 和既有 full trace checker，之后才做 strict payload validation、trace reader 和 `audit_logs` 写入。审计失败时不得返回导出内容；duplicate `include_full` key 中只要任一 top-level `include_full: true`，都按 full export 授权。
- `POST /v1/projects/{projectId}/agent-traces/{traceId}/export` 的 JSON decode validation failure 只返回稳定 `VALIDATION_FAILED` message 和空 details；decoder 原始错误、unknown field 名称、Go struct 字段名、`api_key`、prompt、`credential_ref`、draft 或 manuscript 不得进入公开错误响应。LLM Facility module binding/channel mutation 的 validation failure 也遵守同一边界。
- W2-S4c 起，Go HTTP runtime/admission/audit actor context 必须来自同一个 HTTP actor subject resolver：signed Bearer token、signed `mirofish_session` cookie，或在没有 credential 时的 development `X-User-Id` fallback。Bearer/cookie subject 会缓存在 request context，authorizer、workflow starter/canceller、trace access checker、trace auditor、source upload、asset/worldline/character/archive mutations 应消费同一个 actor。W2-S4d 之后，首批 project-scoped read runtime/API surfaces 也必须消费同一 actor resolver 并在 reader/store/resolver 前通过 `project_read`：readiness、source files、assets/facets、worldline saved paths/sessions、character interactions、story graph current/view/node/edge/layout/clusters、LLM modules/module-bindings/module-binding resolution/channels/models/activity/usage、manuscript metadata/export。W2-S4f 之后，manual asset create、asset ingestion, style extraction 和 asset reindex 必须在 JSON decode、mutation store 或 workflow starter 前通过 resolved-project `asset_manage`；该 permission 只允许 matching active project role `project_owner`、`owner`、`admin` 或 `editor`，不允许 raw tenant role alone、`writer`、`analyst`、`viewer`、`billing`、inactive/blank status 或无 matching project。W2-S4g 之后，owner-aware `GET /v1/assets/{assetId}` 必须先读取 tenant-scoped sanitized asset record，使用 returned `project_id` 执行 `project_read`，通过后才返回 public metadata；reader `NOT_FOUND` 或 backend error 不调用 authorizer，blank `project_id` 在 HTTP 边界 fail closed，reserved GET `/v1/assets/search` / `/v1/assets/bulk-actions` 保持普通 404。W2-S4h-a 之后，owner-aware `PATCH /v1/assets/{assetId}`、`DELETE /v1/assets/{assetId}` 和 `POST /v1/assets/{assetId}/adoptions` 必须在 JSON decode、mutation/adoption store 或 audit side effect 前执行同一 tenant-scoped asset owner lookup，再对 returned `project_id` 执行 `asset_manage`；reader backend errors 在该 preflight 边界只返回稳定 public message，不透出 driver/SQL/body/prompt/credential/object/draft/manuscript 文本；reserved asset names `search` / `bulk-actions` 不进入 single-asset mutation/adoption preflight。W2-S4h-b 之后，`POST /v1/assets/bulk-actions` 必须在 strict JSON decode 和 required field validation 后、bulk store side effect 前对 body `project_id` 执行 `asset_manage`；body tenant 不可信，body project 只是请求授权 scope，DB store 仍必须按 header tenant、project 和 submitted asset ids 过滤；bulk store errors 在 HTTP 边界只返回 stable public message。W2-S4h-c 之后，archive memory review adoptions/rejections 必须在 strict JSON decode 和 required body `project_id` validation 后，使用 header tenant + path memory id 读取 sanitized archive memory owner project，再对 returned project 执行 `asset_manage`，通过后才调用 review store；body project 保持必填兼容但不作为授权或 store scope truth，owner lookup/review errors 在 HTTP 边界只返回 stable public message。已呈现 credential 但签名/格式/secret/duplicate header 无效时，actor/RBAC-sensitive known routes 必须在 fallback actor、authorizer、reader/starter/store/resolver/auditor 前返回稳定 `UNAUTHENTICATED`，不得继续写空 actor；`/healthz` 和 default unknown-route 404 保持 public。W2-S4e 后，nested actor-sensitive route predicate 与 matching dispatch 必须使用 shape helpers，拒绝 project/resource id 含额外 path segment；malformed route-shaped paths 即使带 invalid credential 也应保持 404 且不触发 authorizer/backend，canonical protected routes 仍在 side effects 前 fail closed。直到引入完整 middleware/router auth，新 actor-consuming route 必须同步加入 route-scoped predicate 和 invalid-credential tests。
- W2-S5d/W2-S5e 起，在配置 `DATABASE_URL` / `AuthSessionStore` 的 Go API 中，signed Bearer token 和 `mirofish_session` cookie 不是只靠 HMAC 放行：resolver 必须先验证签名，再用 token hash 校验 `user_sessions` 中 active、未过期、未 revoked 的 session row。W2-S5g 后新签发 credential 使用 nonce-bearing `v2:<user_id>:<nonce>:<signature>`，legacy `v1:<user_id>:<signature>` 仍可验证兼容；runtime/admission 只消费验证后的 actor subject 和 token hash，不消费 raw token/nonce。校验失败、lookup failure、missing/revoked/expired session 必须在 development `X-User-Id` fallback、auth reader、authorizer、workflow starter、LLM resolver、store 或其他 runtime/admission side effect 前 fail closed。Dev session issuance 在设置 cookie 前必须先持久化 token hash；持久化失败不得发 cookie。Current-session logout/revocation 必须使用 presented signed Bearer/cookie credential，按 token hash revoke matching active session row，且 revoke failure 不得清 browser cookie 或 fallback 到 development actor。W2-S5h current-session rotation is cookie-only and store-required: it verifies the existing `mirofish_session`, signs a fresh nonce-bearing token, atomically swaps old token hash to new token hash in `user_sessions`, and sets a replacement cookie only after the store succeeds; Bearer and development header fallback are not rotation sources. W2-S5v adds exact `POST /v1/auth/session/jwt-rotation`: it follows the same cookie-only/session-store-required rotation ordering, but signs the replacement `mirofish_session` as a compact HS256 JWT with fixed issuer/audience/subject/session/iat/exp claims, stores only the JWT hash, and returns no JSON token body. W2-S5w adds exact `POST /v1/auth/session/access-token`: it uses the current cookie only as the source, verifies cookie-bound CSRF before any store/signing side effect, validates the old active session row, creates a new persisted compact JWT token hash, and returns only bearer JSON after persistence succeeds without setting or clearing browser cookies. W2-S5x adds exact `POST /v1/auth/session/jwt-refresh`: it accepts exactly one compact JWT Bearer token, rejects legacy `v1` / `v2` Bearer tokens and cookie/development fallback, signs a fresh compact JWT in memory, then uses `AuthSessionStore.RotateSession(oldHash -> newHash)` as the single DB side effect so the old row must be active/unexpired/non-revoked before the replacement token is publicly returned; it does not mutate browser cookies or multiply sessions through `CreateSession`. W2-S5i adds a focused cookie-session CSRF seam: `GET /v1/auth/csrf-token` validates the presented `mirofish_session` and active session row before returning only a session-bound token, and cookie-auth destructive/current-token routes (`DELETE /v1/auth/session`, `POST /v1/auth/session/rotation`, `POST /v1/auth/session/jwt-rotation`, `POST /v1/auth/session/access-token`) must verify `X-CSRF-Token` before revoke/rotate/create store calls, cookie clearing/replacement, or fresh-token signing. Bearer logout and Bearer JWT refresh remain non-cookie and do not require CSRF. W2-S5j wires an explicit Web refresh action to this path: Next fetches CSRF, calls rotation, parses only the replacement `mirofish_session` Set-Cookie server-side, and updates the browser cookie only after successful rotation. W2-S5k/W2-S5t add an automatic project-shell trigger that posts to a same-origin Next route only near expiry; the client receives only `currentSessionExpiresAt` public metadata plus an enabled boolean, skips missing/invalid or more-than-15-minute-away expiry, and stores only cooldown/status metadata, while the route handler reads the HttpOnly cookie server-side and reuses the same CSRF + rotation path before setting a replacement cookie. W2-S5l adds current-user all-session revocation: exact `DELETE /v1/auth/sessions` requires a presented signed credential, a configured session store, cookie CSRF before cookie-sourced store/cookie side effects, and a presented token hash that is still active/unexpired/non-revoked before all active sessions for that user are revoked; stale signed credentials cannot revoke newer sessions. W2-S5u wires tenant-wide session revocation into the Web shell only through a server action: the client component receives no cookie/CSRF/token material, the action reads the HttpOnly cookie at execution time, fetches CSRF server-side, calls path-tenant `DELETE /v1/tenants/{tenantId}/sessions`, and clears the Next cookie only after API success. `user_sessions` 不保存 raw token、secret、credential、prompt、object key、draft 或 manuscript；nil store 只作为兼容既有 stateless dev behavior，nonce-bearing issuance/explicit rotation/JWT cookie rotation/JWT bearer access-token issuance/Bearer JWT refresh/current-session CSRF/Web refresh/automatic near-expiry project-shell trigger/current-user all-session revocation/Web tenant-wide revocation action 也不代表 production login/route-wide auth middleware/refresh-token lifecycle 或 complete production session management 完成。
- W2-S4i 之后，project-scoped creative mutation admission 必须在 JSON decode 和 starter/store side effects 前通过 resolved-project `creative_write`：`POST /v1/projects/{projectId}/worldline-sessions`、`POST /v1/projects/{projectId}/worldlines/preparations` 和 `POST /v1/projects/{projectId}/character-interactions`。该 permission 只允许 matching active project role `project_owner`、`owner`、`admin`、`editor` 或 `writer`，不允许 raw tenant role alone、`analyst`、`viewer`、`billing`、blank/inactive status、无 matching project 或 different project。Denied responses must remain stable `AUTH_ACCESS_DENIED` and must not expose authorizer messages, actor ids, raw request body, prompt/provider response/content, API keys, encrypted credential material, `credential_ref`, object keys, drafts, or manuscripts. The actor-sensitive route predicate already includes these canonical project paths; future owner-aware/global worldline or character mutations must add equivalent invalid-credential and pre-side-effect authorization tests.
- W2-S4m 之后，Character Console interaction-scoped mutation/handoff routes 也必须在 runtime 或 Writer admission side effects 前通过 owner-aware `creative_write`。`POST /v1/character-interactions/{interactionId}/turns`、`PATCH /v1/character-interactions/{interactionId}` 和 `POST /v1/character-interactions/{interactionId}/chapter-drafts` 先用 header tenant + path interaction id 读取 interaction owner project，再用 returned project id 授权；body tenant/project 不可信。Denied/lookup/blank-owner paths 必须发生在 JSON decode、AppendTurn、UpdateInteractionStatus、ListTurns、LLM resolver 和 WriterStarter 之前，且 public errors 不得暴露 prompt/provider response/raw body/content、API key、encrypted credential、`credential_ref`、object key、draft 或 manuscript 正文。Malformed double-slash 或 extra-segment paths 保持 404，不触发 actor resolver、store、authorizer、LLM resolver 或 WriterStarter。
- W2-S4n 之后，tenant-level LLM settings/channel management routes 必须在 tenant settings reader、JSON decode、channel store、model syncer、credential decrypt 或 provider side effect 前通过 tenant-scoped `llm_module_binding_manage`。`GET /v1/llm/settings`、`POST /v1/llm/channels`、`PATCH /v1/llm/channels/{channelId}`、`DELETE /v1/llm/channels/{channelId}` 和 `POST /v1/llm/channels/{channelId}/sync-models` 使用 header tenant + resolved actor 授权；body tenant/project 不可信，project id 为空是该 permission 的显式 tenant scope。该 permission 只允许 active tenant `owner` / `admin`，不允许 project role alone。Denied responses must use stable public auth messages and must not expose authorizer/backend text, raw body/content, prompt/provider response, API keys, encrypted credential material, `credential_ref`, object keys, drafts, or manuscripts. Malformed double-slash or extra-segment LLM channel mutation/sync paths stay ordinary 404s and must not trigger actor resolver, authorizer, channel store, or model syncer.
- W2-S5a 之后，`POST /v1/auth/dev-sessions` 可以作为 development-only browser session issuance seam 发放 `mirofish_session`，但它不是 runtime/admission actor-consuming route。该 route 必须先要求 `SessionAuthSecret`，再 strict-decode `user_id`，通过 auth reader 验证 existing active user 后才发 signed cookie；W2-S5g 后新 cookie value 必须为 non-deterministic v2 session token，同一 user 重复签发不应复用相同 token/hash。public response 只返回 current-user summary，不返回 token、secret、nonce、raw body、credential、draft 或 manuscript。Malformed auth paths 保持普通 404，不触发 actor resolver、auth reader 或 cookie issuance。W2-S5h adds an exact `POST /v1/auth/session/rotation` API seam for explicit current-cookie rotation; malformed rotation paths must likewise stay ordinary 404 without actor resolver/store/cookie side effects. W2-S5v adds exact `POST /v1/auth/session/jwt-rotation` for cookie-only JWT migration; malformed JWT rotation paths likewise stay ordinary 404 without actor resolver/store/cookie side effects. W2-S5w adds exact `POST /v1/auth/session/access-token` for current-cookie-to-Bearer JWT issuance; malformed access-token paths likewise stay ordinary 404 without actor resolver/session-store/cookie side effects. W2-S5x adds exact `POST /v1/auth/session/jwt-refresh` for Bearer-only compact JWT renewal; malformed jwt-refresh paths stay ordinary 404 without actor resolver/session-store/signing/cookie side effects. W2-S5i adds exact `GET /v1/auth/csrf-token`; malformed double-slash or extra-segment CSRF paths stay ordinary 404 and do not validate actors, session store, or issue token metadata. W2-S5l adds exact `DELETE /v1/auth/sessions`; malformed all-session revocation paths stay ordinary 404 and do not validate actors, call the session store, or mutate cookies. W2-S5b/W2-S5c 已让 Next project shell 和 downstream project page reads/actions server-side 转发该 cookie-first context，只有无 cookie 时才使用 development actor fallback；W2-S5i Web logout fetches the CSRF token with the browser cookie before cookie revoke and does not clear the Next cookie if either token fetch or revoke fails. W2-S5j Web refresh action likewise fetches CSRF before rotation, uses no development actor fallback, and leaves the browser cookie unchanged if CSRF, rotation, or replacement cookie parsing fails. W2-S5t hardens W2-S5k automatic project-shell refresh by deriving only the current session's public `expires_at` from `GET /v1/auth/sessions`, passing only that timestamp plus an enabled flag to the client, and skipping same-origin refresh unless the expiry is parseable and within the 15-minute threshold. W2-S5u adds an owner/admin-only ProjectNav tenant-wide revocation form whose server action fetches CSRF and calls the exact path-tenant API without body/dev actor fallback; browser JS never receives the cookie value, CSRF token, replacement token, token hash, or signing secret; failure leaves the cookie unchanged and returns only sanitized status. Production login completion、refresh-token lifecycle、route-wide middleware、production-grade session management UX hardening 和 revocation-aware runtime admission 仍是后续工作。
- W2-S5n adds a shared Go HTTP preflight for unsafe actor-sensitive routes when the credential source is `mirofish_session`: missing or invalid `X-CSRF-Token` fails before actor resolver, session-store validation, authorizer, JSON decode, LLM resolver, workflow starter, or business store side effects. Bearer credentials and development `X-User-Id` remain non-cookie paths and do not require this guard. Malformed non-matching paths must still remain ordinary 404s without actor/session/backend side effects. Production login/JWT/session persistence, refresh-token lifecycle, route-wide auth middleware, production-grade session management UI, and revocation-aware runtime admission remain follow-up work.
- W2-S5y expands shared actor credential preflight to canonical global run read/replay routes: `GET /v1/workflow-runs/{runId}`, `GET /v1/workflow-runs/{runId}/events`, `GET /v1/seed-runs/{runId}`, `GET /v1/seed-runs/{runId}/events`, `GET /v1/writer-runs/{runId}`, and `GET /v1/writer-runs/{runId}/events`. Invalid, malformed, or duplicate presented credentials must fail closed before development `X-User-Id` fallback and before workflow/seed/writer readers or event readers. Missing Bearer/cookie credentials preserve existing read behavior for this credential-preflight slice. Strict single-segment route helpers must keep malformed double-slash, missing-id, extra-segment, and false-prefix paths as ordinary 404s with no actor resolver/session-store/reader side effects. This is not owner-aware run authorization and does not cover cancel/retry hardening.
- W2-S5z adds owner-aware `project_read` authorization to canonical global run read/replay routes. `GET /v1/workflow-runs/{runId}`, `GET /v1/workflow-runs/{runId}/events`, `GET /v1/seed-runs/{runId}`, `GET /v1/seed-runs/{runId}/events`, `GET /v1/writer-runs/{runId}`, and `GET /v1/writer-runs/{runId}/events` must first read the tenant-scoped owner run by header tenant + path run id, require a nonblank returned `ProjectID`, authorize `auth.PermissionProjectRead` on that returned project, and only then write run metadata or call event readers. Event replay must sanitize workflow and writer payloads at the HTTP boundary, including `provider` / `provider_response`, prompt/body/content, credential/API key fields, object keys, draft, and manuscript fields. Owner lookup, event reader, SQL query/scan/rows, and cursor errors must map to stable public workflow messages instead of raw driver/store text. Malformed double-slash, missing-id, extra-segment, and false-prefix paths remain ordinary 404s with no actor resolver, session-store, owner reader, authorizer, event reader, or WriterStarter side effects. This slice does not cover global run cancel/retry owner authorization.
- W2-S5za adds owner-aware authorization to canonical global run control routes. `POST /v1/workflow-runs/{runId}/cancel` and `/retry` must read the tenant/path owner workflow run first, require a nonblank returned `ProjectID`, choose permission from returned `WorkflowType`, authorize the returned project, and only then call cancellation/retry side effects. Asset workflows (`asset_ingestion`, `style_extraction`, `asset_reindex`) require `auth.PermissionAssetManage`; creative workflows (`writer_run`, `writer_review`, `seed_pipeline`, `story_graph_build`, `story_graph_bond_generation`, `hello_agent`, `worldline_session`, `worldline_step`, `worldline_preparation`) require `auth.PermissionCreativeWrite`; unknown workflow types fail closed before authorizer and backend side effects. Seed-specific `POST /v1/seed-runs/{runId}/cancel` / `/retry` and Writer-specific `POST /v1/writer-runs/{runId}/cancel` must use their tenant/path owner readers and returned `ProjectID` with `creative_write` before generic workflow or writer cancellation/retry side effects. Body tenant/project values are not ownership truth. Owner lookup and side-effect errors must use stable workflow public messages, and malformed double-slash / extra-segment control paths must remain ordinary 404s with no actor resolver, session-store, owner reader, authorizer, canceller, retrier, or WriterStarter side effects.
- W2-S5o adds exact `GET /v1/auth/sessions` as current-user active session metadata read side. It requires a presented signed Bearer or `mirofish_session` credential plus configured `AuthSessionStore`, does not use development `X-User-Id` fallback, does not call `/v1/me` auth reader, does not require CSRF because it is safe `GET`, and does not mutate cookies. `SQLSessionStore.ListUserSessions` uses the presented token hash only as an active/unexpired/non-revoked precondition and current-session marker; public response exposes only `session_id`, `status`, `expires_at`, `last_seen_at`, and `current`, never raw token, token hash, signing secret, nonce, user id, prompt/provider response, API key, `credential_ref`, object key, draft, or manuscript. Malformed double-slash or extra-segment session-list paths remain ordinary 404s without session-store side effects. Production login/JWT/session persistence, refresh-token lifecycle, route-wide auth middleware, and production-grade session management UI remain follow-up work.
- W2-S5q/W2-S5r add a narrow password login issuance and Web consumption seam. Go exact `POST /v1/auth/login` verifies active user + active bcrypt credential, persists only session token hash metadata, and sets `mirofish_session` only after persistence succeeds. Next `/login` calls that endpoint through `loginWithPassword` with JSON `email` and exact `password`, no development actor, tenant header, Cookie, or CSRF; the server action parses the returned `Set-Cookie`, requires a public active project redirect target, and sets the browser cookie via `next/headers` only on the server side. Runtime/admission routes still consume only verified actor subject/session hash context, never password, raw token, nonce, token hash, signing secret, prompt/provider response, API key, `credential_ref`, object key, draft, or manuscript. Signup/password reset/OAuth/MFA, JWT claims, refresh-token lifecycle, route-wide auth middleware, and complete production auth remain follow-up work.
- W2-S5s adds compact HS256 JWT Bearer subject resolution to the same runtime admission seam. The verifier accepts only the fixed `iss=mirofish-auth` / `aud=mirofish-api` / `sub` / `sid` / `iat` / `exp` claim schema, returns only `sub` plus the full compact JWT hash for existing `AuthSessionStore` validation, and does not trust role/project claims or expose JWT claim/token material to runtime payloads, events, logs, UI, or public API responses. W2-S5v reuses that verifier for JWT-shaped `mirofish_session` cookies after the cookie-only migration endpoint persists the JWT hash. W2-S5w reuses the same signer/verifier for bodyless current-cookie-to-Bearer issuance, persisting only the new compact JWT hash before returning the newly issued `access_token` JSON. W2-S5x reuses the compact JWT verifier for Bearer-only renewal, but deliberately rejects legacy `v1` / `v2` Bearer tokens and uses `RotateSession` rather than `CreateSession`, so a stale presented JWT cannot remain active after a successful refresh. Refresh-token lifecycle, OAuth/MFA, and complete production auth remain follow-up work.
- W2-S4j 之后，session-scoped worldline creative mutations 也必须在 JSON decode 和 starter/store side effects 前通过 owner-aware `creative_write`：`POST /v1/worldline-sessions/{sessionId}/steps`、`POST /v1/worldline-sessions/{sessionId}/variables` 和 `POST /v1/worldline-sessions/{sessionId}/saved-paths`。这些 routes 没有 path project id，HTTP boundary 必须使用 header tenant + path session id 调用 session reader，使用 returned `ProjectID` 授权；body tenant/project 字段不得作为 resource ownership truth。Blank returned project 必须 fail closed 为 `AUTH_ACCESS_DENIED`；session lookup errors must use stable public worldline session lookup messages and must not call the authorizer or mutation store/starter. Future owner-aware/global worldline event edit/adoption/read routes and Character Console session-scoped mutations must add equivalent invalid-credential, owner-lookup, blank-owner, denied-before-decode, and no-side-effect tests.
- W2-S4k 之后，session-scoped worldline read routes 也必须先做 owner-aware `project_read`：`GET /v1/worldline-sessions/{sessionId}`、`GET /v1/worldline-sessions/{sessionId}/timeline` 和 `GET /v1/worldline-sessions/{sessionId}/events`。Detail response must not be written before authorization; timeline/event final readers must not be called before authorization. Malformed double-slash or extra-segment paths must remain ordinary 404s and must not become actor-sensitive protected routes. Owner lookup failures and final timeline/event reader failures must use stable public worldline session lookup messages rather than raw driver/store text.
- W2-S4p 之后，preparation-scoped worldline read routes 也必须先做 owner-aware `project_read`：`GET /v1/worldline-preparations/{prepareId}` 和 `GET /v1/worldline-preparations/{prepareId}/agents`。HTTP boundary 必须使用 header tenant + path prepare id 调用 preparation store，使用 returned `ProjectID` 授权；detail response 和 prepared-agent reader must not be reached before authorization. Blank returned project must fail closed as `AUTH_ACCESS_DENIED`; owner lookup and final prepared-agent reader errors must use stable worldline preparation public messages rather than raw driver/store text. Malformed double-slash or extra-segment preparation paths must remain ordinary 404s and must not trigger actor resolver, session store, preparation store, authorizer, or prepared-agent reader.
- W2-S4l 之后，event-scoped worldline adoption/update routes 也必须先做 owner-aware `creative_write`：`POST /v1/worldline-events/{eventId}/adoptions` 和 `PATCH /v1/worldline-events/{eventId}`。这些 routes 没有 path project id，HTTP boundary 必须使用 header tenant + path event id 调用 event reader，使用 returned `ProjectID` 授权；body tenant/project 字段不得作为 resource ownership truth。Authorization must happen before JSON decode, adoption store, mutation store, workflow event side effects, or canon metadata changes. Blank returned project must fail closed as `AUTH_ACCESS_DENIED`; owner lookup/store errors must use stable public messages and must not expose prompt/provider response/raw body/content, API keys, encrypted credential material, `credential_ref`, object keys, drafts, manuscripts, actor ids, or driver/store text. Malformed double-slash or extra-segment event paths must remain ordinary 404s and must not become actor-sensitive protected routes.
- Pi Writer Runtime 写入 `prompt_snapshot`、`llm_call_started`、`llm_call_completed`、`artifact_written` 和 `error`；其中 prompt snapshot 标记为 `full`，默认读侧不得泄露用户小说原文或 prompt。
- LLM Activity 读侧必须把 `llm_activity.error_jsonb` 和 reader 返回的 `error` map 都当作不可信 payload 递归清洗，移除 `api_key`、`encrypted_api_key`、`credential_ref`、`prompt`、`response`、`body`、`content`、`candidate_body`、`event_body`、`source_material`、`source_text`、`draft`、`manuscript` 等高风险字段；解析失败时返回稳定摘要，不把原始错误字符串透传给前端。清洗同时发生在 SQL reader 和 HTTP response 边界，避免替换 reader 实现后绕过隐私防线。Activity / Usage SQL query、scan 或 rows error 也必须收敛为稳定 `LLM_ACTIVITY_QUERY_FAILED` / `LLM activity query failed`，HTTP 边界不得把 driver/SQL 异常文本透出到公开响应。LLM Usage 读侧只聚合 `usage_events.usage_type = llm_tokens`，并继续按 tenant/project/run/module 过滤；不得把 storage、workflow、import 或其他非 LLM billing events 暴露为 LLM Facility usage。Runtime 写入侧也要在入库前清洗错误 payload；Worldline `PostgresLLMTelemetryWriter` 已对 `llm_activity.error_jsonb` 执行同一类递归 key 清洗，避免未来调用方把 credential/prompt/source 字段写进 telemetry 表。
- Worldline step runner 在 provider 调用、schema validation 和 completed `llm_activity` / optional `usage_events` 写入成功后，如果 `worldline_events.status = candidate` metadata persistence 失败，必须返回 candidate persistence 的明确错误，但不得追加一条 failed LLM activity；Activity/Usage read side 应保持对同一 `run_id` 的 provider-call 事实一致性。即使 candidate writer 抛出非规范普通异常，runner 也必须把它收敛为稳定 `WORLDLINE_CANDIDATE_EVENT_WRITE_FAILED`，不得误报为 `LLM_PROVIDER_ERROR` 或把底层异常文本透出。
- Worldline candidate event writer 的 DB/driver 异常文本不得进入公开 `LLMFacilityError.message`；普通 insert 异常必须 rollback 并返回稳定 `WORLDLINE_CANDIDATE_EVENT_WRITE_FAILED` / `worldline candidate event write failed`，避免异常消息夹带 prompt、source text、API key 或 `credential_ref`。`INSERT ... SELECT` 未命中 admitted session 时返回 `WORLDLINE_SESSION_NOT_FOUND` 的显式失败路径也必须 rollback，避免 batch 中部分 candidate event 停留在未清理事务里。
- Worldline LLM telemetry writer boundary 必须把注入式 writer、非 Postgres writer 或 driver wrapper 抛出的普通异常也视为不可信异常：completed telemetry 普通异常必须收敛为 `LLM_TELEMETRY_WRITE_FAILED` / `worldline completed telemetry write failed`，failed telemetry 普通异常必须收敛为 `LLM_TELEMETRY_WRITE_FAILED` / `worldline LLM activity write failed`。这些路径不得把底层异常文本、prompt、source text、API key 或 `credential_ref` 暴露到 runner result、workflow event/status 或公开 API，也不得在 completed telemetry 失败后继续写 candidate event。
- Worldline DB-backed success chain 现在有 integration-like 和 opt-in live Postgres/app-role local-provider E2E 覆盖：`worldline_step_activity` 通过 DB-backed module binding resolver、AES-GCM credential decrypt、JSON provider response、atomic completed `llm_activity` + `usage_events` write、tenant/project/session-scoped `worldline_events.status = candidate` persistence、admitted `workflow_runs.workflow_type = worldline_step` completed event/status 写入同一 `run_id` 链路。live E2E 使用真实 migration、`mirofish_live_app` app role/RLS、local OpenAI-compatible JSON provider 和同一 `run_id` 校验 provider request、`llm_activity`、token-only `usage_events`、candidate event、workflow event/status 关联；Go read-side live test 也用同一 RLS tenant context 读取 `worldline_director` Activity/Usage。公开 result、persisted public payload 和 provider-facing recorded data 不包含 provider API key、candidate event body、用户 prompt 或 `credential_ref`。
- Worldline source loader 已接入 `LLMFacilityWorldlineStepRunner`：当 `options.source_refs` 非空但 runner 未装配授权 source loader 时，必须在 binding/credential/provider 调用前以 `WORLDLINE_SOURCE_LOADER_UNCONFIGURED` fail closed，不写 telemetry/candidate event。配置 `DATABASE_URL` 时默认装配 `PostgresWorldlineSourceLoader`，只从 tenant/project/session scoped `assets` public metadata 与同 session `worldline_events` public metadata 读取 summary，不选择 `content_text`、event body、prompt 或 credential 字段；只允许把 sanitized public source summaries 注入 provider message。如果提供了 `source_refs` 但 loader 返回空 summaries，runner 必须在 binding/credential/provider/telemetry/candidate 之前以 `WORLDLINE_SOURCE_NOT_FOUND` / `worldline source_refs did not resolve to public summaries` fail closed。DB query exception 收敛为 `WORLDLINE_SOURCE_LOAD_FAILED` / `worldline source load failed`，不得透出底层异常文本。richer director tools、外部 provider/cluster E2E 和 Character Console runtime 仍是后续 Phase 6 工作。
- Character Console 当前只落地 Go/API/Web metadata skeleton，不启动角色对话 runtime、不调用 `worldline_agent_dialogue` / `character_interaction_director` 等 module binding。Next `/character-console` 已通过 API client/server action/form 接入 `POST /v1/projects/{projectId}/character-interactions`，只提交 worldline/session/anchor/POV/mode/title/summary 等 public metadata，并用显式 success/error query state 回到列表；同页也通过 server action/form 接入 `POST /v1/character-interactions/{interactionId}/turns`，只记录显式提交的 actor/kind/summary/action/world-state-delta/trace public turn metadata。Go HTTP append route 会先按当前 tenant scope 读取 parent interaction，缺失、跨租户或无 backend 时返回稳定错误并停止，不把任意 interaction id 写成 fake created turn。Go store 在 SQL 前校验 interaction anchor type/mode 和 turn actor/kind enum，非法值以 `VALIDATION_FAILED` fail closed，避免任意字符串被当成 runtime action、runtime anchor 或 fake agent reply metadata；读侧也把 DB 中已有的 `metadata` / `action` / `world_state_delta` JSON 当作不可信 payload，返回前递归移除 prompt/body/content/credential/draft/manuscript 类 key。HTTP response boundary 会在写出 create/list/detail/append/turn replay 响应前再次清洗 interaction/turn record，使注入 store、替换 store 或 alternate writer 返回 unsafe map 时也不会绕过公开 API 隐私边界；SQL store 会把 query、scan、`rows.Err()`、rows close 和 transaction commit failure 收敛为稳定 `CHARACTER_INTERACTION_QUERY_FAILED`，store 层 scan 错误使用固定 interaction/turn query failed 文案，同一 HTTP 边界会把公开 message 固定为 `character interaction query failed`，避免普通 store/driver exception 文本夹带 prompt、API key、`credential_ref`、正文或 draft/manuscript。Next replay read side 现在可用 `selected_interaction_id` 调 `GET /v1/character-interactions/{interactionId}`，展示 selected interaction 和 saved turn metadata；独立 turn replay store/read side 会先确认 parent interaction 在当前 tenant 下存在，缺失或跨租户时返回 `NOT_FOUND`，不会把无效 interaction 当成空历史。Next create interaction form 也读取真实 `GET /v1/projects/{projectId}/worldline-sessions` public metadata；有 session 时作为 worldline/session anchor 下拉选择，无 DB/backend 时显式显示 `WORLDLINE_SESSION_BACKEND_UNCONFIGURED`，不伪造可选 session。Next 同时读取 `GET /v1/projects/{projectId}/worldline/saved-paths` public metadata，作为 saved path anchor choices 和侧栏预览；缺 DB/backend 时显式显示 `WORLDLINE_BACKEND_UNCONFIGURED`，不伪造 saved path。Next 还读取 `GET /v1/projects/{projectId}/story-graph/views/current` 的 public graph node metadata，把 character/organization/location/plot_thread 节点作为 graph node anchor choices 和侧栏预览；缺 Story Graph backend 时显式显示 `STORY_GRAPH_BACKEND_UNCONFIGURED` 或等价查询错误，不伪造 graph node。若作者通过 `anchor_session_id` 选择了已 admission 的 worldline session，Next 会读取 `GET /v1/worldline-sessions/{sessionId}/events` public candidate/canon event metadata，作为 `anchor_id` event selector；未选择或 event read side 失败只显示明确状态，不生成 worldline event、不采用 canon、不保存 path。若作者通过 `prepare_id` 选择了已 admission 的 worldline preparation，Next 还会读取 `GET /v1/worldline-preparations/{prepareId}/agents` public prepared-agent metadata，作为 POV agent selector 和 roster preview；未选择或 backend 失败只显示明确状态，不生成 playable agent。Next typed API client 和 server actions 现在接入两个不同边界：`GET /v1/character-interactions/{interactionId}/events` 仍只回显 `CHARACTER_CONSOLE_RUNTIME_PENDING` / 稳定错误状态，Go pending endpoint 会先按当前 tenant 读取 interaction，缺失/跨租户或无 backend 直接返回对应稳定错误，不把任意 id 报成 pending；`POST /v1/character-interactions/{interactionId}/chapter-drafts` 则是明确用户动作，会读取 tenant-scoped interaction/public turns、通过 LLM Facility 解析 `writer_composer`，并调用既有 Writer runtime admission 创建真实 `writer_run`，UI 只显示 Writer run queued，不合成 `draft_id`、正文、manuscript 或 Character Console runtime event。角色对话 runtime 仍必须 fail closed，直到具备 tenant/project/session/interaction/run context、权限检查、trace、错误状态和可审计记录。未来 runtime 产生的世界反馈仍只能写 candidate/public metadata；Writer draft persistence 仍由 Writer pipeline 负责。
- Character Console HTTP error boundary 现在还会把 coded `NOT_FOUND` / `CHARACTER_INTERACTION_BACKEND_UNCONFIGURED` store error 映射为固定安全文案；即使替换 store 或 injected store 把 prompt、API key、`credential_ref`、draft/manuscript 文本塞进 error message，公开 API 也不能回显该文本。
- Character Console create/append route 的 JSON decode validation error 不再回显 decoder 原始错误详情；unknown field 名称如果包含 `api_key`、`prompt`、`credential_ref`、draft/manuscript 等敏感词，也不能进入公开 error details。
- Character Console -> Writer handoff 现在还有空材料防护：`POST /v1/character-interactions/{interactionId}/chapter-drafts` 必须先读到至少一条带非空 public summary 的 saved turn；空 public turn history 或只有空白 summary 的 turn history 都以 `CHARACTER_INTERACTION_TURNS_REQUIRED` fail closed，并且发生在 `writer_composer` binding 解析和 `WriterStarter` admission 之前。

## Tool Calling

### 工具分类

Read tools：

- query_entity。
- query_relationship。
- query_graph_neighbors。
- global_search。
- query_asset。
- query_worldline_session。
- query_manuscript。

Write tools：

- manage_entity。
- manage_relationship。
- manage_thread。
- manage_world_rule。
- record_character_event。
- update_scene。
- commit_manuscript。

Proposal tools：

- propose_outline_scene。
- propose_chapter_structure。
- propose_relationship。
- propose_prose_continuation。
- propose_rewrite_span。

### 执行规则

- read tools 可并行。
- write tools 串行。
- proposal tools 不写 canon。
- 每个工具执行前检查权限。
- 每个工具结果写 trace。
- 工具失败返回结构化错误，不让整个 Agent 无解释中断，除非是必需工具。

## Schema Validation

所有 Agent 输出都要定义 schema：

- Pydantic v2。
- JSON schema 导出给 prompt。
- validation error 写 trace。
- repair 有次数上限。

不允许：

- 未校验 dict 直接落库。
- 解析失败变空对象继续。

## 工作流与 Activity

### Task Queues

```text
seed-heavy
graph-heavy
asset-light
worldline-interactive
writer-streaming
reviewer
maintenance
```

不同队列可独立扩容。

`graph-heavy` 当前注册 `StoryGraphBuildWorkflow` / `story_graph_build_activity`。入口 payload 必须携带 `tenant_id`、`project_id`、`run_id`、`workflow_type=story_graph_build`、`module_key=story_graph_build`、`trace_id` 和 `story_graph_build:run` permission；缺权限、module mismatch 或缺少 DB-backed graph builder 时写 sanitized `graph.stage.failed` event 并返回结构化错误。默认缺 builder 必须 fail closed 为 `STORY_GRAPH_BUILDER_UNCONFIGURED`，不得生成 mock graph snapshot、节点或边。配置 `DATABASE_URL` 时，Python runtime 会默认装配 `PostgresStoryGraphBuilder`，从结构化 canon/assets 表生成 `story_graph_snapshots`、nodes、edges、public evidence metadata、layout 和 clusters，并通过 `PostgresWorkflowRunStatusWriter` 同步更新 tenant/project scoped `workflow_runs` public status：成功置为 `completed`、`progress = 100`、`result_jsonb` 仅包含 graph id/counts；失败置为 `failed` 并记录稳定 error code/message。公开 result/completed event/status 只包含 graph id 与 counts，builder 持久化路径不写 evidence snippet、raw source text、prompt、`content_text` 或 credential 字段到公开 payload。

同一 `graph-heavy` 队列也注册 `GraphBondGenerationWorkflow` / `graph_bond_generation_activity`。Go control plane 在配置 `TEMPORAL_ADDRESS` 与 `DATABASE_URL` 时会先写 tenant/project scoped `workflow_runs` 和 sanitized `workflow.queued` event，再启动 `GraphBondGenerationWorkflow`；admission 失败必须返回 `WORKFLOW_ADMISSION_FAILED` 且不得启动 worker。该 activity 要求 `workflow_type = story_graph_bond_generation`、`module_key = graph_bond_generator`、`graph_bond_generator:run` permission，以及 tenant/project/run/trace context；缺少真实 runner 时以 `GRAPH_BOND_RUNNER_UNCONFIGURED` fail-closed，并只写 sanitized `graph.stage.failed` workflow event / failed run status。配置 `DATABASE_URL` 与显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 时，默认 runner 会通过 LLM Facility 解析 `graph_bond_generator` module binding、解密 tenant-scoped credential、调用 JSON-capable provider、schema-validate bonds / plot threads / conflict triggers，并通过 candidate writer 只写 lifecycle=`candidate` assets。它不写 relationships、plot_threads 或 canon，不生成 mock output，candidate -> canon 仍必须是明确用户动作。公开 result/event/status 不得包含 selected node ids、focus text、prompt/response、evidence snippet、candidate body、API key、encrypted credential 或 `credential_ref`。

`reviewer` 队列用于后续 `writer_reviewer` runtime。当前 Go control plane 只实现 `POST /v1/drafts/{draftId}/reviews` admission/read side：HTTP 要求显式 `project_id`，先用该 project scope 解析 `writer_reviewer` LLM Facility binding，DB-backed path 只写 tenant/project-scoped `workflow_runs`、不含 user note/body 的 sanitized `workflow.queued` event 和 `draft_reviews.status = queued` metadata。真实 reviewer activity、issue production、dedup/apply-revision runtime 仍 pending；未实现前不得生成 fake `draft_review_issues`、不得读取或公开 draft/manuscript 正文、不得采用 manuscript，也不得回退旧 env LLM 配置。未来 runtime 写 `draft_review_issues` 时只能写同一 `(tenant_id, project_id, draft_id, review_id)` 下的 severity/category/summary/suggestion/status public metadata，并继续通过 LLM Facility credential/binding path。

`worldline-interactive` 当前注册 `WorldlineStepWorkflow` / `worldline_step_activity`，用于承接 Go `POST /v1/worldline-sessions/{sessionId}/steps` admission 后的单世界 step execution。该 activity 要求 payload 携带 `tenant_id`、`project_id`、`run_id`、`trace_id`、`session_id`、`workflow_type = worldline_step`、`module_key = worldline_director` 和 `worldline_director:run` permission；缺权限、module mismatch 或缺少真实 `WorldlineStepRunner` 时必须 fail closed。默认未装配 runner 时返回 `WORLDLINE_STEP_RUNNER_UNCONFIGURED`，并在配置 writer/status writer 时只写 sanitized `worldline.stage.failed` workflow event 和 failed `workflow_runs` public status；runner 直接抛出的 `LLMFacilityError` 会保留原始 code/message 写入 failed result/event/status，不能被泛化成 `WORLDLINE_STEP_FAILED` 或伪成功。未装配 runner 时不能调用 LLM，不能生成 mock candidate event、timeline event、saved path、canon event、draft 或 manuscript。配置 `DATABASE_URL` 后，默认 `LLMFacilityWorldlineStepRunner` 会先验证 `context.run_id` 是有效 UUID；非法 run id 以 `VALIDATION_FAILED` fail closed，且不会解析 module binding、解密 credential、调用 provider、写 telemetry 或写 candidate event，避免破坏 candidate event 与 Activity/Usage telemetry 的同 run 关联。run id 合法后，runner 才会通过 LLM Facility 解析 `worldline_director` module binding；resolution 必须包含 `provider`、`channel_id`、`model_id`、`base_url` 和 `credential_ref`，缺 provider 会在 credential decrypt/provider call/candidate write 前以 `LLM_PROVIDER_ERROR` fail closed。resolution 合法后才用显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 解密 tenant-scoped credential、调用 JSON-capable OpenAI-compatible provider、schema-validate `candidate_events`，并通过 `PostgresWorldlineCandidateEventWriter` 只写 `worldline_events.status = candidate` / `lifecycle = simulation` 的 public metadata；candidate insert 先通过 `worldline_sessions` 校验当前 tenant/project/session 已 admission，缺失或跨租户/项目 session 以 `WORLDLINE_SESSION_NOT_FOUND` fail closed 并 rollback；普通 DB/driver insert exception 会 rollback 并返回稳定 `WORLDLINE_CANDIDATE_EVENT_WRITE_FAILED`，不透传底层异常文本；`source_run_id` 使用规范化后的 UUID run id，不能静默写成 NULL。该 runner 现在也会通过 `PostgresLLMTelemetryWriter` 写入 completed/failed `llm_activity`；completed activity 和 token usage 必须在 provider `candidate_events` schema validation 通过后写入，当 provider 返回 token usage 时写 `usage_events.usage_type = llm_tokens`，同时支持 `prompt_tokens` / `completion_tokens` breakdown 和仅 `total_tokens` 的 OpenAI-compatible 返回；Postgres completed path 必须把 completed `llm_activity` 与可选 `usage_events` 放入同一个 DB transaction/commit，避免 activity 与 usage 半成功拆裂；若 completed transaction 内的 usage insert 或其他 DB 写入失败，必须显式 rollback、返回 `LLM_TELEMETRY_WRITE_FAILED`，并且不写 candidate event。provider/schema/credential 类失败只写 failed activity、不写 usage event，activity error payload 入库前会清除 credential/prompt/source/body/draft/manuscript 类高风险 key；单条 `llm_activity` 或 `usage_events` 写入失败也必须显式 rollback 后再返回稳定 `LLM_TELEMETRY_WRITE_FAILED`，不能留下未清理事务。telemetry 写入失败必须以 `LLM_TELEMETRY_WRITE_FAILED` fail closed，不能写 candidate event，也不能通过二次 failed telemetry 写入把异常抛到调用方；如果 candidate metadata persistence 在 completed telemetry 成功后失败，runner 返回该 candidate persistence 错误，但不追加 failed `llm_activity`，避免同一 `run_id` 的 provider call 出现 completed/failed 双重 telemetry。普通 provider/SDK exception 不得把 `str(exc)` 透传到公开 result/event/status；当前统一返回 `LLM_PROVIDER_ERROR` / `worldline provider call failed`，避免 SDK 错误消息泄露 API key、prompt 或 source material；Go LLM Activity read side 还会在 SQL reader 和 HTTP response 边界递归清洗 activity error payload，避免历史或外部写入的错误对象泄露 credential/prompt/source 字段。成功后 activity 还会写 sanitized `worldline.stage.completed` workflow event 并更新 admitted `workflow_runs` public status；completed payload 只包含 session/mode/step/model/count 等公开字段。candidate -> canon、saved path、writer draft 仍必须是明确用户动作。公开 result/event/status 不得包含 prompt/response、source text、event body、draft/manuscript、API key、encrypted credential 或 `credential_ref`。

Worldline Postgres workflow event/status writer 也属于 runtime public persistence 边界：`PostgresWorkflowEventWriter` 和 `PostgresWorkflowRunStatusWriter` 的 DB/driver 异常路径必须显式 rollback，并只抛稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `WORKFLOW_STATUS_WRITE_FAILED` 文本，避免 prompt、API key 或 `credential_ref` 从底层异常泄露到 runtime failure。
当 `PostgresWorkflowEventWriter` 写 `workflow_events` 或 `PostgresWorkflowRunStatusWriter` 更新 `workflow_runs` 未命中已 admission 的 `worldline_step` parent row 时，必须在 commit 前 rollback，并以 `WORKFLOW_RUN_NOT_FOUND` 显式失败；不能创建 orphan workflow event，也不能把缺失 admission 当作成功状态更新。
`worldline_step_activity` 的 completed persistence 边界也必须结构化这些失败：当 runner 已完成但 `worldline.stage.completed` 事件写入失败时，activity 返回 `WORKFLOW_EVENT_WRITE_FAILED` / `WORKFLOW_RUN_NOT_FOUND` 的 failed result，并尝试把 admitted run 标记为 failed；当 completed status update 失败时，activity 返回稳定 `WORKFLOW_STATUS_WRITE_FAILED` / `WORKFLOW_RUN_NOT_FOUND`，不得让 writer exception 直接冒出为未结构化 activity crash。activity 层不得信任 writer exception message，即使异常文本以稳定 code 开头，公开 message 也必须按 code 映射为固定安全文案，不得把 prompt、API key 或 `credential_ref` 透出到 result/event/status。

### Activity Timeout

必须显式设置：

- start_to_close_timeout。
- schedule_to_close_timeout。
- heartbeat_timeout。

长 LLM activity 要 heartbeat：

- 当前 segment。
- 当前 entity。
- token stream position。

### Cancellation

Workflow cancellation 必须传递到：

- LLM call abort。
- file parse。
- DB write stage boundary。
- SSE close event。
- Go API 的 `POST /v1/writer-runs/{runId}/cancel` 是 fail-closed cancellation 入口：必须有 tenant context，并把 actor/request metadata 传给配置的 backend；没有 backend 时返回 `WORKFLOW_CANCEL_BACKEND_UNCONFIGURED`，不得伪造取消成功。配置 Temporal 后必须取消 `writer_run_{runId}` workflow；同时配置 SaaS Postgres 后，只有 Temporal 接受取消后才可把 `writer_runs` / `workflow_runs` 置为 `cancelled` 并追加 `writer.run.cancelled` 事件。

## Streaming

Writer 和 worldline 可以流式输出：

- Python activity 产出事件。
- Temporal activity 事件写入 `workflow_events`。
- Go SSE 读取事件表或订阅 channel。
- Writer stream 恢复必须以持久化 `workflow_events` 为准：`GET /v1/writer-runs/{runId}/events` 支持 `after_event_id` query cursor 和 SSE `Last-Event-ID`，只返回 cursor 之后的事件；cursor 不存在时返回显式错误，不静默从头重放或吞错。
- Next Writer Workbench 的 recovered stream UI 必须把 `after_event_id` 作为显式用户 cursor 提交，并保留当前 query 选择的 run/trace metadata；公共 Writer/Trace event panels 不得渲染 raw event payload JSON，只能展示事件 metadata 和 payload key counts，避免替换 reader 或历史 unsafe payload 通过 UI 泄露 prompt、provider response、credential、object key、draft 或 manuscript 正文。
- Go writer admission 在启动 `PiWriterRunWorkflow` 前必须先写入目标 `workflow_runs` / `writer_runs` 父行；写入失败返回 `WORKFLOW_ADMISSION_FAILED` 且不得启动 worker，避免 Pi runtime 后续写 `workflow_events` / `writer_drafts` 时依赖缺失父行或伪造 queued success。
- `GET /v1/writer-runs/{runId}` 在 SaaS Postgres backend 配置后必须从持久化 `writer_runs` 读取 public run status，不能依赖 Go 进程内存作为恢复真相源；读侧仍按 `X-Tenant-Id` 隔离并只返回公开 metadata。
- Pi Writer Runtime 的 DB-backed activity 写入 `writer.run.started`、`writer.draft.saved`、`writer.run.completed` 和 `writer.run.failed` 到 `workflow_events`，供 Go API replay 读侧恢复 stream。
- Pi Writer Runtime 的 DB-backed activity 同步更新 `writer_runs` / `workflow_runs` 状态：started 后置为 `running`，成功后置为 `completed` 并记录 `draft_id` result，失败后置为 `failed` 并记录稳定错误 code/message；状态回写不得包含 credential、prompt 或明文正文，并且必须验证 admission 父行确实存在，未命中 `writer_runs` 或 `workflow_runs` 时以 `WORKFLOW_RUN_NOT_FOUND` 显式失败。
- 当 Pi worker 配置了 `DATABASE_URL` 但缺少 `LLM_CREDENTIAL_ENCRYPTION_KEY` 时，仍必须使用 DB-backed activity path 记录 `writer.run.started`、failed `llm_activity`、`error` trace、`writer.run.failed` 和 failed run status；credential 解密以 `LLM_CREDENTIAL_KEY_UNCONFIGURED` 显式失败，不回退到无 DB 写入的基础 activity。

不要让浏览器直接连接 Python worker。

## Human-in-the-loop

以下步骤需要用户采用：

- archive candidate -> canon archive。
- graph bond candidate -> relationship/plot_thread。
- worldline candidate event -> canon/saved path。
- writer draft -> manuscript。
- reviewer suggestion -> applied revision。

Agent 只生成 candidate，除非用户明确配置 auto-adopt policy。

## 旧模块映射

| 旧模块 | 新位置 |
|---|---|
| `llm_router.py` | `mirofish_agents.llm.router` |
| `novel_seed_analyzer.py` | `seed.activities` |
| `sequential_reader.py` | `seed.sequential_reader` |
| `story_ontology_generator.py` | `seed.ontology` |
| `character_agent_profile_generator.py` | `seed.profile_generator` |
| `graph_builder.py` | `graph.workflows` + `graph.builder` |
| `assets/ingestion_agent` | `assets.ingestion_agent` |
| `worldline_prepare_service.py` | `worldline.prepare` |
| `worldline_engine.py` | `worldline.workflows` + `worldline.director` |
| `writer_agent/orchestrator.py` | `writer.orchestrator` |
| `writer_agent/agent_loop.py` | `writer.agent_loop` |
| `writer_agent/tool_executors.py` | `writer.tools` |

## 验收清单

- 每个 Agent 调用都有 tenant/project/run context。
- LLM 未绑定显式失败。
- trace 可按 run 查询。
- tool call 有权限检查。
- worker 崩溃后 workflow 可恢复。
- writer token stream 可断线恢复。
- candidate/adopt 边界清晰。
- Agent Runtime 不暴露公网。
