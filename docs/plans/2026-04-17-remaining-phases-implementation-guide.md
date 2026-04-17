# 剩余 Phase 实施详细指南（基于 2026-04-16~17 深度调研）

**创建日期：** 2026-04-17
**前置基线：** HEAD = `701b067`（Phase D Task 3 完成后）
**测试基线：** 429 passed / 4 skipped / 0 failed（偶现 flake：`test_graph_build_task_state` 或 `test_local_story_graph_pipeline`，1/3 频率，非回归）
**分支：** gemini

---

## 一、整体进度速查

| Phase | Task | 状态 | 安全锚 | 完成 commit |
|---|---|---|---|---|
| Phase B (test infra) | — | ✅ 完成 | `pre-phase-b-20260416` | `225274e` |
| Phase A (C2/C3/C4) | — | ✅ 完成 | `pre-phase-a-20260416` | `c2d2278`/`531647f`/`7c80058` |
| Phase C (测试修复) | — | ✅ 完成 | `pre-phase-c-20260416` | `d020f94`~`67a63c9` |
| Phase D / Task 3 | Alembic 正式化 | ✅ 完成 | `pre-phase-d-task3-20260416` | `7bfbafb` |
| **Phase D / Task 11** | **迁移校验器扩展** | ⏸ 未开始 | — | — |
| **Phase D / Task 4** | **分域迁移器框架** | ⏸ 未开始 | — | — |
| **Phase E / Task 6** | **worldline 数据库化** | ⏸ 未开始 | — | — |
| **Phase F / Task 7** | **archive/assets/llm 切主库** | ⏸ 未开始 | — | — |
| **Phase G / Task 8** | **novel/graph/seed 读路径切库** | ⏸ 未开始 | — | — |
| **Phase H / Task 9** | **搜索抽象** | ⏸ 未开始 | — | — |

**推荐执行顺序：** Task 11 → Task 4 → Task 6 → Task 7 → Task 8 → Task 9
（Task 11 + Task 4 可并行；Task 7 + Task 8 + Task 9 互相独立可并行。）

---

## 二、调研成果汇总（2026-04-16 三组 agent 并行调研）

### 2.1 统一数据库表清单（`backend/app/tables/` 中 `metadata.tables`）

当前 unified schema 包含以下表（均已通过 `alembic upgrade head` 或 `metadata.create_all` 可创建）：

- **小说/实体域**：`entities`, `entity_aliases`, `entity_labels`, `entity_evidence`, `relationships`, `relationship_events`, `plot_threads`, `thread_lifecycle`, `world_rule_evidence`, `consistency_notes`, `character_events`
- **章节/内容域**：`chapter_content`, `chapter_meta`, `scenes`, `outline_versions`, `manuscripts`, `presets`, `sessions` (writer)
- **叙事/分析域**：`narrative_arcs`, `volume_summaries`, `segment_summaries`, `book_plans`
- **图谱域**：`graph_nodes`, `graph_edges`
- **资产域**：`assets`, `asset_links`, `global_index`
- **档案域**：`archive_library`, `archive_sources`, `archive_agent_memory`
- **LLM 设施域**：`llm_channels`, `llm_bindings`
- **世界线域**：`prepare_runs`, `prepared_agent_dossiers`, `prepare_event_log`, `agent_registry`, `agent_state_snapshots`, `agent_action_log`, `agent_dialogue_log`, `relation_state_log`, `agent_episodic_memory`
- **任务域**：`task_runs`
- **项目域**：`project_meta`
- **FTS 虚表**：`entities_fts`, `chapter_content_fts`, `scenes_fts`, `assets_fts`, `global_index_fts` 等 16 个（仅 SQLite）

### 2.2 Legacy 存储源清单

#### 2.2.1 Per-Project Legacy SQLite（位于 `uploads/projects/<pid>/`）

