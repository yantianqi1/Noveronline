# 新数据库架构全面迁移实施方案

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 将项目现有“统一主库 + 多个旧 SQLite / JSON / 文件系统 silo 并存”的状态，完整收口为**新数据库架构**：以 `backend/data/mirofish.db`（开发）/ PostgreSQL（生产）为唯一主真相源，所有核心业务统一通过 SQLAlchemy Core + Repository 层读写，旧存储仅保留为一次性迁移输入或只读备份。

**Architecture:** 采用“单主库 + project_id 隔离 + Repository 访问层 + 分阶段双写/校验/切换”方案。先补齐 schema 与迁移器，再对每个业务域建立数据库真相源和回填流程，最后逐步移除 JSON / 文件系统 / 旧 SQLite 的运行时读路径。所有查询必须经过 Repository / Service 抽象，禁止新业务继续直接读 legacy 文件。

**Tech Stack:** Python 3.11、SQLAlchemy Core 2.x、Alembic、SQLite（开发）、PostgreSQL 16+（生产目标）、pytest。

---

## 一、背景结论（基于当前仓库现状）

### 当前已落地基础
- 主数据库已存在：`backend/data/mirofish.db`
- 数据库入口已统一：`backend/app/database.py`
- 统一表定义已存在：`backend/app/tables/*.py`
- Repository 层已存在：`backend/app/repositories/*.py`
- Alembic 骨架已存在：`backend/alembic/`
- 部分业务数据已写入主库：worldline、task、assets、chapter、archive、outline 等

### 当前主要问题
1. **真相源未统一**：数据库、旧 SQLite、JSON、文件系统并存
2. **worldline 运行态仍大量依赖文件系统**
3. **seed / archive / graph / context pack 仍直接读取大量项目 JSON**
4. **搜索层尚未完成“SQLite FTS5 / PostgreSQL pg_trgm”双实现**
5. **PostgreSQL 兼容停留在架构设计层，未形成真实落地链路**
6. **部分表已建但业务读写未全面切换**

### 本方案的最终定义
迁移完成后应满足：
- 数据库成为**唯一主真相源**
- 所有核心业务运行时只读写主库
- legacy SQLite / JSON / worldline 文件仅作为迁移输入或导出产物
- 支持 SQLite 开发 + PostgreSQL 生产
- 搜索、迁移、校验、回滚路径完整可验证

---

## 二、目标数据库架构定义

## 2.1 唯一主真相源

### 开发环境
- `sqlite:///./data/mirofish.db`

### 生产环境
- `postgresql+psycopg://...`

### 核心原则
- 所有项目级数据通过 `project_id` 隔离
- 禁止运行时以 JSON / 独立 SQLite / 文件系统作为主读源
- 文件系统只允许承载：
  - 上传原始文件
  - 导出产物
  - 临时 trace / 日志
  - 可再生缓存

---

## 2.2 业务域拆分

| 业务域 | 新真相源 | 迁移目标 |
|---|---|---|
| LLM 设施 | 主库 `llm_*` 表 | 废弃独立 `llm_facility.sqlite3` 运行时依赖 |
| 档案库 | 主库 `archive_*` 表 | 废弃 `archive_library.sqlite3` 运行时依赖 |
| 资产库 | 主库 `assets` / `asset_links` | 废弃 `assets_library.sqlite3` / `project_assets.sqlite3` 运行时依赖 |
| 小说内容 | 主库 `chapter_content` / `chapter_meta` / `scenes` / `outline_versions` | 废弃 `chapter_meta.sqlite3`、JSON 正文真相源 |
| 小说设定 | 主库 `entities` / `relationships` / `plot_threads` / `world_rule_evidence` 等 | 废弃 `novel.sqlite3` 旧运行时依赖 |
| 图谱 | 主库 `graph_*` 表 | 废弃 `story_graph.sqlite3/json` 运行时依赖 |
| 世界线准备态 | 主库 `prepare_*` / `agent_states` | 废弃 prepare legacy 存储 |
| 世界线运行态 | 主库 `sessions` / `worldline_branches` / `world_events` / `agent_registry` / `agent_state_snapshots` / `agent_episodic_memory` / `relation_state_log` | 废弃 worldline 文件系统真相源 |
| 全局搜索 | 主库统一索引 + FTS/pg_trgm | 废弃独立 `global_search.sqlite3` 概念 |
| 任务运行时 | 主库 `task_runs` | 废弃 `task_runtime.sqlite3` 概念 |

