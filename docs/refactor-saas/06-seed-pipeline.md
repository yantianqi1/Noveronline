# 06. Seed Pipeline

更新时间：`2026-07-07`

## 模块定位

Seed Pipeline 是整个小说系统的入口。它把上传文本、设定、大纲和素材转化为结构化故事世界数据。

旧能力包括：

- TXT / MD / PDF 上传。
- 文件解析。
- 智能分段。
- 顺序精读。
- 全局聚合。
- ontology 生成。
- 角色 Agent 档案生成。
- reading notes / seed analysis / story memory / chapter continuity 等 artifact。
- 任务进度、trace、失败重试、断点续传。
- DB-first 写入 entities、relationships、plot_threads、thread_lifecycle、narrative_arcs、volume_summaries、world_rule_evidence、character_events、relationship_events、consistency_notes、segment_summaries。

新系统必须全部覆盖，并把流程升级为可恢复的 Temporal workflow。

## 目标流程

```text
Upload Source
  -> Parse File
  -> Normalize Text
  -> Segment Novel
  -> Sequential Reading
  -> Runtime Facts Persist
  -> Global Aggregation
  -> Ontology Generation
  -> Entity Resolution
  -> Agent Profile Generation
  -> Archive Candidate Generation
  -> Search / Vector Index
  -> Project Readiness Update
```

## Workflow 设计

### SeedPipelineWorkflow

输入：

```json
{
  "tenant_id": "ten_...",
  "project_id": "proj_...",
  "upload_id": "upl_...",
  "source_file_id": "file_...",
  "source_object_key": "projects/proj_.../source-files/upl_.../novel.txt",
  "source_filename": "novel.txt",
  "source_mime_type": "text/plain",
  "source_size_bytes": 123456,
  "source_sha256": "sha256...",
  "requested_by": "usr_...",
  "options": {
    "language": "zh-CN",
    "analysis_depth": "standard",
    "generate_agent_profiles": true,
    "generate_archive_candidates": true,
    "chapter_detection": "auto"
  }
}
```

`source_object_key` 等 source metadata 只存在于 Go -> Temporal 的内部 payload，用于 Python `parse_file` activity 读取对象存储。公网 Seed start response 只返回 run metadata，不返回 object key、raw text 或 parsed text。

Go `sourcefiles.SQLStore` 在 `DATABASE_URL` 配置下会通过 tenant-context-aware SQL path 读写 `source_files`：create、upload object metadata lookup、upload complete、source list 和 Seed source validation 都会在支持的 queryer 上先设置 app-role `app_set_tenant_context`，再触碰 RLS-protected source metadata。source upload admission 现在只接受与 Python parse path 对齐的 TXT/Markdown/PDF MIME：`text/plain`、`text/markdown`、`text/x-markdown`、`application/x-markdown`、`application/pdf`，并允许 `; charset=...` 这类参数；不支持的 MIME 会在 HTTP 和 SQL store 两层以稳定 `VALIDATION_FAILED` 拒绝，且不会创建 `source_files` pending row。tenant-scoped rows close / transaction commit failure 和 scan failure 都会收敛为稳定 source-file public error，并且 scan failure 会 abort tenant-scoped rows/transaction，避免 source upload admission 或 completion 在 app-role/RLS live path 上留下不可解释的 partial state。Go API 现在提供 `PUT /v1/uploads/{uploadId}/object` 作为 server-side object upload handoff：它只信任 `X-Tenant-Id` 和 path upload id，从 `source_files` 读取内部 object metadata 和 `parse_status`，只允许 `pending` upload 写入 source object；`uploaded`、`parsing`、`parsed`、`failed`、`cancelled` 或未知状态会在调用 object writer 前返回稳定 `SOURCE_FILE_UPLOAD_NOT_WRITABLE` / HTTP `409 Conflict`。允许写入时，object writer 先把请求 body 写入临时文件并校验 byte count / SHA-256，匹配 admission metadata 后才写入 MinIO/S3-compatible object storage；公开响应只返回 `upload_id` 和 `stored` 状态，不返回 object key、presigned URL、raw content、object credentials 或 fake parse result。Next `/overview` 已新增 browser file picker 和 typed Web API client 调用该 endpoint，仍要求用户随后显式 complete 才会执行 object verification 与 Seed admission。upload complete 现在必须配置 object verifier；缺少 verifier / object storage 配置时返回稳定 `SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED`，不会把 `parse_status` 更新为 `uploaded`。`CompleteUpload` 只允许 `pending` / `uploaded` source row 进入 verifier 和 `uploaded` 更新；`parsing`、`parsed`、`failed`、`cancelled` 等非可完成状态会在 verifier 前返回稳定 `SOURCE_FILE_UPLOAD_NOT_COMPLETABLE`，避免已进入 Seed/parse 生命周期的 source row 被 complete 调用倒退回 `uploaded`。Seed start 现在在 HTTP 边界要求 source-file backend 已配置；未配置时返回稳定 `SOURCE_FILE_BACKEND_UNCONFIGURED`，不会调用 `SeedStarter` 或启动缺 source metadata 的 workflow shell。Seed workflow DB admission 现在在写 `workflow_runs` / `workflow_events` 前，通过同一条 SQL CTE 把当前 tenant/project/upload 下 `parse_status = uploaded` 的 `source_files` row 推进为 `parsing`；如果 upload 不存在、跨 scope 或已经不是 uploaded，则返回稳定 `SOURCE_FILE_NOT_UPLOADED`，不创建 queued workflow row、不启动 Temporal。`SQLSeedAdmissionStore` 在 admission 和 Temporal start-failure compensation 写路径上会优先使用 tenant-context execer；真实 SQL DB execer 会在同一 transaction 中调用 `app_set_tenant_context(tenant_id, project_id, false)` 后再触碰 RLS-protected `source_files`、`workflow_runs` 和 `workflow_events`。Python Seed 现在也有 opt-in live Postgres/app-role parse/segment harness：设置 `MIROFISH_SEED_LIVE_DATABASE_URL` 后，`apps/agent-runtime/tests/test_seed_live_e2e.py` 会应用 migration、创建 app-role login、准备 queued Seed run 和 `parse_status = parsing` source row，再用 app-role `DATABASE_URL` 跑本地 parse -> segment，验证 source row 变 `parsed`、artifact/segment/public workflow event metadata 落库且公开 event 不泄露 object key/raw text。`TemporalSeedRunStarter` 也要求 admission store 已配置；缺失时返回 `WORKFLOW_BACKEND_UNCONFIGURED` / `seed admission store is not configured`，且不会调用 Temporal `ExecuteWorkflow`。普通 admission SQL/RowsAffected error 收敛为稳定 `WORKFLOW_ADMISSION_FAILED`，不透传 driver 文本、object key、prompt、API key、`credential_ref`、draft 或 manuscript；admission 成功但 Temporal `ExecuteWorkflow` 普通启动失败时返回稳定 `WORKFLOW_FAILED` / `failed to start seed_pipeline workflow`，不透传 Temporal/client exception 文本、object key、source path、prompt、API key、`credential_ref`、draft 或 manuscript，同时 DB-backed compensation 会把已 admission 的 `workflow_runs` 标为 `failed`、追加 sanitized `workflow.failed` event，并把同 tenant/project/upload 的 `source_files.parse_status` 从 `parsing` 释放回 `uploaded`，避免留下 orphan queued/parsing 状态。配置 MinIO/S3-compatible object verifier 时，upload complete 不再只验证对象存在；verifier 会以 checksum mode 调用 `StatObject`，返回的 size 必须匹配 admission `size_bytes`，且 `ChecksumSHA256`、user metadata 或 object metadata 中的 sha256 证据必须匹配 admission `sha256`，否则返回稳定 `SOURCE_FILE_STORAGE_VERIFY_FAILED`，不把 object key、hash、底层 storage message 或 raw content 公开给调用方。

