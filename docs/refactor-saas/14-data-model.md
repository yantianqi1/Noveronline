# 14. Data Model

更新时间：`2026-07-07`

## 目标

新数据模型以 Postgres 为统一真相源，覆盖当前 SQLite 统一库和 legacy artifact 的全部业务语义，并支持多租户、多人协作、长任务、Agent trace、向量检索和对象存储。

## 全局规则

- 租户业务表必须有 `tenant_id`。
- 项目级表必须有 `project_id`。
- 长文本和大文件进 object storage，DB 存引用。
- JSONB 用于半结构化 payload，但可查询核心字段必须列化。
- RLS 默认开启。
- 所有写操作记录 `created_at` / `updated_at`。
- 关键采用/删除/权限变更写 audit log。

## Core SaaS Tables

```text
users
tenants
tenant_memberships
project_members
projects
user_preferences
audit_logs
usage_events
resource_locks
```

Wave 2 已新增 `/v1/me` 的 Go auth reader seam、DB-backed membership read side、Go HTTP RBAC seam、W2-S4c signed HTTP actor subject resolver seam 和 W2-S4d 首批 project-scoped read RBAC expansion，未新增 schema。该 endpoint 的数据源是既有 `users`、`tenants`、`tenant_memberships`、`projects` 和 `project_members`：返回 current user public metadata、active tenant membership summaries，以及 active project membership summaries。未配置 reader 时返回 `AUTH_BACKEND_UNCONFIGURED`，不会从 `X-Tenant-Id`、body 或 route params 伪造 tenant/project membership。配置 `DATABASE_URL` 时，`auth.SQLReader` 按 current `user_id` 读取 active user public columns、active tenant memberships joined active tenants，以及该用户 active tenant memberships 可访问的 active projects；只有 active `project_members` row 才能覆盖项目 role，否则继承 tenant role。这个跨 tenant 查询只用于 current-user membership discovery，不能扩展成普通业务表 read bypass。W2-S4a/W2-S4b/W2-S4d 的 `auth.Authorizer` 直接消费这份 resolved active project summary：project read / writer run / trace full access 不再 OR 原始 tenant role，避免 inactive/blank project override、project-level viewer/analyst/writer override 或缺 matching project row 时仍通过 writer admission、full trace read 或 project-scoped metadata read。W2-S4d 新增的 readiness/source/assets/worldline/character/story graph/LLM/manuscript project-scoped reads，包括 `llm_module_bindings` resolution 公开 metadata，必须在读取业务表或解析 binding 前通过 `project_read`；LLM module binding mutation 仍只看 active tenant owner/admin。`trace_full_access` 只允许 matching active project role `project_owner`、`owner`、`admin` 或 `editor`。W2-S4c 的 signed Bearer / `mirofish_session` resolver 不写入数据库，不新增 session table，也不把 `MIROFISH_AUTH_SESSION_SECRET`、token 或 cookie material 存入业务表；它只在 HTTP 边界把 actor subject 转成当前 request context，后续 membership truth source 仍是 `auth.SQLReader`。W2-S4d 同样不新增数据表或权限表；route permission matrix 仍在 HTTP 层组合既有 resolved memberships。完整 session persistence、refresh/revocation、JWT claim schema、audit expansion 和持久化 permission matrix 仍属后续 Auth/production hardening。query/scan/rows/close failure 稳定为 `AUTH_LOOKUP_FAILED`，不得公开 prompt/body/content、API key、encrypted credential、`credential_ref`、object key、draft、manuscript 或底层 driver 文本。

## Project / File Tables

```text
projects
source_files
project_text_artifacts
project_settings
project_import_reports
```

`project_settings` 承载：

- reviewer rules。
- worldline config。
- default writer preset。
- analysis options。

但查询频繁或需版本化的数据不应长期塞 settings JSON。

当前 `source_files` admission/read/object-upload/complete/Seed validation path 只把 `object_key` 作为内部 worker/object-storage handoff metadata 使用。Go `sourcefiles.SQLStore` 在 queryer 支持时通过 tenant-context-aware path 执行 create、object lookup、complete、list 和 Seed validation；真实 `SQLDBQueryer` 会在 transaction 中调用 `app_set_tenant_context` 后再读写 RLS-protected `source_files`。source upload admission 与 Python parse path 使用同一类 MIME 边界，只接受 `text/plain`、`text/markdown`、`text/x-markdown`、`application/x-markdown` 和 `application/pdf`，并会忽略 `; charset=...` 参数后再判断；HTTP handler 会在调用 store 前拒绝 unsupported MIME，SQL store 也会在 DB insert 前拒绝，返回稳定 `VALIDATION_FAILED` 而不创建 pending source row。tenant-scoped rows close / transaction commit failure 会稳定为 source-file public error，scan failure 会 abort tenant-scoped rows/transaction，避免 upload admission 或 completion 在 app-role/RLS live path 上留下 partial state。`PUT /v1/uploads/{uploadId}/object` 会用 tenant/upload scope 从 `source_files` 查 internal object metadata 和当前 `parse_status`，只允许 `pending` row 进入 object writer；`uploaded`、`parsing`、`parsed`、`failed`、`cancelled` 或未知状态返回稳定 `SOURCE_FILE_UPLOAD_NOT_WRITABLE` / HTTP `409 Conflict`，避免 complete/Seed admission/parse 后的 source object 被覆盖。允许写入时，object writer 会校验上传 body 的 exact size 和 SHA-256 后写 MinIO/S3-compatible storage；Next `/overview` browser file picker 通过 typed Web API client 调用该写路径，但 public response 仍只显示 upload status，不把 `object_key`、presigned URL、raw content 或 object credentials 放入公开响应。配置 object verifier 时，complete path 会在 update 前以 checksum mode 读取 object metadata，比对对象 `Size` 与 admission `size_bytes`，并要求 MinIO/S3-compatible checksum/user/object metadata 中存在匹配 admission `sha256` 的 sha256 证据；对象存在但 size/hash 不一致或缺少 hash 证据时不得把 `parse_status` 标为 `uploaded`。Seed start 必须先有配置好的 source-file backend 并成功验证 tenant/project/upload scope；缺 source backend 时返回 `SOURCE_FILE_BACKEND_UNCONFIGURED`，不创建 queued run，不启动 Temporal，也不产生缺 source metadata 的 workflow shell。Seed workflow DB admission 会在创建 queued `workflow_runs` / `workflow_events` 之前，以 tenant/project/upload scope 把 `source_files.parse_status` 从 `uploaded` 推进为 `parsing`；没有命中 uploaded source row 时返回 `SOURCE_FILE_NOT_UPLOADED`，不创建 queued run，不启动 Temporal。`SQLSeedAdmissionStore` 在 queryer 支持时通过 tenant-context SQL execer 执行 admission 和 Temporal start failure compensation；真实 `sqlDBWriterAdmissionExecer` 会在同一 transaction 中调用 `app_set_tenant_context(tenant_id, project_id, false)` 后再写 RLS-protected `source_files`、`workflow_runs` 和 `workflow_events`，避免 app-role live path 只依赖 WHERE 条件而没有 session context。`TemporalSeedRunStarter` 缺 admission store 时同样返回 `WORKFLOW_BACKEND_UNCONFIGURED`，不会绕过 `source_files` parse-status / `workflow_runs` / `workflow_events` admission 直接启动 Temporal。admission 成功但 Temporal start 失败时，DB-backed compensation 会把同 tenant/project/run 的 `workflow_runs` 从 `queued` 标为 `failed`，写入稳定 `WORKFLOW_FAILED` public error metadata 和 sanitized `workflow.failed` event，并把同 tenant/project/upload 的 `source_files.parse_status` 从 `parsing` 释放回 `uploaded`，避免没有 Temporal worker 的 run/source 停在 queued/parsing。Python `parse_file_activity` 在 DB-backed source status writer 可用时，会在成功写入 extracted text artifact 后把 tenant/project/source_file scoped row 从 `parsing` 标为 `parsed`，在 parse activity 自身失败时尝试把仍为 `parsing` 的 row 标为 `failed`；未命中 `parsing` row 或普通 source status SQL/driver failure 会 rollback 并返回稳定 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED`，不透传底层文本，也不覆盖 cancelled/parsed/failed 等并发状态。Parse completed workflow event 只在 source row 成功标为 `parsed` 后写入；status 更新失败时写 sanitized parse failed event，避免公开 event replay 出现 completed event 与 failed activity result 不一致。Parse failure event 也只在 source row 成功标为 `failed` 后写入原始稳定 parse 错误；如果 failed-status 更新失败，event 与 activity result 都使用同一个 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED` code/message。普通 admission SQL/RowsAffected error 返回固定 `WORKFLOW_ADMISSION_FAILED` public message，不透传底层 driver/storage 文本；Temporal start failure compensation SQL/RowsAffected error 也只返回稳定 public message，不公开底层 exception。Go `sourcefiles.SQLStore` 对 create/complete/list/validate 的普通 SQL query、scan 和 rows error，以及 object verifier 的普通 storage exception，都会返回稳定 `SOURCE_FILE_CREATE_FAILED` / `SOURCE_FILE_COMPLETE_FAILED` / `SOURCE_FILE_QUERY_FAILED` / `SOURCE_FILE_STORAGE_VERIFY_FAILED` public message；`NOT_FOUND`、`SOURCE_FILE_NOT_UPLOADED` 和已结构化 object verifier `AppError` 继续保留原 code/message。Go HTTP response boundary 也会对 source file store error code 重新映射固定 public message，避免替换 store 或 injected store 的不可信 message 绕过 store 层清洗。底层 driver/storage exception 中的 prompt、API key、`credential_ref`、object key、hash metadata 或 source path 不得进入 HTTP response、Seed start validation failure 或公开 workflow metadata。