---

## 2.3 分层约束

### 允许访问数据库的层
- `app/repositories/*`
- 极少量 schema bootstrap / migration 脚本

### 禁止行为
- service 直接执行裸 SQL（除临时迁移脚本）
- service 直接把 JSON 文件当真相源
- 新代码继续新增独立 SQLite 文件
- API 层直接拼装数据库读写逻辑

### 统一规则
- 读写必须走 repository
- repository 返回 Python dict / DTO
- service 负责业务编排、容错、事务边界
- API 只负责协议转换

---

## 三、迁移范围清单

## 3.1 需要迁入主库的 legacy 来源

### 旧 SQLite
- `novel.sqlite3`
- `story_graph.sqlite3`
- `archive_library.sqlite3`
- `assets_library.sqlite3`
- `project_assets.sqlite3`
- `llm_facility.sqlite3`
- `task_runtime.sqlite3`
- 任何 prepare / runtime 相关遗留 SQLite

### 项目 JSON
- `seed_analysis.json`
- `narrative_archives.json`
- `agent_profiles.json`
- `reading_notes.json`
- `ontology.json`
- `story_memory.json`
- `chapter_segments.json`
- `chapter_continuity.json`
- `reviewer_rules.json`
- 其他被 `ProjectManager.load_project_json()` 直接读取且影响运行时的文件

### 文件系统 worldline
- `backend/uploads/projects/<pid>/worldlines/**`
- `backend/uploads/system/global_worldlines/**`

---

## 3.2 可保留但降级为“非真相源”的内容
- 原始上传小说文件
- 导出的图谱 json
- 导出的分析包
- 调试 trace
- 可再生成缓存
- 手动导入/导出包

---

## 四、总体实施策略

采用 6 阶段推进：

1. **Schema 对齐阶段** —— 明确目标表模型、补缺字段、解决 legacy 与现库差异
2. **迁移器建设阶段** —— 为所有 legacy source 建立可重复执行的导入器
3. **双写与回填阶段** —— 新流程写主库，旧存储只做旁路兼容
4. **读路径切换阶段** —— 各业务模块改为优先/只读主库
5. **PostgreSQL 兼容阶段** —— 补搜索抽象、索引、方言差异
6. **收口与删除阶段** —— 删掉 legacy 读逻辑，保留一次性迁移脚本和导出能力

---

# 五、实施计划（按任务拆分）

### Task 1: 建立数据库迁移基线文档

**Objective:** 形成数据库统一迁移的权威规格，冻结“哪些源要迁、哪些表是主真相源、哪些字段允许为空”。

**Files:**
- Modify: `docs/plans/2026-04-14-database-unification-migration-plan.md`
- Create: `docs/database/database-source-of-truth-matrix.md`

**Step 1: 编写真相源矩阵文档**
写出每个业务对象的：
- 当前来源
- 目标表
- 目标主键
- 是否项目级
- 迁移优先级
- 切换完成判定条件

**Step 2: 列出 legacy 读取点**
用 `search_files("load_project_json\(|sqlite3|worldlines/|archive_library.sqlite3|assets_library.sqlite3", ...)` 收集所有 legacy 入口，整理到矩阵文档中。