| 文件名 | 包含表（与 unified 同名） | 服务层拥有者 | 迁移器当前状态 | 校验器当前状态 |
|---|---|---|---|---|
| `novel.sqlite3` | entities, relationships, entity_aliases, entity_labels, entity_evidence, plot_threads, etc. | ProjectManager / SeedExtractRunner | ✅ 已有（Task 4 现有 `_copy_database`） | ✅ 已有（Task 11 DOMAIN_SOURCES） |
| `story_graph.sqlite3` | graph_nodes, graph_edges | GraphBuilder / LocalStoryGraphStorage | ✅ 已有 | ✅ 已有 |
| `project_assets.sqlite3` | assets (per-project subset) | AssetsService | ❌ 缺失 | ❌ 缺失 |
| `worldlines/runtime.sqlite3` | agent_registry, agent_action_log, agent_dialogue_log, etc. | WorldlineRuntimeService | ❌ 缺失 | ❌ 缺失 |

#### 2.2.2 Global/System Legacy SQLite（位于 `uploads/system/`）

| 文件名 | 包含表（与 unified 同名） | 服务层拥有者 | 迁移器当前状态 | 校验器当前状态 |
|---|---|---|---|---|
| `llm_facility.sqlite3` | llm_channels, llm_bindings | LlmModuleRegistry | ❌ 缺失 | ❌ 缺失 |
| `archive_library.sqlite3` | archive_library, archive_sources, archive_agent_memory | ArchiveLibraryService | ❌ 缺失 | ❌ 缺失 |
| `assets_library.sqlite3` | assets (global), asset_links | AssetsService (global) | ❌ 缺失 | ❌ 缺失 |

#### 2.2.3 Per-Project Legacy JSON（通过 `ProjectManager.load_project_json()` 读取）

共 20+ 个 JSON 文件仍在运行时被读取（详见 §四 Task 4 实施细节），主要有：

| 文件名 | 主要消费方 | 对应 unified 表 |
|---|---|---|
| `seed_analysis.json` | chapter_context_pack_builder, worldline_source_loader | project_meta.seed_analysis_json / 待确认 |
| `reading_notes.json` | unified_asset_view | segment_summaries / narrative_arcs / 待确认 |
| `agent_profiles.json` | novel.py, unified_asset_view | archive_library / entities 扩展 |
| `ontology.json` | unified_asset_view | project_meta.ontology_json / 待确认 |
| `story_memory.json` | chapter_meta_service | various narrative tables |
| `chapter_segments.json` | chapter_context_pack_builder, chapter_meta_service | chapter_content / chapter_meta |
| `chapter_continuity.json` | chapter_context_pack_builder | chapter_meta 扩展 |
| `reviewer_rules.json` | novel.py | world_rule_evidence / 待确认 |
| `narrative_archives.json` | archive_library_service, unified_asset_view | archive_library |
| 其他 11 个 | 各 service | 待映射 |

### 2.3 Repository 层 Upsert API 可复用性

`backend/app/repositories/base.py` 提供通用 `upsert_by_keys(project_id, values, keys)` 方法，所有 `ProjectScopedRepository` 子类继承。具体可复用：

| 仓库 | 可复用方法 |
|---|---|
| `entity_repo.py` | `upsert_entity()`, `upsert_alias()`, `upsert_label()` |
| `relationship_repo.py` | `upsert_relationship()` |
| `graph_repo.py` | 仅有 `_insert*()` 内部方法 |
| `archive_repo.py` | `upsert_archive()`, `upsert_source()`, `upsert_memory()` |
| `asset_repo.py` | `upsert_link()` |
| `llm_repo.py` | `upsert_channel()`, `upsert_binding()` |
| `narrative_repo.py` | `upsert_narrative_arc()`, `upsert_volume_summary()`, `upsert_segment_summary()`, `upsert_consistency_note()` |
| `thread_repo.py` | `upsert_thread()` |
| `world_rule_repo.py` | `upsert_world_rule()` |
| `scene_repo.py` | `upsert_scene()` |

### 2.4 Worldline 持久化现状（Phase E 调研重点）