2026-07-07 live Go source upload/complete/admission harness 已验证同一 app-role/RLS connection path 下 `source_files` metadata admission、内部 object metadata lookup、MinIO object write、object verifier complete、Seed source validation 和 workflow admission 能连续执行。该验证补充了一个重要 rows lifecycle 约束：tenant-scoped single-row scan 应在 close/commit 前读取 `rows.Err()`，close/commit 成功后不得再次把 driver 的 post-close `context canceled` 当作业务 query failure；真实 close/commit failure 仍必须稳定收敛为 source-file public error。

Project Overview aggregate 不是独立真相源表，而是 Go read side 在 app-role tenant context 下按当前 tenant/project 即时聚合 public metadata。`GET /v1/projects/{projectId}/overview` 只可读取 `source_files` count、Seed `workflow_runs` count/active workflow metadata、latest failed `workflow_runs` public summary（run id、workflow type、error code、updated at）、最新 `project_readiness_snapshots` public counts、enabled `assets` count、最新 `story_graph_snapshots` node/edge counts、`worldline_sessions` / `worldline_events` counts、`character_interaction_sessions` count、`writer_runs` count、`llm_activity` count、`usage_events.usage_type = llm_tokens` token sum，以及 LLM configuration public diagnostics：enabled `llm_channels` count、enabled channel `last_sync_status` / `last_sync_at` model-sync health counts（ok / failed / pending / latest sync at）、指向 enabled channel 且存在 model 的 distinct `llm_module_bindings` count、核心创作 module missing count。核心创作 module 当前固定为 `writer_composer`、`writer_reviewer`、`sequential_reading`、`anchor_point_summary`、`narrative_archives`、`asset_ingestion`、`style_extractor`、`graph_bond_generator`、`worldline_director`。该 read side 不得选择 `source_files.object_key`、asset `content_text`、`global_search_index.body`、graph evidence `snippet`、worldline/character body fields、writer `instruction` / `options_jsonb` / draft/manuscript body、`workflow_runs.error_message`、LLM prompt/response、credential/API key、encrypted credential、`credential_ref`、channel/model/provider/base URL 详情；model-sync health 不触发 provider call，也不公开 channel/provider/base URL；普通 query/scan/rows failure 稳定为 `PROJECT_OVERVIEW_QUERY_FAILED`。

## Seed / Canon Tables

```text
text_segments
reading_passes
reading_segment_notes
entities
entity_aliases
entity_labels
entity_evidence
relationships
relationship_events
character_events
world_events
plot_threads
thread_lifecycle
world_rule_evidence
consistency_notes
narrative_arcs
volume_summaries
segment_summaries
seed_analysis_snapshots
project_readiness_snapshots
```

Python Seed parse/segment 阶段的失败 result 和 persisted workflow event 只属于公开 workflow metadata，不是诊断日志。对象存储、artifact writer、segment writer、TXT/Markdown decoder 或 PDF text extraction 的底层 exception 文本不得持久化到这些公开字段；`SOURCE_FILE_OBJECT_READ_FAILED`、`FILE_PARSE_DECODE_FAILED`、`TEXT_ARTIFACT_WRITE_FAILED`、`TEXT_ARTIFACT_READ_FAILED`、`TEXT_ARTIFACT_DECODE_FAILED`、`TEXT_SEGMENT_WRITE_FAILED` 等失败只保留稳定 code/message，避免 object key、prompt/source/body 文本、PDF 原文、解析后正文、API key、`credential_ref`、draft 或 manuscript 从 runtime result/event 反向泄露。`application/pdf` 解析只把可提取文本写入私有 `extracted_text` object reference；扫描/OCR PDF 仍不属于当前可声明的解析能力。

`text_segments.metadata_jsonb.segmentation_strategy` 记录当前分段来源。中文章节标题或 Markdown English `Chapter ...` 标题命中的 segment 仍使用 `chapter_heading_or_single_document`，无章节标题的长文本会按 `paragraph_window` 分段写入多个有序 segment object refs。`text_segments` 和公开 activity result 仍只保存 segment id、order、offset、章节/标题猜测、摘要占位和 object ref metadata，不保存 segment raw content。