**Step 3: 定义迁移完成标准**
每个域都要明确：
- 写路径切换完成
- 读路径切换完成
- 回归测试通过
- legacy 依赖删除或仅保留导出职责

**Step 4: 提交**
```bash
git add docs/database/database-source-of-truth-matrix.md docs/plans/2026-04-14-database-unification-migration-plan.md
git commit -m "docs: define database migration source-of-truth matrix"
```

---

### Task 2: 为 unified schema 建立“差异审计”脚本

**Objective:** 确认 `app/tables/*.py` 是否已覆盖目标架构所需全部表与关键列。

**Files:**
- Create: `backend/scripts/audit_schema_coverage.py`
- Test: `backend/tests/test_schema_coverage_audit.py`

**Step 1: 写失败测试**
测试要求脚本输出：
- 缺失表
- 缺失列
- 仅存在于 legacy 的表
- 仅存在于新 schema 的表

**Step 2: 实现审计脚本**
输入：
- 主库 schema metadata
- legacy 数据源探测结果
输出 JSON 报告。

**Step 3: 运行测试**
```bash
cd backend && python -m pytest tests/test_schema_coverage_audit.py -q
```

**Step 4: 提交**
```bash
git add backend/scripts/audit_schema_coverage.py backend/tests/test_schema_coverage_audit.py
git commit -m "feat: add schema coverage audit for db migration"
```

---

### Task 3: 补齐 Alembic 迁移链而不是只靠 create_all

**Objective:** 把当前“初始迁移 + create_all”提升为可演进的正式数据库版本管理。

**Files:**
- Modify: `backend/alembic/versions/20260412_0001_initial_schema.py`
- Create: 后续 revision 文件
- Modify: `backend/app/database.py`
- Test: `backend/tests/test_alembic_upgrade_downgrade.py`

**Step 1: 写测试**
验证：
- 空库可 upgrade 到 head
- downgrade 再 upgrade 可恢复
- SQLite 与 PostgreSQL URL 下 migration 路径都能初始化 schema

**Step 2: 调整启动策略**
避免业务长期依赖 `metadata.create_all()` 自动补表；改成：
- 测试环境可允许 `init_db()`
- 应用启动优先要求 schema 已迁移

**Step 3: 按表域拆 revision**
后续 schema 变化全部通过 Alembic revision，而非静默 create_all。

**Step 4: 提交**
```bash
git add backend/alembic backend/app/database.py backend/tests/test_alembic_upgrade_downgrade.py
git commit -m "refactor: formalize alembic-based schema lifecycle"
```

---

### Task 4: 重写 legacy 数据迁移器为“分域迁移器”

**Objective:** 把当前只迁 `novel.sqlite3` / `story_graph.sqlite3` 的脚本扩展为覆盖全部 legacy source 的完整迁移框架。

**Files:**
- Modify: `backend/scripts/migrate_legacy_data.py`
- Create: 
  - `backend/scripts/migrations/migrate_llm_facility.py`
  - `backend/scripts/migrations/migrate_archive.py`
  - `backend/scripts/migrations/migrate_assets.py`
  - `backend/scripts/migrations/migrate_novel.py`
  - `backend/scripts/migrations/migrate_graph.py`
  - `backend/scripts/migrations/migrate_worldline.py`
  - `backend/scripts/migrations/migrate_seed_json.py`
- Test: `backend/tests/test_full_legacy_migration.py`

**Step 1: 写失败测试**
构造一个最小 legacy 项目样本，断言迁移后主库对应表行数与关键字段正确。

**Step 2: 建立统一迁移上下文**
包含：
- project_id
- upload_root
- source paths
- dry_run
- replace_project
- report collector

**Step 3: 每个域单独实现迁移器**
要求：
- 幂等
- 可重复执行
- 可按 project 迁移
- 失败显式报错
- 输出详细 counts

**Step 4: 支持 dry-run + report**
生成 JSON 报告，包含：
- 迁入行数
- 跳过条目
- 主键冲突
- 字段丢失
- 数据修复次数

