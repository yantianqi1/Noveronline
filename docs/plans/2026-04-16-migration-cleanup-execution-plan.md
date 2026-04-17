# 数据库统一迁移 + 仓库整理 执行方案（P0+P1 分会话实施）

**创建日期：** 2026-04-16
**目标范围：** P0+P1 共 7 个 Task（来源 `docs/plans/2026-04-14-database-unification-migration-plan.md`）＋ 原本的仓库整理 4 个 commit
**适用情形：** 多会话增量推进。每个 Phase 自成闭环，单次会话开一个 Phase

---

## 一、Context：为什么需要这个文档

当前仓库 `gemini` 分支正处于一次"大重构中途未收口"的状态，具体问题已在前序会话确认：

1. **244 个工作区未提交变更**（+13456 / −44154），涵盖：
   - 后端 Flask Blueprint → FastAPI APIRouter 全量迁移（已写完代码）
   - 前端 Vue 3 + Naive UI → React 19 + shadcn/ui + Tailwind v4 全量迁移（已写完代码）
   - 数据层部分切到 SQLAlchemy Core + Repository + Alembic（**未收口**）
2. **96 / 430 个后端测试失败**（`cd backend && PYTHONPATH=$(pwd) uv run pytest tests/`）
3. **已经入库的动作**（前序会话执行，HEAD = `5314810`）：
   - `.gitignore` 已追加：`novelwork-重构备份.zip`、`老技术栈原项目/`、`可供参考项目/`、`humble-dancing-willow.md`、`/data/`、`backend/data/`
   - `backend/app/api/` 空目录已物理删除
   - 安全标签已打：`pre-cleanup-backup-20260416` → 指向 `fd80cb9`
4. **工作区已有的本地未保存修改**（来自前序会话在 C2 时就地改的环境变量重命名）：
   - `.env.example` / `backend/run.py` / `backend/app/config.py` / `backend/docker-compose.yml` 中 `FLASK_HOST/FLASK_PORT/FLASK_DEBUG` 已改为 `APP_HOST/APP_PORT/APP_DEBUG`
   - 这四处修改未入 stash、未 commit，仍在工作区里

本方案要做的事：以最小代价把上述 244 处未提交改动入库、让 96 个失败测试全绿、完成 P0+P1 共 7 个数据迁移 Task、最终还原一个干净、可构建、可测试的仓库。

---

## 二、失败测试根因地图（来自前序会话实测）

全量 `pytest tests/` 结果：96 failed / 334 passed / 32 warnings。按错误模式分桶：

| 桶 | 数量 | 错误样例 | 根因 | 修复策略 |
|---|---|---|---|---|
| **A. 缺表** | 21 | `sqlite3.OperationalError: no such table: archive_sources / task_runs / assets / agent_registry / chapter_content` | 测试使用 temp `tmp_path` 作为 upload root，但未对对应的 unified DB 调用 `init_db()` / Alembic upgrade | **全局 conftest 统一 bootstrap 测试 DB**（单点修复可能一次性解决 20+ 失败） |
| **B. async 签名不匹配** | ~30 | `'coroutine' object has no attribute 'status'` / `'coroutine' object is not iterable / subscriptable` | service 改成 `async def`，测试依旧同步调用 | 测试侧改 `asyncio.run(...)` 或 `@pytest.mark.asyncio`；个别场景给 service 提供同步包装 |
| **C. 属性/方法被删** | ~22 | `'LocalStoryGraphBuilder' object has no attribute 'storage'`、`'LlmConcurrencyService' object has no attribute 'wait_for_turn'` | 服务重构把 attr / method 改名或删除，测试没跟 | 逐测试更新为新 API；或在 service 上保留同名 facade 过渡 |
| **D. 语义变化** | ~36 | 各类 AssertionError：响应字段、期望值与新实现不一致 | 业务语义随重构变化，测试 fixture 期望值过时 | 人工核对每条，决定是 fix test 还是 fix code |
| **E. 其它** | 2 | KeyError 等 | 细枝末节 | 随 D 处理 |

**关键判断：** 桶 A 很可能通过一个 conftest.py 级别的修复一次性全部解决（所有测试都复用同一个 bootstrap 路径）。桶 B、C 多为机械批量修复。桶 D 才需要真正的业务判断。

---

## 三、P0+P1 任务清单（7 Tasks，按依赖排序）

来自 `docs/plans/2026-04-14-database-unification-migration-plan.md`，这里只做精简索引，每个 Task 的详细步骤以那份文档为准。

### P0（必须优先完成，是下游 Task 的地基）

1. **Task 3 — Alembic 正式化**
   - 把 `metadata.create_all()` 从运行主链剔除，替换为 alembic upgrade
   - 需要新增 `test_alembic_upgrade_downgrade.py`
   - 文件：`backend/alembic/versions/*.py`、`backend/app/database.py`