Target Postgres migration 现在也会为已存在的 `project_text_artifacts` 和 `text_segments` 表补齐 parse/segment upsert 所需的唯一索引：`idx_project_text_artifacts_upsert_unique` 覆盖 `(tenant_id, project_id, run_id, artifact_type, object_key)`，`idx_text_segments_upsert_unique` 覆盖 `(tenant_id, project_id, run_id, segment_order)`。这修复了 `CREATE TABLE IF NOT EXISTS` 遇到旧表时不会补表内 `UNIQUE` 约束的问题，保证 Python `PostgresTextArtifactWriter` / `PostgresTextSegmentWriter` 的 `ON CONFLICT` 在 live app-role DB 上可执行。

Python Seed parse/segment/sequential-reading/runtime-facts/global-aggregation/archive-candidates/index-assets/finalize DB writer 在 app-role / RLS Postgres path 下写公开 metadata、结构化 canon、私有 seed analysis snapshot、candidate archive assets/memories、Seed asset/search index、project readiness snapshot 或 admitted workflow status 前必须设置 tenant/project context。`PostgresWorkflowEventWriter`、`PostgresSeedWorkflowRunStatusWriter`、`PostgresTextArtifactWriter`、`PostgresTextSegmentWriter`、`PostgresReadingNotesWriter`、`PostgresRuntimeFactsWriter`、`PostgresSeedAnalysisWriter`、`PostgresArchiveCandidateWriter`、`PostgresSeedAssetIndexer` 与 `PostgresProjectReadinessUpdater` 分别写 `workflow_events`、`workflow_runs` public status、`project_text_artifacts`、`text_segments`、`reading_passes`、`reading_segment_notes`、Seed/Canon target tables、`seed_analysis_snapshots`、candidate `assets` / `archive_memories` / `archive_memory_events`、Seed `assets` / `global_search_index` 和 `project_readiness_snapshots` 前执行 `app_set_tenant_context(tenant_id, project_id, false)`；SQL execute 或 commit failure 要显式 rollback，并由 activity 层保持稳定 public failure。`PostgresSeedWorkflowRunStatusWriter` 只能更新同一 tenant/project/run 的 `workflow_runs.workflow_type = seed_pipeline` parent row，worker 接受 run 时可标记 `running` 且不写 result/error，completed result 只保留 stage、readiness snapshot id 和 ready counts，failed status 只保留稳定 public error code/message；普通 DB/driver exception 稳定为 `WORKFLOW_STATUS_WRITE_FAILED`，缺 admission parent 稳定为 `WORKFLOW_RUN_NOT_FOUND`。`PostgresArchiveCandidateWriter` 的普通 DB/driver exception 稳定为 `ARCHIVE_CANDIDATE_WRITE_FAILED` / `archive candidate write failed`，`PostgresProjectReadinessUpdater` 的普通 DB/driver exception 稳定为 `PROJECT_READINESS_UPDATE_FAILED` / `project readiness update failed`，不公开底层 SQL/driver 文本。该约束只覆盖 public metadata/reference/canon fact/private snapshot/candidate archive/asset projection/readiness snapshot/workflow status 写入，不允许把 extracted text、segment raw content、seed analysis body、archive candidate body、memory body、search document body、readiness report body、prompt、credential、draft 或 manuscript 放进公开返回 payload。

`project_readiness_snapshots` 是 finalize stage 的公开 metadata snapshot 表，只保存同一 tenant/project/run 的 ready asset/entity/relationship/world-rule counts 与 metadata，不保存 readiness report 正文。`PostgresProjectReadinessUpdater` 在 `DATABASE_URL` 配置时由 `finalize_seed_activity` 默认装配，从 Seed asset projection 与 structured canon tables 计数并 upsert snapshot；缺 DB/updater 时仍 fail closed，不伪造 ready 状态。Go `projectreadiness.SQLReader` 在 `DATABASE_URL` 配置时通过 app-role tenant context 读取当前 tenant/project 最新 snapshot，并且只返回 snapshot id、project/run id、ready counts 和 timestamps；普通 query/scan/rows failure 稳定为 `PROJECT_READINESS_QUERY_FAILED`，不公开底层 SQL/driver 文本或 readiness report body。

`PostgresSeedAggregateSource` 是 global aggregation 的 DB-backed read side，也必须在读取 `segment_summaries`、`entities` 和 `relationships` counts 前设置 app-role tenant context。普通 DB/driver query exception 稳定为 `SEED_AGGREGATE_SOURCE_QUERY_FAILED` / `seed aggregate source query failed`，不得把底层 SQL/driver 文本、prompt、API key、`credential_ref`、raw text 或 evidence 传给 provider-facing result、workflow event 或公开错误。

`PostgresEntityResolutionSnapshotWriter` 是 entity resolution 的 DB-backed private snapshot writer，也必须在写 `seed_entity_resolution_snapshots` 前设置 app-role tenant context。普通 DB/driver write exception 稳定为 `ENTITY_RESOLUTION_SNAPSHOT_WRITE_FAILED` / `entity resolution snapshot write failed`，不得把底层 SQL/driver 文本、resolution body、prompt、API key、`credential_ref` 或 raw text 传给 provider-facing result、workflow event 或公开错误。

Go `SQLSeedRunReader` 是 Seed run list/detail 的 DB-backed read side。配置 `DATABASE_URL` 时，它会在支持的 queryer 上通过 app-role tenant context 读取 `workflow_runs.workflow_type = seed_pipeline` 的 public columns；普通 query、scan 或 rows iteration failure 稳定为 `WORKFLOW_QUERY_FAILED` / `seed run query failed`，不公开底层 driver 文本、prompt、API key、`credential_ref`、object key、source/raw text、draft 或 manuscript。

Go `SQLWorkflowEventReader` 是 Seed run event replay 和通用 workflow event replay 的 DB-backed read side。配置 `DATABASE_URL` 时，它会在支持的 queryer 上通过 app-role tenant context 读取 `workflow_events` public columns；普通 query、scan 或 rows iteration failure 稳定为 `WORKFLOW_EVENT_QUERY_FAILED` / `workflow event query failed`，不公开底层 driver 文本、prompt、API key、`credential_ref`、object key、source/raw text、draft 或 manuscript。event payload 仍会递归移除 credential/prompt/body/content/draft/manuscript/source object key/artifact object key/segment object key 等高风险字段。

旧 `project_artifacts` 中仍有价值的 payload 迁移到：

- structured tables。
- `agent_trace_events`。
- `project_text_artifacts`。
- `legacy_artifact_imports` 审计表。

## Seed Ontology Snapshots

`seed_ontology_snapshots` 是 `story_ontology` stage 的私有 DB snapshot 表，保存 schema-valid ontology JSON 和类型 counts。公开 workflow event、Seed run event replay 和后续 handoff 只能使用 snapshot id、model id 与 counts，不能返回 `ontology_jsonb` 正文。

```text
seed_ontology_snapshots
  tenant_id
  seed_ontology_snapshot_id
  project_id
  run_id
  module_key
  model_id
  ontology_jsonb
  entity_type_count
  relationship_type_count
  world_rule_type_count
  metadata_jsonb
  created_at
  updated_at
```

