# 数据库真相源矩阵

更新时间：2026-04-19（P5 合表完成）

## 目的

这份矩阵基于当前代码库实际读写路径，盘点每个业务域/业务对象的：

- 当前来源
- 目标统一表
- 当前真相源状态
- 迁移优先级
- 切换完成判定条件
- 已知 legacy 读取点

> 说明：这里的“当前来源”以代码现状为准，不以迁移计划目标为准。

## 状态图例

- **已统一**：主库已经是运行时主读写源。
- **DB 镜像 + legacy 真相**：主库有表，但运行时仍会从 JSON / 旧 SQLite / 文件系统回填或同步。
- **混合**：运行时同时依赖主库与 legacy 存储。
- **仅 legacy / 目标未落表**：当前仍直接依赖 legacy 文件，或现有 schema 尚无明确承载表。

## 真相源矩阵

| 业务域 / 对象 | 当前来源（代码证据） | 目标统一表 | 当前真相源状态 | 优先级 | 切换完成判定条件 | 已知 legacy 读取点 |
|---|---|---|---|---|---|---|
| LLM 渠道、模型缓存、模块绑定 | `LlmSettingsService` 直接通过 `LlmRepository(get_engine())` 读写主库，运行链已不读独立 SQLite（`backend/app/services/llm_settings_service.py:26-37,62-167`；`backend/app/tables/llm.py:7-10`）。但 `Config` 仍保留 `llm_facility.sqlite3` 文件名常量（`backend/app/config.py:32-35,58-61`）。 | `llm_channels` / `llm_models` / `llm_module_bindings` / `writer_presets_global` | 已统一（仅剩 legacy 常量/命名残留） | P3 | 1) 服务层不再引用 legacy 文件名语义；2) 文档/配置只指向主库；3) CRUD/绑定回归通过。 | 无直接运行时读取；仅 `backend/app/config.py:32-35,58-61` 保留 legacy 文件名常量。 |
| 任务运行时 | `TaskRepository` 直接读写 `task_runs`（`backend/app/repositories/task_repo.py:12-32`；`backend/app/tables/task.py:7`）。 | `task_runs` | 已统一 | P3 | 1) 不再存在 `task_runtime.sqlite3` 相关实现；2) task create/update/query 全部走主库；3) API 与后台任务测试通过。 | 未发现运行时 legacy 读路径；计划文档中的 `task_runtime.sqlite3` 更像历史概念。 |
| 资产库（含 project/global assets） | `AssetsService` 通过 `AssetRepository(get_engine())` 操作主库 `assets`（`backend/app/services/assets/assets_service.py:55-107,152-254`；`backend/app/tables/assets.py:7-8`）。但 `Config` 仍保留 `assets_library.sqlite3` / `project_assets.sqlite3` 文件名常量，`UnifiedAssetView` 顶部注释仍描述旧 silo（`backend/app/config.py:33-35,59-61`；`backend/app/services/assets/unified_asset_view.py:3-12`）。 | `assets` / `asset_links` | 已统一（但注释/配置漂移） | P2 | 1) 聚合层和配置不再把 assets 描述为独立 SQLite；2) 所有素材 CRUD、检索、启停、分类只经主库；3) 相关 API / service 测试通过。 | 运行时未见直接 legacy 读取；残留主要是 `backend/app/config.py` 与 `backend/app/services/assets/unified_asset_view.py:3-12` 的历史描述。 |
| 手稿块 / manuscript blocks | 手稿块已落在 `assets` 表中，`ManuscriptRepository` 明确把 `asset_type='manuscript_block'` 作为存储模型，`ManuscriptService` 通过适配器和仓库读写（`backend/app/repositories/manuscript_repo.py:1-10,60-120`；`backend/app/services/writer_agent/manuscript_service.py:17-35,53-143`）。 | `assets`（`asset_type='manuscript_block'`） | 已统一 | P2 | 1) 手稿提交/编辑/导出/检索不依赖任何单独 manuscript DB；2) chapter 关联只通过主库章节表解析；3) 手稿 API 测试通过。 | 未发现运行时 legacy 读取点。 |
| 档案库 archive records | **P5 合表完成（2026-04-19, migration 20260419_0003）**：entity 档案现在作为 `asset_type='archive_entity'` 行存在 `assets` 表；`archive_library` 独立表已 drop。`ArchiveRepository` 对外签名不变，内部查 `assets` 过滤 `asset_type`。archive 特有字段（entity_name/entity_type/core_drive/template_*等 23 列）直接加到 `assets` 表。`ArchiveLibraryService` 的 `sync_incremental` / JSON 同步路径仍保留作为 legacy 导入接口（仅 `/api/archive/library/reindex` 用）。 | `assets` (`asset_type='archive_entity'`) + `archive_sources` / `archive_agent_memory` / `archive_agent_memory_events`（卫星表保留，`archive_id` 列现在 soft FK 到 `assets.asset_id`） | 已统一 | P2 | 1) ~~档案生成流程直接写 `archive_library`~~ 档案生成直接写 `assets` ✓；2) list/get 不再先扫描 `narrative_archives.json`（仍有 reindex 入口，Phase G 清理）；3) `archive_sources` 只保留导入审计。 | `backend/app/services/archive_library_service.py:80-167, 169-220`；`backend/app/services/worldline_source_loader.py:105-112`。 |
| 档案记忆审核（candidate/canon） | 档案记忆事件/状态已有主库表（`backend/app/tables/archive.py:27-28`），统一资产视图直接读取 `archive_agent_memory`（`backend/app/services/assets/unified_asset_view.py:39,47-48`）。 | `archive_agent_memory` / `archive_agent_memory_events` | 已统一 | P1 | 1) adopt/reject/timeline 全部只读写 archive 表；2) 无额外 JSON 旁路；3) 记忆时间线测试通过。 | 未发现新的 legacy 读路径。 |
| 小说 canon 设定：实体、关系、情节线、世界规则证据 | schema 已有 `entities` / `relationships` / `plot_threads` / `world_rule_evidence` 等表（`backend/app/tables/novel.py:9-40,73,80,85-86`），多个 repo 已建立；但 seed 流程仍把同类数据回填到 `novel.sqlite3` 供旧 writer 访问（`backend/app/services/seed_extract_runner.py:115-130`），`ChapterMetaService` 取世界规则时仍直接读 `story_memory.json`（`backend/app/services/chapter_meta_service.py:205-208`）。 | `entities` / `entity_aliases` / `entity_labels` / `relationships` / `plot_threads` / `world_rule_evidence` / `thread_entity_links` / `rule_entity_links` | 混合 | P0 | 1) seed/archivist/graph/writer 全部从 repo 取 canon 数据；2) 删除 `novel.sqlite3` 回填与兼容读取；3) 世界规则不再从 `story_memory.json` 直接读取。 | `backend/app/services/seed_extract_runner.py:115-130`；`backend/app/services/chapter_meta_service.py:205-208`；`backend/app/api_fastapi/novel.py:118-122`（档案生成仍从 `agent_profiles.json` 拼输入）。 |
| 章节内容、章节卡、场景、大纲版本 | `ChapterRepository`/`ChapterMetaService` 已直接使用 `chapter_content`、`chapter_meta`、`scenes` 等主库表（`backend/app/repositories/chapter_repo.py:77-180`；`backend/app/tables/novel.py:41-67,84`）。但 `ChapterMetaService` 仍从 `chapter_segments.json` 回退取上一章正文片段（`backend/app/services/chapter_meta_service.py:307-308`），`ChapterContextPackBuilder.build_options()` 直接读 `chapter_segments.json`/`chapter_continuity.json`（`backend/app/services/chapter_context_pack_builder.py:35-59`）。 | `chapter_content` / `chapter_meta` / `scenes` / `outline_versions` | 混合 | P0 | 1) 章节列表、连续性、上一章结尾、outline 选项全部从主库生成；2) `chapter_segments.json` / `chapter_continuity.json` 仅保留导出；3) chapter-context / writer 相关测试在无 JSON 时仍通过。 | `backend/app/services/chapter_meta_service.py:307-308`；`backend/app/services/chapter_context_pack_builder.py:35-59,61-77,124-209`。 |
| Chapter Context Pack / 连续性上下文 | 当前 pack 构建强依赖 `story_memory.json`、`chapter_continuity.json`、`chapter_segments.json`，仅 worldline 分支部分会额外拼 DB/worldline 数据（`backend/app/services/chapter_context_pack_builder.py:35-59,61-77,124-209,524-525`）。现有 schema 没有“context pack 真相表”；更合理的承载应来自 `chapter_*`、`world_rule_evidence`、`plot_threads`、`world_events` 等组合查询。 | 目标应为组合查询：`chapter_content` / `chapter_meta` / `world_rule_evidence` / `plot_threads` / `world_events`（当前无专门 pack 表） | 仅 legacy / 目标未完全落表 | P0 | 1) build_options/build 在缺少上述 JSON 时仍可运行；2) 连续性摘要与 open threads 由主库聚合生成；3) 不再调用 `ProjectManager.load_project_json()` 构建 pack。 | `backend/app/services/chapter_context_pack_builder.py:35-59,524-525`；`backend/tests/test_chapter_context_pack_builder.py:213`。 |
| 本地图谱快照（节点/边/证据） | 图谱对外读取已经走 `GraphRepository` 和主库 `graph_*` 表（`backend/app/services/graph_builder.py:98-114`；`backend/app/services/local_story_graph_builder.py:37-41,93-101`；`backend/app/tables/graph.py:7-12`）。但测试与注释仍提到 `story_graph.json/.sqlite3` 产物（`backend/tests/test_local_story_graph_pipeline.py:94-98`；`backend/app/services/assets/unified_asset_view.py:5-7`）。 | `graph_meta` / `graph_nodes` / `graph_node_labels` / `graph_aliases` / `graph_edges` / `graph_evidence` | 已统一（输出侧） | P1 | 1) 运行主链不再依赖 `story_graph.sqlite3/json`；2) 旧图谱文件仅作为导出/fixture；3) 图谱查询和 API 全部走 repo。 | 测试/注释残留：`backend/tests/test_local_story_graph_pipeline.py:94-98`；`backend/app/services/assets/unified_asset_view.py:5-7`。 |
| 图谱构建输入（reading notes / story memory / continuity / ontology） | 构图前仍直接加载 `story_memory.json`、`chapter_continuity.json`、`reading_notes.json`、`seed_analysis.json`、`chapter_segments.json`，缺失时由 `reading_notes.json` 重新适配（`backend/app/services/graph_builder.py:70-84,131-138`）。 | 目标应为：`entities` / `relationships` / `world_rule_evidence` / `chapter_*` + 必要补充表；当前 schema 对 `reading_notes.json`/`ontology.json` 尚无完整承载 | 仅 legacy / 部分 schema 缺口 | P1 | 1) graph build 不再直接 load JSON；2) ontology / reading notes 若仍需保留，需有明确 DB 表或 payload 表；3) graph pipeline 在无 JSON 时可重建。 | `backend/app/services/graph_builder.py:70-84,131-138`；`backend/app/services/assets/unified_asset_view.py:675-744`。 |
| 世界线 prepare（prepare run + dossier + 事件） | prepare 生命周期本身已经入主库（`WorldlinePrepareRepository` 读写 `prepare_runs`、`prepared_agent_dossiers`、`prepare_event_log`，见 `backend/app/repositories/worldline_prepare_repo.py:1-139`；`backend/app/services/worldline_prepare_service.py:48-85`）。但 prepare 输入仍通过 `worldline_source_loader` 从 `seed_analysis.json`、`narrative_archives.json`、`parallel_world_config.json` 读取（`backend/app/services/worldline_source_loader.py:52-112`）。 | `prepare_runs` / `prepared_agent_dossiers` / `prepare_event_log` | DB 运行态 + legacy 输入 | P1 | 1) prepare 输入改由 archive / entity / graph / settings 表聚合；2) `parallel_world_config.json` 若仍保留需明确定义表；3) prepare 可在无 JSON 文件时启动。 | `backend/app/services/worldline_source_loader.py:52-112`；`backend/app/services/worldline_prepare_service.py:210-216`。 |
| 世界线 session 快照、索引、timeline 总体状态 | `WorldStateStore` 仍把 session/index 持久化到 `backend/uploads/projects/<pid>/worldlines/**` 或 `backend/uploads/system/global_worldlines/**` 下的 JSON（`backend/app/services/world_state_store.py:16-210`）。同时 `worldline_engine` 会把 session/branch/event 同步入主库（`backend/app/services/worldline_engine.py:357-448`），`WorldlineRuntimeService` 把 agent runtime 写入主库（`backend/app/services/worldline_runtime_service.py:30-60,102-203`；`backend/app/repositories/worldline_runtime_repo.py:1-218`）。 | `sessions` / `worldline_branches` / `world_events` / `agent_registry` / `agent_state_snapshots` / `agent_action_log` / `agent_dialogue_log` / `agent_episodic_memory` / `relation_state_log` | 混合 | P0 | 1) `load_session` / `list_sessions` 不再读 worldlines 目录；2) session create/step/auto-evolve 在无 worldlines 目录时仍可恢复；3) 文件系统降级为导出层；4) 删除 runtime.sqlite3 / session.json 依赖。 | `backend/app/services/world_state_store.py:22-25,50-86,132-184`；`backend/tests/test_worldline_runtime_api.py:60-61,98-99,279`。 |
| Seed artifacts：`seed_analysis.json` / `agent_profiles.json` / `narrative_archives.json` | seed 流程继续写 JSON 工件（`backend/app/services/seed_extract_runner.py:169-175,338,528`），下游世界线/档案/统一资产/API 仍直接读取（`backend/app/services/worldline_source_loader.py:88-112`；`backend/app/services/assets/unified_asset_view.py:612-744`；`backend/app/api_fastapi/novel.py:63-64,118-122`）。 | 目标应拆入 `entities` / `archive_library` / `archive_*memory*` / 补充 payload 表 | DB 镜像 + legacy 真相 | P0 | 1) seed pipeline 直接写主库结构化表；2) `agent_profiles.json`、`narrative_archives.json` 只保留导出；3) 下游服务不再直接 load 这些文件。 | `backend/app/services/worldline_source_loader.py:88-112`；`backend/app/services/assets/unified_asset_view.py:612-744`；`backend/app/api_fastapi/novel.py:63-64,118-122`。 |
| 阅读笔记、ontology、story_memory、chapter_segments、chapter_continuity | 这些 JSON 仍是 graph、chapter-context、统一资产聚合的重要输入（`backend/app/services/graph_builder.py:70-84`；`backend/app/services/chapter_context_pack_builder.py:35-59,524-525`；`backend/app/services/assets/unified_asset_view.py:675-744`）。其中 `story_memory.json` 还是世界规则直接真相源（`backend/app/services/chapter_meta_service.py:205-208`）。 | 部分已有目标表：`world_rule_evidence` / `plot_threads` / `chapter_content` / `chapter_meta`；其余需要新增补充表或 payload 表 | 仅 legacy / 部分 schema 缺口 | P0 | 1) graph/chapter-context/unified assets 都能在无这些 JSON 时运行；2) 明确每个 JSON 的主库存放位置；3) JSON 退化为导出/调试产物。 | `backend/app/services/graph_builder.py:70-84`；`backend/app/services/chapter_context_pack_builder.py:35-59,524-525`；`backend/app/services/assets/unified_asset_view.py:675-744`；`backend/app/services/chapter_meta_service.py:205-208`。 |
| Reviewer rules（审校提示） | API 直接读写 `reviewer_rules.json`，当前没有对应表（`backend/app/api_fastapi/novel.py:245-257`）。迁移计划原文也未把它列入 JSON 真相源清单。 | **当前 schema 缺口**：需要新增项目级 settings / prompt 表，或扩展现有 preset 表 | 仅 legacy / 目标未落表 | P0 | 1) reviewer prompt 不再落 JSON；2) 有明确 project-scoped DB 表；3) writer/reviewer 链路只从主库取规则。 | `backend/app/api_fastapi/novel.py:245-257`。 |
| 全局搜索索引 | `global_index` 的 `assets` / `archive` 两路镜像由 SQLite 触发器在源表写入时自动维护（migration `20260419_0001`，同步表定义见 `backend/app/tables/search.py`）；`global_index_fts` 沿原有触发器跟 `global_index` 联动。其余 source（story_graph / novel_db / worldline / seed）仍由 `GlobalSearchIndexer.reindex_project()` 手动全量物化（`backend/app/services/assets/global_search_indexer.py:46-55`）。 | `global_index` + `global_index_fts`（后续再补 pg_trgm backend） | 已统一索引表 + 两路 silo 自动同步 + 其余 silo 仍需手动 reindex | P1 | 1) 上游 unified asset 来源统一后重建索引（assets/archive 无需 reindex）；2) 搜索后端完成 SQLite/PostgreSQL 抽象；3) 其余 silo 也能做到事件驱动同步或彻底删除 reindex 入口。 | 间接 legacy 来源：`backend/app/services/assets/unified_asset_view.py:3-12,611-744`；世界线文件：`backend/app/services/world_state_store.py:16-210`。 |