**Step 5: 提交**
```bash
git add backend/scripts/migrate_legacy_data.py backend/scripts/migrations backend/tests/test_full_legacy_migration.py
git commit -m "feat: add full domain legacy-to-unified db migration framework"
```

---

### Task 5: 为 JSON 运行时真相源建立数据库表映射

**Objective:** 把当前运行时仍直接读取的 JSON 资产映射进数据库正式表或附属表。

**Files:**
- Modify/Create:
  - `backend/app/tables/novel.py`
  - `backend/app/tables/archive.py`
  - `backend/app/tables/graph.py`
  - `backend/app/tables/worldline.py`
  - `backend/app/repositories/*.py`
- Test: `backend/tests/test_json_artifact_ingestion.py`

**Step 1: 建模 JSON → 表映射**
至少处理：
- `seed_analysis.json`
- `reading_notes.json`
- `agent_profiles.json`
- `ontology.json`
- `story_memory.json`
- `chapter_segments.json`
- `chapter_continuity.json`
- `reviewer_rules.json`

**Step 2: 确定存储策略**
优先规则：
- 能拆成结构化列就拆
- 暂时无法结构化的部分落入 `payload_json`/补充表
- 禁止继续把关键运行信息只留在 JSON 文件中

**Step 3: 回填迁移器**
在 Task 4 的迁移框架中调用。

**Step 4: 测试**
验证数据库可独立重建这些上下文，而不依赖原 JSON 文件。

**Step 5: 提交**
```bash
git add backend/app/tables backend/app/repositories backend/tests/test_json_artifact_ingestion.py
git commit -m "feat: map runtime json artifacts into unified database tables"
```

---

### Task 6: worldline 运行态数据库化

**Objective:** 彻底把 worldline 从文件系统真相源切换到数据库真相源。

**Files:**
- Modify:
  - `backend/app/services/world_state_store.py`
  - `backend/app/services/worldline_runtime_service.py`
  - `backend/app/services/worldline_prepare_service.py`
  - `backend/app/services/worldline_source_loader.py`
  - `backend/app/services/assets/unified_asset_view.py`
- Repositories:
  - `backend/app/repositories/worldline_runtime_repo.py`
  - `backend/app/repositories/worldline_prepare_repo.py`
- Test:
  - `backend/tests/test_worldline_db_persistence.py`
  - `backend/tests/test_worldline_fileless_restore.py`

**Step 1: 写失败测试**
验证没有 `worldlines/` 文件夹时，以下能力仍可用：
- session create
- timeline query
- auto evolve
- agent memory/history
- writer side worldline retrieval

**Step 2: 实现 DB-backed worldline store**
将 session / branch / event / agent registry / state snapshots / dialogue / episodic memory / relation logs 全部从 DB 读写。

**Step 3: 文件系统降级为导出层**
仅在需要时生成调试导出；不再作为主读源。

**Step 4: 提交**
```bash
git add backend/app/services/world_state_store.py backend/app/services/worldline_* backend/app/repositories/worldline_* backend/tests/test_worldline_db_persistence.py backend/tests/test_worldline_fileless_restore.py
git commit -m "refactor: move worldline runtime source-of-truth to unified db"
```

---

### Task 7: archive / assets / llm facility 完全切主库

**Objective:** 去掉对 `archive_library.sqlite3`、`assets_library.sqlite3`、`project_assets.sqlite3`、`llm_facility.sqlite3` 的运行时依赖。

**Files:**
- Modify:
  - `backend/app/services/archive_library_service.py`
  - `backend/app/services/assets/assets_service.py`
  - `backend/app/services/llm_module_registry.py`
  - `backend/app/services/assets/unified_asset_view.py`
- Repositories:
  - `archive_repo.py`
  - `asset_repo.py`
  - `llm_repo.py`