2026-07-07 live Postgres/app-role parse -> segment harness 已在本地 `127.0.0.1:54329` 真实执行通过：migration 会为既有 `project_text_artifacts` / `text_segments` 补 upsert unique index，`run_seed_workflow_locally` 会复用 env workflow event writer 写完整 parse/segment public stage events，最终验证 `source_files.parse_status = parsed`、`project_text_artifacts`、`text_segments` 和 sanitized `workflow_events` 均落库。随后新增 opt-in MinIO/Postgres live harness：当 `MIROFISH_SEED_LIVE_DATABASE_URL` 与 `MIROFISH_SEED_LIVE_OBJECT_STORAGE_*` 同时设置时，测试会先将 source bytes 写入真实 MinIO/S3-compatible bucket，再让 Python parse/segment 从对象存储读取 source、写回 extracted artifact 和 segment objects，并验证 public workflow events 不泄露 object keys/raw text。parse/segment object persistence 已由 live harness 覆盖；browser upload、sequential-reading/provider、semantic/LLM/OCR stages 和 full Seed pipeline E2E 仍是后续检查。

2026-07-07 追加 Go control-plane live MinIO/Postgres app-role harness：`apps/api/internal/workflows/seed_live_test.go` 在 opt-in 环境变量齐备时，会用 app-role/RLS Postgres 走 `sourcefiles.SQLStore.CreateSourceFile -> GetUploadObject -> MinIOObjectWriter.WriteObject -> CompleteUpload -> ValidateSourceFile -> SQLSeedAdmissionStore.AdmitSeedRun`，验证真实 MinIO 对象写入/校验、`source_files.parse_status` 从 `pending` 到 `uploaded` 再到 `parsing`、`workflow_runs` queued row 和 sanitized `workflow.queued` event。该 slice 同时修正 Go `sourcefiles.SQLStore.scanRow` 的 tenant-scoped rows 生命周期：在 successful close/transaction commit 后不再二次读取 `rows.Err()`，避免 app-role live path 把 close 后的 driver `context canceled` 误判为 `SOURCE_FILE_QUERY_FAILED`。公开 admission event 仍不暴露 object key、raw text、prompt、API key、`credential_ref`、draft 或 manuscript。Go API upload/complete -> Temporal cluster -> Python parse/segment handoff 已有 opt-in live 覆盖；browser upload/complete、sequential-reading/provider、semantic/LLM/OCR stages 和 full Seed pipeline E2E 仍是后续检查。

2026-07-07 追加 Python parse worker source object integrity guard：`parse_file_activity` 现在会在读取 source object bytes 后、TXT/Markdown/PDF extraction 前，使用 Go handoff payload 中可选的 `source_size_bytes` 与 `source_sha256` 复核 actual bytes。字段缺省时兼容旧 payload；字段存在但类型、格式、size 或 SHA-256 不匹配时以稳定 `SOURCE_FILE_OBJECT_INTEGRITY_MISMATCH` / `source object integrity check failed` fail closed，并尝试将仍处于 `parsing` 的 source row 标记为 `failed`。公开 activity result / workflow event 不返回 expected hash、actual hash、source object key、raw text、prompt、API key、`credential_ref`、draft 或 manuscript。该 guard 缩小 Go admission 后 object 被外部篡改仍进入 parse/segment 的窗口；parse/segment live handoff 已覆盖，browser upload/complete、sequential-reading/provider、semantic/LLM/OCR stages 和 full Seed pipeline E2E 仍是后续检查。

2026-07-07 追加 Go Temporal Seed starter source handoff validation：`TemporalSeedRunStarter` 现在在 admission store 写入、run id 分配和 Temporal `ExecuteWorkflow` 前复核内部 source handoff metadata，缺少 source file/object/mime/SHA metadata、source MIME 不在 TXT/Markdown/PDF allowlist、`source_sha256` 不是 64 位 hex，或 size 为负时以稳定 `VALIDATION_FAILED` / `seed source metadata is incomplete` fail closed，且不会写 `workflow_runs`、不会把 source row 推进到 `parsing`、不会启动 source-less 或 invalid-source `SeedPipelineWorkflow`。该 public error 不返回 object key、source path、MIME、hash 字段名/值、prompt、API key、`credential_ref`、draft 或 manuscript。HTTP Seed start 仍以 `sourcefiles.ValidateSourceFile` 作为正常入口；starter 级校验是防止内部调用绕过 source validation 的第二道防线。真实 parse/segment handoff 已由 live harness 覆盖，full Seed pipeline E2E 仍待后续 semantic/LLM/OCR/browser 检查。

2026-07-07 追加 Temporal Seed starter UUID preflight hardening：`TemporalSeedRunStarter` 现在会在 admission store 写入、run id 分配和 Temporal `ExecuteWorkflow` 前验证 tenant/project/upload/source id 以及非空 actor id 的 UUID shape；非法内部 context 以稳定 `VALIDATION_FAILED` / `seed workflow context is invalid` fail closed，不调用 admission store、不启动 Temporal，也不回显不可信 id 中的 prompt/API key/`credential_ref`/object key/draft/manuscript。该 guard 是 HTTP/source validation 与 SQL admission UUID preflight 之间的 Go -> Temporal 第二道防线，不改变 payload shape、SQL CTE、Python parse/segment 或完整 live E2E 状态。

2026-07-07 追加 Seed HTTP request-id privacy hardening：Go HTTP `requestID` helper 现在只保留短安全字符集内且不含高风险键族的 `X-Request-Id`；包含 prompt/API key/`credential_ref`/object key/draft/manuscript 等敏感片段、非法字符或过长的 header 会被替换为生成的 `req_...`。`POST /v1/projects/{projectId}/seed-runs` 因此不会再把客户端可控敏感 request id 传给 `SeedStarter`、admission metadata、Temporal payload 或公开 error envelope。该更新只收紧 HTTP correlation metadata 边界，不改变 upload/complete、source validation、Temporal worker 或 Python parse/segment 语义。

2026-07-07 追加 Go Temporal Seed starter options handoff 隐私边界：`TemporalSeedRunStarter` 现在会在组装 `SeedPipelineWorkflow` payload 前递归清洗 `options`，移除 body-provided `tenant_id` / `project_id`、prompt/response/body/content/raw/source/material/candidate/event/draft/manuscript 和 credential/API key 字段；`api-key`、`credential-ref`、`raw-text`、`source-material`、`candidate-event-body` 等 hyphenated key，以及 `sourceMaterial`、`candidateBody`、`candidateEventBody`、`eventBody` 等 camelCase key，都与 underscore 形式等价处理。安全 public analysis options（例如 language、analysis depth、chapter detection）仍保留。HTTP handler 仍会在调用 starter 前先清洗一次；starter 级 sanitizer 是 Go -> Temporal -> Python handoff 的第二道防线，防止未来内部调用绕过 HTTP 边界时把 prompt、API key、`credential_ref`、raw text、draft 或 manuscript 放入 Temporal payload。该 slice 不改变 source metadata handoff、admission、parse/segment 成功语义，也不代表完整 Seed live E2E 完成。

