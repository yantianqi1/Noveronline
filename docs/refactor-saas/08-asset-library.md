# 08. Asset Library

更新时间：`2026-07-05`

## 模块定位

资产库是小说系统的统一知识入口。它必须涵盖当前小说系统中的所有内容：

- 角色。
- 组织/势力。
- 关系。
- 世界规则。
- 剧情线。
- 伏笔。
- 事件。
- 地点。
- 文风。
- 作者素材。
- 提示词模板。
- worldline 推演路径。
- 角色控制互动记录。
- 章节、场景和手稿块。
- 审校规则和禁用词。
- Agent 生成的候选资产。

旧资产库已经有 unified asset view，但新系统要把它产品化为可审阅、可入库、可检索、可引用的资产平台。

## 旧功能覆盖

旧能力：

- `/api/assets` CRUD。
- asset search。
- batch toggle。
- batch categorize。
- asset ingestion。
- style extraction。
- unified-assets list/search/facets/sources/detail/reindex。
- archive library detail。
- archive memory panel。
- asset cards/list/kanban。
- facets：source、entity_type、category、lifecycle。

新系统必须全部覆盖。

当前 Phase 5 skeleton 已落地 `assets` 与 `global_search_index` 目标 schema/RLS，并让 Seed `index_assets_activity` 在配置 `DATABASE_URL` 时通过 `PostgresSeedAssetIndexer` 把结构化 canon 中的角色/组织、关系、世界规则和剧情线投射为 lifecycle=`seed` 的资产，再 upsert 到 `global_search_index`。Go API 已新增 `GET /v1/projects/{projectId}/assets`、`GET /v1/assets/{assetId}`、`GET /v1/projects/{projectId}/assets/facets` 和 `POST /v1/assets/search` skeleton：配置 DB 时读取 tenant/project scoped sanitized asset/search metadata，并聚合 asset type、category、lifecycle、source 和 tag facets；未配置 DB 时显式返回 `ASSET_BACKEND_UNCONFIGURED`。Go API 现在也提供 DB-backed manual CRUD：`POST /v1/projects/{projectId}/assets`、`PATCH /v1/assets/{assetId}`、`DELETE /v1/assets/{assetId}`；无 DB 时以 `ASSET_MUTATION_BACKEND_UNCONFIGURED` fail-closed，配置 DB 时只按当前 tenant/project 或 tenant/asset scope 写入，创建/更新/删除分别写 `asset.create`、`asset.update`、`asset.delete` audit log，公开响应不返回 `content_text`、prompt/response、API key、encrypted credential、`credential_ref` 或高风险 payload 字段。Next SaaS shell 已新增 `/assets` Asset Library 页面：读取资产列表、facets 和 keyword search，提供 create/update/delete、candidate adoption、bulk action、asset ingestion、reindex 和 style extraction 表单，并通过 server actions 显示显式成功或错误状态；页面不展示 credential 字段或私有 `content_text`。Go API 也已新增 `POST /v1/projects/{projectId}/asset-ingestions` 与 `GET /v1/asset-ingestions/{runId}` skeleton：缺少真实 ingestion backend 时以 `ASSET_INGESTION_BACKEND_UNCONFIGURED` fail-closed，不创建 workflow row、不伪造 candidate asset；配置 `TEMPORAL_ADDRESS` 与 `DATABASE_URL` 时会先写 tenant/project scoped `workflow_runs` 与 sanitized `workflow.queued` event，再启动 Temporal `AssetIngestionWorkflow` 到 `asset-light` 队列，公开 start response 仍只返回 run metadata。配置 DB 时 detail 读侧只返回 `workflow_type = asset_ingestion` 的公开 workflow metadata。Python Agent Runtime 已新增 `asset-light` 队列的 `AssetIngestionWorkflow` / `asset_ingestion_activity`：activity 要求 `asset_ingestion` permission 和 `asset_ingestion` module context，缺少 runner 时返回 `ASSET_INGESTION_RUNNER_UNCONFIGURED` 并写 sanitized `asset.stage.failed` event；配置 `DATABASE_URL` 和显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 时默认装配 `LLMFacilityAssetIngestionRunner`，通过 `asset_ingestion` module binding、tenant-scoped credential 解密和 OpenAI-compatible JSON client 调用真实 provider，并由 `PostgresAssetCandidateWriter` 将 schema-valid 输出 upsert 为 lifecycle=`candidate` 的 `assets`。公开 result/event 只包含 `candidate_batch_id`、candidate count、asset type counts 和可选 model id，不返回素材正文、prompt、candidate body、API key 或 `credential_ref`。Go API 已新增显式 `POST /v1/assets/{assetId}/adoptions`：无 DB 时返回 `ASSET_ADOPTION_BACKEND_UNCONFIGURED`，配置 DB 时只允许当前 tenant 下 lifecycle=`candidate` 的资产被用户动作采用为 `canon` 或 `material`，并写 `audit_logs`；响应沿用 sanitized asset metadata，不返回 `content_text`、素材正文、prompt、API key 或 credential。Go API/Next 还新增 `POST /v1/assets/bulk-actions`：无 DB 时仍以 `ASSET_BULK_ACTION_BACKEND_UNCONFIGURED` fail-closed；配置 DB 时支持显式 `enable`、`disable`、`pin`、`unpin`、`set_lifecycle` 和 `categorize` 批量操作，只更新当前 tenant/project 范围内提交的资产，写一条 sanitized `asset.bulk_action` audit log，并且公开响应只返回 project/action/status 与 matched/updated counts，不回显提交的 asset ids 或私有字段。Go API/Next 已新增 `POST /v1/projects/{projectId}/assets/reindex` shell：无真实 backend 时以 `ASSET_REINDEX_BACKEND_UNCONFIGURED` fail-closed，不创建 workflow row、不写 search index、不伪造 indexed counts；公开成功响应未来也只允许返回 run metadata。Go API/Python worker/Next 还新增 style extraction DB-backed candidate path：`POST /v1/projects/{projectId}/style-extractions` 与 `GET /v1/style-extractions/{runId}` 使用 `style_extractor` module key，Temporal+DB 时先写 tenant/project scoped `workflow_runs` 和 sanitized `workflow.queued` 再启动 `StyleExtractionWorkflow`；Python `style_extraction_activity` 要求 `style_extractor:run` permission，配置 `DATABASE_URL` 和显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 时默认装配 `LLMFacilityStyleExtractionRunner`，通过 LLM Facility 解析 `style_extractor`、解密 credential、按需用 tenant/project/source asset scoped loader 私下读取 enabled `assets.content_text`，调用 JSON provider，并把 schema-valid `style_profile` 作为 lifecycle=`candidate` / source_kind=`style_extraction` asset 持久化。公开 result/event 只包含 batch/count/type/model metadata，不公开素材正文、source asset content、prompt、提取 body、credential 或 API key；hybrid/vector search、向量 embeddings、live provider E2E 和 live DB-backed bulk/reindex browser 验收仍 pending。