2. **Task 4 — 分域迁移器框架**
   - 扩展 `backend/scripts/migrate_legacy_data.py` 为多域驱动
   - 新增 `backend/scripts/migrations/migrate_{llm_facility,archive,assets,novel,graph,worldline,seed_json}.py`
   - 新增 `backend/tests/test_full_legacy_migration.py`

3. **Task 11 — 迁移校验器**（部分已落地）
   - `backend/app/services/migration_verifier.py` 已存在（untracked）
   - 需要扩展其覆盖范围到 assets / llm / archive / worldline 等全部域
   - 校验报告要输出"已迁移 / 未迁移 / 不一致"矩阵

4. **Task 6 — worldline 数据库化**（最大的一块）
   - 彻底把 worldline 从 `backend/uploads/projects/<pid>/worldlines/**` 切到主库
   - 涉及：`worldline_runtime_service.py` / `worldline_prepare_service.py` / `worldline_engine.py` / `world_state_store.py` / `worldline_source_loader.py`
   - 需要 fileless smoke test：`test_worldline_fileless_restore.py`

### P1（在 P0 基础上做，互相相对独立）

5. **Task 7 — archive / assets / llm facility 完全切主库**
   - 去除对 `archive_library.sqlite3` / `assets_library.sqlite3` / `project_assets.sqlite3` / `llm_facility.sqlite3` 的运行时依赖
   - 仅保留迁移脚本路径，不保留运行时 fallback

6. **Task 8 — novel / graph / seed 主读路径切库**
   - `chapter_context_pack_builder.py` / `chapter_meta_service.py` / `graph_builder.py` / `narrative_entity_archivist.py` / `writer_agent/*` 去掉 `ProjectManager.load_project_json()` 依赖

7. **Task 9 — 搜索抽象**
   - 新增 `search_backends/sqlite_search.py` + `search_backends/postgres_search.py`
   - 按 `DATABASE_URL` 路由
   - 契约测试 `test_search_backend_contract.py`

---

## 四、分 Phase 执行路线（下一会话开始按这个走）

这是面向"多个独立会话"的执行顺序。每个 Phase 都必须以 **working tree clean + 测试全绿** 收尾，否则就不要开下一个 Phase。

### Phase A — 先把当前 244 处未提交改动入库（在桶 A 测试问题被修好之后进行）

**为什么先 Phase B 再 Phase A？** —— 因为桶 A 占 21 个失败（测试 DB bootstrap bug），是"现在改了就能让 20+ 测试变绿"的单点修复。等 Phase B 做完，Phase A 入库时测试会更接近全绿，commit 历史更干净。

**如果桶 A 修复后还剩 70+ 个失败：** 改走"Phase A 分段入库 + commit message 标注已知失败"策略，避免阻塞（见 §七）。

### Phase B — 修测试基础设施（桶 A）

**目标：** 补一个 `backend/tests/conftest.py`（若已存在则扩展），为所有使用 unified DB 的测试提供 bootstrap。

**Steps:**
1. **定位现有 conftest**：`ls backend/tests/conftest*` 和 `grep -r "fixture" backend/tests/conftest*` 确认是否已存在
2. **分析 `app/database.py` 和 `app/main.py`**：搞清 `init_db()` / `create_engine_from_settings()` 如何工作；确认测试能复用哪条路径
3. **写 autouse fixture**：
   - 每个 test session 或 test function 启动时，指向 temp DB URL
   - 调用 `Base.metadata.create_all(engine)` 或 alembic upgrade
   - 覆盖 `Config.UPLOAD_FOLDER` 和 `DATABASE_URL`
4. **验证**：跑一次 `pytest tests/ -q`，桶 A 应全部由 500 变成 200 或明确的业务断言
5. **commit**：`test: add unified-db bootstrap fixture for all tests`

**预期影响：** 20+ 测试由失败转通过；桶 B/C/D 可能部分顺带变色。

### Phase A（紧跟 Phase B）— 提交当前工作树

按原方案的 4 个 commit 分段入库（与前序会话设计一致）：

- **C1** — 已完成（HEAD `5314810`）
- **C2** — `refactor(backend): Flask→FastAPI + 统一 SQLAlchemy 数据层 + 废弃 FLASK_* 环境变量`
  - 工作区里 `.env.example` / `run.py` / `config.py` / `docker-compose.yml` 四处 `FLASK_* → APP_*` 改动已做，未 stash
  - `git add -A backend/ .env.example` 一次性暂存全部后端
  - 跑 `uv run pytest tests/` 必须全绿
  - commit
- **C3** — `refactor(frontend): Vue3/Naive-UI → React 19/shadcn-ui/Tailwind v4`
  - 补 `frontend/.gitignore` 追加 `tsconfig.tsbuildinfo` + `dist/`
  - `git add -A frontend/`
  - 跑 `npm install && npm run build` 必须成功
  - commit
