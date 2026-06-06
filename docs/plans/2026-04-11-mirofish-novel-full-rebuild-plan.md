# MiroFish-Novel Full Rebuild Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将当前 `MiroFish-Novel` 重构为新技术栈模块化单体，并在不丢失任何现存功能与语义的前提下完成一次切换。

**Architecture:** 采用“内部阶段化重建，外部一次切换”的方案。先冻结 contracts 与迁移基线，再按 bounded context 与前端 feature 并行建设，最后执行迁移 rehearsal、故障演练和正式切换。

**Tech Stack:** React 19, TypeScript, Vite, TanStack Query, Zustand, FastAPI, Pydantic, SQLAlchemy 2, Alembic, PostgreSQL, MinIO, Redis, Temporal.

---

### Task 1: Freeze Baseline

**Files:**
- Review: `重构方案/00-重构总控与并行执行总览.md`
- Review: `重构方案/06-全功能盘点与迁移对照矩阵.md`
- Review: `重构方案/07-全接口与前端页面覆盖清单.md`
- Review: `重构方案/08-旧数据逐字段映射与迁移脚本规范.md`
- Review: `重构方案/09-功能等价验收与回归测试矩阵.md`
- Review: `重构方案/10-隐性语义与底层兼容矩阵.md`

**Step 1: 冻结功能与语义边界**

- 以 `06/07/08/09/10` 为唯一基线。
- 将所有 `TBD / unknown / not planned` 清零。

**Step 2: 核对真实代码面是否仍有遗漏**

Run:

```bash
rg -n "@.*route\\(|add_url_rule|Blueprint\\(" backend/app/api
rg -n "export function|async function" frontend/src/api
rg -n "def test_" backend/tests
```

Expected: 无未进入矩阵的新接口、新前端 client、新测试语义。

**Step 3: 记录冻结版本**

- 在执行日志中标记 baseline revision。

### Task 2: Create New Monorepo Skeleton

**Files:**
- Create: `apps/web/`
- Create: `apps/api/`
- Create: `packages/contracts/`
- Create: `workflows/`
- Create: `infra/`
- Create: `migrations/`

**Step 1: 初始化目录骨架**

- 创建前端、后端、contracts、workflow、infra、migration 一级目录。

**Step 2: 初始化基础配置**

- 创建 `pnpm-workspace.yaml`
- 创建 `apps/web/package.json`
- 创建 `apps/api/pyproject.toml`
- 创建 `workflows/pyproject.toml`

**Step 3: 验证基础结构**

Run:

```bash
rg --files apps packages workflows infra migrations
```

Expected: 新目录结构完整可见。

### Task 3: Establish Contracts and Shared Schemas

**Files:**
- Create: `packages/contracts/openapi/`
- Create: `packages/contracts/typescript/`
- Create: `apps/api/openapi.yaml`

**Step 1: 定义统一错误模型和 operation 模型**

- 明确 `error.code / message / details / retryable`
- 明确 operation status / step trace / event schema

**Step 2: 生成 typed client 输入面**

- 为前端预留 generated client 输出目录

**Step 3: 验证 contracts 可被前后端共同消费**

Run: 生成脚本或 schema 校验脚本
Expected: contracts 无冲突，TS/Python 均可消费。

### Task 4: Build Migration Foundation

**Files:**
- Create: `migrations/sqlite_extractors/`
- Create: `migrations/json_importers/`
- Create: `migrations/checksums/`
- Create: `migrations/runbooks/`

**Step 1: 建立 artifact registry 与 checksum 规则**

- 明确所有旧数据源的导入批次和对象存储规则

**Step 2: 建立 PostgreSQL schema 与 Alembic**

- 覆盖 projects / artifacts / archives / memories / worldline / draft / llm

**Step 3: 完成一次导入 dry-run**

Expected: 单个真实项目可导入，checksum 可校验。

### Task 5: Backend Parallel Lanes

**Files:**
- Modify/Create: `apps/api/src/modules/project/**`
- Modify/Create: `apps/api/src/modules/seed_analysis/**`
- Modify/Create: `apps/api/src/modules/graph/**`
- Modify/Create: `apps/api/src/modules/archive_library/**`
- Modify/Create: `apps/api/src/modules/llm_facility/**`
- Modify/Create: `apps/api/src/modules/worldline/**`
- Modify/Create: `apps/api/src/modules/writer/**`