## 关键结论

### 1. 已经比较接近统一的域

- **LLM 设施**：运行时基本已经完全主库化。
- **任务运行时**：已经由 `task_runs` 承载。
- **资产库 / 手稿块**：主写路径已经在统一库。
- **图谱快照输出**：对外读取已转向 `graph_*` 表。

### 2. 仍然阻塞“单一真相源”目标的核心域

- **档案库**：`archive_library` 目前更像 `narrative_archives.json` 的镜像，不是真主库。
- **章节上下文 / writer canon 数据**：`chapter_context_pack_builder`、`chapter_meta_service` 仍直接读取 `story_memory.json`、`chapter_segments.json`、`chapter_continuity.json`。
- **世界线 session 总体状态**：session/index 仍落文件系统，只有 agent runtime 日志比较像真正 DB-backed。
- **seed artifacts**：下游多个服务继续把 JSON 当成正式输入。
- **reviewer rules**：是当前计划文档漏掉的 runtime JSON 入口，且现有 schema 没有对应表。

### 3. 本次核查发现的计划级遗漏

以下运行时 JSON 在当前计划里应被显式纳入：

- `chapter_continuity.json`
- `reviewer_rules.json`

另外，以下兼容钩子说明当前仍存在 **legacy dual-write / legacy backfill**：

- `backend/app/services/seed_extract_runner.py:115-130` 仍会回填 `novel.sqlite3`
- `backend/app/services/worldline_engine.py:361-448` 仍保留“同步 worldline 到旧 writer 语义库”的兼容思路

## 推荐执行顺序

1. **P0**：worldline session 文件系统 → 主库；移除 `novel.sqlite3` 回填。
2. **P0**：chapter context / writer 读路径去 JSON 化。
3. **P0**：archive 从“JSON 镜像”切到“DB 原生写入”。
4. **P0**：为 `reviewer_rules.json`、`chapter_continuity.json` 明确建模并入迁移计划。
5. **P1**：graph build 输入去 JSON 化。
6. **P1**：搜索后端抽象与 PostgreSQL 兼容。