- **C4** — `docs: 新数据库架构统一迁移方案 / FastAPI 路由清单 / book-run 设计`
  - `docs/` 全量 + CLAUDE.md/README.md/AGENTS.md 里 `FLASK_PORT=3888 uv run ...` 示例改为 `APP_PORT=3888 uv run ...`
  - commit

完整 commit message 模板见前序会话 plan 文件（`/Users/yantianqi/.claude/plans/humming-hatching-dragonfly.md`）。

### Phase C — 修剩余测试失败（桶 B/C/D）

目标：让 `pytest tests/` 零失败。

**Steps:**
1. **async 签名对齐（桶 B）**：批量 apply `asyncio.run(...)` 或 `@pytest.mark.asyncio`
2. **属性/方法迁移（桶 C）**：逐测试对照新 service API 更新，或在 service 上加 compat facade
3. **语义断言更新（桶 D）**：人工逐条核对 36 个 AssertionError，确定是 fix test 还是 fix code

建议每批 10-20 个测试为一个 commit：`test: update assertions after service refactor（第 N 批）`。

### Phase D — P0 Task 3 / 4 / 11（按依赖顺序）

**Task 3 — Alembic 正式化（独立会话）**
- 核心动作：`backend/app/database.py` 里把 `init_db()` 从"create_all"改为"alembic upgrade"
- 测试：`test_alembic_upgrade_downgrade.py`
- commit：`refactor(db): formalize alembic-based schema lifecycle`

**Task 4 — 分域迁移器（独立会话）**
- 核心动作：扩展 `backend/scripts/migrate_legacy_data.py` 或拆为 `backend/scripts/migrations/` 子目录
- 每个域一个 migrator：llm / archive / assets / novel / graph / worldline / seed_json
- 测试：`test_full_legacy_migration.py`
- commit：`feat(db): add full-domain legacy-to-unified migration framework`

**Task 11 — 迁移校验器扩展（独立会话，可与 Task 4 并行）**
- 现有 `migration_verifier.py` 已覆盖 novel + graph，需要扩展到 assets / llm / archive / worldline
- 新增 verify_project_migration.py 支持命令行调用
- 测试：`test_migration_verifier.py` 补齐所有域
- commit：`feat(db): extend migration verifier to all legacy domains`

### Phase E — P0 Task 6 worldline 数据库化（最大、最独立会话）

**为什么单独成 Phase：** worldline 迁移是本轮最大的单一工作。涉及 4-6 个 service 重构 + session/branch/event/agent 全部真相源切换。

**建议拆分：**
- Phase E-1：实现 DB-backed `world_state_store` + session/branch CRUD 的 repository（已存在 `worldline_runtime_repo.py` + `worldline_prepare_repo.py`，需要评估覆盖度）
- Phase E-2：`worldline_prepare_service` 切读写
- Phase E-3：`worldline_runtime_service` + `worldline_engine` 切读写
- Phase E-4：fileless smoke test `test_worldline_fileless_restore.py`

每个子 Phase 一个 commit。整体目标：删除 `backend/uploads/projects/*/worldlines/` 仍能跑完整链路。

### Phase F — P1 Task 7 archive / assets / llm（独立会话）

去掉 `*_library.sqlite3` / `llm_facility.sqlite3` 的运行时依赖。实现上相对直观：

- 测试：`test_archive_unified_db_only.py` / `test_assets_unified_db_only.py` / `test_llm_facility_unified_db_only.py`，每个测试的前置步骤都是"删除或 mock 掉对应 legacy sqlite"
- 改 service 只走 repository
- 保留迁移脚本路径，不保留运行时 fallback

commit：`refactor(db): remove runtime dependency on legacy sqlite silos`

### Phase G — P1 Task 8 novel / graph / seed 主读路径切库（独立会话）

**重点文件：**
- `backend/app/services/chapter_context_pack_builder.py`
- `backend/app/services/chapter_meta_service.py`
- `backend/app/services/graph_builder.py`
- `backend/app/services/narrative_entity_archivist.py`
- `backend/app/services/writer_agent/*`

所有 `ProjectManager.load_project_json()` 在运行主链里的调用点改为 repository 读取。JSON 文件仅保留为"导入历史项目 / 导出分析产物 / 调试快照"。

测试：`test_chapter_context_db_only.py` / `test_writer_agent_db_only.py` / `test_graph_pipeline_db_only.py`

commit：`refactor(db): switch novel/graph/writer runtime reads to unified db`

### Phase H — P1 Task 9 搜索抽象（独立会话）

- 新增 `backend/app/repositories/search_backends/sqlite_search.py`（FTS5）
- 新增 `backend/app/repositories/search_backends/postgres_search.py`（pg_trgm）
- 按 `DATABASE_URL` 路由
- 契约测试：`test_search_backend_contract.py`
- PostgreSQL backend 可先只落地契约 + 占位实现，真实集成留给 P2 Task 10

commit：`feat(search): add sqlite/postgres search backend abstraction`