**Step 1: 先完成 BE-A / BE-B**

- `contracts + bootstrap`
- `migration + schema + artifact registry`

**Step 2: 并行推进 BE-C / BE-D**

- BE-C: `project + seed-analysis + graph`
- BE-D: `archive-library + llm-facility`

**Step 3: 最后推进 BE-E**

- `worldline + writer`

**Step 4: 每个 lane 完成后跑模块测试**

Expected: 模块测试绿，且更新 `06/07/09/10` 对应项。

### Task 6: Frontend Parallel Lanes

**Files:**
- Modify/Create: `apps/web/src/app/**`
- Modify/Create: `apps/web/src/pages/**`
- Modify/Create: `apps/web/src/features/**`
- Modify/Create: `apps/web/src/entities/**`
- Modify/Create: `apps/web/src/shared/**`

**Step 1: 先完成 FE-A**

- `app shell + router + query client + shared api`

**Step 2: 并行推进 FE-B / FE-C**

- FE-B: `story-graph + worldline + character-console`
- FE-C: `writer`

**Step 3: 补齐 FE-A 剩余页面**

- `overview + guide + archive-library + llm-facility`

**Step 4: 页面级回归**

Expected: 八个页面全部非占位，且关键交互可用。

### Task 7: Run Migration Rehearsal and Failure Injection

**Files:**
- Modify/Create: `migrations/rehearsal/**`
- Modify/Create: `docs/runbooks/**`

**Step 1: 迁移 rehearsal**

- 导入真实项目样本
- 对账 project/artifact/archive/worldline/chapter/llm 数据

**Step 2: 故障注入**

- worker 重启
- SSE 中断
- LLM timeout
- object storage 短暂不可用

**Step 3: 回滚演练**

- 验证切换前快照可恢复旧系统

### Task 8: Final Cutover Checklist

**Files:**
- Review: `重构方案/00-14`
- Review: `docs/plans/2026-04-11-mirofish-novel-full-rebuild-design.md`

**Step 1: 关闭所有矩阵项**

- `06`、`07`、`08`、`09`、`10`、`11`

**Step 2: 验证前后端完整交付**

- `13` 与 `14` 的交付条件全部满足

**Step 3: 执行正式切换**

- 仅在 rehearsal、故障演练、回滚演练全部通过后执行

---

## Execution Log

### Baseline Revision `BR-2026-04-11-01`

- 审计时间：`2026-04-11`
- Git HEAD：`1aba6d5c188650a9b60cdf5ae7ca747e5b9cc203`
- 执行前工作区状态：dirty，但限定在 `README.md`、`docs/CODEX_HANDOFF_GUIDE.md`、两份 full rebuild 计划文档和整套 `重构方案/` 文档；未发现会直接干扰本轮重构边界的代码层未提交改动。
- 文档完整性：本轮要求的 12 份执行文档均已存在并完成审阅。
- 基线修正：
  - 将 `test_long_novel_pipeline.py`、`test_chapter_context_pack_builder.py`、`test_chapter_context_ranker.py`、`test_chapter_card_generator.py`、`test_anchor_point_builder.py`、`test_skeleton_timeline.py`、`test_chapter_fingerprint.py`、`test_novel_seed_analyzer.py`、`test_task_runtime_persistence.py`、`test_worldline_branch_comparison.py`、`test_legacy_llm_config_cleanup.py` 纳入矩阵。
  - 明确 `draft finalize` 属于后端接口与测试已固化能力；即使旧前端没有独立 helper，新技术栈也必须显式承接。
  - 扫描 `06/07/08/09/10` 与真实代码面后，未发现 `TBD / unknown / not planned` 残留项。

### Progress Update `2026-04-11 / Batch 01`

- `Task 2`：已创建 `apps/web`、`apps/api`、`packages/contracts`、`workflows`、`infra`、`migrations` 骨架，并通过 `rg --files apps packages workflows infra migrations` 验证。
- `Task 3`：已冻结 `error / operation / step trace` 初版 contract，新增 `apps/api/openapi.yaml`、FastAPI app factory、health route、operation query baseline；已验证 Python 可导入 app，且 OpenAPI YAML 可解析。
- `Task 4`：已实现并验证 `legacy inventory scanner` 与 `checksum manifest builder`：
  - 测试：`python3 -m pytest migrations/tests/test_legacy_inventory.py migrations/tests/test_checksum_manifest.py`
  - 结果：`4 passed`
  - 真实资产盘点 runbook：`migrations/runbooks/2026-04-11-legacy-inventory-baseline.md`
  - 真实 checksum runbook：`migrations/runbooks/2026-04-11-checksum-baseline.md`