- Test:
  - `backend/tests/test_archive_unified_db_only.py`
  - `backend/tests/test_assets_unified_db_only.py`
  - `backend/tests/test_llm_facility_unified_db_only.py`

**Step 1: 写测试**
删除/屏蔽 legacy sqlite 文件后，功能仍可跑。

**Step 2: 调整 service**
所有 service 统一走 repository + 主库表。

**Step 3: 删除 legacy 路径分支**
保留迁移脚本，不保留运行时 fallback。

**Step 4: 提交**
```bash
git add backend/app/services backend/app/repositories backend/tests/test_archive_unified_db_only.py backend/tests/test_assets_unified_db_only.py backend/tests/test_llm_facility_unified_db_only.py
git commit -m "refactor: remove runtime dependency on legacy sqlite silos"
```

---

### Task 8: novel / graph / seed 主读路径全面切库

**Objective:** 让 writer / chapter context / graph / ontology / seed 相关业务在运行时主要从主库获取数据。

**Files:**
- Modify:
  - `backend/app/services/chapter_context_pack_builder.py`
  - `backend/app/services/chapter_meta_service.py`
  - `backend/app/services/graph_builder.py`
  - `backend/app/services/narrative_entity_archivist.py`
  - `backend/app/services/worldline_source_loader.py`
  - `backend/app/services/writer_agent/*`
- Tests:
  - `backend/tests/test_chapter_context_db_only.py`
  - `backend/tests/test_writer_agent_db_only.py`
  - `backend/tests/test_graph_pipeline_db_only.py`

**Step 1: 写失败测试**
在移除对应 JSON 文件的情况下，writer / graph / chapter-context 仍能输出正确结果。

**Step 2: 建数据库读取路径**
把 `ProjectManager.load_project_json()` 从运行主链中移除，改成 repository 查询。
同时显式删除当前为旧 writer 兼容保留的 legacy 回填/双写钩子：
- `backend/app/services/seed_extract_runner.py` 中对 `novel.sqlite3` 的自动回填
- `backend/app/services/worldline_engine.py` 中 worldline → legacy writer 数据面的同步兼容逻辑

**Step 3: 仅保留导入/导出接口**
JSON 只用于：
- 导入历史项目
- 导出分析产物
- 调试快照

**Step 4: 提交**
```bash
git add backend/app/services backend/tests/test_chapter_context_db_only.py backend/tests/test_writer_agent_db_only.py backend/tests/test_graph_pipeline_db_only.py
git commit -m "refactor: switch novel graph and writer runtime reads to unified db"
```

---

### Task 9: 完成搜索抽象（SQLite FTS5 / PostgreSQL pg_trgm）

**Objective:** 把搜索层从当前 SQLite 偏置/LIKE 偏置实现，升级为正式的双后端抽象。

**Files:**
- Modify:
  - `backend/app/repositories/search_repo.py`
  - `backend/app/tables/fts.py`
  - `backend/app/services/assets/global_search_indexer.py`
- Create:
  - `backend/app/repositories/search_backends/sqlite_search.py`
  - `backend/app/repositories/search_backends/postgres_search.py`
- Test:
  - `backend/tests/test_search_sqlite_backend.py`
  - `backend/tests/test_search_backend_contract.py`
  - （可选）`backend/tests/test_search_postgres_backend.py`

**Step 1: 写契约测试**
定义统一搜索返回格式。

**Step 2: 实现 SQLite backend**
- 章节 / 场景 / 资产 / global index 用 FTS5
- 保证 snippet / limit / project filter / source filter 生效

**Step 3: 实现 PostgreSQL backend**
- `pg_trgm`
- GIN 索引
- `similarity()` 排序
- 兼容多列检索

**Step 4: 抽象路由**
按 `DATABASE_URL` 自动选择 backend。