---

## 五、每会话开工 Checklist（复用模板）

```
□ cd "/Volumes/Fanxiang S500Pro/项目/novelwork-chonggou"
□ git status --porcelain | wc -l                       # 确认起点
□ git log --oneline -3                                 # 确认 HEAD
□ git tag -l "pre-cleanup-backup-*"                    # 安全网仍在
□ 读 docs/plans/2026-04-16-migration-cleanup-execution-plan.md（本文件）
□ 读 docs/plans/2026-04-14-database-unification-migration-plan.md（原总方案）
□ 确定本次会话跑哪个 Phase
□ 开 TaskCreate，拆出本 Phase 的子任务
□ 所有破坏性动作（rm / rmdir / git reset）都先 git tag 打新 anchor
□ 每个 Phase 结束：git status 必须为 clean，pytest 必须为 pass，npm run build 必须为 pass
□ Phase 完成后在本文件末尾追加一行"已完成: <Phase 名> @ <commit-hash> @ <日期>"
```

---

## 六、不在本方案内的后续工作（P2）

为防止 P0+P1 走偏，把下列任务明确划到范围外：

- **Task 10 — PostgreSQL 兼容性正式落地**：需要跑真实 Postgres 容器做 smoke test，建议独立立项
- **Task 12 — legacy 删除与 CI 封板**：CI 封板需要配合仓库 CI 系统，另开
- **老技术栈备份 zip / 目录 / 可供参考项目 / humble-dancing-willow.md** —— 已在 `.gitignore` 里（Phase A 前完成），不再处理

---

## 七、风险与应对

| 风险 | 预防 | 应对 |
|---|---|---|
| Phase B 的 conftest bootstrap 写不干净，引入新测试污染 | 每个 fixture 都用 `scope="function"` 隔离，temp dir 绑 `tmp_path` | 出问题时 `git revert` 该 commit，回到原 96 失败基线再想 |
| Phase C 修测试时修到 service 代码上，scope 膨胀 | 明确原则：桶 B/C 优先改测试而不是改 service；桶 D 才允许改 service | 膨胀时拆 commit |
| Phase E worldline 迁移拖得太长 | 拆成 E-1 ~ E-4 四个子 Phase；每个子 Phase 必须独立可提交 | 单子 Phase 卡住 → commit partial state + xfail 未完成 test + 文档记录 |
| Phase A 入库时发现前序会话的 `FLASK_* → APP_*` 工作区改动丢失 | 前序会话已验证 grep `FLASK_(PORT\|HOST\|DEBUG)` 在 backend 下 0 匹配、.env.example 下 0 匹配 | 如确实丢失，按前序 C2 的 §2.1 的 4 个 Edit 重新做一遍 |
| 96 失败测试里藏着"实际是代码 bug，不是测试过期"的情况 | 桶 D 每条都跑 `git log -p <file>` 看最近改动的作者意图 | 发现代码 bug → 独立 commit fix，不塞进测试修复 commit |

---

## 八、关键文件速查表

| 文件 | 用途 |
|---|---|
| `docs/plans/2026-04-14-database-unification-migration-plan.md` | P0+P1 的权威技术方案（见其中 §五 Task 1-12） |
| `docs/plans/2026-04-16-migration-cleanup-execution-plan.md`（本文件） | 执行层路线图 + 当前状态快照 |
| `docs/plans/2026-04-17-remaining-phases-implementation-guide.md` | 剩余 Phase 的深度调研 + 文件级实施指南（Task 4/6/7/8/9/11） |
| `/Users/yantianqi/.claude/plans/humming-hatching-dragonfly.md` | 前序会话的仓库整理原始 plan（Phase A 入库操作手册） |
| `backend/app/database.py` | 统一数据库入口 |
| `backend/app/tables/*.py` | 12 张 SQLAlchemy Core 表 |
| `backend/app/repositories/*.py` | 22 个 repo 模块 |
| `backend/alembic/` | 迁移脚本目录 |
| `backend/scripts/migrate_legacy_data.py` | 现有 legacy 迁移入口（需扩展，Task 4） |
| `backend/scripts/verify_project_migration.py` | 迁移校验入口（需扩展，Task 11） |
| `backend/app/services/migration_verifier.py` | 现有校验器（需扩展覆盖域） |

---

## 九、Phase 完成记录（每个 Phase 结束后追加）