### Progress Update `2026-04-11 / Batch 02`

- `Task 4` 继续推进：
  - 新增 `asset classification` 基线，并用 `08-旧数据逐字段映射与迁移脚本规范.md` 的映射规则冻结 `structured_import / artifact_archive / projection_rebuild_reference / anomaly` 决策。
  - 新增 shared-kernel SQLAlchemy metadata：`workspaces / projects / manuscripts / artifacts / workflow_runs / workflow_steps`
  - 新增 Alembic 骨架：`migrations/alembic.ini`、`migrations/env.py`、`migrations/versions/20260411_0001_shared_kernel.py`
- 验证：
  - `python3 -m pytest apps/api/tests/test_shared_schema_baseline.py migrations/tests/test_legacy_inventory.py migrations/tests/test_checksum_manifest.py migrations/tests/test_asset_classification.py`
  - 结果：`9 passed`
- 新增 runbook：
  - `migrations/runbooks/2026-04-11-asset-classification-baseline.md`

### Progress Update `2026-04-11 / Batch 03`

- `Task 3` 补完 operation contract 基线缺口：
  - FastAPI baseline 新增 `/api/v2/operations/{operation_id}/events`
  - FastAPI baseline 新增 `/api/v2/operations/{operation_id}/stream`
  - OpenAPI 同步新增 `events` 与 `stream` 两条路径
- 验证：
  - `python3 -m pytest apps/api/tests/test_operation_contract_baseline.py`
  - 结果：`1 passed`

### Progress Update `2026-04-11 / Batch 04`

- `Task 4` 新增 dry-run 汇总与 CLI：
  - `migrations/dry_run.py`
  - `migrations/tests/test_dry_run_summary.py`
  - `migrations/tests/test_dry_run_cli.py`
  - `migrations/runbooks/2026-04-11-dry-run-baseline.md`
- dry-run 当前已能统一输出：
  - `project_count`
  - `entry_count`
  - `classification_counts`
  - `zero_byte_assets`
  - `anomalies`
- `Task 2 / Phase 1` 补充统一开发入口：
  - 根目录 `Makefile`
  - 根目录 `.tool-versions`
- `Task 2 / Phase 1` 补充统一配置模型：
  - `AppSettings`
  - `DbSettings`
  - `ObjectStorageSettings`
  - `LlmFacilitySettings`
- 并行侧车已验收：
  - `infra/**`：compose/env/README 基线已落地，并通过 `docker compose ... config`
  - `workflows/**`：worker bootstrap 与测试已落地，并通过 `python3 -m pytest workflows/tests -q`
- 发现并修复 monorepo 测试导入冲突：
  - `workflows` 测试不再依赖与 `apps/api` 冲突的 `src.*` 命名空间
- 本轮联合验证：
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`16 passed`

### Progress Update `2026-04-11 / Batch 05`

- `Task 4` 继续推进对象制品注册表：
  - shared schema 新增 `artifact_objects`
  - `manuscripts`、`artifacts` 新增 `artifact_object_id` 引用
  - Alembic 首个 revision 已同步更新
- 新增迁移规划组件：
  - `migrations/object_registry_plan.py`
  - `migrations/import_plan.py`
  - `migrations/tests/test_object_registry_plan.py`
  - `migrations/tests/test_import_plan.py`
  - `migrations/tests/test_import_plan_cli.py`
- 新增 runbook：
  - `migrations/runbooks/2026-04-11-object-registry-baseline.md`
  - `migrations/runbooks/2026-04-11-import-plan-baseline.md`
- 真实结果：
  - object registry `entry_count = 5`
  - import plan `entry_count = 14`
  - `projects/proj_1edaa458dd75/story_graph.sqlite3` 继续显式落入 `skipped_rebuild_refs`
- 本轮联合验证：
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`21 passed`

### Progress Update `2026-04-11 / Batch 06`

- shared schema 继续扩张到 `archive-library` 主事实层：
  - `entities`
  - `archives`
  - `memories`
  - `memory_events`