表必须启用 tenant RLS，并通过 `(tenant_id, project_id, run_id, module_key)` 保持同一 Seed run / module 的 upsert 幂等性。`PostgresOntologySnapshotWriter` 写入前设置 `app_set_tenant_context`，并清洗 prompt/API key/`credential_ref`/raw content 等高风险字段。

## Seed Entity Resolution Snapshots

`seed_entity_resolution_snapshots` 是 `entity_resolution` stage 的私有 DB snapshot 表，保存 schema-valid entity resolution JSON 和 public counts。公开 workflow event、Seed run event replay 和后续 handoff 只能使用 snapshot id、model id 与 merged/alias/conflict counts，不能返回 `resolution_jsonb` 正文。

```text
seed_entity_resolution_snapshots
  tenant_id
  seed_entity_resolution_snapshot_id
  project_id
  run_id
  module_key
  model_id
  resolution_jsonb
  merged_entity_count
  alias_count
  conflict_count
  metadata_jsonb
  created_at
  updated_at
```

表必须启用 tenant RLS，并通过 `(tenant_id, project_id, run_id, module_key)` 保持同一 Seed run / module 的 upsert 幂等性。`PostgresEntityResolutionSnapshotWriter` 写入前设置 `app_set_tenant_context`，并清洗 prompt/API key/`credential_ref`/raw content 等高风险字段；普通 DB/driver failure 稳定为 `ENTITY_RESOLUTION_SNAPSHOT_WRITE_FAILED`。

## Asset Tables

```text
assets
asset_links
asset_versions
asset_embeddings
asset_collections
asset_collection_items
archive_memories
archive_memory_events
classification_rules
global_search_index
```

当前 Phase 5 schema baseline 已在 `infra/postgres/migrations/0001_core_saas.sql` 中创建 `assets`、`asset_versions`、`asset_collections`、`asset_collection_items`、`archive_memories`、`archive_memory_events` 与 `global_search_index`，并补充 tenant RLS、项目/source/type 查询索引、collection/version 查询索引和 Seed projection / archive memory read/review side 所需唯一键。`PostgresSeedAssetIndexer` 目前只从 Seed canon 表投射 lifecycle=`seed` 的资产和 keyword search 文档；`PostgresAssetReindexer` 已可在 DB-backed `AssetReindexWorkflow` 中从 tenant/project scoped `assets` 重建 project/keyword `global_search_index` 的 `asset` 文档，公开 result/event 只暴露 batch/count metadata 与 `embedding_count = 0`；Go Asset Search read side 会在 app-role/RLS path 下设置 tenant context 后读取 `global_search_index`、`asset_versions`、`asset_collections` 和 `asset_collection_items`，公开返回 sanitized search document metadata 以及 public `version` summary / `collections` refs；`LLMFacilityArchiveCandidateRunner` / `PostgresArchiveCandidateWriter` 已可通过 `narrative_archives` module binding 将 schema-valid archive entity 与 memory 输出持久化为 candidate `assets` / `archive_memories` / `archive_memory_events`，writer 在 app-role/RLS path 下先设置 tenant context，失败时 rollback 并只返回稳定 write failure，公开 workflow result/event 只暴露 batch/count/model metadata；`archive_memories` / `archive_memory_events` 已有 Go read API 和显式 adopt/reject mutation，会写 review event 与 audit log；`asset_embeddings` 与完整 hybrid/vector search 仍待后续阶段落地。

Phase 5 Go HTTP request decode failure 同样是公开错误边界：asset create/search/bulk/adoption/patch、archive memory review、asset ingestion、style extraction、asset reindex、story graph build/bond generation 写入口的无效 JSON 或类型错误只返回稳定 `VALIDATION_FAILED` message 和空 details，不回显 decoder 字符串、unknown field 名称、Go struct field 名称，或 `api_key` / prompt / `credential_ref` / draft / manuscript / raw body/content 等敏感词。

`assets` 字段：

```text
tenant_id
asset_id
project_id nullable
scope = tenant | project | system
asset_type
category
lifecycle
title
summary
content_text
payload_jsonb
tags_jsonb
source_kind
source_ref
enabled
pinned
created_by
created_at
updated_at
```

archive-specific 字段可以：

1. 保持在 assets 宽表。
2. 或拆到 `archive_entities` 扩展表。

推荐 SaaS 目标：拆扩展表，避免 assets 宽表无限膨胀。

```text
archive_entities
  tenant_id
  asset_id
  entity_id
  entity_name
  entity_type
  agent_kind
  importance_tier
  core_drive
  surface_mask
  hidden_tension
  relationship_summary
  agent_behavior_hint
  template_key
  template_payload_jsonb
```

## Story Graph Tables

```text
story_graph_snapshots
story_graph_nodes
story_graph_edges
story_graph_node_aliases
story_graph_node_labels
story_graph_evidence
story_graph_layouts
story_graph_clusters
```

旧 `graph_meta` / `graph_nodes` / `graph_edges` / `graph_evidence` 映射到这些表。

P5 skeleton 已在 `infra/postgres/migrations/0001_core_saas.sql` 落地这些目标表的 tenant/project scoped schema、RLS、grants 和基础索引。当前 Go read side 公开 `story_graph_snapshots` 的 sanitized current snapshot metadata：`graph_id`、`project_id`、`version`、`status`、`build_run_id`、`source_version_hash`、`node_count`、`edge_count`、`created_at`、`updated_at`；同时公开 current graph 的 viewport node/edge summaries、单节点/单边 public detail、public evidence source metadata、sanitized layout payload 和 sanitized cluster summaries。节点/边/layout/cluster response 会递归清洗 prompt/body/content/raw text/snippet/credential 字段；默认 evidence response 不选择也不返回 `snippet`，只有 `include_full=true` 且通过 Story Graph evidence access checker 后才会读取并返回 `snippet`。Python `PostgresStoryGraphBuilder` 已可在 `DATABASE_URL` 配置下从 `entities`、`relationships`、`plot_threads`、`world_rule_evidence` 和 sanitized `assets` metadata 写入 snapshot、nodes、edges、public evidence metadata、layout 和 clusters；`PostgresWorkflowRunStatusWriter` 会同步更新 `workflow_runs.status/progress/result_jsonb/error_code/error_message`，result 只包含 graph id/counts。写入公开 payload 不包含 snippet/raw text/prompt/content_text/credential 字段。语义合并/布局增强和 legacy graph import 仍 pending。

## Worldline Tables

```text
worldline_sessions
worldline_preparations
worldline_prepared_agents
worldline_variables
worldline_events
worldline_event_adoptions
worldline_saved_paths
worldline_agent_registry
worldline_agent_state_snapshots
worldline_agent_actions
worldline_agent_dialogues
worldline_agent_memories
worldline_relation_events
```