2026-07-07 追加 Seed admission queued event source metadata handoff：`TemporalSeedRunStarter` 现在会把 validated `source_file_id` 传给 admission store，DB-backed `SQLSeedAdmissionStore` 写入的 `workflow.queued` public payload 会包含 `upload_id` 与 `source_file_id`，方便 Overview/worker event replay 将 queued -> parse/segment 链路对齐。SQL admission 的 `source_file_id` 从同一条 CTE 实际推进到 `parsing` 的 `source_update.file_id` 派生，不信任 caller-supplied source file id。该 public metadata 不包含 source object key、source path、raw/parsed text、prompt、API key、`credential_ref`、draft 或 manuscript；opt-in Go MinIO/Postgres live harness 也覆盖 queued event 中的 `source_file_id`。

2026-07-07 追加 Seed admission source-file scope hardening：DB-backed `SQLSeedAdmissionStore.AdmitSeedRun` 现在要求 admission input 带 `source_file_id`，并在同一条 source update CTE 中同时匹配 tenant/project、`upload_id`、`source_file_id` 和 `parse_status = uploaded` 后才推进 `source_files.parse_status = parsing`、写 `workflow_runs` 和 `workflow.queued`。这样内部调用即使绕过 HTTP/source validation，也不能用某个 upload 的 row 搭配另一个 source file id 启动会与 DB public event 分叉的 Temporal payload；queued event 中公开的 `source_file_id` 仍从实际命中的 DB row 派生，不把 caller JSON 写入 public payload。该更新不改变 object storage、Temporal start、Python parse/segment 语义，也不代表完整 Seed live E2E 完成。

2026-07-07 追加 Seed start-failure compensation event source metadata handoff：admission 成功但 Temporal `ExecuteWorkflow` 启动失败时，DB-backed `RecordSeedRunStartFailure` 要求同一个 `source_file_id` scope，并且只有 tenant/project/upload/source-file 下仍处于 `parsing` 的 source row 会被释放回 `uploaded`。写入的 `workflow.failed` public payload 会在 source row 成功释放时包含 row-derived `source_file_id`；该值来自同一条 `source_update.file_id`，不信任 caller JSON。若 source row 已无法释放，failure payload 仍只保留稳定 public failure metadata。该更新只增强 failed compensation source scope 与 failed event correlation，不改变 Temporal start、source 状态机或 Python parse/segment 语义，也不公开 object key、source path、raw text、prompt、API key、`credential_ref`、draft 或 manuscript。

2026-07-07 追加 Seed admission UUID preflight hardening：DB-backed `SQLSeedAdmissionStore.AdmitSeedRun` 和 `RecordSeedRunStartFailure` 现在会在执行带 `::uuid` cast 的 SQL 前验证 tenant/project/run/upload/source id 以及非空 actor id 的 UUID shape；非法内部 context 以稳定 `VALIDATION_FAILED` / `seed admission context is invalid` fail closed，不调用 admission SQL、不推进 source row、不写 workflow rows/events，也不回显包含 prompt/API key/`credential_ref` 的不可信 id 文本。该更新只前移 DB admission/compensation 的输入校验，不改变 HTTP Seed start、Temporal payload、Python parse/segment 或完整 live E2E 状态。

2026-07-07 追加 Go workflow event replay payload 隐私边界：通用 `GET /v1/workflow-runs/{runId}/events` 与 Seed event replay 会在 HTTP/Go 读侧递归清洗 persisted `workflow_events.payload_jsonb`。`source_file_id` 作为安全 public correlation metadata 保留；`object_key`、`source_object_key`、`artifact_object_key`、`segment_object_key`、raw/source/input/output/body/content text、hash/checksum、prompt/response、API key、`credential_ref`、draft 和 manuscript 字段会被剥离，覆盖旧 row、alternate writer 或 injected store payload。该更新只收紧 public replay boundary，不改变 event schema、cursor、SSE 格式、Temporal/Python runtime 或完整 Seed live E2E 状态。

2026-07-07 追加真实 Temporal Worker event-writer handoff 覆盖：`SeedPipelineWorkflow` 现在在 Temporal test worker 中通过默认 sandbox 验证，Seed activity 在未显式注入 `WorkflowEventWriter` 时会从环境解析 writer，让真实 worker path 的 parse completed、segment pending/completed 和 sequential-reading failed public stage events 可以落到同一 `workflow_events` writer。`pypdf` import 已作为 Temporal sandbox passthrough，仅供 activity PDF extraction 使用；Python `run_worker()` 现在为同步 activity 提供 `ThreadPoolExecutor`，避免 worker 启动时因 sync activity 缺 executor 失败。Go API upload/complete -> Temporal cluster -> Python parse/segment 已有 opt-in live E2E 覆盖；sequential-reading provider、semantic/LLM/OCR stages、browser full-path 和 full Seed pipeline 仍是后续检查。

2026-07-07 追加 Seed pending event write failure 隐私边界：`seed_pipeline_activity` 在 worker 接受 run 但 workflow event writer 环境解析或 `seed.stage.pending` 写入失败时，只返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`。底层 workflow event writer factory / writer exception 不得进入公开 activity result，避免 prompt、API key、`credential_ref`、object key、source path、draft 或 manuscript 通过真实 worker handoff 失败路径泄露。

2026-07-07 追加 parse stage workflow event writer env-resolution 隐私边界：`parse_file_activity` 在解析 workflow event writer 时如果遇到环境或 writer factory 异常，会返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，并只保留 `stage = parse_file` 与 `source_file_id` public metadata。底层 exception 不得进入公开 result，避免 prompt、API key、`credential_ref`、object key、source path、draft 或 manuscript 在 parse worker 入口泄露。

2026-07-07 追加 segment stage workflow event writer env-resolution 隐私边界：`segment_text_activity` 在 artifact type 校验、object storage 读取和 segment 写入前会先解析 workflow event writer；如果环境或 writer factory 异常，会返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，并只保留 `stage = segment_text` 与 `source_file_id` public metadata。底层 exception 不得进入公开 result，也不得被误归类为 object storage failure，避免 prompt、API key、`credential_ref`、object key、draft 或 manuscript 在 segment worker 入口泄露。

2026-07-07 追加 sequential-reading stage workflow event writer env-resolution 隐私边界：`sequential_reading_activity` 在读取 LLM Facility binding、reading notes writer 或 provider 前会先解析 workflow event writer；如果环境或 writer factory 异常，会返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，并只保留 `stage = sequential_reading` 与 `module_key = sequential_reading` public metadata。底层 exception 不得进入公开 result，避免 prompt、API key、`credential_ref`、segment object key、draft 或 manuscript 在 sequential worker 入口泄露。

2026-07-07 追加后续 Seed stages workflow event writer env-resolution 隐私边界：`persist_runtime_facts_activity`、`global_aggregation_activity`、`ontology_activity`、`entity_resolution_activity`、`agent_profile_activity`、`archive_candidate_activity`、`index_assets_activity` 和 `finalize_seed_activity` 在读取 runtime writer、LLM runner、asset indexer、readiness updater 或 status writer 前会先解析 workflow event writer；如果环境或 writer factory 异常，会返回稳定 `WORKFLOW_EVENT_WRITE_FAILED` / `workflow event write failed`，并只保留 stage/module public metadata。底层 exception 不得进入公开 result，避免 prompt、API key、`credential_ref`、object key、draft 或 manuscript 在后续 worker stage 入口泄露。该更新只收紧失败边界，不代表真实 ontology/entity/profile/archive/finalize runner 或完整 Seed live E2E 已完成。

2026-07-07 追加本地 workflow status writer 复用覆盖：`run_seed_workflow_locally` 现在可显式注入同一个 workflow status writer，并把它传递给 seed admission、sequential-reading terminal failure 和 finalize terminal success。该 harness 可验证本地 parse -> segment -> sequential fail-closed 链路中的 `running -> failed` 状态交接，公开 result/event/status 仍不得暴露 source object key、segment object key、raw text、prompt/API key、`credential_ref`、draft 或 manuscript。Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 已覆盖；semantic/LLM/OCR stages、browser full-path 和 full Seed pipeline 仍待后续验证。

2026-07-07 追加 parse/segment terminal workflow status handoff：`parse_file_activity` 与 `segment_text_activity` 的 terminal failure 现在会在写 sanitized `seed.stage.failed` 后，尝试通过 workflow status writer 将已 admission 的 `workflow_runs.workflow_type = seed_pipeline` 标为 `failed`，并只写稳定 public error code/message。真实 worker path 会从 `DATABASE_URL` 解析 status writer；如果 status writer 环境解析或写入失败，公开 result 收敛为 `WORKFLOW_STATUS_WRITE_FAILED` / `seed workflow status write failed`，不透传可能夹带 prompt、API key、`credential_ref`、object key、draft 或 manuscript 的底层 exception。该更新修复早期 parse/segment terminal failure 可能让 Overview/Seed read side 看到 run stuck `running` 的缺口；Go API upload/complete -> Temporal cluster -> Python parse/segment live E2E 已覆盖，semantic/LLM/OCR stages、browser full-path 和 full Seed pipeline 仍待后续验证。

2026-07-07 追加 parse source-status writer env-resolution 隐私边界：`parse_file_activity` 在真实 worker path 解析 DB-backed source parse-status writer 时，如果环境或 writer factory 异常，会返回稳定 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED` / `source file parse status update failed`，写 sanitized `seed.stage.failed` parse event，并在 workflow status writer 可用时把 admitted Seed run 标为 `failed`。底层 exception 不得进入公开 activity result、workflow event 或 status，避免 prompt、API key、`credential_ref`、object key、draft 或 manuscript 在 Go admission 后的 Python parse 入口泄露。