- `artifact_objects` 已正式进入 shared schema，并由 `manuscripts / artifacts` 引用，不再只是迁移计划里的字符串目标。
- Alembic 首个 revision 已同步包含：
  - shared-kernel
  - object registry
  - archive-library 核心事实表
- 验证：
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`21 passed`

### Progress Update `2026-04-11 / Batch 07`

- shared DB schema 已按上下文拆分，不再继续把所有表堆在一个文件：
  - `shared_kernel.py`
  - `archive_library.py`
  - `llm_facility.py`
  - `worldline.py`
  - `table_helpers.py`
- 新增 `llm-facility` 主事实表：
  - `llm_providers`
  - `llm_channels`
  - `llm_models`
  - `llm_module_bindings`
- 新增 `worldline` 主事实表：
  - `worldline_preparations`
  - `prepared_agent_dossiers`
  - `worldline_sessions`
  - `world_states`
  - `timeline_events`
  - `session_agents`
  - `agent_actions`
  - `agent_dialogues`
- Alembic 新增第二个 revision：
  - `migrations/versions/20260411_0002_llm_worldline.py`
- 新增测试：
  - `apps/api/tests/test_context_schema_baseline.py`
- 本轮联合验证：
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`24 passed`

### Progress Update `2026-04-11 / Batch 08`

- `Task 4` 已从 planning baseline 进入最小 `import-only` 执行阶段：
  - `migrations/import_only.py`
  - `migrations/db_runtime.py`
  - `migrations/sqlite_extractors/task_runtime.py`
  - `migrations/sqlite_extractors/chapter_meta.py`
  - `migrations/sqlite_extractors/llm_facility.py`
  - `migrations/sqlite_extractors/archive_library.py`
  - `migrations/sqlite_extractors/worldline_prepare.py`
- 新增测试：
  - `test_import_only.py`
  - `test_import_only_cli.py`
  - `test_import_only_system_sqlite.py`
  - `test_import_only_llm.py`
  - `test_import_only_archive_library.py`
  - `test_import_only_worldline.py`
- 新增 runbook：
  - `migrations/runbooks/2026-04-11-import-only-baseline.md`
- 真实结果：
  - `import-only` 已能导入 `project/object/manuscript/artifact + task_runtime + chapter_meta + llm_facility + archive_library`
  - worldline 资产在“项目存在”场景下可导入；当前真实旧数据里 4 条 worldline 资产仍 blocked，原因是其目录缺 `project.json`
- 本轮联合验证：
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`33 passed`

### Progress Update `2026-04-11 / Batch 09`

- `Task 4` 的 `import-only` 继续推进，已消化 system 与 archive/worldline 的最小导入：
  - `task_runtime.sqlite3 -> workflow_runs`
  - `chapter_meta.sqlite3 -> chapters + chapter_history_items`
  - `llm_facility.sqlite3 -> llm_providers + llm_channels + llm_models + llm_module_bindings`
  - `archive_library.sqlite3 -> entities + archives + memories + memory_events`
  - `worldline prepare/session` 在“项目存在”的场景下可导入
- 真实 `import-only` 当前只剩 4 条 worldline 资产 blocked，原因都是其目录缺 `project.json`
- `/api/v2` contract 继续冻结：
  - 新增 `workspace` 路由基线
  - 新增 `llm-facility` 路由基线
  - 当前 OpenAPI 已覆盖 `workspaces + graph + llm + operations`
- 本轮联合验证：
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`38 passed`

### Progress Update `2026-04-11 / Batch 10`

- `/api/v2` 业务 contract 继续冻结，新增：
  - `archive-library` 路由占位
  - `writer` 路由占位
- 当前 OpenAPI 已覆盖：
  - `workspaces`
  - `graph`
  - `llm`
  - `archive`
  - `writer`
  - `operations`
- `import-only` 真实运行结果进一步收口：
  - 现在只剩 4 条 worldline 资产 blocked
  - `archive_library.sqlite3` 与 `llm_facility.sqlite3` 已不再阻塞
- 本轮联合验证：
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`40 passed`

### Progress Update `2026-04-11 / Batch 11`

- `Task 4` 的真实 import-only 剩余 blocker 已清零：
  - `archive_library.sqlite3` 已导入
  - `llm_facility.sqlite3` 已导入
  - worldline 资产在“project 缺失”场景下已允许按 orphan worldline 导入
  - 当前真实 `blocked_targets = []`