Archive Memory read/review side 已补齐最小 skeleton：`infra/postgres/migrations/0001_core_saas.sql` 新增 `archive_memories` 与 `archive_memory_events`、tenant RLS 和 project/asset 查询索引；Python Seed `archive_candidate_activity` 在配置 `DATABASE_URL` 与显式 `LLM_CREDENTIAL_ENCRYPTION_KEY` 时可通过 `narrative_archives` module binding 持久化 candidate archive assets、candidate memories 和 candidate memory events；Go API 新增 `GET /v1/archive-assets/{assetId}/memories?project_id={projectId}` 与 `/memory-events`，只返回 tenant/project/asset-scoped 公开摘要和 sanitized payload，并新增 explicit memory adoption/rejection mutation；Next Asset Library 新增 Archive Memory review panel 和 Adopt / Reject memory 表单。公开 API / workflow result 不返回 `body_text`、`content_text`、source material、archive candidate body、memory body、prompt/response、API key、encrypted credential 或 `credential_ref`；live provider E2E 和 full reviewer workflow 仍待后续实现。

## 资产类型

### Canon Assets

来自项目正典数据：

- `character`
- `organization`
- `relationship`
- `world_rule`
- `plot_thread`
- `event`
- `location`
- `chapter`
- `scene`
- `manuscript_block`

### Agent Assets

由 Agent 生成，默认 candidate：