当前 baseline 已在 `infra/postgres/migrations/0001_core_saas.sql` 落地 `worldline_sessions`、`worldline_preparations`、`worldline_prepared_agents`、`worldline_variables`、`worldline_events`、`worldline_event_adoptions` 和 `worldline_saved_paths` 的第一批目标表。`worldline_sessions` 用于 Phase 6 session admission/read side，字段只包含 `tenant_id`、`project_id`、`session_id`、`run_id`、status/lifecycle、`goal_summary`、optional `anchor_path_id`、created_by 和 timestamps；Go SQL store 在 DB 配置下会先写 tenant/project scoped `workflow_runs`、`worldline_sessions` 和 sanitized `workflow.queued` event，再返回 queued run metadata，不启动 runtime、不生成 candidate/saved-path 内容。`POST /v1/worldline-sessions/{sessionId}/steps` 当前不新增专用 worldline step 表；DB-backed admission 只通过 tenant-scoped `worldline_sessions` 校验 session，写 `workflow_runs.workflow_type = worldline_step` 和 sanitized `workflow.queued` event，公开 payload 只含 run/project/session/workflow/status metadata，不写 `worldline_saved_paths`、canon、draft 或 manuscript。Python `LLMFacilityWorldlineStepRunner` 的最小真实执行路径会在 DB/key/provider 都配置后写入 `worldline_events.status = candidate` / `lifecycle = simulation` 的 public metadata：step、title、summary、kind、confidence、involved agent ids、state change summary、source run 和 actor；runner 会在解析 binding、解密 credential 或调用 provider 前先验证 `context.run_id` 是有效 UUID，非法 run id 会以 `VALIDATION_FAILED` fail closed，不能产生无同-run 关联的 telemetry 或 candidate event；candidate insert 使用 `INSERT ... SELECT ... FROM worldline_sessions` 校验 tenant/project/session admission，不能对未 admission 或跨租户/项目 session 写事件，并会在 `WORLDLINE_SESSION_NOT_FOUND` 显式失败时 rollback；普通 DB/driver insert 异常也会 rollback 并返回稳定 `WORLDLINE_CANDIDATE_EVENT_WRITE_FAILED`，不会把底层异常文本、prompt、API key 或 `credential_ref` 透传到公开错误；runner 侧也会把非规范 candidate writer 普通异常收敛为同一稳定错误，不能误报为 provider failure；`source_run_id` 使用规范化后的 UUID run id，不能静默写成 NULL。同一 provider 调用现在也写入共享 LLM telemetry 表：completed/failed `llm_activity` 按 tenant/project/run/module/channel/model 记录，provider token usage 存入 `usage_events`；成功路径下 Postgres writer 会用同一 connection/transaction/commit 写 completed activity 和可选 usage event，避免只落 activity 或只落 usage 的半成功状态；completed transaction 内任一 insert 失败会显式 rollback 并返回 `LLM_TELEMETRY_WRITE_FAILED`，不写 candidate event；失败路径不写 usage event；单条 `llm_activity` 或 `usage_events` 写入失败也会 rollback 当前 connection 后返回稳定 `LLM_TELEMETRY_WRITE_FAILED`，不留下未清理事务。即使 telemetry writer 是测试注入、非 Postgres 实现或 driver wrapper，completed/failed telemetry 普通异常也必须被收敛为稳定 `LLM_TELEMETRY_WRITE_FAILED`，且不得透传底层异常文本或继续写 candidate event。如果 completed telemetry 已成功但后续 candidate metadata persistence 因 session/admission/scope 或非规范 writer 异常失败，runner 返回 candidate persistence 错误，但不会再追加 failed `llm_activity`，让同一 `run_id` 的 Activity/Usage 继续准确表示 provider call 已完成。成功后还会追加 sanitized `worldline.stage.completed` 到 `workflow_events` 并更新 `workflow_runs` completed public status，payload 只含 session/mode/step/model/count。它不新增 event body 表，不持久化 prompt/response/source text/credential，也不自动采用 canon 或保存 path。`GET /v1/worldline-sessions/{sessionId}/timeline` 当前从 tenant-scoped `workflow_events` join `worldline_sessions` 读取 public timeline metadata，只公开 event id/session/run/project/type/sequence/status/lifecycle/title/summary/kind/timestamp，不引入或读取 private worldline event body 表。`worldline_variables` 用于 author variable injection 的 metadata-only 写路径，字段只包含 `tenant_id`、`project_id`、`session_id`、`variable_id`、name/description/impact_axis、locked/source、created_by 和 timestamps；Go SQL store 通过 tenant-scoped `worldline_sessions` join 校验 admitted session，写入变量并追加 sanitized `worldline.variable.injected` workflow event，不启动 runtime、不重算 world state、不生成 candidate/canon event。`worldline_events` 用于 candidate/canon event read side 的 public metadata，字段只包含 tenant/project/session/event id、step、title/summary、kind、status/lifecycle、confidence、involved agent ids、state change summary、source run、created_by 和 timestamps；Go SQL reader 通过 tenant-scoped `worldline_sessions` join 校验 session，只返回 metadata，不存放或返回 event body、source text、prompt/response、draft/manuscript 或 credential 字段；Go SQL mutation store 只允许显式作者动作更新 tenant-scoped `status = candidate` 事件的 `title`、`summary` 和 `kind`，并追加 sanitized `worldline.event.updated` workflow event。`worldline_event_adoptions` 用于显式 candidate -> canon metadata adoption，字段只包含 `tenant_id`、`project_id`、`session_id`、`event_id`、`adoption_id`、from/to status、public note、adopted_by 和 timestamp；Go SQL store 只更新 tenant-scoped `worldline_events.status = candidate` 为 `status = canon` / `lifecycle = canon_reference`，写 adoption row，并追加 sanitized `worldline.event.adopted` workflow event，不启动 runtime、不生成 event、不写正文或 canon body。`worldline_preparations` 用于 prepare admission/read side，字段只包含 `tenant_id`、`project_id`、`prepare_id`、`run_id`、status/lifecycle、`goal_summary`、optional `anchor_path_id`、created_by 和 timestamps；Go SQL store 在 DB 配置下写 `workflow_runs`、`worldline_preparations` 和 sanitized `workflow.queued` event，不启动 prepare runtime、不生成 agents/timeline/candidates。`worldline_prepared_agents` 是 metadata-only prepared agent read side，字段只包含 `tenant_id`、`project_id`、`prepare_id`、`agent_id`、display name、role、status、optional `source_asset_id`、summary 和 timestamps；没有 private body/prompt/action/dialogue 字段。`worldline_saved_paths` 用于 Writer 引用 picker 和 metadata-only saved-path producer：字段只包含 `tenant_id`、`project_id`、`session_id`、`path_id`、title/summary/lifecycle、`selected_event_ids_jsonb`、optional `writer_instruction`、created_by 和 timestamps；Go SQL store 通过 tenant-scoped `worldline_sessions` 与同 session 的 `worldline_events` 校验显式选择的 event id，写入 path 并追加 sanitized `worldline.saved_path.created` workflow event，不启动 runtime、不采用 canon。以上表已启用 tenant RLS、基础 project/session/run/prepare/variable/event/adoption/path 索引和 `mirofish_app` grant；Go/Python read/write side 只处理 public metadata，不选择或返回 `body_text`、`content_text`、prompt/response 或 credential 字段。Python DB-backed Worldline writer/loader 和 LLM resolver/credential provider 在 app-role 连接上先设置 `app_set_tenant_context`，Go Activity/Usage SQL read side 也在 read-only transaction 中设置 tenant context；本地 provider/live Postgres app-role E2E 已验证同一 `run_id` 串联 `worldline_director` binding、credential decrypt、provider JSON、LLM telemetry/usage、candidate event 和 workflow event/status。prepare runtime、agent source loader、richer director tools、外部 provider/cluster E2E 和 Character Console runtime 仍在 Phase 6 后续。