- `/api/v2` 继续从 contract 占位推进到真查询：
  - `GET /api/v2/workspaces`
  - `GET /api/v2/workspaces/{workspace_id}`
  这两条已不再返回 `501`，而是走真实 DB 查询
- `/api/v2` 路由基线现已覆盖：
  - `workspaces`
  - `graph`
  - `llm`
  - `archive`
  - `writer`
  - `worldline`
  - `operations`
- 本轮联合验证：
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`44 passed`

### Progress Update `2026-04-11 / Batch 12`

- `Task 4` 继续收口：
  - 真实 `import-only` 已清零 `blocked_targets`
  - worldline orphan 资产允许在 `project_id = null` 场景下导入，anomaly 继续保留
- `/api/v2` 从占位继续推进到真实查询，当前已打通：
  - `GET /api/v2/workspaces`
  - `GET /api/v2/workspaces/{workspace_id}`
  - `GET /api/v2/llm/settings`
  - `GET /api/v2/archives`
  - `GET /api/v2/archives/{archive_id}`
  - `GET /api/v2/archives/{archive_id}/memories`
  - `GET /api/v2/archives/{archive_id}/memory-events`
  - `GET /api/v2/chapter-context/options`
  - `GET /api/v2/workspaces/{workspace_id}/reviewer-rules`
  - `GET /api/v2/worldlines/preparations/{preparation_id}`
  - `GET /api/v2/worldlines/preparations/{preparation_id}/agents`
  - `GET /api/v2/worldlines/sessions`
  - `GET /api/v2/worldlines/sessions/{session_id}`
  - `GET /api/v2/worldlines/sessions/{session_id}/timeline`
  - `GET /api/v2/workspaces/{workspace_id}/graph`
  - `GET /api/v2/workspaces/{workspace_id}/graph/nodes/{node_id}`
- 当前结论：
  - 各主要 bounded context 已至少有一条真实 `/api/v2` 查询链路
  - 其余大量命令面和复杂查询面仍是显式 `501`，但不再存在“只有路径没有任何真实查询”的上下文
- 本轮联合验证：
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`49 passed`

### Progress Update `2026-04-12 / Batch 13`

- `Task 4` 补齐了 worldline runtime projection 真空地带：
  - inventory 现在可扫描 `system/global_worldlines/graphs/*/worldlines/{runtime.sqlite3,sessions/*/session.json}`
  - checksum manifest 与 import plan 已纳入 system global worldline 资产
  - 新增 `migrations/sqlite_extractors/worldline_runtime.py`
  - 新增 `migrations/worldline_runtime_importer.py`
  - `import-only` 现在可导入：
    - `session_agents`
    - `agent_state_snapshots`
    - `agent_actions`
    - `agent_dialogues`
    - `relation_events`
- `Task 5` 继续推进 worldline query lane：
  - `GET /api/v2/worldlines/sessions/{session_id}/agents/{agent_id}`
  - `GET /api/v2/worldlines/sessions/{session_id}/agent-history`
  - `GET /api/v2/worldlines/sessions/{session_id}/agent-actions`
  - `GET /api/v2/worldlines/sessions/{session_id}/agent-dialogues`
  - `GET /api/v2/worldlines/sessions/{session_id}/relations`
  - `GET /api/v2/worldlines/sessions/{session_id}/events`
  这些接口已不再返回 `501`，而是走新 projection 的真实查询。
- shared schema 已新增 / 扩张：
  - `session_agents.agent_id`
  - `session_agents.role / drive / tension / status / summary / can_chat / can_act / state_json / state_source / state_version / source_ref / last_action_at / last_dialogue_at`
  - `agent_actions.intent / target / source / detail_json / applied_at / discarded_at`
  - `agent_dialogues.reply / model_name / context_summary`
  - `agent_state_snapshots`
  - `relation_events`
- Alembic 已新增：
  - `migrations/versions/20260411_0006_worldline_runtime_projection.py`
- 新增 runbook：
  - `migrations/runbooks/2026-04-12-worldline-runtime-projection-baseline.md`
- 真实旧数据 `import-only` 结果：
  - `blocked_targets = []`
  - anomaly 新增：
    - `ws_3ffe941c7761: imported legacy branch branch_1 as current_world; ignored 2 extra branches`
  - 导入后计数：
    - `worldline_sessions = 2`
    - `session_agents = 2`
    - `agent_state_snapshots = 4`
    - `agent_actions = 0`
    - `agent_dialogues = 0`
    - `relation_events = 0`