2026-07-07 追加 parse text-artifact writer env-resolution 隐私边界：`parse_file_activity` 在真实 worker path 解析 DB-backed text artifact writer 时，如果环境或 writer factory 异常，会返回稳定 `TEXT_ARTIFACT_WRITE_FAILED` / `text artifact write failed`，尝试把 source row 标为 `failed`，写 sanitized `seed.stage.failed` parse event，并在 workflow status writer 可用时把 admitted Seed run 标为 `failed`。底层 exception 不得进入公开 activity result、workflow event 或 status；该路径不会读取 source object 或写 extracted artifact，避免 prompt、API key、`credential_ref`、object key、draft 或 manuscript 在 extracted artifact 持久化依赖装配阶段泄露。

2026-07-07 追加 segment text-segment writer env-resolution 隐私边界：`segment_text_activity` 在真实 worker path 解析 DB-backed text segment writer 时，如果环境或 writer factory 异常，会返回稳定 `TEXT_SEGMENT_WRITE_FAILED` / `text segment write failed`，写 sanitized `seed.stage.failed` segment event，并在 workflow status writer 可用时把 admitted Seed run 标为 `failed`。底层 exception 不得进入公开 activity result、workflow event 或 status；该路径不会读取 extracted artifact 或写 segment object，避免 prompt、API key、`credential_ref`、object key、draft 或 manuscript 在 segment persistence dependency 装配阶段泄露。

2026-07-07 追加 parse/segment object-store env-resolution 隐私边界：`parse_file_activity` 与 `segment_text_activity` 在真实 worker path 解析 MinIO/S3-compatible object store 时，如果环境或 factory 抛出非 `ValueError` 的普通异常，也会返回稳定 `OBJECT_STORAGE_BACKEND_MISCONFIGURED` / `object storage backend is misconfigured`。parse 路径会尝试把 source row 标为 `failed`，写 sanitized `seed.stage.failed` parse event，并在 workflow status writer 可用时把 admitted Seed run 标为 `failed`；segment 路径会写 sanitized segment failed event 并标记 workflow failed。底层 exception、object credential、source/artifact object key、prompt、API key、`credential_ref`、draft 或 manuscript 不进入公开 result/event/status；失败路径不读取 source/extracted artifact，也不写 extracted artifact 或 segment object。

2026-07-07 追加 sequential-reading 默认 reader object-store env-resolution 隐私边界：`sequential_reading_activity` 在真实 worker path 装配 DB-backed `LLMFacilitySequentialReader` 时，如果 segment text object store 环境或 factory 抛出普通异常，会返回稳定 `OBJECT_STORAGE_BACKEND_MISCONFIGURED` / `object storage backend is misconfigured`，写 sanitized `seed.stage.failed` sequential-reading event，并在 workflow status writer 可用时把 admitted Seed run 标为 `failed`。该路径不会调用 LLM、不会写 reading notes，也不会把底层 exception、segment object key、prompt/API key、`credential_ref`、draft 或 manuscript 透出到公开 result/event/status。

2026-07-07 追加 `story_ontology` LLM Facility runner skeleton：Python Seed runtime 新增可注入的 `LLMFacilityOntologyRunner` 和 `OntologySnapshotWriter` contract。runner 会解析 `story_ontology` module binding、要求 JSON-capable provider resolution、用显式 credential 调用 JSON client、校验 `seed_ontology.entity_types` / `relationship_types` / `world_rule_types` 数组，并在 writer 持久化私有 ontology snapshot 后才返回 completed public metadata。公开 result / workflow event 只允许 `ontology_snapshot_id`、`model_id` 和类型 counts，不返回 ontology body、prompt/response、API key、`credential_ref`、raw text、draft 或 manuscript。live provider E2E、entity resolution/profile/finalize runner 仍 pending。

2026-07-07 追加 `story_ontology` DB-backed snapshot writer 与 env wiring：target schema 新增 `seed_ontology_snapshots` 表、tenant RLS、run/project 索引和 `(tenant_id, project_id, run_id, module_key)` 唯一键；`PostgresOntologySnapshotWriter` 先设置 `app_set_tenant_context(tenant_id, project_id, false)`，再 upsert 私有 `ontology_jsonb` 与类型 counts，SQL/commit failure 会 rollback 并稳定为 `ONTOLOGY_SNAPSHOT_WRITE_FAILED`。`_ontology_runner_from_env()` 现在可在 `DATABASE_URL` 与显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 可用时装配 DB-backed `LLMFacilityOntologyRunner`，复用 LLM Facility module binding resolver、credential provider 和 OpenAI-compatible JSON client；缺 DB 时仍 fail closed，不生成 mock ontology。该 slice 不代表 live provider E2E、entity resolution/profile/finalize runner 或完整 Seed pipeline 完成。