**已在 unified DB 的（不需要迁移）：**
- Prepare 工作流：`prepare_runs`, `prepared_agent_dossiers`, `prepare_event_log` — WorldlinePrepareRepository 已全面 DB 化
- Agent 运行态：`agent_registry`, `agent_state_snapshots`, `agent_action_log`, `agent_dialogue_log`, `relation_state_log`, `agent_episodic_memory` — WorldlineRuntimeRepository 已全面 DB 化
- Agent 记忆：`AgentMemoryService` 100% DB 化

**仍在文件系统的（需要迁移）：**
- **Session 元数据**：`WorldStateStore` 100% 文件系统，写 `sessions/<session_id>/session.json` + `index.json`
- **Engine 写入**：`WorldlineEngine.create_session/step/queue_action` 各处调 `store.save_session(container_dir, session)`，共 3 个写入点
- **Prepare 启动**：`WorldlinePrepareService.start_session()` 调 `engine.store.save_session()`，1 个写入点
- **资产聚合**：`unified_asset_view.read_worldline()` 扫描文件系统 sessions 目录（且路径逻辑有 bug，期望 `sessions/<sid>.json` 但实际是 `sessions/<sid>/session.json`）

**文件系统路径布局：**
```
uploads/projects/<pid>/worldlines/
  index.json                              # session 元数据索引
  sessions/<session_id>/session.json      # WorldlineSession 序列化（50~500KB）

uploads/system/global_worldlines/
  mixed/worldlines/sessions/...           # 不绑项目的 session
  graphs/<graph_id>/worldlines/sessions/  # 按图绑定的 session
```

**迁移核心动作**：新增 `worldline_sessions` 表 → `WorldStateStore` 改为 DB read/write → `WorldlineEngine` 3 处 save_session 改走 DB → `unified_asset_view.read_worldline` 改为查 DB → fileless smoke test

---

## 三、Phase D / Task 11（迁移校验器扩展）实施细节

**目标**：扩展 `MigrationVerifier` 覆盖所有 legacy 域，支持 global 级校验。

**修改文件：**
- `backend/app/services/migration_verifier.py` — 扩展 DOMAIN_SOURCES + 新增 global 验证
- `backend/scripts/verify_project_migration.py` — 新增 `--include-global` 参数
- `backend/tests/test_migration_verifier.py` — 新增域测试

**实施步骤：**

### Step 1：扩展 DOMAIN_SOURCES（per-project）
```python
DOMAIN_SOURCES = {
    "novel": "novel.sqlite3",
    "story_graph": "story_graph.sqlite3",
    "project_assets": "project_assets.sqlite3",       # 新增
    "worldline_runtime": "worldlines/runtime.sqlite3", # 新增（子目录路径）
}
```

### Step 2：新增 GLOBAL_SOURCES + verify_global()
```python
GLOBAL_SOURCES = {
    "llm_facility": "llm_facility.sqlite3",
    "archive_library": "archive_library.sqlite3",
    "assets_library": "assets_library.sqlite3",
}
```
- `verify_global(upload_root)` 方法：遍历 GLOBAL_SOURCES，路径为 `upload_root / "system" / filename`
- Global 表没有 project_id，所以 `_source_tables` 需要跳过 project_id 过滤
- 可以新增 `_source_tables_global(connection)` 只检查表名是否在 metadata 中，不要求 project_id

### Step 3：扩展 _legacy_source_report
添加 `project_assets`, `worldline_runtime_db`, `llm_facility_db`, `archive_library_db`, `assets_library_db` 的 `exists`/`path` 条目。

### Step 4：CLI 更新
`verify_project_migration.py` 新增 `--include-global` flag，当设置时调用 `verify_global()` 合并到报告中。

### Step 5：测试
1. `test_verify_project_assets_domain` — fabricate project_assets.sqlite3 with assets 表
2. `test_verify_global_llm_domain` — fabricate llm_facility.sqlite3 with llm_channels 表
3. `test_verify_global_archive_domain` — fabricate archive_library.sqlite3
4. 确保 `--include-global` CLI 路径能跑通