**Step 5: 提交**
```bash
git add backend/app/repositories/search_* backend/app/tables/fts.py backend/tests/test_search_* 
git commit -m "feat: add sqlite and postgres search backend abstraction"
```

---

### Task 10: PostgreSQL 兼容性正式落地

**Objective:** 确保主库 schema、repository、搜索和测试可在 PostgreSQL 上运行。

**Files:**
- Modify: 相关 repository / migration / test config
- Create:
  - `backend/docker-compose.postgres.yml`
  - `backend/tests/conftest_postgres.py`
  - `backend/tests/test_postgres_smoke.py`

**Step 1: 写 smoke test**
验证 PostgreSQL 下：
- schema upgrade 成功
- 关键 repository CRUD 成功
- 搜索 backend 成功
- worldline 最小链路成功

**Step 2: 修方言差异**
重点排查：
- JSON 函数
- upsert 语法
- FTS 替代方案
- SQLite 专用 DDL
- 自增/约束行为

**Step 3: 文档化部署方式**
README 增加 PostgreSQL 启动和迁移命令。

**Step 4: 提交**
```bash
git add backend/docker-compose.postgres.yml backend/tests backend/README.md
git commit -m "feat: add postgres-compatible unified db runtime"
```

---

### Task 11: 读写切换保护与数据校验

**Objective:** 在切库过程中保证数据一致性，避免双源漂移。

**Files:**
- Create:
  - `backend/app/services/migration_verifier.py`
  - `backend/scripts/verify_project_migration.py`
- Test:
  - `backend/tests/test_migration_verifier.py`

**Step 1: 校验器能力**
比较 legacy source 与主库：
- 行数
- 主键集合
- 摘要 hash
- 关键字段一致性

**Step 2: 输出迁移报告**
按项目输出：
- 已迁移域
- 未迁移域
- 不一致项
- 风险等级

**Step 3: 在切换前强制校验**
切换运行时读路径前必须验证通过。

**Step 4: 提交**
```bash
git add backend/app/services/migration_verifier.py backend/scripts/verify_project_migration.py backend/tests/test_migration_verifier.py
git commit -m "feat: add migration verification and consistency reports"
```

---

### Task 12: 删除 legacy 运行时依赖并封板

**Objective:** 完成真正的“新数据库架构”收口，禁止业务继续依赖 legacy source。

**Files:**
- Modify: 所有仍存在 legacy runtime read 的 services
- Create: `docs/database/deprecation-checklist.md`
- Test: 全量回归测试

**Step 1: 移除 legacy fallback 逻辑**
只保留：
- 导入脚本
- 导出脚本
- 只读备份工具

**Step 2: 增加护栏**
在 CI 中加入 grep 检查：
- 禁止新增 `load_project_json(` 到主运行链路
- 禁止新增独立 sqlite 路径直连

**Step 3: 跑全量测试**
```bash
cd /Volumes/Fanxiang\ S500Pro/项目/novelwork-重构/backend
python -m pytest tests/ -q
```

**Step 4: 提交**
```bash
git add .
git commit -m "refactor: finalize migration to unified database architecture"
```

---

# 六、数据建模补充规则

## 6.1 完整正文策略
- `chapter_content.content` / `scenes.content` 保存完整正文
- 默认不进入 agent 基础上下文
- 只能通过显式检索 / 显式展开进入上下文
- 数据库存全量，prompt 层按需裁剪

## 6.2 JSON 字段原则
- 高频查询字段必须结构化列化
- 低频/异构字段可临时保留 `payload_json`
- 任何 `payload_json` 中的字段，只要被 2 个以上功能稳定依赖，就应升级为正式列

## 6.3 主键与幂等
- 所有迁移器必须幂等
- 所有 upsert 必须显式指定业务主键
- 禁止依赖“重复迁移时先删全表再灌”的粗暴策略，除非限定到单 project 且在 dry-run/replace_project 开关下执行

---

# 七、测试策略