- `archive_entity`
- `character_agent_profile`
- `bond_candidate`
- `plot_thread_candidate`
- `worldline_path`
- `interaction_record`
- `review_issue`
- `style_profile`

### User Materials

用户手动导入：

- `writing_style`
- `worldview`
- `character_archetype`
- `plot_template`
- `prompt_template`
- `note`
- `forbidden_lexicon`
- `reference_doc`

## 生命周期

```text
seed
candidate
canon
material
simulation
draft
manuscript
archived
```

解释：

- `seed`：来自初始分析。
- `candidate`：Agent 生成但未确认。
- `canon`：已被用户采用为正典。
- `material`：可引用素材，不直接等于正典。
- `simulation`：worldline 或角色控制产生的实验内容。
- `draft`：草稿。
- `manuscript`：进入手稿。
- `archived`：不活跃但保留。

## 标准资产格式

所有资产必须可统一检索：

```json
{
  "asset_id": "ast_...",
  "tenant_id": "ten_...",
  "project_id": "proj_...",
  "asset_type": "world_rule",
  "category": "world",
  "lifecycle": "canon",
  "title": "灵气不能凭空生成",
  "summary": "世界规则摘要",
  "content": "长文本内容或原始素材",
  "payload": {},
  "tags": ["世界规则", "修炼"],
  "source": {
    "kind": "seed_pipeline",
    "ref": "run_..."
  },
  "links": [],
  "permissions": {},
  "created_by": "usr_...",
  "created_at": "...",
  "updated_at": "..."
}
```

## Asset Ingestion Agent

用户明确要求：资产库需要依靠 Agent，把新资产按设定好的标准格式入库。

### 流程

```text
用户粘贴/上传素材
  -> 选择项目/全局范围
  -> 可选 hint type
  -> AssetIngestionWorkflow
  -> Python asset_ingestion Agent 抽取结构
  -> schema validation
  -> candidate asset preview
  -> 用户编辑/确认
  -> asset canon/material 入库
  -> search/vector index
```

### 支持 hint type

继承旧系统：

- writing_style
- worldview
- character_archetype
- world_rule
- plot_template
- prompt_template
- note

新增：

- relationship
- plot_thread
- location
- scene_seed
- interaction_record
- reviewer_rule
- forbidden_lexicon

### Agent 输出要求

```json
{
  "asset_type": "world_rule",
  "title": "8-30 字标题",
  "summary": "1-3 句摘要",
  "category": "world",
  "lifecycle": "candidate",
  "tags": [],
  "payload": {
    "rule_name": "...",
    "statement": "...",
    "scope": "...",
    "exceptions": []
  },
  "confidence": 0.82,
  "needs_review": true
}
```

## 资产库页面

### Layout

```text
Header
  search
  create / ingest
  reindex
  view mode

Left Facets
  project
  category
  lifecycle
  source
  type
  tags
  updated range

Center Result
  card/list/kanban/table

Right Detail Drawer
  summary
  payload
  links
  evidence
  usage
  memory
  trace
```

### View Modes

覆盖旧：

- Cards。
- List。
- Kanban。

新增建议：

- Table：适合批量审阅。
- Graph-linked：显示和图谱节点关系。

### Facets

必须保留：

- source。
- entity type。
- category。
- lifecycle。

新增：

- project。
- owner。
- tags。
- used by writer。
- has memory。
- needs review。

## Archive Entity

旧 archive_library 已并入 assets，目标系统继续采用资产化档案：

`asset_type = archive_entity`

关键字段：

- entity_uuid。
- entity_name。
- entity_type。
- agent_kind。
- importance_tier。
- core_drive。
- surface_mask。
- hidden_tension。
- relationship_summary。
- agent_behavior_hint。
- template_key。
- template_sections_json。

档案记忆保留独立表：

- archive_memories。
- archive_memory_events。

## 搜索

### Keyword Search

Postgres full text search：

- title。
- summary。
- content。
- tags。
- payload text projection。

### Semantic Search

pgvector：

- asset embeddings。
- archive memory embeddings。
- manuscript block embeddings。
- worldline event embeddings。

### Hybrid Search

排序：