**关键设计决策：**
- Global 表的比较策略：全行比较（不按 project_id 分片，因为 global 表无此列）
- JSON 文件的校验暂缓——Task 8 实施完毕后可按需追加
- 现有 `verify_project()` 不改签名——`verify_global()` 独立返回报告

**预估改动量：** migration_verifier.py +50 行, verify_project_migration.py +15 行, test +80 行

---

## 四、Phase D / Task 4（分域迁移器框架）实施细节

**目标**：把 monolithic `migrate_legacy_data.py` 拆为多域驱动 + 新增 JSON 源迁移。

**新增文件：**
```
backend/scripts/migrations/
  __init__.py
  base.py             — MigrationContext dataclass + BaseDomainMigrator ABC
  migrate_novel.py    — novel.sqlite3 → entities/relationships/evidence/...
  migrate_graph.py    — story_graph.sqlite3 → graph_nodes/graph_edges
  migrate_archive.py  — archive_library.sqlite3 (global) → archive_library/sources/memories
  migrate_assets.py   — assets_library.sqlite3 (global) + project_assets.sqlite3 (per-proj) → assets/asset_links
  migrate_llm_facility.py — llm_facility.sqlite3 (global) → llm_channels/llm_bindings
  migrate_worldline.py    — worldlines/runtime.sqlite3 (per-proj) → agent_registry/action_log/dialogue_log/...
  migrate_seed_json.py    — seed_analysis.json + ontology.json + chapter_segments.json + ... → project_meta/narrative tables
```

**修改文件：**
- `backend/scripts/migrate_legacy_data.py` — 改为 orchestrator，导入各域 migrator 并按序执行
- `backend/tests/test_full_legacy_migration.py` — 新增

**实施步骤：**

### Step 1：定义 MigrationContext + BaseDomainMigrator
```python
# backend/scripts/migrations/base.py
@dataclass
class MigrationContext:
    upload_root: Path
    engine: Engine
    project_id: str | None = None  # None = global
    dry_run: bool = False
    replace_project: bool = False
    report: dict = field(default_factory=dict)

class BaseDomainMigrator(ABC):
    domain_name: str
    @abstractmethod
    def migrate(self, ctx: MigrationContext) -> dict[str, int]: ...
```

### Step 2：每域迁移器实现

核心逻辑复用现有 `_copy_database()` / `_copy_table()` 模式。每个域迁移器：
1. 构造 source_path（per-project: `ctx.upload_root / "projects" / ctx.project_id / filename`；global: `ctx.upload_root / "system" / filename`）
2. 打开 source sqlite3
3. 遍历 `_copyable_tables()`（已有通用逻辑）
4. 对每张表执行 `_copy_table()`（幂等：先 DELETE WHERE project_id = ? 再 INSERT）
5. 收集 counts

对于 `migrate_seed_json.py`（JSON 源迁移），逻辑不同：
1. 用 `ProjectManager.load_project_json(filename)` 读取 JSON
2. 按 JSON 结构提取字段
3. 通过 repository `upsert_*()` 写入 unified DB
4. 收集 counts

### Step 3：Orchestrator 重写
`migrate_legacy_data.py` 改为：
```python
MIGRATORS = [
    NovelMigrator(), GraphMigrator(), ArchiveMigrator(),
    AssetsMigrator(), LlmFacilityMigrator(), WorldlineMigrator(),
    SeedJsonMigrator(),
]

def migrate_all(upload_root, database_url=None, dry_run=False):
    ctx = MigrationContext(upload_root=upload_root, engine=..., dry_run=dry_run)
    for project_dir in _project_dirs(upload_root):
        ctx.project_id = project_dir.name
        for migrator in MIGRATORS:
            if migrator.is_project_scoped:
                migrator.migrate(ctx)
    # Global migrators
    for migrator in MIGRATORS:
        if not migrator.is_project_scoped:
            migrator.migrate(ctx)
    return ctx.report
```