2026-07-07 追加 `entity_resolution` LLM Facility runner skeleton 与 DB-backed snapshot writer：target schema 新增 `seed_entity_resolution_snapshots` 表、tenant RLS、run/project 索引和 `(tenant_id, project_id, run_id, module_key)` 唯一键；Python runtime 新增可注入 `LLMFacilityEntityResolutionRunner` 与 `EntityResolutionSnapshotWriter` contract。runner 会解析 `entity_resolution` module binding、要求 JSON-capable provider resolution、用显式 credential 调用 JSON client、校验 `entity_resolution.merged_entities` / `aliases` / `conflicts` 数组，并通过 `PostgresEntityResolutionSnapshotWriter` 写入私有 `resolution_jsonb` 与 counts。公开 activity result / workflow event 只允许 `resolution_snapshot_id`、`model_id`、merged/alias/conflict counts，不返回 resolution body、prompt/response、API key、`credential_ref`、raw text、draft 或 manuscript。该 slice 不代表 live provider E2E、profile live provider E2E/finalize runner 或完整 Seed pipeline 完成。

2026-07-09 追加 `character_agent_profile` LLM Facility runner 与 DB-backed snapshot writer：target schema 新增 `seed_agent_profile_snapshots` 表、tenant RLS、run/project 索引和 `(tenant_id, project_id, run_id, module_key)` 唯一键；Python runtime 新增可注入 `LLMFacilityAgentProfileRunner`、`AgentProfileSnapshotWriter` contract 和 `PostgresAgentProfileSnapshotWriter`。runner 会解析 `character_agent_profile` module binding、要求 JSON-capable provider resolution、用显式 credential 调用 JSON client、校验 `agent_profiles.profiles` / `memory_seeds` / `relationship_views` 数组，并通过 snapshot writer 写入私有 `profiles_jsonb` 与 counts。公开 activity result / workflow event 只允许 `profile_snapshot_id`、`model_id`、profile/memory seed/relationship view counts，不返回 public/private profile body、prompt/provider response、API key、`credential_ref`、raw text、draft 或 manuscript。该 slice 不代表 live provider E2E、finalize runner 或完整 Seed pipeline 完成。

2026-07-09 追加 `character_agent_profile` allow-listed context loader：`LLMFacilityAgentProfileRunner` 现在必须在 binding resolution、credential decrypt、provider call 和 snapshot write 之前，通过 `AgentProfileContextLoader` 读取 tenant/project/run scoped Seed context；缺 loader、空 context、metadata-only context 或 loader 失败都会稳定 fail closed。DB-backed loader 会先设置 app-role tenant context，只读取 `seed_entity_resolution_snapshots` public metadata / allow-listed resolution arrays，以及 `entities`、`relationships`、`segment_summaries` 的 public summary fields，并把白名单 `source_context` 注入 provider message。公开 result/event 仍只返回 snapshot/model/count metadata，不公开 prompt/provider response、raw body/content、API key、encrypted credential、`credential_ref`、object key、draft、manuscript 或 profile body。该 slice 不代表 `character_agent_profile` live provider E2E、finalize runner 或完整 Seed pipeline 完成。

2026-07-09 追加 `character_agent_profile` opt-in Postgres/local-provider harness 与隐私硬化：`tests/test_seed_live_e2e.py` 现在可在 `MIROFISH_SEED_LIVE_DATABASE_URL` 配置时准备 workflow admission、entity-resolution context、structured canon metadata、encrypted LLM channel credential、model 和 module binding rows，启动本地 OpenAI-compatible JSON provider，并用 app-role `DATABASE_URL` 执行 `agent_profile_activity`，验证 provider request、`seed_agent_profile_snapshots` 和 sanitized `workflow_events` 同链路关联。默认无 live DB env 时该测试显式 skipped，不把 skip 当作 live E2E 已执行。`story_ontology`、`entity_resolution` 与 `character_agent_profile` runner 现在都会在 credential lookup/provider call 前拒绝缺 `provider` 的 resolution；ontology/agent-profile snapshot sanitizer 也移除 `raw_body`、`provider_raw_body` 和 `provider_response` 等 provider/raw body 字段。实际 live env execution、full browser/provider Seed pipeline、finalize runner 和完整产品闭环仍 pending。