```text
keyword score
+ vector score
+ recency boost
+ lifecycle boost
+ project relevance
+ user pinned boost
```

## API

### List

```http
GET /v1/projects/{projectId}/assets
```

### Detail

```http
GET /v1/assets/{assetId}
```

当前 skeleton 只按 `X-Tenant-Id` 与 `assetId` 读取 sanitized asset metadata。响应不包含 `content_text`、原始正文、object key、prompt/response、API key、`encrypted_api_key` 或 `credential_ref`。

### Facets

```http
GET /v1/projects/{projectId}/assets/facets
```

当前 skeleton 从 `assets` 表按 `asset_type`、`category`、`lifecycle`、`source_kind` 和 `tags_jsonb` 聚合计数，只返回 `{value, count}` bucket。Tag facets 只在 `tags_jsonb` 是数组时展开 tag 值；它不读取 `content_text`、payload body、原始正文、object key、prompt/response 或 credential material。

### Search

```http
POST /v1/assets/search
```

请求：

```json
{
  "project_id": "proj_...",
  "query": "主角师门规则"
}
```

当前 skeleton 只实现 tenant/project scoped keyword search，不接受 body tenant 作为真相源。Go read side 在 app-role/RLS path 下设置 tenant context 后读取 `global_search_index`，并为 asset search result 补充 public `version` summary 与 `collections` refs。公开响应只返回 title、sanitized search document metadata、tags、payload、version/collection metadata 和 timestamps，不返回 `global_search_index.body`、asset `content_text`、body/content/raw text；payload 会递归移除 prompt/response/body/content/raw text/object key/API key/credential/draft/manuscript 等高风险键及变体。`filters`、`mode = hybrid` 和 vector rerank 仍属于后续搜索增强；基础 facets 已由 `GET /v1/projects/{projectId}/assets/facets` 覆盖。

### Ingest

```http
POST /v1/projects/{projectId}/asset-ingestions
GET /v1/asset-ingestions/{runId}
```

当前 skeleton 冻结公网 contract 和 fail-closed 行为。`POST` 会解析 `X-Tenant-Id`、path project、actor 和 request context，并把素材正文只交给已配置 backend；默认 backend 返回 `ASSET_INGESTION_BACKEND_UNCONFIGURED`，不得伪造 queued success 或 candidate asset。配置 `TEMPORAL_ADDRESS` 与 `DATABASE_URL` 时，Go starter 会先持久化 `workflow_runs` 和 sanitized `workflow.queued` event，再启动 Temporal `AssetIngestionWorkflow` 到 `asset-light` 队列；admission 写入失败返回 `WORKFLOW_ADMISSION_FAILED` 且不启动 Temporal。`GET` 仅返回公开 workflow metadata，并隐藏非 `asset_ingestion` workflow id。Python runtime 侧的 `AssetIngestionWorkflow` / `asset_ingestion_activity` 在 DB 与 credential key 配置齐全时可通过 LLM Facility 调用 JSON provider，并把 schema-valid candidates 持久化到 `assets.lifecycle = candidate`；公开 workflow result/event 仍只返回 batch/count/type metadata，不返回素材正文、candidate body、prompt 或 credential。

### Style Extraction

```http
POST /v1/projects/{projectId}/style-extractions
GET /v1/style-extractions/{runId}
```

当前 skeleton 冻结 style extraction 的公网 contract 和 fail-closed 行为。`POST` 会解析 `X-Tenant-Id`、path project、actor、request、run 和 trace context，接受 `material_text` 或 `source_asset_id`，并只把素材交给已配置 backend；默认 backend 返回 `STYLE_EXTRACTION_BACKEND_UNCONFIGURED`，不得伪造 queued success 或 `style_profile` asset。配置 `TEMPORAL_ADDRESS` 与 `DATABASE_URL` 时，Go starter 会先持久化 `workflow_runs` 和 sanitized `workflow.queued` event，再启动 Temporal `StyleExtractionWorkflow` 到 `asset-light` 队列；admission 写入失败返回 `WORKFLOW_ADMISSION_FAILED` 且不启动 Temporal。`GET` 仅返回公开 `workflow_type = style_extraction` metadata，并隐藏非 style extraction workflow id。Python runtime 侧的 `StyleExtractionWorkflow` / `style_extraction_activity` 要求 `style_extractor:run` permission 和 `style_extractor` module context；缺少 runner 时返回 `STYLE_EXTRACTION_RUNNER_UNCONFIGURED` 并写 sanitized failed event。配置 DB 与显式 credential key 后，默认 runner 会通过 `style_extractor` module binding 调用 JSON provider，schema-validate `style_profile`，并写入 candidate asset；当仅提供 `source_asset_id` 时，runner 先通过 tenant/project scoped loader 读取 enabled `assets.content_text`，缺失、跨租户/项目或空内容返回 `STYLE_SOURCE_MATERIAL_UNAVAILABLE` 且不调用 provider。公开 result/event 仍只返回 `candidate_batch_id`、candidate count、asset type counts 和可选 model id，不公开素材正文、source asset content、prompt、credential、提取 body 或样本文本。live provider E2E 仍待后续实现。