### Step 4：测试
`test_full_legacy_migration.py`:
1. 构造 `tmp_path / uploads / projects / proj_test /` 下放置最小 legacy sqlite + JSON fixtures
2. 构造 `tmp_path / uploads / system /` 下放置 global legacy sqlite
3. 运行 `migrate_all(tmp_path / "uploads", db_url)`
4. 断言 unified DB 各表行数
5. 运行 `MigrationVerifier.verify_project()` 断言 verdict == "pass"

**关键设计决策：**
- 幂等性：先 DELETE WHERE project_id = ? 再 INSERT（与现有逻辑一致）
- dry_run 模式：只统计不写入
- JSON 迁移器先做 seed_analysis + ontology + chapter_segments 三个最核心的；其余 JSON 按需追加
- replace_project 开关控制是否跳过已存在数据

**预估改动量：** 新增 ~500 行代码 + ~150 行测试

---

## 五、Phase E / Task 6（worldline 数据库化）实施细节

**目标**：消除 worldline 的文件系统真相源依赖，session 元数据迁入 unified DB。

**前提发现（Phase C + 调研确认）：**
- Prepare 3 表已 DB 化 ✅
- Runtime 6 表已 DB 化 ✅
- AgentMemoryService 100% DB 化 ✅
- **唯一缺口**：session 元数据（`session.json` + `index.json`）仍全走文件系统

### Step 1：新增 worldline_sessions 表

在 `backend/app/tables/worldline.py` 新增：
```python
worldline_sessions = Table(
    "worldline_sessions", metadata,
    Column("session_id", String, primary_key=True),
    Column("project_id", String, nullable=True),   # global sessions 可无 project
    Column("graph_id", String, nullable=True),
    Column("session_scope", String, nullable=False, server_default="project"),
    Column("title", String, nullable=True),
    Column("status", String, nullable=False, server_default="active"),
    Column("focus_question", Text, nullable=True),
    Column("branch_count", Integer, nullable=False, server_default="1"),
    Column("world_variables_json", Text, nullable=True),
    Column("timeline_steps", Integer, nullable=False, server_default="12"),
    Column("session_data_json", Text, nullable=False),  # 完整 session 序列化
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)
```

### Step 2：新增 Alembic revision
```bash
alembic revision -m "add worldline_sessions table"
```

### Step 3：新增 WorldlineSessionRepository
`backend/app/repositories/worldline_session_repo.py`:
- `save_session(session_id, data)` — upsert
- `load_session(session_id)` → dict
- `list_sessions(project_id=None, graph_id=None, limit=50)` → list[dict]
- `delete_session(session_id)`

### Step 4：重写 WorldStateStore
将 13 个方法从文件 I/O 改为调用 WorldlineSessionRepository：
- `save_session(container_dir, session)` → `repo.save_session(session.session_id, session.to_dict())`
- `load_session(session_id, ...)` → `repo.load_session(session_id)`
- `list_sessions(...)` → `repo.list_sessions(project_id=..., graph_id=...)`
- 移除所有 `_sessions_root`, `_session_dir`, `_session_file`, `_index_file` 路径构建方法
- `container_dir` 参数保留但标记 deprecated（兼容期内仍向下传递但不使用）

### Step 5：更新 WorldlineEngine 写入点
3 处 `self.store.save_session(container_dir, session)` 调用无需改动——因为 WorldStateStore 内部已改 DB。但删除 container_dir 的传入如果方便的话。

### Step 6：修复 unified_asset_view.read_worldline()
当前代码扫描文件系统，且路径逻辑有 bug。改为：
```python
def read_worldline(self, project_id: str | None) -> list[UnifiedAsset]:
    if not project_id:
        return []
    from app.repositories.worldline_session_repo import WorldlineSessionRepository
    repo = WorldlineSessionRepository()
    sessions = repo.list_sessions(project_id=project_id)
    return [UnifiedAsset(silo="worldline", ..., payload=s) for s in sessions]
```