Worldline Python runtime 写 `workflow_events` 和更新 `workflow_runs` public status 时，DB/driver 异常必须 rollback 当前 connection，并只返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `WORKFLOW_STATUS_WRITE_FAILED` runtime error 文本；底层异常中的 prompt、API key 或 `credential_ref` 不得进入 public status、event payload 或 runtime failure message。
如果 workflow event insert 或 status update 未命中 admitted `workflow_runs.workflow_type = worldline_step` parent row，runtime 必须 rollback 后返回 `WORKFLOW_RUN_NOT_FOUND`，避免创建 orphan `workflow_events` 或把没有 admission 父行的 step 误记为 completed/failed。
Worldline Go HTTP request decode failure 同样是公开错误边界：session/step/preparation/adoption/mutation/variable/saved-path 写入口的无效 JSON 或类型错误只返回稳定 `VALIDATION_FAILED` message 和空 details，不回显 decoder 字符串、unknown field 名称、Go struct field 名称，或 `api_key` / prompt / `credential_ref` / draft / manuscript 等敏感词。
当 `LLMFacilityWorldlineStepRunner` 已完成 provider/candidate path 但 activity 写 `worldline.stage.completed` 或 completed `workflow_runs` status 失败时，`worldline_step_activity` 必须把该 persistence failure 转成结构化 failed result：completed event 写入失败时不标记 completed status，并可把 run 标记为 failed；completed status 写入失败时不得把底层 writer exception 作为未结构化 activity crash 暴露。公开 result/status 仍只允许稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `WORKFLOW_STATUS_WRITE_FAILED` / `WORKFLOW_RUN_NOT_FOUND` code 和固定安全 message；activity 不得复用 writer exception message 中的后缀文本，因为其中可能包含 prompt、source text、API key 或 `credential_ref`。

Worldline source loader 不新增专用 source body 表。`options.source_refs` 只能是授权 source loader 的引用输入；未装配 loader 时 `LLMFacilityWorldlineStepRunner` 在任何 binding/credential/provider 调用前返回 `WORLDLINE_SOURCE_LOADER_UNCONFIGURED`，不写 `llm_activity`、`usage_events` 或 `worldline_events`。配置 `DATABASE_URL` 时，`PostgresWorldlineSourceLoader` 支持从 tenant/project scoped enabled `assets` 读取 title/summary/type/category public metadata，并从 tenant/project/session scoped `worldline_events` 读取 candidate/canon event title/summary/kind/status public metadata；它不选择 `assets.content_text`，也不读取 event body、prompt、credential、draft 或 manuscript 字段。DB/driver 异常只公开 `WORLDLINE_SOURCE_LOAD_FAILED` / `worldline source load failed`。若 `source_refs` 存在但解析结果为空，runner 返回 `WORLDLINE_SOURCE_NOT_FOUND` / `worldline source_refs did not resolve to public summaries`，并在 binding/credential/provider/telemetry/candidate 前停止。runner 只把 loader 返回的 sanitized public source summaries 放入 provider message；raw source text、prompt、credential、`source_text`、`content_text`、event body、draft 或 manuscript 仍不得进入公开 result、workflow event、candidate metadata 或 telemetry。

注意：

- 不恢复多分支主模型。
- 如果保留 `branch_id` 字段，只能作为兼容字段，默认 `current_world`。

## Character Console Tables

```text
character_interaction_sessions
character_interaction_turns
character_interaction_summaries
character_interaction_chapter_links
```

当前 baseline 已在 `infra/postgres/migrations/0001_core_saas.sql` 落地 `character_interaction_sessions` 与 `character_interaction_turns` 的第一批 metadata-only 表、tenant RLS、索引和 `mirofish_app` grant。`character_interaction_sessions` 字段只包含 tenant/project/interaction id、optional `worldline_session_id`、anchor type/id、POV agent id、mode/status、title/summary、public metadata、created_by 和 timestamps；它可以锚定 worldline session / saved path / event / scene / graph node 等 public metadata，但不自动采用 worldline candidate，不写 canon，不写 writer draft/manuscript。Go store 和 Postgres CHECK 约束都会校验 `anchor_type` 只允许空值、`worldline_session`、`worldline_event`、`saved_path`、`chapter`、`scene`、`graph_node`、`plot_thread`，`mode` 只允许 `first_person`、`director_assisted`、`dialogue`、`replay`，interaction list `status` filter 只允许空值、`active`、`saved`、`archived`，metadata status mutation 只允许 `active`、`saved`、`archived`，非法值返回 `VALIDATION_FAILED` 或被 DB 拒绝且不写入；读侧也会在返回 `metadata_jsonb` 前递归清洗高风险 key，避免历史或外部写入的 prompt/credential/body/source text/source material/candidate body/event body/draft/manuscript 字段透出；Go HTTP response boundary 会对 store 返回的 interaction record 再做同类清洗，防止替换 store 或测试注入路径绕过 SQL read side；query、scan 和 `rows.Err()` failure 都收敛为稳定 `CHARACTER_INTERACTION_QUERY_FAILED`，store 层 interaction/turn scan 分别使用固定 `character interaction query failed` / `character interaction turn query failed`，并在 scan failure 时 abort tenant-scoped rows / transaction，避免 write-returning scan error 后提交 partial metadata；HTTP 公开 message 固定为 `character interaction query failed`，避免底层 DB/store exception 文本泄露。Next Character Console shell 现在可通过 server action/form 创建这类 public metadata session，并通过 query state 显示真实 success/error，不伪造无 DB 成功；创建表单会读取 tenant/project scoped `worldline_sessions` public metadata，把真实 session 作为可选 anchor，下游缺 DB/backend 时只显示 `WORLDLINE_SESSION_BACKEND_UNCONFIGURED`。Next shell 也读取 tenant/project scoped `worldline_saved_paths` public metadata，把真实 saved path id/title/summary/lifecycle/selected event count 用于 anchor selector 和 anchor preview；缺 DB/backend 时只显示 `WORLDLINE_BACKEND_UNCONFIGURED`，不补假 path。Next shell 还读取 tenant/project scoped Story Graph viewport public node metadata，把 character/organization/location/plot_thread 的 node id/title/summary 作为 graph node anchor choices 和 anchor preview；缺 Graph backend 时只显示 `STORY_GRAPH_BACKEND_UNCONFIGURED` 或等价查询错误，不补假 graph node。当 URL/query 选择 `anchor_session_id` 时，Next shell 会读取同 session 的 `worldline_events` public metadata，把 candidate/canon event id/title/summary/kind/status 用于 `anchor_id` selector；没有 session 或读侧失败时不生成事件、不采用 canon、不保存 path。当 URL/query 选择 `prepare_id` 时，Next shell 还读取既有 `worldline_prepared_agents` public metadata，把真实 prepared agent id/name/role/status/summary 用于 POV selector 和 roster preview；没有 preparation 或读侧失败时不补假角色。Next shell 还通过 typed API client/server action 调用 `PATCH /v1/character-interactions/{interactionId}` 显式保存、归档或恢复 active interaction status，只更新 `character_interaction_sessions.status/updated_at` public metadata，不写 turns、worldline events、drafts 或 manuscripts。`character_interaction_turns` 字段只包含 tenant/project/interaction/turn id、turn_order、actor_type (`user` / `agent` / `director` / `system`)、actor id、turn kind、summary、public action/world-state-delta JSON、trace id、created_by 和 timestamp；Go store 和 Postgres CHECK 约束都会校验 `actor_type` 只允许 `user`、`agent`、`director`、`system`，`turn_kind` 只允许 `action`、`dialogue`、`thought`、`director_note`、`system_note`，非法值不会写入；读侧也会在返回 `action_jsonb` / `world_state_delta_jsonb` 前递归清洗高风险 key；HTTP append route 会先确认 parent interaction 存在于当前 tenant，再调用 turn append store，缺失、跨租户或无 backend 时不会写 turn metadata 或返回 fake created turn；DB-backed `ListTurns` 会先确认 parent interaction 存在于当前 tenant，再返回 public turn metadata，因此缺失或跨租户 interaction 不会被误读为空回放；Go HTTP response boundary 会在 append/detail/turn replay 响应中对 turn `action` 和 `world_state_delta` 再做同类清洗；当前 Go store 和 Next shell 只保存显式提交的 public metadata，不自动生成 agent reply，也不保存 `input_text` / `output_text` / prompt / response / body/content raw text / credential / draft / manuscript 字段。Next selected-interaction replay panel 从 detail API 读取同一 public metadata 和 turn list，不读取私密正文。`GET`/`POST`/`PATCH` API 均通过 header/path tenant/project/session/interaction context scoped 读写；无 DB/backend 时显式 `CHARACTER_INTERACTION_BACKEND_UNCONFIGURED`。Next typed client/server actions 已接入 runtime events pending 和 interaction -> Writer handoff admission：`GET /v1/character-interactions/{interactionId}/events` 仍只向真实 pending endpoint 请求并展示 `CHARACTER_CONSOLE_RUNTIME_PENDING` 或稳定错误；`POST /v1/character-interactions/{interactionId}/chapter-drafts` 会先读取 tenant-scoped interaction/public turns、解析 `writer_composer` LLM binding，并通过既有 `WriterStarter` 创建真实 `writer_run` admission，公开响应只含 `run_id` / `trace_id` / `workflow_type` / `status` metadata，不写 fake `draft_id`、Writer draft、manuscript 或 Character Console runtime event。Character Console dialogue runtime 仍是 Phase 6 后续。

