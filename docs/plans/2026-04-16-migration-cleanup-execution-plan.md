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
| Phase A (C2/C3/C4) | _未开始_ | | |
| Phase C (剩余测试) | _未开始_ | | |
| Phase D / Task 3 | _未开始_ | | |
| Phase D / Task 4 | _未开始_ | | |
| Phase D / Task 11 | _未开始_ | | |
| Phase E / Task 6 worldline | _未开始_ | | |
| Phase F / Task 7 archive-assets-llm | _未开始_ | | |
| Phase G / Task 8 novel-graph-seed | _未开始_ | | |
| Phase H / Task 9 搜索抽象 | _未开始_ | | |

---

## 十、下一会话开工指令（给 Claude）

把下面这段话粘进下一会话：

```
当前在 /Volumes/Fanxiang S500Pro/项目/novelwork-chonggou，分支 gemini，HEAD 应为 5314810。
先读 docs/plans/2026-04-16-migration-cleanup-execution-plan.md（执行路线图）和
docs/plans/2026-04-14-database-unification-migration-plan.md（技术方案）。
按本次我指定的 Phase 开工，结束时在执行路线图的 §九 追加完成记录。

本次要做的是：<Phase X>
```

Claude 必须：
- 开 TaskCreate 跟踪进度
- 破坏性操作前 `git tag` 新 anchor
- 每个 Phase 以 clean working tree + green tests 收尾
- Phase 结束在本文件 §九 留痕