### Step 7：fileless smoke test
`backend/tests/test_worldline_fileless_restore.py`:
1. 不创建任何 worldlines/ 目录
2. 调用 `WorldlineEngine.create_session()`
3. 调用 `WorldlineEngine.step()`
4. 调用 `WorldlineEngine.list_sessions()`
5. 断言所有操作成功且查询 DB 确认数据存在

**关键设计决策：**
- `session_data_json` 存完整序列化——避免过早拆列，session 结构变化频率高
- `container_dir` 参数 deprecated 但不立即删（Phase G 或 Task 12 再收口）
- Global sessions 用 `project_id IS NULL` 区分
- 现有 worldline 测试大部分已在 Phase C 修改为查 unified DB，本 phase 重点是 session 元数据层

**预估改动量：** 新增 ~250 行 + 修改 ~150 行 + 新增 ~100 行测试

**子 Phase 拆分：**
- E-1：worldline_sessions 表 + repository（最小可提交）
- E-2：WorldStateStore 切 DB + WorldlineEngine 跟进
- E-3：unified_asset_view 修复 + fileless smoke test

---

## 六、Phase F / Task 7（archive/assets/llm 切主库）实施细节

**目标**：去掉对 `archive_library.sqlite3` / `assets_library.sqlite3` / `project_assets.sqlite3` / `llm_facility.sqlite3` 的运行时依赖。

**需修改的 service 文件：**
- `backend/app/services/archive_library_service.py` — 查找 `archive_library.sqlite3` 或 `Config.ARCHIVE_LIBRARY_DB_*` 引用，改为 `ArchiveRepository` 调用
- `backend/app/services/assets/assets_service.py` — 查找 `assets_library.sqlite3` / `project_assets.sqlite3` 引用，改为 `AssetRepository` 调用
- `backend/app/services/llm_module_registry.py` — 查找 `llm_facility.sqlite3` 引用，改为 `LlmRepository` 调用
- `backend/app/services/assets/unified_asset_view.py` — 查找 legacy sqlite 直读点

**测试策略**：
- `test_archive_unified_db_only.py` — monkeypatch 删除 archive_library.sqlite3 路径，断言 service CRUD 正常
- `test_assets_unified_db_only.py` — 同上
- `test_llm_facility_unified_db_only.py` — 同上

**关键判断**：
- 当前 service 层可能已部分切库（Phase A 重构时），需要实际 grep `sqlite3.connect` / `Config.*DB_FILENAME` 确认残余读路径
- 保留迁移脚本路径（migrate_archive.py 等），不保留运行时 fallback

**预估改动量：** 每域 ~50 行 service 修改 + ~80 行测试 = 总 ~400 行

---

## 七、Phase G / Task 8（novel/graph/seed 读路径切库）实施细节

**目标**：从运行主链中移除 `ProjectManager.load_project_json()` 依赖。

**需修改的文件（按消费量排序）：**
1. `backend/app/services/chapter_context_pack_builder.py` — 读 seed_analysis, chapter_segments, chapter_continuity
2. `backend/app/services/chapter_meta_service.py` — 读 story_memory, chapter_segments
3. `backend/app/services/assets/unified_asset_view.py` — 读 narrative_archives, reading_notes, ontology, agent_profiles
4. `backend/app/api_fastapi/novel.py` — 读 seed_analysis, agent_profiles, reviewer_rules
5. `backend/app/services/worldline_source_loader.py` — 读 seed_analysis (可保留为 read-only 数据来源)
6. `backend/app/services/writer_agent/*` — 间接通过 context_pack_builder

**策略**：
- 对每个 JSON 文件确认其内容在 unified DB 中的对应表
- 如果已有对应 repository，直接改 service 调 repo
- 如果没有对应表/repo，决定是否需要新建（部分 JSON 的数据可能已通过 seed pipeline 写入 DB，只是读路径未切）

**测试策略**：
- 在 tmp_path 中不创建对应 JSON 文件，断言 service 仍能运行
- 重点关注 `chapter_context_pack_builder`，因为它是 writer agent 的上游