### Adopt Candidate

```http
POST /v1/assets/{assetId}/adoptions
```

当前 Go API 已实现显式采用 skeleton。请求必须携带 `X-Tenant-Id`，body 只接受 `target_lifecycle = canon | material`；body tenant 不作为真相源。默认无 DB 时返回 `ASSET_ADOPTION_BACKEND_UNCONFIGURED`，DB-backed path 使用 tenant + asset id + `lifecycle = candidate` 条件更新，非 candidate 或跨 tenant asset 返回 `NOT_FOUND`，并写 `asset.adopt` audit log。响应只返回公开 asset metadata，不返回 `content_text`、candidate body、prompt/response 或 credential material。

### Reindex

```http
POST /v1/projects/{projectId}/assets/reindex
```

当前 Go API / Next shell 已实现 reindex 入口。请求必须携带 `X-Tenant-Id`，body tenant 不作为真相源；`scope` 默认为 `project`，`mode` 默认为 `keyword`，options 会清理 prompt/body/content/credential 等高风险字段后交给 backend。默认无真实 backend 时返回 `ASSET_REINDEX_BACKEND_UNCONFIGURED`，不得创建 workflow row、写 `global_search_index`、伪造 indexed counts 或返回 raw text/search body/embedding chunk。配置 `TEMPORAL_ADDRESS` 与 `DATABASE_URL` 时，Go starter 会先写 tenant/project scoped `workflow_runs` 和 sanitized `workflow.queued` event，再启动 `AssetReindexWorkflow` 到 `asset-light` 队列；admission 失败返回 `WORKFLOW_ADMISSION_FAILED` 且不启动 Temporal。Python `asset_reindex_activity` 要求 `asset_reindex:run` permission 和 `asset_reindex` module context；缺少 DB reindexer 时返回 `ASSET_REINDEXER_UNCONFIGURED` 并写 sanitized failed event。配置 DB 时默认 `PostgresAssetReindexer` 执行 project/keyword reindex，从 tenant/project scoped `assets` 重建 `global_search_index` 的 `asset` 文档，公开 result/event 只返回 `reindex_batch_id`、asset/search document counts 和 `embedding_count = 0`，不返回 `content_text`、search body、embedding chunk、prompt 或 credential。向量 embeddings、hybrid ranking 和 live DB-backed browser/E2E 验收仍待后续完成。

## 旧功能映射

| 旧功能 | 新设计 |
|---|---|
| `assets` CRUD | Project/Tenant asset API |
| `unified_assets` | Asset read model + hybrid search |
| `classification_map` | category/lifecycle classifier table |
| asset ingestion | AssetIngestionWorkflow |
| style extraction | StyleExtractionWorkflow + style_profile asset |
| archive detail | Asset detail for `archive_entity` |
| archive memory | Asset memory tab |
| batch toggle/categorize | bulk actions |
| reindex | index workflow |

## 验收清单

- 资产库能看到 seed 角色、关系、规则、线索。
- 能手动粘贴素材并由 Agent 入库。
- 入库结果符合 schema，不合格进入错误状态。
- 能按来源/类型/生命周期过滤。
- 能查看 archive memory。
- 能搜索 manuscript block。
- 能把 worldline path 保存为 simulation asset。
- writer 能检索 asset library。
- 不同 tenant 资产完全隔离。