- 本轮联合验证：
  - `python3 -m py_compile apps/api/src/interfaces/http/worldline.py apps/api/src/modules/worldline/query_service.py migrations/worldline_runtime_importer.py migrations/sqlite_extractors/worldline_runtime.py migrations/import_only.py`
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`51 passed`

### Progress Update `2026-04-12 / Batch 14`

- `Task 4` 补齐了 `task_runtime.sqlite3 -> workflow_steps` 的真实拆解：
  - `migrations/sqlite_extractors/task_runtime.py` 现在读取 `result_json / metadata_json / progress_detail_json`
  - 新增 `migrations/task_runtime_importer.py`
  - `import-only` 现在会把 `progress_detail_json.timeline` 同时导入：
    - `workflow_steps`（按 `stage` 聚合）
    - `workflow_events`（按 timeline 原始事件落库）
  - `workflow_runs.project_id` 现在可从 `metadata_json.project_id` 回填
- `Task 5` 新增 operations query lane 的真实读取：
  - `GET /api/v2/operations/{operation_id}`
  - `GET /api/v2/operations/{operation_id}/steps/{step_id}`
  - `GET /api/v2/operations/{operation_id}/events`
  - `GET /api/v2/operations/{operation_id}/stream`
  这四条接口已不再返回 `501`，支持：
  - 按 `workflow_run_id` 查询
  - 按 `legacy_task_id` 兼容查询 operation
  - 按 `workflow_step_id` 或 `step_key` 查询单个 step trace
  - 读取持久化 operation event log
  - 基于 `workflow_events` 做 SSE replay，并支持 `Last-Event-ID` 续播
- 真实旧数据 `import-only` 落库计数：
  - `workflow_runs = 286`
  - `workflow_steps = 1747`
  - `workflow_events = 5662`
  - 样例 stage：
    - `extract_text`
    - `segment_chapters`
    - `skeleton_timeline`
- 文档同步：
  - `重构方案/08-旧数据逐字段映射与迁移脚本规范.md` 已补充 `progress_detail_json.timeline -> workflow_steps / operation_events` 的当前实现说明
  - `migrations/runbooks/2026-04-11-import-only-baseline.md` 已同步更新 task runtime 导入范围
- 本轮联合验证：
  - `python3 -m py_compile apps/api/src/interfaces/http/operations.py apps/api/src/modules/operations/query_service.py migrations/task_runtime_importer.py migrations/sqlite_extractors/task_runtime.py migrations/import_only.py`
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`52 passed`

### Progress Update `2026-04-12 / Batch 15`

- `Task 5` 继续推进 worldline agent console query lane：
  - `GET /api/v2/worldlines/sessions/{session_id}/agent-memory`
  - `GET /api/v2/worldlines/sessions/{session_id}/agent-memory-context`
  这两条接口已不再返回 `501`，当前实现基于：
  - `session_agents`
  - `agent_actions`
  - `agent_dialogues`
  - `archives`
  - `memories`
- 新增模块：
  - `apps/api/src/modules/worldline/memory_query_service.py`
- 当前 memory projection 规则：
  - `session_memories`：由 runtime action/dialogue 日志派生
  - `long_term_memories`：读取 archive 下非 candidate 记忆
  - `candidate_memories`：读取 archive 下 candidate 记忆
  - `agent-memory-context`：将以上三组真实数据渲染为可解释上下文与 `debug_hits`
- 本轮联合验证：
  - `python3 -m py_compile apps/api/src/interfaces/http/worldline.py apps/api/src/modules/worldline/query_service.py apps/api/src/modules/worldline/memory_query_service.py apps/api/src/interfaces/http/operations.py apps/api/src/modules/operations/query_service.py migrations/task_runtime_importer.py migrations/worldline_runtime_importer.py migrations/import_only.py`
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`52 passed`

### Progress Update `2026-04-12 / Batch 16`

- `Task 5` 继续推进 archive + writer command lane：
  - `POST /api/v2/archives/{archive_id}/memory-adoptions`
  - `POST /api/v2/archives/{archive_id}/memory-rejections`
  - `PUT /api/v2/workspaces/{workspace_id}/reviewer-rules`
  这些接口已不再返回 `501`。