**预估改动量：** ~500 行 service 修改 + ~200 行测试

---

## 八、Phase H / Task 9（搜索抽象）实施细节

**目标**：SQLite FTS5 + PostgreSQL pg_trgm 双后端搜索层。

**新增文件：**
```
backend/app/repositories/search_backends/
  __init__.py
  base.py            — SearchBackend ABC (search, get_suggestions)
  sqlite_search.py   — FTS5 实现
  postgres_search.py — pg_trgm 实现（占位 + 基础实现）
```

**修改文件：**
- `backend/app/repositories/search_repo.py` — 改为 backend 路由器（按 DATABASE_URL 选 backend）
- `backend/app/tables/fts.py` — 可能需要调整 FTS 索引定义

**测试策略**：
- `test_search_backend_contract.py` — 定义 contract（同一组输入，两个 backend 返回相同格式）
- `test_search_sqlite_backend.py` — 具体 FTS5 回归
- PostgreSQL backend 先落地 contract + 占位实现（真实集成留 P2 Task 10）

**关键约束**：
- 搜索接口必须支持：query string / project_id filter / source filter (assets/archives/chapters) / limit / offset
- 返回格式：`[{id, title, snippet, score, source, project_id}]`
- SQLite backend 用已注册的 FTS5 虚表

**预估改动量：** 新增 ~300 行 + 测试 ~150 行

---

## 九、跨 Phase 并行安全矩阵

| Phase 对 | 文件交叉 | 能否并行 | 风险 |
|---|---|---|---|
| Task 11 + Task 4 | migration_verifier.py 仅被 Task 11 改；迁移器仅被 Task 4 改 | ✅ 可并行 | 低 — 共享 test fixtures 但不冲突 |
| Task 6 + Task 7 | worldline 与 archive/assets 无文件交叉 | ✅ 可并行 | 低 |
| Task 7 + Task 8 | unified_asset_view.py 被两者修改 | ⚠️ 有限并行 | 中 — 需要协调 unified_asset_view 的修改 |
| Task 7 + Task 9 | search_repo.py 被两者修改 | ⚠️ 有限并行 | 中 |
| Task 8 + Task 9 | 几乎无交叉 | ✅ 可并行 | 低 |

**推荐并行组合：**
- 会话 1：Task 11 + Task 4（同一会话顺序做，总量约 700 行）
- 会话 2：Task 6（独立会话，约 500 行，拆 3 个子 commit）
- 会话 3：Task 7 + Task 8 + Task 9（3 个 agent worktree 并行，约 1200 行总量）

---

## 十、每会话开工 Checklist

```
□ cd "/Volumes/Fanxiang S500Pro/项目/novelwork-chonggou"
□ git status --porcelain | wc -l                       # 确认起点 = 0
□ git log --oneline -3                                 # 确认 HEAD
□ git tag -l "pre-phase-*"                             # 安全网仍在
□ 读 docs/plans/2026-04-16-migration-cleanup-execution-plan.md（总路线图 §九）
□ 读 docs/plans/2026-04-17-remaining-phases-implementation-guide.md（本文件详细方案）
□ 确定本次会话跑哪个 Phase
□ 开 TaskCreate，拆出本 Phase 的子步骤
□ 破坏性动作前 git tag 打新 anchor
□ 每个 Phase 结束：git status 必须为 clean，pytest 必须为 pass
□ Phase 完成后在总路线图 §九 追加完成记录
```

---

## 十一、下一步指令（给 Claude）

```
当前在 /Volumes/Fanxiang S500Pro/项目/novelwork-chonggou，分支 gemini。
先读两份 plan：
  docs/plans/2026-04-16-migration-cleanup-execution-plan.md（总路线图）
  docs/plans/2026-04-17-remaining-phases-implementation-guide.md（详细实施方案）

本次要做的是：Phase D / Task 11 + Task 4（迁移校验器 + 分域迁移器）

Task 11 → Task 4 顺序做，各自独立 commit。完成后在总路线图 §九 追加记录。
```