当前 SaaS skeleton 已在 `SeedPipelineWorkflow` 中完成 `seed_pipeline_activity -> parse_file_activity -> segment_text_activity -> sequential_reading_activity -> persist_runtime_facts_activity -> global_aggregation_activity -> ontology_activity -> entity_resolution_activity -> agent_profile_activity -> archive_candidate_activity -> index_assets_activity -> finalize_seed_activity` 链接：先写 sanitized pending stage event，再在 payload 带 source metadata 时读取对象存储并写 extracted text object reference，随后读取 extracted text artifact、按中文章节标题、Markdown English `Chapter ...` 标题或无标题段落窗口生成真实 text segment object references。`parse_file_activity` 在 DB-backed source status writer 可用时会把 source row 从 `parsing` 推进到 `parsed`；parse activity 自身读取/解码/写入失败时会尝试把仍处于 `parsing` 的 source row 标记为 `failed`，且公开 failed result/event 仍只使用稳定 public error，不透传 object key、raw text、prompt、API key、`credential_ref`、draft 或 manuscript；source status 更新未命中 `parsing` row 或遇到普通 DB 异常都会稳定为 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED`，避免取消或并发状态被 parse worker 覆盖，并且 `seed.stage.completed` parse event 只会在 source status 成功标为 `parsed` 后写入，status 失败时改写 sanitized `seed.stage.failed`。parse failure event 也只在 source row 成功标为 `failed` 后写入原始稳定 parse 错误；如果 failed-status 更新失败，公开 failed event 与 activity result 都使用同一个 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED`，避免 event replay 与最终 activity error code 不一致。`segment_text_activity` 为每个 segment 生成稳定 UUID `segment_id`，写入 `text_segments`，并只把 `segment_id`、顺序、章节猜测、分段策略和 segment object key 作为下一阶段 refs/metadata 传给 `sequential_reading_activity`，不返回 raw text/content；无章节标题的长文本会按段落窗口拆分，避免整篇长文落进单个 segment。Python seed worker 可通过 `MIROFISH_OBJECT_STORAGE_*` 绑定 MinIO/S3-compatible object store，并通过 `DATABASE_URL` 记录 extracted text artifact、source parse status 与 `text_segments` 引用；缺少 object storage、object storage env 不完整、缺少 text artifact/segment writer、source/artifact object 读取、写入、TXT/Markdown UTF-8 decode、PDF text extraction 或 segment metadata persistence 失败时必须显式失败，activity failed result 和 sanitized `seed.stage.failed` event 都只使用稳定 public message，不在公开 workflow event/HTTP response 中暴露 source object key、artifact object key、segment object key、raw text、prompt、API key、`credential_ref`、draft 或 manuscript。成功 parse/segment 的内部 activity result 仍可携带下一阶段 handoff 所需 object references，但 `seed.stage.completed` / `seed.stage.pending` public workflow event 只公开 stage/status/count/type/source id/segment id/strategy 这类 metadata；hash/checksum 只作为内部校验或私有持久化 metadata，不进入 public workflow event。`sequential_reading_activity` 已作为 fail-closed LLM stage contract 注册：没有显式 LLM reader 或 `sequential_reading` 模块绑定失败时返回稳定错误并写 sanitized failed event，不生成 mock reading notes；显式注入的 reader 返回成功结果时会校验 sequential reading schema、清洗 prompt/content/API key 等高风险字段、写入 `reading_passes` / `reading_segment_notes`，并记录 sanitized completed stage event。Python 侧已新增 `LLMFacilitySequentialReader` adapter contract：它通过显式注入的 LLM Facility binding resolver、credential provider、OpenAI-compatible JSON client 和 segment object store 读取 segment text、显式传递本次调用 API key、调用 JSON-capable模型，并在缺绑定/缺 credential/provider 失败时 fail-closed，不读取旧式 LLM env fallback。Python 侧还新增 DB-backed module binding resolver 和 AES-256-GCM credential provider，可按 project binding > tenant default 解析 `sequential_reading`，以 channel id 作为内部 credential ref 解密 `aes-256-gcm:v1:<iv>:<tag>:<ciphertext>`，且 resolution 不选择或返回 credential material。`sequential_reading_activity` 默认装配已能在 `DATABASE_URL`、segment object store 和显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 可用时构建 DB-backed `LLMFacilitySequentialReader`；缺少对象存储时保持 unconfigured fail-closed，credential key 缺失或无效时返回 sanitized failed stage event。`persist_runtime_facts_activity` 已新增结构化 canon 写入路径：从 schema-validated reading notes 或 DB-backed `reading_segment_notes` 回读角色、组织、实体标签、关系、伏笔线索、叙事弧线、分卷摘要、世界规则、角色事件、世界事件、关系事件、一致性提示与分段摘要，写入 `entities`、`entity_aliases`、`entity_labels`、`entity_evidence`、`relationships`、`plot_threads`、`thread_lifecycle`、`narrative_arcs`、`volume_summaries`、`world_rule_evidence`、`character_events`、`world_events`、`relationship_events`、`consistency_notes` 和 `segment_summaries`，并且 completed/failed workflow event 只返回 counts 或 public error，不暴露 evidence/raw text/summary text。`global_aggregation_activity` 已接入 Temporal worker 和 local runner，当前使用 `anchor_point_summary` 作为 Seed 全局聚合的 LLM module key；Python 侧已新增 `LLMFacilityGlobalAggregator` adapter contract 和 `PostgresSeedAggregateSource`，默认装配可在 `DATABASE_URL` 和显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 可用时解析 LLM Facility module binding、解密本次调用 credential、在 app-role/RLS context 下读取公开 `segment_summaries` / structured fact counts，并调用 OpenAI-compatible JSON-capable provider。aggregate source 普通 DB/driver query exception 会稳定为 `SEED_AGGREGATE_SOURCE_QUERY_FAILED`，不透传 prompt/API key/`credential_ref` 或 raw text。缺绑定、缺 credential 或 credential key 无效时显式失败并写 sanitized failed event，不生成 fake seed analysis；成功时 activity 可通过 DB-backed `PostgresSeedAnalysisWriter` 把私有 `seed_analysis` 对象写入 `seed_analysis_snapshots`，公开 result / workflow event 只包含 `seed_analysis_snapshot_id`、`segment_count`、`summary_count`、`model_id` 等 public metadata，不暴露 aggregation 正文、证据、prompt 或 raw text。`ontology_activity` 已从纯 fail-closed shell 推进到 DB-backed `story_ontology` runner 装配路径：缺少真实 runner 或 LLM Facility binding 时仍返回稳定失败并写 sanitized `seed.stage.failed`，不生成假 ontology；配置 `DATABASE_URL` 和显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 后，默认 runner 会解析 module binding、调用 JSON-capable provider、校验 ontology schema，并通过 `PostgresOntologySnapshotWriter` 写入 `seed_ontology_snapshots`，activity 只公开 `ontology_snapshot_id`、model 和类型 counts，不返回 ontology body、seed analysis 正文、prompt 或 credential。`entity_resolution_activity` 已从纯 fail-closed shell 推进到 DB-backed `entity_resolution` runner 装配路径：缺少真实 LLM Facility runner 时仍返回 `ENTITY_RESOLUTION_RUNNER_UNCONFIGURED` 并写 sanitized `seed.stage.failed`，不生成假实体合并结果；配置 DB 和显式 credential key 后，默认 runner 写入私有 `seed_entity_resolution_snapshots`，activity 只接受并公开 `resolution_snapshot_id`、model、merged/alias/conflict counts，不返回 resolution body。`agent_profile_activity` 已从纯 fail-closed shell 推进到 DB-backed `character_agent_profile` runner 装配路径：缺少真实 LLM Facility runner 时仍返回 `AGENT_PROFILE_RUNNER_UNCONFIGURED` 并写 sanitized `seed.stage.failed`，不生成假角色档案；配置 DB 和显式 credential key 后，默认 runner 写入私有 `seed_agent_profile_snapshots`，activity 只接受并公开 `profile_snapshot_id`、model、profile/memory seed/relationship view counts，不返回 public/private profile body。`archive_candidate_activity` 目前是 `narrative_archives` 的 fail-closed stage shell：注册到 worker/spec，Temporal workflow 会在 agent profiles 完成后进入 archive candidate stage；缺少真实 LLM Facility runner 时返回 `ARCHIVE_CANDIDATE_RUNNER_UNCONFIGURED` 并写 sanitized `seed.stage.failed`，不生成假档案候选；如果后续 runner 已自行完成持久化，activity 只接受并公开 `archive_candidate_batch_id`、model 和候选 counts，不返回 archive candidate body 或 memory body。`index_assets_activity` 已在缺少 `DATABASE_URL`/indexer 时保持 `ASSET_INDEXER_UNCONFIGURED` fail-closed；配置 DB 后默认使用 `PostgresSeedAssetIndexer`，把本 run 的 `entities`、`relationships`、`world_rule_evidence` 和 `plot_threads` 投射为 lifecycle=`seed` 的 `assets`，再从这些 seed assets upsert `global_search_index` 文档。公开 result / workflow event 只返回 `asset_index_batch_id`、indexed asset/search document counts 和 `embedding_count = 0`，不返回 search document body、embedding chunk 或 raw text；真实 vector embeddings、facets/API/UI 和 live indexing E2E 仍待实现。`finalize_seed_activity` 已接入 DB-backed `PostgresProjectReadinessUpdater`：缺少 `DATABASE_URL`/updater 时仍返回 `PROJECT_READINESS_UPDATER_UNCONFIGURED` 并写 sanitized failed event，不伪造项目 ready 状态；配置 DB 后 updater 会在 app-role/RLS context 下从同一 tenant/project/run 的 seed assets、entities、relationships 和 world rules 计数，写入 `project_readiness_snapshots`，公开 result / workflow event 只返回 `project_readiness_snapshot_id` 与 ready counts，不返回 readiness report body。parse/segment object persistence 已 live-verified；live provider E2E、扫描/OCR PDF 解析、browser full-path、更完整的语义分段策略、retry failed segments、character_agent_profile live provider E2E、archive candidate/finalize runner E2E 仍待实现。

Python `parse_file_activity` 现在接受 `application/pdf`，通过 `pypdf` 从可提取文本的 PDF 中抽取正文并写入标准 `extracted_text` object reference；公开 workflow event 只返回 artifact type/count/source id 等 metadata，不返回 PDF 原文、解析后正文、object key、hash/checksum、prompt、API key、`credential_ref`、draft 或 manuscript。PDF byte hash/checksum 只用于内部对象完整性校验或私有 artifact 持久化 metadata。activity result 中的 artifact object reference 仅用于内部 parse -> segment handoff。损坏、空文本或不可提取文本的 PDF 会以稳定 `FILE_PARSE_DECODE_FAILED` / `source object text extraction failed` fail closed；扫描件/OCR PDF 仍是后续能力。

更正：上方长段中的 `entity_resolution_activity` 与 `agent_profile_activity` 状态已由 fail-closed shell 推进为 DB-backed runner 装配路径。当前缺真实 provider/live E2E、实际 live env 执行的 profile provider harness 和 finalize/full Seed pipeline 验收，但不再把 `entity_resolution` 或 `character_agent_profile` 本身列为纯 pending shell。