Character Console HTTP error boundary 对 coded `NOT_FOUND` / `CHARACTER_INTERACTION_BACKEND_UNCONFIGURED` store error 使用固定安全文案，避免替换 store 或 alternate writer 的 error message 把 prompt、API key、`credential_ref`、draft/manuscript 文本带到公开 API。

Character Console create/append route 的 JSON decode validation error 不回显 decoder 原始错误详情，避免未知字段名中的 `api_key`、`prompt`、`credential_ref`、draft/manuscript 等敏感词进入公开 error details。

Character Console -> Writer handoff 只消费已保存的 public turn summary metadata。`POST /v1/character-interactions/{interactionId}/chapter-drafts` 在解析 `writer_composer` binding 或调用 `WriterStarter` 之前会检查 sanitized turn list；没有 turn，或所有 turn 的 public `summary` 都为空白时，返回 `CHARACTER_INTERACTION_TURNS_REQUIRED`，不会写 `writer_run`、draft、manuscript 或 Character Console runtime event。

Postgres baseline 还用 `(tenant_id, project_id, worldline_session_id)` 复合外键把 interaction 的 optional worldline session anchor 限定在同 tenant/project scope；删除 worldline session 时只把 `worldline_session_id` 置空，不清空 interaction 自身的 tenant/project。`character_interaction_turns` 也用 `(tenant_id, project_id, interaction_id)` 复合外键绑定到同 scope 的 `character_interaction_sessions`，避免绕过 Go store 的外部写入为同一 interaction 伪造跨项目 turn metadata。DB-backed Go Character Console store 在真实 `*sql.DB` queryer 上通过 `app_set_tenant_context` 设置 RLS tenant context 后再执行 read/write query；rows close / transaction commit failure 也会收敛为稳定 `CHARACTER_INTERACTION_QUERY_FAILED`，不把 driver text 暴露到公开 API。

这些表和 worldline 关联，但不直接混进 worldline event 表，避免互动草稿污染推演正典。

## Writer Tables

```text
chapters
chapter_versions
scenes
scene_versions
drafts
draft_events
manuscript_blocks
manuscript_exports
writer_presets
book_plans
book_run_events
outline_versions
forbidden_lexicon_entries
dedup_index
reviewer_issues
reviewer_rules
```

当前 SaaS baseline 已在 `infra/postgres/migrations/0001_core_saas.sql` 落地 `writer_runs`、`writer_drafts`、`draft_reviews`、`draft_review_issues` 和 `manuscript_blocks`。Pi Writer Runtime 只写 `writer_drafts.status = candidate` 的私有 draft content；draft -> manuscript 只能通过 `POST /v1/drafts/{draftId}/adoptions` 这类显式作者动作完成。DB-backed adoption store 在 app-role tenant context 下锁定 tenant-scoped candidate draft，内部把 `writer_drafts.content_text` 写入 `manuscript_blocks.content_text`，随后把 draft 标记为 `adopted` 并记录 `adopted_block_id`；公开 API 只返回 draft/block/project/status/order 等 metadata，不返回 draft/manuscript 正文、`content_text`、prompt/response、credential、object key 或 raw body/content。缺 backend、缺 candidate、已 adopted/rejected 或跨租户 draft 必须 fail closed，不得伪造 manuscript block。

`manuscript_blocks` 的公开读侧当前只开放 metadata。`GET /v1/projects/{projectId}/manuscript` 的 SQL reader 只选择 block id、project id、chapter/source draft id、block order、status、word count 和 timestamps，不选择 `content_text`。`GET /v1/projects/{projectId}/manuscript/export` 当前只生成 `metadata_manifest` readiness/manifest，聚合 block count、word count 和 block ids/order，不写 `manuscript_exports`、不返回 `exported_at` 或 artifact reference，也不返回正文。缺 DB/backend 或 query/scan/close failure 必须 fail closed，公开错误使用稳定 `MANUSCRIPT_*` code/message，不透出 driver exception、draft/manuscript 正文、prompt/provider response、credential、object key 或 raw body/content。