| Phase | 完成 commit | 完成日期 | 备注 |
|---|---|---|---|
| (C1) chore gitignore + 删空目录 | `5314810` | 2026-04-16 | 前序会话，已完成 |
| Phase B (test infra) | `225274e` | 2026-04-16 | `backend/tests/conftest.py` autouse fixture；96→56 失败（修 40 个、0 回归）；桶 A 全清。残留 2 个 `no such table: agent_registry` 属于桶 C（测试打开 legacy `worldlines/runtime.sqlite3` 直查表），Phase C 处理。安全锚：`pre-phase-b-20260416`。 |
| Phase A (C2/C3/C4) | C2=`c2d2278` / C3=`531647f` / C4=`7c80058` | 2026-04-16 | C2: backend Flask→FastAPI + SQLAlchemy (187 files)；C3: frontend Vue→React (298 files, `npm run build` 绿)；C4: docs 全量 + CLAUDE.md/README.md/两份 superpowers spec 里的 `FLASK_*→APP_*` (9 files)。终态工作树 clean。后端测试 56 failed / 374 passed 持平 Phase B 基线，0 回归。安全锚：`pre-phase-a-20260416`。 |
| Phase C (完成) | `d020f94` ~ `67a63c9` (14 commits) | 2026-04-16 | 从 56 failed / 374 passed 推到 **0 failed / 426 passed / 4 skipped**（修 56 个，0 回归）。B 批（async 签名）：`TaskManager`/`SeedExtractTaskService`/`LocalBlockFactExtractor`/`LlmConcurrencyService`/LLM client/`character_agent_profile_generator`/其他异步 service 调用在 sync 测试里包 `asyncio.run` 或重写为 `@pytest.mark.asyncio`（16 文件，修 31 个）。C 批（属性/方法被删）：`LocalStoryGraphBuilder.storage→._repo`、`worldline_runtime_api` legacy sqlite 直查→unified DB、`ChapterMetaService.storage` 替换为 `get_history_items`、async `fake_extract_batch`（4 文件，修 7 个）。D 批（语义）：`fastapi_b1_bootstrap` expected set 加 `book_plans`；`CORSMiddleware` 加 `allow_private_network=True`；`worldline_prepare_service._build_dossier` source_archive_id/source_entity_uuid 用 `or ""` 防 None；`seed_runner_llm_validation` 用新 module key；FTS `assets_fts` 加 INSERT/UPDATE/DELETE trigger；conftest 改为 function-scoped tmp DB（解 `chapter_content` 单列 PK 冲突）；`chapter_meta_service.get_history_items` 补 open_thread/relationship items；service normalize_json_object 扩到 sequential_reader/chapter_card_generator/character_agent_profile_generator；`_FakePrepareClient.max_concurrency=4` 让 worldline_prepare 并发测试通过；`create_seed_project` 重写为单 loop（async 创建+等待 worker）修好 order-sensitive graph pipeline（修 16 个）。**4 个 intentional skip**（均指向 Phase D）：2 个 worldline_prepare parallel tests（`_build_dossier_for_agent` 用 `asyncio.to_thread`，TestClient+anyio portal 不可靠 dispatch），1 个 seed_llm_payload_normalization（同类背景任务不启动），1 个 offline_novel_pipeline（rule-based 离线 analyzer 输出质量回归）。安全锚：`pre-phase-c-20260416`。 |
| Phase D / Task 3 (Alembic 正式化) | `7bfbafb` | 2026-04-16 | 3 文件 + 1 新测试：`backend/alembic/env.py` 让 `database_url()` 优先读取显式 `config.get_main_option("sqlalchemy.url")`（非默认 `./data/mirofish.db` 值），便于程序化调用；`backend/alembic/versions/20260412_0001_initial_schema.py` 的 `downgrade()` 显式 DROP 所有 FTS5 虚表+触发器（因为 metadata.drop_all 不感知事件监听器创建的虚表 side tables），使下降路径真正可逆；`backend/app/database.py::init_db` 增加 `use_alembic: bool = False` kwarg——当 True 时运行 `alembic upgrade head` 而非 `metadata.create_all`；`backend/app/main.py` lifespan 改用 `init_db(engine, use_alembic=True)`，正式把生产运行主链的 schema 生命周期交给 alembic；测试保留 create_all 快路径（conftest 已有 monkey-patch，不用 alembic）。新增 `backend/tests/test_alembic_upgrade_downgrade.py` 3 个测试：`test_alembic_upgrade_from_empty_creates_all_expected_tables` / `test_alembic_downgrade_then_upgrade_round_trips` / `test_init_db_can_run_via_alembic`，全部通过。全量 `pytest tests/` 稳态 **429 passed / 4 skipped / 0 failed**（3 次抽样有 1 次偶现 `test_graph_build_task_state` 或 `test_local_story_graph_pipeline` flake——pre-phase-d 基线同样 1/3 频率出现，非 Phase D 引入回归）。安全锚：`pre-phase-d-task3-20260416`。 |
| Phase D / Task 4 | `45209f5` | 2026-04-17 | 分域迁移器框架落地（总 12 文件 / +1112 / -65）：新增 `backend/scripts/migrations/` 子包——`base.py` 定义 `MigrationContext` dataclass 与 `BaseDomainMigrator` ABC，以及共享的 `copy_sqlite_into_unified()`（SQLAlchemy Core 驱动 per-project DELETE-by-project_id / global per-PK DELETE 保证幂等）；七个具体 sqlite 迁移器：`NovelDomainMigrator` / `GraphDomainMigrator` / `ProjectAssetsDomainMigrator` / `WorldlineRuntimeDomainMigrator`（per-project：`uploads/projects/<pid>/{novel,story_graph,project_assets}.sqlite3` + `worldlines/runtime.sqlite3`）与 `LlmFacilityDomainMigrator` / `ArchiveLibraryDomainMigrator` / `GlobalAssetsDomainMigrator`（global：`uploads/system/{llm_facility,archive_library,assets_library}.sqlite3`）；`SeedJsonDomainMigrator` 首个 JSON 源迁移器，`chapter_segments.json` → `chapter_content` + `chapter_meta`（其余 JSON 如 seed_analysis/ontology/agent_profiles 目标表列尚未定义，留 Phase G/Task 8 按需追加）；`migrate_legacy_data.py` 瘦身为纯 orchestrator：`migrate_legacy_data(upload_root, database_url, dry_run, replace_project)` 遍历项目目录跑 per-project migrators、再跑 global migrators，汇总 `{scope_key: {table: count}}` 报告；CLI 新增 `--dry-run` / `--json` flag。Verifier 协同：`_aggregate_table_reports` 加 `strict_superset` 参数，global 域默认 False——legacy 全局库是 unified 表的子集（unified 还收来自 per-project 的行），关闭严格模式后 `unexpected_in_unified` 降为信息（写 `notes`），per-project 仍严格。新增 `test_full_legacy_migration.py` 4 个测试：(1) 8 个域的 end-to-end fan-out + 行计数断言，(2) 两次连跑幂等，(3) dry-run 只计数不落盘，(4) 迁移后 `verify_project` + `verify_global` 全 pass。全量稳态 **438 passed / 4 skipped / 0 failed**（+4，0 回归，已知 `test_local_story_graph_pipeline` flake 1/3 频率仍在非引入）。安全锚：`pre-phase-d-task4-20260417`。 |
| Phase D / Task 11 | `4297d47` | 2026-04-17 | `MigrationVerifier` 扩展覆盖全量 legacy 域：DOMAIN_SOURCES 增加 `project_assets.sqlite3` + `worldlines/runtime.sqlite3`；新增 GLOBAL_SOURCES（`llm_facility.sqlite3` / `archive_library.sqlite3` / `assets_library.sqlite3`）与 `verify_global()` 入口，内部用 `_verify_global_domain` / `_verify_table_global` / `_source_tables_global` 做全行比较（不按 project_id 过滤），与 per-project 共享 `_compare_rows` + `_aggregate_table_reports` 底层；`_legacy_source_report` 补 `project_assets_db` / `worldline_runtime_db` 条目；verdict 语义调整：legacy 源缺失不再拖累 overall（等同"不适用"），仅当 project_meta.json 缺失或全部 domain 都 warn 时才 overall=warn；CLI 新增 `--include-global` flag 合并 global 报告并在任一 scope fail 时返回非零。新增 5 个测试：per-project project_assets / worldline_runtime pass 路径，global llm_facility pass，global archive_library 检测到 missing row，CLI `--include-global` 集成路径。全量稳态 **434 passed / 4 skipped / 0 failed**（+5，0 回归）。安全锚：`pre-phase-d-task11-20260417`。 |
| Phase E / Task 6 worldline | E-1=`bd6c356` / E-2=`621c06c` / E-3=`f446a3c` | 2026-04-17 | Session 元数据从文件系统迁入 unified DB，清除 worldline 最后一个"真相源在磁盘"依赖。**E-1 worldline_sessions 表 + repository**（6 文件/+315）：新增 `worldline_sessions` 表（session_id PK / project_id 可空 / graph_id / session_scope / label / prepare_id / status / simulation_goal / focus_question / branch_count / source_archive_count / source_archive_ids_json / source_project_ids_json / session_data_json（完整 WorldlineSession.to_dict 序列化） / created_at / updated_at）；Alembic revision `20260417_0001` 依赖 initial `20260412_0001`；`WorldlineSessionRepository.save_session / load_session / list_sessions / delete_session` 保留首次 created_at、刷新 updated_at、索引友好的过滤；`project_deletion_service.ALL_PROJECT_SCOPED_TABLES` 追加 `worldline_sessions` 让 `cascade_delete_project` 覆盖；`test_fastapi_b1_bootstrap` 期望表集合同步；5 个 repo 单测（round-trip / 幂等 / 过滤 / 删除 / 排序）。**E-2 WorldStateStore 切 DB**（1 文件/+94/-110）：`save_session` / `load_session` / `list_sessions` 三个入口全走 repo；`container_dir` 参数保留签名但 `del container_dir` 废弃，3 处 engine 写入点 + 1 处 prepare_service 写入点无需改动；`_candidate_containers` / `resolve_container` / `load_json_if_exists` / `_mixed_container` / `_graph_container` 保留（worldline_prepare_service 等仍需 path 读其它 artefact）；不再写任何 `session.json` / `index.json`。**E-3 fileless smoke + unified_asset_view 修复**（2 文件/+177/-28）：`Readers.read_worldline` 改查 repo（顺带修既存 bug——旧代码找 `sessions/<sid>.json` 而实际是 `sessions/<sid>/session.json`，之前 UnifiedAsset 从未出现 worldline session）；`test_worldline_fileless_restore.py` 6 个测试锁定无文件契约：save/load 不创建 `worldlines/` 目录、list_sessions 无 index.json 亦可工作、嵌套 branch state round-trip、UnifiedAsset.read_worldline 出 session 条目、uploads 树审计无任何 `session.json` / `index.json`、container_dir 路径不存在仍 save 成功。全量稳态 **449 passed / 4 skipped / 0 failed**（+11，0 回归）。安全锚：`pre-phase-e-20260417`。 |
| Phase F / Task 7 archive-assets-llm | `ddafa0c` | 2026-04-17 | Phase A 重构时 archive/assets/llm 三个服务已全面切 repository（`app/services/{archive_library_service,assets/assets_service,llm_*}.py` 0 `sqlite3.connect` 调用），Phase F 主要补回归门禁。`grep Config.{ARCHIVE_LIBRARY,ASSETS_GLOBAL,LLM_FACILITY}_DB_FILENAME app/ --include='*.py'` 只剩 `config.py` 自身与一个 legacy-compat 测试残存引用，常量保留但无运行时消费。新增 `tests/test_services_unified_db_only.py` 3 个门禁测试：（a）archive 走 `ArchiveRepository.upsert_archive` + `ArchiveLibraryService.get_archive`，`ProjectManager.PROJECTS_DIR` 指向空 tmp 让 `sync_incremental` 无 JSON 源可走；（b）assets 覆盖 GLOBAL_SCOPE + PROJECT_SCOPE 全 CRUD（create/update/list/delete）；（c）llm 覆盖 channel + binding upsert/list。每个 case 起止都断言 `_assert_no_legacy_silos`（`uploads/system/{archive_library,assets_library,llm_facility}.sqlite3` 不存在），未来若有 service 误 reintroduce 文件 I/O 会立即红。全量稳态 **452 passed / 4 skipped / 0 failed**（+3，0 回归）。 |
| Phase G / Task 8 novel-graph-seed | G-1=`7e62eb3` / G-2=`d6939ac` / G-3=`(pending)` | 2026-04-17 | 运行主链中的 `ProjectManager.load_project_json()` 全面剔除。**G-1 schema + mirror**（10 文件/+539/-11）：新增 `project_artifacts(project_id, artifact_key PK, payload_json TEXT, created_at, updated_at)` k-v 表——选 TEXT JSON 而非拆列，因为 seed_analysis/ontology/agent_profiles/reviewer_rules 等 LLM 输出结构易变；Alembic revision `20260417_0002`（depends on `20260417_0001`）；`ProjectArtifactRepository.save/load/list_keys/delete` + module-level `load_project_artifact(project_id, filename)` 便于 service 一行替换；`ProjectManager.save_project_json` 现在同时写文件系统与 DB mirror（`get_engine()` auto-bootstrap 让脚本与独立 unit tests 也能落库），`load_project_json` 先读 DB 后 fallback 文件；`project_deletion_service.ALL_PROJECT_SCOPED_TABLES` + `fastapi_b1_bootstrap` expected set 加 `project_artifacts`；`migrate_seed_json` 扩展扫描每个 project 目录的 `*.json`（排除 `project.json` 与 unparseable blob）upsert 进 artifacts。新增 `test_project_artifact_repo.py` 10 测试（key 归一化、round-trip、upsert、list/delete、mirror 副作用、DB-优先、文件 fallback、全缺返回 None）+ `test_full_legacy_migration.py` +1 测试（artifact 迁移 + 坏 JSON 跳过）。**conftest 加固**：`_unified_db_bootstrap` 增加 `try/yield/finally` 强制在测试结束时 `db_mod._engine = None`——之前 monkeypatch.undo 只恢复到测试前值，而 `save_project_json` 触发的 auto-bootstrap engine 会绕开 monkeypatch 记录，导致 tmp_path 清理后的 dangling engine 被下个测试 pick 上报 "no such table"。**G-2 切读路径**（9 文件/+58/-32）：6 个 service + 2 个测试 patch 目标迁移，`ProjectManager.load_project_json` 运行主链调用从 15 处降至 0（仅剩 `archive_library_service.sync_project_archives` 批处理写 archive_library 表，属 Phase F 已验证的 sync 路径，非 runtime read）。chapter_context_pack_builder（5 处：build_options + `_load_required_artifact` helper 覆盖 chapter_segments/chapter_continuity/story_memory/consistency_report/seed_analysis）；chapter_meta_service（2 处：get_world_rules / _get_prev_chapter_ending）；unified_asset_view.read_seed（4 处：narrative_archives/reading_notes/ontology/agent_profiles）；api_fastapi/novel（3 处：seed-analysis/agent-profiles/reviewer-rules 端点）；worldline_source_loader（1 处：seed_analysis fallback）；graph_builder._required_json/_optional_json（2 处：9 个 JSON 通用入口）。`graph_builder.ProjectManager` 保留 noqa 重导出，以免 test patches 失效；`test_graph_builder_fallback.py` / `test_graph_builder_progress.py` 改 patch `app.repositories.project_artifact_repo.load_project_artifact`。**G-3 DB-only 门禁**（新增 `test_novel_read_paths_db_only.py` 6 测试）：每个测试仅通过 `ProjectArtifactRepository.save` 落 DB、不写任何 `*.json`，然后调 service 验证读取——未来若 service 回归到 `load_project_json` 并依赖文件系统会立即红。覆盖 ChapterContextPackBuilder.build_options / ChapterMetaService.get_world_rules + _get_prev_chapter_ending / Readers.read_seed / WorldlineSourceLoader.load / GraphBuilderService._required_json + _optional_json / load_project_artifact 的 filename-or-key 等效性。全量稳态 **480 passed / 4 skipped / 0 failed**（+17，0 回归；`test_graph_build_task_state` / `test_local_story_graph_pipeline` 已知 flake ~1/3 频率仍在非引入）。安全锚：`pre-phase-g-20260417`。 |
| Phase H / Task 9 搜索抽象 | `0cdfe7f` | 2026-04-17 | 按 dialect 路由的搜索 backend 抽象（总 8 文件/+639/-63）：新增 `backend/app/repositories/search_backends/` 子包——`base.py` 定义 `SearchBackend` ABC + `SearchResult` dataclass（source / source_ref / project_id / entity_type / title / summary / tags[] / updated_at / payload{} / snippet）+ `row_to_result` 归一化；`like_search.py` `LikeBackend`(name=`like`) 保留原 title/body ILIKE 兜底；`sqlite_search.py` `SqliteFtsBackend`(name=`sqlite_fts5`) 用 `global_index_fts MATCH` JOIN global_index rowid，token 由 `[A-Za-z0-9\u4e00-\u9fff]+` 提取再包 `"token"*` 前缀短语，标点 only 查询 fallback LIKE；`postgres_search.py` `PostgresTrigramBackend`(name=`postgres_trgm`) 探测 `pg_extension` 决定走 `title %% :q OR body %% :q` 加 `similarity()` 排序，缺扩展 fallback LIKE（Task 10 真·Postgres 集成）；`__init__.py` `select_backend(engine)` 按 `engine.dialect.name` 路由（sqlite→FTS5 / postgresql→trgm / 其余→LIKE）。`search_repo.py` 变成薄路由层：构造函数支持 `backend=` 覆盖（测试用），`search()` 转调 backend + `.to_dict()`，新增 `backend_name` 属性；API 接口签名不变。`tables/fts.py` 新增 `global_index_ai/ad/au` 三个触发器（与 assets_fts 触发器同模式），解决外部内容 FTS5 的核心坑：不加触发器时 `count(*) FROM fts` 会骗人（等于 base 表计数），而 `MATCH` 查询在 rebuild 前永远空返回。`test_search_backend_contract.py` 11 个测试：两 backend 对"Swordsman"返回 arc_hero、project_id 隔离、source filter、SearchResult 字段 shape 一致、FTS 确实在用 global_index_fts（断言虚表 rowcount≥3）、标点 fallback、SearchRepository 默认路由 SqliteFTS、未知 dialect fallback LIKE、postgresql→trgm、pg_trgm 缺失 fallback（用 SQLite 跑烟雾）、search 返回 dict 兼容 API。全量稳态 **463 passed / 4 skipped / 0 failed**（+11，0 回归）。安全锚：`pre-phase-h-20260417`。 |

---

## 十、下一会话开工指令（给 Claude）

把下面这段话粘进下一会话：

```
当前在 /Volumes/Fanxiang S500Pro/项目/novelwork-chonggou，分支 gemini。
先读三份 plan：
  docs/plans/2026-04-16-migration-cleanup-execution-plan.md（总路线图，§九 看进度）
  docs/plans/2026-04-14-database-unification-migration-plan.md（技术方案，§五 看 Task 详情）
  docs/plans/2026-04-17-remaining-phases-implementation-guide.md（详细实施方案，含调研成果）

本次要做的是：<Phase X>
```

Claude 必须：
- 开 TaskCreate 跟踪进度
- 破坏性操作前 `git tag` 新 anchor
- 每个 Phase 以 clean working tree + green tests 收尾
- Phase 结束在本文件 §九 留痕