Go API 现在提供 `GET /v1/projects/{projectId}/readiness` 读取最新 `project_readiness_snapshots` public metadata。该 endpoint 只信任 `X-Tenant-Id` 和 path project id；真实 Postgres reader 会先设置 app-role tenant context，再读取 snapshot id、project/run id、ready counts 和 timestamps。Next `/overview` 已通过 typed Web API client 接入该读侧，并在 Project readiness 面板展示 public counts / snapshot metadata 或显式 fail-closed error。未配置 DB reader 时返回 `PROJECT_READINESS_BACKEND_UNCONFIGURED`，缺 snapshot 返回 `NOT_FOUND`，普通 query/scan/rows failure 稳定为 `PROJECT_READINESS_QUERY_FAILED`，不公开 readiness report body、raw text、prompt、API key、`credential_ref`、draft 或 manuscript。该读侧和 UI handoff 不代表完整 live Seed E2E 已验收。

Python Seed parse/segment、sequential reading public metadata writer、runtime facts canon writer、global aggregation seed analysis writer、ontology snapshot writer、entity resolution snapshot writer、agent profile snapshot writer、archive candidate writer、seed asset indexer 和 project readiness updater 也必须按 app-role / RLS contract 执行。`PostgresWorkflowEventWriter`、`PostgresTextArtifactWriter`、`PostgresSourceFileStatusWriter`、`PostgresTextSegmentWriter`、`PostgresReadingNotesWriter`、`PostgresRuntimeFactsWriter`、`PostgresSeedAnalysisWriter`、`PostgresOntologySnapshotWriter`、`PostgresEntityResolutionSnapshotWriter`、`PostgresAgentProfileSnapshotWriter`、`PostgresArchiveCandidateWriter`、`PostgresSeedAssetIndexer` 和 `PostgresProjectReadinessUpdater` 在写 `workflow_events`、`project_text_artifacts`、`source_files.parse_status`、`text_segments`、`reading_passes`、`reading_segment_notes`、结构化 canon 表、`seed_analysis_snapshots`、`seed_ontology_snapshots`、`seed_entity_resolution_snapshots`、`seed_agent_profile_snapshots`、candidate `assets` / `archive_memories` / `archive_memory_events`、Seed `assets` / `global_search_index` 或 `project_readiness_snapshots` 前会先执行 `app_set_tenant_context(tenant_id, project_id, false)`；任一 SQL execute 或 commit failure 都必须显式 rollback，并由 activity 层转成稳定 public failure。source status writer 的普通 DB/driver exception 会稳定为 `SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED` / `source file parse status update failed`；ontology snapshot writer 的普通 DB/driver exception 会稳定为 `ONTOLOGY_SNAPSHOT_WRITE_FAILED` / `ontology snapshot write failed`；entity resolution snapshot writer 的普通 DB/driver exception 会稳定为 `ENTITY_RESOLUTION_SNAPSHOT_WRITE_FAILED` / `entity resolution snapshot write failed`；agent profile snapshot writer 的普通 DB/driver exception 会稳定为 `AGENT_PROFILE_SNAPSHOT_WRITE_FAILED` / `agent profile snapshot write failed`；archive candidate writer 的普通 DB/driver exception 会稳定为 `ARCHIVE_CANDIDATE_WRITE_FAILED` / `archive candidate write failed`；readiness updater 的普通 DB/driver exception 会稳定为 `PROJECT_READINESS_UPDATE_FAILED` / `project readiness update failed`，不透传 prompt/API key/`credential_ref` 或 raw text。这样 live object upload -> complete -> parse/segment -> sequential reading -> runtime facts -> global aggregation -> ontology -> entity resolution -> agent profile -> archive candidates -> index assets -> finalize E2E 后续在 `mirofish_app` 权限下仍按 tenant/project scope 写入，不依赖 owner connection，不留下半开事务，也不把 object key、raw text、seed analysis body、ontology body、resolution body、profile body、archive candidate body、memory body、search body、readiness report body 或 prompt/credential 材料放入公开 result/event。

阶段：

| 阶段 | Activity | 输出 |
|---|---|---|
| validate_input | Go/Python | 文件元数据、权限、配额 |
| parse_file | Python | extracted_text object |
| segment_text | Python | segments |
| chapter_detect | Python | chapter candidates |
| sequential_reading | Python LLM | reading notes |
| persist_runtime_facts | Python/Go | canon tables |
| global_aggregation | Python LLM | seed analysis |
| ontology | Python LLM | ontology |
| entity_resolution | Python LLM | merged entities |
| agent_profiles | Python LLM | character profiles |
| archive_candidates | Python LLM | candidate archives |
| index_assets | Go/Python | search/vector indexes |
| finalize | Go/Python | project readiness |

## 关键数据产物

### SourceFile

```text
source_files
  tenant_id
  file_id
  project_id
  upload_id
  object_key
  filename
  mime_type
  size_bytes
  sha256
  purpose
  parse_status
  created_by
  created_at
```

### ExtractedText

大文本存 object storage，数据库存引用：

```text
project_text_artifacts
  tenant_id
  artifact_id
  project_id
  artifact_type = extracted_text
  object_key
  char_count
  line_count
  sha256
  created_at
```

### Segments

```text
text_segments
  tenant_id
  project_id
  segment_id
  segment_order
  chapter_guess
  title_guess
  start_offset
  end_offset
  summary
  object_key 或 content_excerpt
  created_at
```

### Reading Notes

目标不再把 reading notes 只作为 JSON artifact，而是拆成结构化表和可审计 payload：

```text
reading_passes
  tenant_id
  project_id
  run_id
  pass_type
  status
  model
  created_at

reading_segment_notes
  tenant_id
  project_id
  run_id
  segment_id
  payload_json
  summary
  created_at
```

### Seed Analysis Snapshot

全局聚合正文不进入 workflow event，写入私有快照表：

```text
seed_analysis_snapshots
  tenant_id
  project_id
  run_id
  module_key = anchor_point_summary
  model_id
  analysis_jsonb
  summary_count
  segment_count
  metadata_jsonb
  created_at
```

### Seed Ontology Snapshot

`story_ontology` 输出正文不进入 workflow event，写入私有快照表：

```text
seed_ontology_snapshots
  tenant_id
  project_id
  run_id
  module_key = story_ontology
  model_id
  ontology_jsonb
  entity_type_count
  relationship_type_count
  world_rule_type_count
  metadata_jsonb
  created_at
```

结构化事实写入：

- `entities`
- `entity_aliases`
- `entity_labels`
- `entity_evidence`
- `relationships`
- `plot_threads`
- `thread_lifecycle`
- `world_rule_evidence`
- `character_events`
- `relationship_events`
- `world_events`
- `consistency_notes`
- `narrative_arcs`
- `volume_summaries`
- `segment_summaries`
- `chapter_content`
- `chapter_meta`

## LLM 模块

必须覆盖旧 `llm_module_registry.py` 中 seed 相关模块：