`draft_reviews` / `draft_review_issues` 是 Writer reviewer 的 public metadata/read side。`POST /v1/drafts/{draftId}/reviews` 要求 body 显式携带 `project_id`，先用该 project scope 解析 `writer_reviewer` LLM Facility binding，再 admission 真实 review workflow；DB-backed path 校验 draft 必须属于同一 tenant/project，写 `workflow_runs`、不含 note/body 的 sanitized `workflow.queued` event 和 `draft_reviews.status = queued` metadata。`draft_reviews.options_jsonb` 只保存 public options / `module_key`，不得保存 LLM routing snapshot、provider/base URL、channel/model id、settings 或 `credential_ref`。缺 project scope、缺 binding、缺 DB/backend 或缺 draft 都显式失败。当前 slice 不生成 fake issues，不调用旧 env fallback，不自动改写 draft，不采用 manuscript。`draft_review_issues` 通过 `(tenant_id, project_id, draft_id, review_id)` 复合外键绑定到同一 review/draft/project。`GET /v1/drafts/{draftId}/reviews` 只返回 review id/run id/draft id/project id/status/timestamps 和 issue severity/category/summary/suggestion/status public metadata；Go SQL reader 和 HTTP response boundary 都把 issue text 当作不可信 public metadata 清洗，不能返回 draft/manuscript 正文、`content_text`、prompt/provider response、API key、encrypted credential、`credential_ref`、object key 或 raw body/content。

旧 `chapter_content` / `chapter_meta` 可以合并为 `chapters + chapter_versions`，或继续拆分。目标文档推荐合并核心字段，历史进入 versions。

Writer start HTTP 边界会在调用 `WriterStarter` 前递归清洗用户提交的 `options`，移除 body-provided `tenant_id` / `project_id` 以及 credential/API key、prompt/response、body/content、source/material/raw payload、candidate/event body、draft 和 manuscript 字段；随后才补入服务端解析出的 `module_key` 与 internal `llm_resolution`。DB-backed Writer admission 还会在写入 `writer_runs.options_jsonb` 前执行同类 high-risk option 清洗，只保留 `module_key`、public ids、public turn summaries 等可审计 metadata。内部 runtime payload 仍可携带 worker 所需的 private instruction/LLM resolution，但 public read side 和 admission metadata 不返回 `options_jsonb`、prompt/body text、credential refs、draft 或 manuscript。

## Workflow / Trace Tables

```text
workflow_runs
workflow_events
workflow_stage_snapshots
agent_traces
agent_trace_events
llm_activity
```

`workflow_runs` 是产品读模型：

```text
tenant_id
run_id
workflow_type
project_id
status
progress
message
started_by
temporal_workflow_id
temporal_run_id
result_jsonb
error_code
error_message
created_at
updated_at
```

## LLM Tables

```text
llm_channels
llm_models
llm_module_bindings
llm_activity
llm_usage_daily
```

`usage_events` 是 Core SaaS 的通用用量事实表，不是 LLM 专用表。LLM runtime 写 token 用量时必须使用 `usage_type = llm_tokens`，并携带 tenant/project/run/module context；`GET /v1/projects/{projectId}/llm/usage` 只聚合该 usage type，不能把 storage、workflow、import 或其他 billing usage 混入 LLM Facility Usage read side。

API key 使用 envelope encryption：

- KMS master key。
- per row data key。
- encrypted_api_key。

DB-backed LLM binding / credential read side 必须把 SQL/driver exception 当作不可信错误源。`llm_module_bindings` 查询失败只公开 `LLM_BINDING_QUERY_FAILED` / `LLM module binding query failed`；`llm_channels.encrypted_api_key` 查询失败只公开 `LLM_CREDENTIAL_QUERY_FAILED` / `LLM credential query failed`。公开错误、workflow result/status、trace summary 和 Activity error 不得包含底层异常中的 `api_key`、`encrypted_api_key`、`credential_ref`、prompt、source text 或 raw SQL/driver message。

Go HTTP LLM Facility 边界也会把 resolver/store/reader/syncer 返回的 message 当作不可信输入，按 LLM error code 映射固定 public message。`LLM_BINDING_QUERY_FAILED`、`LLM_BINDING_UPDATE_FAILED`、`LLM_BINDING_DELETE_FAILED`、`LLM_CATALOG_QUERY_FAILED`、`LLM_SETTINGS_QUERY_FAILED`、`LLM_CHANNEL_UPDATE_FAILED`、`LLM_MODEL_SYNC_QUERY_FAILED` / `FAILED` / `STATUS_FAILED` 和 `LLM_ACTIVITY_QUERY_FAILED` 等错误都不能把底层 exception 文本、prompt、API key、`credential_ref`、draft 或 manuscript 透出到 HTTP response。

Go HTTP request decode failure 同样是 LLM/Trace 公开错误边界：project module binding upsert、tenant channel create/update 和 trace export 写入口的无效 JSON、unknown field 或类型错误只返回稳定 `VALIDATION_FAILED` message 和空 details，不回显 decoder 字符串、unknown field 名称、Go struct field 名称，或 `api_key` / prompt / `credential_ref` / draft / manuscript 等敏感词。

`llm_channels.provider` 是 runtime resolution 的必填公共字段，和 `channel_id`、`model_id`、`base_url`、`credential_ref` 一样属于 provider invocation 前置条件。Python shared LLM Facility validation 会在 credential lookup/provider call 前拒绝空 provider，并返回 `LLM_PROVIDER_ERROR` / `resolved LLM module is missing provider`；不得在 provider identity 缺失时写 `llm_activity.completed`、`usage_events` 或 candidate/canon 数据。

## Search / Vector

### Full Text

```text
global_search_index
  tenant_id
  source
  source_ref
  project_id
  entity_type
  title
  body
  tags
  payload_jsonb
  search_vector
```

### Vector

```text
semantic_embeddings
  tenant_id
  embedding_id
  source
  source_ref
  project_id
  embedding_model
  dimensions
  vector
  chunk_text
  metadata_jsonb
```

## 旧表映射摘要

| 旧表 | 新表 |
|---|---|
| `project_meta` | `projects`, `project_settings` |
| `project_artifacts` | structured tables + object artifacts + legacy import reports |
| `entities` | `entities` |
| `relationships` | `relationships` |
| `assets` | `assets` + extension tables |
| `classification_map` | `classification_rules` |
| `graph_*` | `story_graph_*` |
| `worldline_sessions` | `worldline_sessions` |
| `agent_registry` | `worldline_agent_registry` |
| `agent_*_log` | `worldline_agent_*` |
| `chapter_content` | `chapters` / `chapter_versions` |
| `chapter_meta` | `chapters` / `chapter_versions` / `outline_versions` |
| `scenes` | `scenes` / `scene_versions` |
| `task_runs` | `workflow_runs` |
| `llm_*` | `llm_*` with tenant scope |

## RLS 测试要求

每个核心表都要有：

- migration enabling RLS。
- policy。
- test: tenant A cannot select tenant B。
- test: service role with explicit tenant can operate。

## 验收清单

- 旧 SQLite 项目可导入。
- 所有旧业务域有新表承载。
- 没有核心业务只存在 object storage JSON。
- 关键查询有索引。
- RLS 生效。
- semantic search 不替代主表。
- 删除项目能级联清理所有域。