- 新增模块：
  - `apps/api/src/modules/archive/memory_review_service.py`
- 当前 archive memory review 语义：
  - 只允许对 `candidate` 记忆执行 adopt/reject
  - adopt 时会将同 `memory_type + normalized_subject` 的 active canon 标记为 `superseded`
  - adopt/reject 都会写入 `memory_events`
  - 重复 adopt / 重复 reject / 非 candidate 操作都会显式返回 `400`
- writer reviewer rules 写接口已按旧语义承接：
  - `custom_prompt=""` 等价于恢复默认规则
  - `workspace_settings` 不存在时会插入，存在时更新
- contract 同步：
  - `apps/api/openapi.yaml` 已补上 `PUT /api/v2/workspaces/{workspaceId}/reviewer-rules`
- 本轮联合验证：
  - `python3 -m py_compile apps/api/src/interfaces/http/archive.py apps/api/src/modules/archive/memory_review_service.py apps/api/src/interfaces/http/writer.py`
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`53 passed`

### Progress Update `2026-04-12 / Batch 17`

- `Task 5` 继续推进 worldline + llm 命令面：
  - `POST /api/v2/worldlines/sessions/{session_id}/event-adoptions`
  - `PATCH /api/v2/worldlines/sessions/{session_id}/events/{event_id}`
  - `POST /api/v2/llm/channels`
  - `PATCH /api/v2/llm/channels/{channel_key}`
  - `DELETE /api/v2/llm/channels/{channel_key}`
  - `PUT /api/v2/llm/module-bindings/{module_key}`
  - `DELETE /api/v2/llm/module-bindings/{module_key}`
  这些接口已不再返回 `501`。
- 新增模块：
  - `apps/api/src/modules/worldline/event_command_service.py`
  - `apps/api/src/interfaces/http/worldline_commands.py`
  - `apps/api/src/modules/llm/command_service.py`
- 当前 worldline event command 语义：
  - 只允许对 `candidate` 事件执行 adopt/reject/edit
  - `event-adoptions` 支持批量将 candidate 事件标记为 `canon` 或 `rejected`
  - `event edit` 会更新 summary/title，并将该 candidate 事件提升为 `canon`
  - 非 candidate 事件编辑、空 `event_ids`、非法 action 都显式返回 `400`
- 当前 llm-facility command 语义：
  - channel create 会创建 `llm_providers + llm_channels`
  - channel patch 支持局部更新 `name/base_url/api_key/is_enabled/max_concurrency/timeout_ms`
  - disabled channel 不允许绑定 model
  - channel delete 会清理关联 `bindings + models + channel + provider`
  - module binding delete 会显式返回 `{deleted: true}`，重复删除返回 `404`
- contract 同步：
  - `apps/api/openapi.yaml` 已补 `DELETE /api/v2/llm/channels/{channelKey}`
  - `apps/api/openapi.yaml` 已补 `DELETE /api/v2/llm/module-bindings/{moduleKey}`
- 本轮联合验证：
  - `python3 -m py_compile apps/api/src/interfaces/http/worldline_commands.py apps/api/src/modules/worldline/event_command_service.py apps/api/src/interfaces/http/llm.py apps/api/src/modules/llm/command_service.py apps/api/src/bootstrap/app_factory.py`
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`56 passed`

### Progress Update `2026-04-12 / Batch 18`

- `Task 5` 继续推进 graph command lane：
  - `PATCH /api/v2/workspaces/{workspace_id}/graph-template-configs/{template_key}`
  该接口已不再返回 `501`，当前实现为真实 upsert。
- 新增模块：
  - `apps/api/src/modules/graph/command_service.py`
- 当前 graph template config 语义：
  - `status` 为必填
  - 若 `workspace` 下只有一个 `project`，默认落到该 `project`
  - 若 `workspace` 下有多个 `project`，必须显式传 `project_id`，否则返回 `400`
  - 同一 `project_id + template_key` 会更新既有配置，不重复插入
- 本轮联合验证：
  - `python3 -m py_compile apps/api/src/interfaces/http/graph.py apps/api/src/modules/graph/command_service.py`
  - `python3 -m pytest apps/api/tests workflows/tests migrations/tests`
  - 结果：`57 passed`

Plan complete and saved to `docs/plans/2026-04-11-mirofish-novel-full-rebuild-plan.md`.