| 模块 key | 新职责 |
|---|---|
| `sequential_reading` | 分段顺序精读 |
| `story_ontology` | 生成故事本体 |
| `local_block_facts` | 兼容旧局部事实提取，可逐步合并到 sequential reading |
| `contextual_block_analysis` | 前情快照分析，保留为深度分析模式 |
| `anchor_point_summary` | 长文本锚点摘要；当前 `global_aggregation_activity` skeleton 先使用该模块 key |
| `entity_resolution` | 实体消歧和合并建议 |
| `character_agent_profile` | 角色 Agent 档案生成 |
| `novel_chapter_summarizer` | 章节卡生成 |
| `narrative_archives` | 生成 archive entity / memory 候选；当前 `archive_candidate_activity` skeleton 使用该模块 key |

## Prompt 与输出契约

每个 LLM activity 必须：

- 使用模块绑定选择模型。
- 输出 JSON 或 line protocol。
- 有 schema 校验。
- 有 parse/repair 记录。
- 失败时写 trace。
- 不静默返回空成功。

### Sequential Reading Output

目标输出：

```json
{
  "segment_id": "seg_001",
  "summary": "...",
  "characters": [
    {
      "name": "角色名",
      "aliases": [],
      "importance": "major",
      "state_update": "...",
      "evidence": "原文片段"
    }
  ],
  "organizations": [],
  "relationships": [],
  "plot_threads": [],
  "world_rules": [],
  "events": [],
  "consistency_notes": []
}
```

### Agent Profile Output

```json
{
  "entity_id": "ent_...",
  "name": "角色名",
  "public_profile": {
    "role": "...",
    "surface_mask": "...",
    "speech_style": "..."
  },
  "private_profile": {
    "core_drive": "...",
    "hidden_tension": "...",
    "knowledge_boundary": {}
  },
  "runtime_seed_state": {},
  "relationship_view": {},
  "memory_seed_summary": []
}
```

## 断点续传

Temporal workflow 自带 history，但业务上还要支持 stage resume：

- 已解析文件不重复解析。
- 已完成 segment 不重复调用 LLM。
- 已落库 facts 幂等 upsert。
- agent profile 按 entity 粒度续传。
- archive candidates 按 entity 粒度续传。

幂等 key：

```text
tenant_id + project_id + run_id + stage + segment_id/entity_id
```

## 错误处理

错误分类：

| 类型 | 用户可操作 |
|---|---|
| file_parse_error | 换文件或检查格式 |
| llm_module_unbound | 去 LLM Facility 绑定 |
| llm_provider_error | 重试或换渠道 |
| schema_validation_error | 查看 trace，开发修 prompt/schema |
| quota_exceeded | 升级套餐或等待额度 |
| cancelled | 可重新开始 |
| worker_crash | 可恢复 |

禁止：

- 解析失败用空文本继续。
- LLM 失败生成 mock analysis。
- JSON 缺字段就吞掉整段。

## 前端界面

Seed 入口在总览和“导入与分析”页。

### 导入与分析页

布局：

- 左侧：上传源文件、分析选项、历史 source files。
- 中央：当前 pipeline 进度。
- 右侧：阶段 trace、输出预览、错误恢复。

分析完成后展示：

- 角色/组织/关系摘要。
- 世界规则和开放线索。
- 章节/叙事阶段。
- 下一步：构建图谱、审阅资产、进入写作。

## API

### Start

```http
POST /v1/projects/{projectId}/seed-runs
```

### List

```http
GET /v1/projects/{projectId}/seed-runs
```

DB-backed list 只读取当前 tenant/project 的 `seed_pipeline` public workflow metadata；真实 app-role queryer 会先设置 tenant context，普通 query/scan/rows failure 稳定为 `WORKFLOW_QUERY_FAILED` / `seed run query failed`，不把 driver 文本、prompt、API key、`credential_ref`、object key、source/raw text、draft 或 manuscript 透给公开响应。

### Detail

```http
GET /v1/seed-runs/{runId}
```

DB-backed detail 同样只返回 tenant-scoped `seed_pipeline` public workflow metadata，非 Seed workflow id 返回 `NOT_FOUND`；query、scan 或 rows iteration failure 使用稳定 `seed run query failed` public message。

### Events

```http
GET /v1/seed-runs/{runId}/events
Accept: text/event-stream
```

DB-backed event replay 会先通过 Seed run detail 校验 run type，再读取当前 tenant/run 的 `workflow_events` public metadata；真实 app-role queryer 会先设置 tenant context，普通 query/scan/rows failure 稳定为 `WORKFLOW_EVENT_QUERY_FAILED` / `workflow event query failed`，并继续递归清洗 event payload 中的 credential、prompt/body/content、draft/manuscript 等高风险字段。

### Cancel

```http
POST /v1/seed-runs/{runId}/cancel
```

### Retry

```http
POST /v1/seed-runs/{runId}/retry
```

### 2026-07-08 Browser Upload/Start Update

Next Overview now exposes a file-first Seed entry action. The server action reads the selected browser file, derives filename, supported MIME, size and SHA-256, then calls the existing Go APIs in this order: create source upload, upload object bytes, complete upload, and start the Seed run. Each failed step redirects with a stable public status and stops before the next side effect. Unknown file types fail closed as `SOURCE_FILE_TYPE_UNSUPPORTED`; empty browser MIME is inferred only for `.txt`, `.md`, `.markdown`, and `.pdf`, and `application/octet-stream` is not used for upload admission. The Web app sets a 64 MB server-action body limit and names that limit in the UI. Overview also keeps row-scoped recovery actions so already admitted `pending` uploads can be completed and `uploaded` sources can start Seed without user-entered upload ids. Public query status and UI do not include object keys, raw text, prompt/provider data, API keys, `credential_ref`, draft, manuscript, filename, or upload id. This is a browser handoff improvement only; full browser/provider Seed E2E, sequential-reading/provider success, OCR PDF, profile/finalize runner, vector/hybrid search, and complete Seed pipeline closure remain pending.

### 2026-07-07 Status Handoff Update

Python Seed worker can now update admitted `workflow_runs.workflow_type = seed_pipeline` rows through `PostgresSeedWorkflowRunStatusWriter`. `seed_pipeline_activity` marks the run `running` after the worker accepts the run and records the sanitized pending stage event while still returning `queued` to the Temporal workflow as its internal control signal. Terminal sequential-reading failures mark the run `failed` with stable public error metadata, and successful `finalize_seed_activity` marks the run `completed` with only stage, readiness snapshot id, and ready counts. The writer uses tenant/project context under app-role/RLS and must not expose object keys, raw segment text, prompt, API keys, `credential_ref`, drafts/manuscripts, or readiness report body in public status.

## 旧功能映射

| 旧实现 | 新实现 |
|---|---|
| `SeedExtractRunner` | `SeedPipelineWorkflow` + Python activities |
| `TaskManager` task row | `workflow_runs` read model + Temporal |
| `SeedTaskProgressTracker` | workflow event writer |
| `step_trace_writer` | unified agent trace store |
| `reading_notes.json` | `reading_segment_notes` + structured tables |
| `seed_analysis` artifact | `seed_analysis_snapshots` + structured tables |
| `agent_profiles` artifact | `entities.profile_json` + `agent_dossiers` |
| retry failed segments | segment-level idempotent retry |

## 验收清单

- TXT / MD / 可提取文本的 PDF 均可上传并解析；扫描/OCR PDF 另列后续能力。
- LLM 未绑定时阻止启动。
- 长篇文本按 segment 调用，不一次塞爆上下文。
- 页面刷新后仍能看到运行中进度。
- worker 崩溃后可恢复或明确失败。
- seed 完成后资产库能看到角色/线索/规则。
- 图谱能从结构化表构建，不依赖旧 JSON 文件。
- writer 能从 seed 结果获得 POV 角色和上下文。