## 7.1 必测层级
1. **Schema 测试** —— 表存在、列存在、约束生效
2. **Repository 测试** —— CRUD / filter / ordering / upsert
3. **Migration 测试** —— legacy → unified
4. **DB-only 运行测试** —— 删除 legacy 文件后功能仍可跑
5. **Search 测试** —— SQLite / PostgreSQL 契约一致
6. **End-to-end 测试** —— seed → archive → worldline → writer 主链可跑

## 7.2 关键验收命令
```bash
cd /Volumes/Fanxiang\ S500Pro/项目/novelwork-重构/backend
python -m pytest tests/test_fastapi_b1_bootstrap.py -q
python -m pytest tests/test_full_legacy_migration.py -q
python -m pytest tests/test_worldline_db_persistence.py -q
python -m pytest tests/test_writer_agent_db_only.py -q
python -m pytest tests/test_search_backend_contract.py -q
python -m pytest tests/ -q
```

---

# 八、风险与应对

## 风险 1：双源漂移
**应对：** 先双写、再校验、后切读，最后删 fallback。

## 风险 2：worldline 文件系统历史数据复杂
**应对：** 先做导入器，再做 fileless smoke test；不要先删旧文件读路径。

## 风险 3：JSON 结构历史不统一
**应对：** 迁移器引入 normalize 层，对异常字段做显式修复并记录报告。

## 风险 4：SQLite → PostgreSQL 方言差异
**应对：** 尽早建立 Postgres smoke test，不要等全迁完再补。

## 风险 5：搜索语义变化影响 writer 质量
**应对：** 为 writer agent 固定一套搜索回归样例，比较召回质量。

---

# 九、最终完成定义（Definition of Done）

满足以下全部条件才算“数据库全面迁移完成”：

- [ ] 所有核心业务运行时只读主库
- [ ] worldline 不再依赖文件系统作为真相源
- [ ] seed/archive/graph/writer/chapter-context 不再依赖项目 JSON 作为主读源
- [ ] archive/assets/llm/task 不再依赖独立 sqlite 运行
- [ ] full legacy migration 脚本可对历史项目重复执行
- [ ] 迁移校验器可输出一致性报告
- [ ] SQLite 开发环境通过全量测试
- [ ] PostgreSQL smoke test 通过
- [ ] 搜索层支持 SQLite FTS5 与 PostgreSQL pg_trgm
- [ ] CI 护栏阻止新增 legacy runtime read

---

# 十、建议执行顺序（实际开发优先级）

## P0
1. Task 3 Alembic 正式化
2. Task 4 分域迁移器
3. Task 11 迁移校验器
4. Task 6 worldline 数据库化

## P1
5. Task 7 archive/assets/llm 全切主库
6. Task 8 novel/graph/seed 主读路径切库
7. Task 9 搜索抽象完成

## P2
8. Task 10 PostgreSQL 正式兼容
9. Task 12 删除 legacy fallback 与 CI 封板

---

# 十一、给执行者的提醒

- 每完成一个业务域，就立即补 **DB-only 测试**。
- 不要在同一个 PR 里同时做“schema 大改 + writer 逻辑大改 + worldline 大改”。
- 迁移脚本必须能在**只给项目目录**的情况下独立执行。
- 所有“暂时先读 JSON”的地方，都必须在真相源矩阵里登记，否则后面一定漏。
- PostgreSQL 兼容不能只停留在 `DATABASE_URL` 可配置；必须有真实 smoke test。

---

# 十二、预期成果

迁移完成后，项目将进入以下状态：
- 一个统一数据库承载项目核心状态
- 所有 agent / writer / worldline / archive / assets 共享同一套数据底座
- JSON 与文件系统从“运行主依赖”降级为“导入导出与缓存”
- 搜索、迁移、部署、备份、校验都围绕统一数据库展开
- 为后续 PostgreSQL、并发、多用户、远程部署打下真正可维护的基础
