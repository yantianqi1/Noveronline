# MiroFish-Novel SaaS GPT-5.5 Subagent Development Plan

更新时间：`2026-07-07`

## 用途

本文用于把当前 SaaS 重构未完成任务拆成可交给子智能体并行推进的开发计划。它不替代：

- `docs/refactor-saas/DEVELOPMENT_PLAN.md`：总纲和阶段顺序。
- `tasks/refactor-saas-live-progress.md`：实时进度和验证流水。
- `tasks/refactor-saas-parallel-board.md`：任务状态看板。
- `docs/refactor-saas/19-parallel-development-orchestration.md`：并行开发规则。
- `docs/refactor-saas/20-agent-window-identities-and-prompts.md`：窗口身份和交接格式。

本文的核心目标是：在不反转总纲、不恢复旧架构、不伪造成功的前提下，用多个 `gpt-5.5` 子智能体加速推进真实闭环缺口。

## 当前进度读数

按产品真实闭环估算，当前整体完成度约为 `55%-60%`。看板中很多条目已经有 schema、API、read side、fail-closed worker shell 或 metadata-only 用户动作，但仍不等价于完整产品闭环。

| Phase | 当前闭环进度 | 未完成重点 |
|---|---:|---|
| Phase 0 | 100% | 已 verified，继续保持总纲、覆盖矩阵和 worktree 边界。 |
| Phase 1 | 80%-90% | Writer 真实 LLM-bound draft generation、reviewer、dedup、book plan、chapters/scenes/manuscript API、one-click actions 仍待验收或补齐。 |
| Phase 2 | 70%-80% | Writer tools 已接入 assets/graph/worldline paths；live LLM reference E2E、proposal tools 和更完整上下文引用仍 pending。 |
| Phase 3 | 70%-80% | Go API、Next shell、Postgres/RLS、Temporal/Python/Pi worker skeleton 已落地；完整 compose health、真实 Temporal handoff、Auth/tenant/project picker 仍 pending。 |
| Phase 4 | 75%-85% | LLM Facility 已有 binding/channel/model/trace/usage/secure key/concurrency；live provider/cluster E2E、retry backend、quota/billing aggregation 仍 pending。 |
| Phase 5 | 45%-60% | Seed/Assets/Graph skeleton 和部分真实持久化已落地；`story_ontology` 与 `entity_resolution` 已有 LLM Facility runner skeleton、DB-backed snapshot writer 和 env wiring；Go upload/complete -> Temporal cluster -> Python parse/segment E2E、OCR PDF、完整智能分段、agent profile/finalize runner、vector/hybrid search、Story Graph candidate adoption/live E2E 仍 pending。 |
| Phase 6 | 35%-45% | Worldline step 和最小 LLM candidate producer 已推进，Character Console metadata skeleton 已硬化；runtime-generated saved paths、prepare runtime、richer director tools、Character Console runtime 仍 pending。 |
| Phase 7 | 0%-10% | Legacy import report skeleton blocked，旧架构清理未开始。 |
| Phase 8 | 0%-10% | Auth/Ops/Billing/Security/production hardening 仍主要停留在设计和少量底座。 |

当前主线仍是 Phase 5：补齐 Seed parse/segment 能力与 live object upload -> pipeline E2E。最近已完成的代码切片是 `P5 Seed entity_resolution LLM Facility runner skeleton + DB-backed snapshot writer/env wiring`；当前推荐下一步是完整验证 Go API upload/complete -> Temporal cluster -> Python parse/segment。

## 子智能体统一规则

所有子智能体必须使用 `gpt-5.5` 主模型：

```text
model = gpt-5.5
reasoning_effort = high
service_tier = priority
```

如果通过 `multi_agent_v1.spawn_agent` 启动，使用：

```text
agent_type = worker
model = gpt-5.5
reasoning_effort = high
service_tier = priority
```

如果通过 Codex 新线程启动，使用：

```text
model = gpt-5.5
thinking = high
target = worktree
startingState.branchName = codex/saas-mainline
```

全体子智能体必须遵守：

1. 只在 `/Users/yantianqi/Documents/Noveronline-saas-mainline` 或从该 worktree 派生的独立 worktree 工作。
2. 不修改主仓库 `/Users/yantianqi/Documents/Noveronline`。
3. 开工前确认分支基线和 dirty worktree，不能回滚用户或其他智能体改动。
4. 读 `DEVELOPMENT_PLAN.md`、`22-midstream-handoff-summary.md`、对应 phase 文档和本计划。
5. 代码行为变更必须 TDD：先 RED，再最小实现，再 GREEN，再 broader verification。
6. 不新增 mock success、fake data、silent fallback、swallowed error 或旧式 LLM env fallback。
7. 所有 LLM 调用必须走 LLM Facility。
8. 公共 API/UI 不得暴露 prompt、response、body/content raw text、API key、encrypted credential、`credential_ref`、object key、draft 或 manuscript。
9. body 中的 `tenant_id` / `project_id` 不可信，必须以 header/path/context 为准。
10. Worldline 保持单世界 `current_world`，不恢复旧多分支主模型。
11. Character Console 不得生成假 AI 回复、假 runtime events 或假 chapter draft success。
12. 除 Coordinator 外，子智能体不要直接修改 `tasks/refactor-saas-parallel-board.md`、`tasks/refactor-saas-live-progress.md` 和 `docs/refactor-saas/18-legacy-coverage-matrix.md`；完成后提交建议更新内容，由 Coordinator 统一落盘，避免冲突。

## 推荐并行节奏

### Wave 0：Coordinator 准备

负责人：主控窗口，不派给 worker。

目标：

- 确认主仓库 dirty 状态，只读不改。
- 确认 SaaS worktree 分支为 `codex/saas-mainline`。
- 冻结本计划和每个 worker 的可写范围。
- 每个 worker 启动时都要求返回固定交接格式。

验收：

- `git status --short --branch` 在主仓库和 SaaS worktree 均已记录。
- 每个 worker 的 write scope 互不重叠。
- 每个 worker 都有 RED/GREEN/broader verification 命令。

### Wave 1：最高收益并行

建议同时启动 4 个 worker，先补真实闭环证明和低冲突模块：

| Agent | 优先级 | 目标 | 并行理由 |
|---|---:|---|---|
| A1 Seed Live E2E | P0 | 打通 Go upload/complete -> Temporal cluster -> Python parse/segment live E2E | 当前主线，直接提升 Phase 5 闭环度。 |
| A2 Writer Live LLM E2E | P0 | 验证 Writer/Pi Runtime/LLM Facility 真实 provider draft path | Phase 1/4 关键真实链路，不与 Seed 主文件冲突。 |
| A3 Asset Search/Vector | P1 | 补 asset versions/collections/embeddings/hybrid search 或明确第一批 DB-backed search | 与 Seed/Writer 解耦，可并行推进 Writer 上下文质量。 |
| A4 Story Graph Runner | P1 | 补 real `graph_bond_generator` runner 或 graph candidate adoption flow | 与 Asset 可共享 canon 契约但写域独立，提升图谱闭环。 |

### Wave 2：Runtime 深水区

Wave 1 至少完成 A1 或 A2 的真实 E2E 后再启动：

| Agent | 优先级 | 目标 | 依赖 |
|---|---:|---|---|
| A5 Worldline Runtime | P1 | runtime-generated saved paths、prepare runtime、richer director tools、external provider/cluster E2E | 依赖现有 worldline step/candidate 基线。 |
| A6 Character Console Runtime | P1 | 真实 LLM Facility-backed interaction runtime，带 trace/audit/permissions/fail-closed | 依赖 Worldline runtime 和 Character metadata skeleton。 |
| A7 Seed Semantic Runners | P1 | agent profile、finalize/readiness 以及 semantic runner live-provider E2E | 避开 A1 对 Seed core 文件的高冲突时段。 |
| A8 LLM Facility Retry/Quota | P2 | retry backend、quota enforcement、billing aggregation | 依赖 live provider/usage 写入稳定。 |

### Wave 3：收尾和上线能力

| Agent | 优先级 | 目标 |
|---|---:|---|
| A9 Auth/Ops/Security | P2 | login、tenant/project picker、compose health、backup/restore、log redaction、incident playbook。 |
| A10 Legacy Import/Cleanup | P3 | legacy import report、旧 endpoint 替代关系、旧架构清理。 |

## Agent 任务卡

### A1 Seed Live E2E Worker

模型：`gpt-5.5`，reasoning `high`。

目标：

- 证明真实 Go API upload/complete -> Temporal cluster -> Python worker parse/segment 能在 Postgres + MinIO/S3-compatible object storage 上跑通。
- 结果只能声明 parse/segment E2E，不声明 ontology/entity/profile/finalize 已完成。

建议可写范围：

- `apps/api/internal/sourcefiles/`
- `apps/api/internal/workflows/`
- `apps/api/internal/httpapi/`
- `apps/api/cmd/api/`
- `apps/agent-runtime/mirofish_agents/temporal/seed.py`
- `apps/agent-runtime/tests/test_seed_live_e2e.py`
- `infra/docker-compose.yml`
- 相关 focused test fixtures

禁止触碰：

- `apps/web/` UI 大改。
- `apps/api/internal/assets/`
- `apps/api/internal/storygraph/`
- `apps/api/internal/worldline/`
- `apps/api/internal/characterconsole/`

TDD 起点：

- RED：新增 opt-in live test，缺真实 upload/complete -> Temporal/Python handoff 时失败或 skip 条件明确。
- GREEN：在配置 live env 时能完成 source object upload、complete、workflow admission、Temporal worker parse、segment object/row 写入和 sanitized public events。

验证：

```bash
cd apps/api && go test ./internal/sourcefiles ./internal/workflows ./internal/httpapi -run 'Seed|Upload|SourceFile|Temporal' -count=1
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py tests/test_seed_live_e2e.py -q
cd apps/api && go test ./...
git diff --check
```

交付必须说明：

- 哪些 live env 变量必须配置。
- 当前默认环境是 skip 还是 pass。
- 是否仍未覆盖 browser upload、OCR PDF、LLM provider、ontology/entity/profile/finalize。

### A2 Writer Live LLM E2E Worker

模型：`gpt-5.5`，reasoning `high`。

目标：

- 验证 Writer run admission -> Pi Writer Runtime -> LLM Facility credential decrypt/provider call -> draft revision -> workflow events/trace/usage/status 的真实链路。
- 不引入旧式 env fallback，不调用假 provider，不生成假 draft。

建议可写范围：

- `apps/pi-agent-runtime/`
- `apps/api/internal/writer/`
- `apps/api/internal/workflows/`
- `apps/api/internal/llmfacility/`
- `apps/api/internal/httpapi/` 中 Writer/LLM 相关 focused paths
- `apps/web/src/app/**/writer` 或 `apps/web` Writer route 的最小测试补充

禁止触碰：

- Seed core parse/segment 文件。
- Worldline/Character Console runtime 文件。
- Story Graph/Asset runner 文件。

TDD 起点：

- RED：真实 DB-backed writer admission + provider fixture 路径不能完成 draft persistence 或 telemetry correlation。
- GREEN：同一 `run_id` 下 draft、workflow event、trace、llm_activity、usage 都可关联，公开响应不泄露 prompt/API key/credential。

验证：

```bash
cd apps/pi-agent-runtime && npm run test
cd apps/pi-agent-runtime && npm run typecheck
cd apps/api && go test ./internal/httpapi ./internal/workflows ./cmd/api -run 'Writer|LLM|Activity|Usage' -count=1
cd apps/web && npm run test -- --test-name-pattern='Writer|writer'
git diff --check
```

### A3 Asset Search/Vector Worker

模型：`gpt-5.5`，reasoning `high`。

目标：

- 在现有 Asset CRUD/search/facets/ingestion/style skeleton 上，补第一批真实 DB-backed asset versions/collections/embeddings 或 hybrid/vector search 能力。
- 优先选择一个可验证闭环，不要一次铺开所有子系统。

建议可写范围：

- `apps/api/internal/assets/`
- `apps/api/internal/httpapi/` 中 Asset paths
- `apps/agent-runtime/` asset/search 相关 runner 和 tests
- `apps/web/` Asset Library 最小 client/test
- `infra/` 仅限必要 migration/extension 配置

禁止触碰：

- Seed live E2E files。
- Story Graph runner files。
- Writer runtime files。

TDD 起点：

- RED：当前 search 只 keyword/sanitized list，无法返回 DB-backed vector/hybrid result 或 asset collection/version metadata。
- GREEN：返回 public metadata、稳定错误、tenant scoped 查询和无 raw content 泄露。

验证：

```bash
cd apps/api && go test ./internal/assets ./internal/httpapi -run 'Asset|Search|Vector|Collection|Version' -count=1
cd apps/agent-runtime && .venv/bin/python -m pytest tests -q -k 'asset or search or embedding'
cd apps/web && npm run test -- --test-name-pattern='Asset|asset'
git diff --check
```

### A4 Story Graph Runner Worker

模型：`gpt-5.5`，reasoning `high`。

目标：

- 补 real `graph_bond_generator` runner、semantic merge/layout hardening 或 candidate adoption flow 中的一个完整 verified slice。
- 不能写假 bond/thread/canon。

建议可写范围：

- `apps/api/internal/storygraph/`
- `apps/api/internal/httpapi/` 中 Story Graph paths
- `apps/agent-runtime/` graph-heavy workflow/activity/runner/tests
- `apps/web/` Story Graph route 的最小 client/test

禁止触碰：

- Asset ingestion runner 共享文件，除非先和 A3 协调。
- Seed live E2E 文件。
- Worldline/Character Console files。

TDD 起点：

- RED：`graph_bond_generator` 缺 LLM Facility real runner 或 candidate adoption 仍 fail-closed。
- GREEN：schema-valid public candidate metadata 可持久化或显式 adoption 可完成，公开响应清洗 evidence/body/prompt/credential。

验证：

```bash
cd apps/api && go test ./internal/storygraph ./internal/httpapi -run 'StoryGraph|Graph|Bond' -count=1
cd apps/agent-runtime && .venv/bin/python -m pytest tests -q -k 'graph'
cd apps/web && npm run test -- --test-name-pattern='Story Graph|graph'
git diff --check
```

### A5 Worldline Runtime Worker

模型：`gpt-5.5`，reasoning `high`。

目标：

- 在现有 Worldline step/candidate/event/adoption/saved-path metadata 基础上，推进 runtime-generated saved paths、prepare runtime、richer director tools 或 external provider/cluster E2E。
- 不自动采用 candidate 为 canon，不写 Writer draft/manuscript。

建议可写范围：

- `apps/api/internal/worldline/`
- `apps/api/internal/httpapi/` 中 Worldline paths
- `apps/agent-runtime/mirofish_agents/temporal/worldline*.py`
- `apps/agent-runtime/tests/test_worldline_workflow.py`
- `apps/web/` Worldline route focused client/test

禁止触碰：

- Character Console runtime files，除非当前任务是 shared contract 且 Coordinator 批准。
- Writer draft/manuscript adoption paths。

TDD 起点：

- RED：runtime 无法从 provider/candidate events 生成 saved path 或 prepare runtime 仍 metadata-only。
- GREEN：真实 runtime 只写 public metadata，trace/audit/status 清晰，失败 fail closed。

验证：

```bash
cd apps/api && go test ./internal/worldline ./internal/httpapi ./cmd/api -run 'Worldline|Step|SavedPath|Preparation' -count=1
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_worldline_workflow.py -q
cd apps/web && npm run test -- --test-name-pattern='Worldline|worldline'
git diff --check
```

### A6 Character Console Runtime Worker

模型：`gpt-5.5`，reasoning `high`。

目标：

- 只有在能实现真实 LLM Facility-backed runtime 时才推进 Character Console runtime。
- 最小合格 runtime 必须具备 tenant/project/session/interaction/run context、permission check、trace、audit、workflow status、sanitized public events 和 fail-closed errors。

建议可写范围：

- `apps/api/internal/characterconsole/`
- `apps/api/internal/httpapi/` 中 Character Console paths
- `apps/agent-runtime/` character interaction workflow/activity/runner/tests
- `apps/web/` Character Console focused client/test

禁止触碰：

- 不写假 agent turn。
- 不把 runtime events 伪造成成功。
- 不直接写 Writer draft/manuscript，除非通过真实 Writer run admission 且用户显式动作触发。

TDD 起点：

- RED：`GET /events` 仍 pending 或 `POST /turns` 只保存 metadata，不产生真实 runtime event。
- GREEN：真实 runtime 产出 schema-valid public event/turn metadata；缺 binding/credential/provider 时明确失败。

验证：

```bash
cd apps/api && go test ./internal/characterconsole ./internal/httpapi ./cmd/api -run 'Character|Interaction' -count=1
cd apps/agent-runtime && .venv/bin/python -m pytest tests -q -k 'character or interaction'
cd apps/web && npm run test -- --test-name-pattern='Character|interaction'
git diff --check
```

### A7 Seed Semantic Runners Worker

模型：`gpt-5.5`，reasoning `high`。

目标：

- 在 `story_ontology` 和 `entity_resolution` 已有 DB-backed runner/writer/env wiring 的基础上，补 `character_agent_profile`、finalize/readiness、semantic runner live-provider E2E 或 entity-resolution 失败边界 hardening 中的一个可验证 slice。
- 只能通过 LLM Facility 调 provider，并持久化 schema-valid private snapshot / public metadata counts。

建议可写范围：

- `apps/agent-runtime/mirofish_agents/temporal/seed.py`
- `apps/agent-runtime/tests/test_seed_workflow.py`
- `apps/api/internal/workflows/` Seed result/read side focused paths
- `docs/refactor-saas/06-seed-pipeline.md` 的 worker-local建议更新

禁止触碰：

- 与 A1 同时修改 Seed live E2E handoff 代码。
- 修改 upload/object verifier/API request-id/privacy hardening。

TDD 起点：

- RED：`character_agent_profile` / finalize semantic path 缺真实 runner，或 provider/write/status 失败后 workflow result/event 不稳定。
- GREEN：缺 binding/credential/provider fail closed；成功只写 public counts/snapshot metadata，不公开 profile/resolution/ontology body。

验证：

```bash
cd apps/agent-runtime && .venv/bin/python -m pytest tests/test_seed_workflow.py tests/test_seed_sequential_reader.py -q
cd apps/api && go test ./internal/workflows ./internal/httpapi -run 'Seed|Ontology|Entity|Profile|Finalize' -count=1
git diff --check
```

### A8 LLM Facility Retry/Quota Worker

模型：`gpt-5.5`，reasoning `high`。

目标：

- 补 retry backend、quota enforcement、billing aggregation 中的一个明确 verified slice。
- 不影响 provider invocation 和 credential decrypt 已有安全边界。

建议可写范围：

- `apps/api/internal/llmfacility/`
- `apps/api/internal/workflows/`
- `apps/api/internal/httpapi/` 中 LLM/usage/retry paths
- `apps/web/` LLM Facility focused panels/tests

禁止触碰：

- Pi Writer provider adapter core，除非必须接入 quota gate 且有 RED/GREEN。
- Worldline/Seed provider runners 的业务输出。

TDD 起点：

- RED：用量超过 quota 不会 fail closed，或 retry route 仍只能返回 backend unconfigured。
- GREEN：tenant/project/module scoped quota/retry 行为稳定，公开错误不泄露私密 payload。

验证：

```bash
cd apps/api && go test ./internal/llmfacility ./internal/workflows ./internal/httpapi -run 'LLM|Usage|Quota|Retry' -count=1
cd apps/web && npm run test -- --test-name-pattern='LLM|Usage|Quota|Retry'
git diff --check
```

### A9 Auth/Ops/Security Worker

模型：`gpt-5.5`，reasoning `high`。

目标：

- 补 login、tenant/project picker、compose health、backup/restore、log redaction、incident playbook 中的一个生产化 slice。
- 优先做可测试的基础能力，不做大规模 UI 重写。

建议可写范围：

- `apps/api/internal/auth/`
- `apps/api/internal/tenant/`
- `apps/web/` shell auth/project picker focused files
- `infra/`
- `docs/refactor-saas/16-deployment-and-ops.md`

禁止触碰：

- Writer/Seed/Worldline runtime core。
- 数据模型大改，除非先冻结 migration contract。

验证：

```bash
cd apps/api && go test ./internal/auth ./internal/tenant ./cmd/api -run 'Auth|Tenant|Project|Health' -count=1
cd apps/web && npm run test -- --test-name-pattern='Auth|Tenant|Project|Shell'
git diff --check
```

### A10 Legacy Import/Cleanup Worker

模型：`gpt-5.5`，reasoning `high`。

目标：

- 建立 legacy project import report 的真实 skeleton，或推进旧 endpoint/page 覆盖矩阵状态核对。
- 不把未导入项目标记为成功。

建议可写范围：

- `docs/refactor-saas/17-migration-roadmap.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md` 的建议 patch
- `apps/api/internal/legacyimport/` 如需新增
- import report focused tests

禁止触碰：

- 旧 FastAPI runtime fallback。
- 任何用户私有小说原文、上传产物、API key 或本地 DB。

验证：

```bash
cd apps/api && go test ./... -run 'Legacy|Import|Coverage' -count=1
git diff --check
```

## Coordinator 集成清单

每个 worker 返回后，Coordinator 必须做：

1. 阅读 worker 汇报，确认 `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED`。
2. 检查 changed files 是否在授权写范围内。
3. 检查是否触碰主仓库或回滚他人改动。
4. 运行 worker 的 focused tests。
5. 运行受影响模块 broader tests。
6. 搜索公开响应和文档中是否出现敏感字段：

```bash
rg -n "api_key|encrypted_api_key|credential_ref|prompt|response|content_text|body_text|source_text|object_key|draft|manuscript" <changed-public-files>
```

7. 更新：

- `tasks/refactor-saas-live-progress.md`
- `tasks/refactor-saas-parallel-board.md`
- `docs/refactor-saas/18-legacy-coverage-matrix.md`
- 相关 phase 文档：`06` / `07` / `08` / `09` / `10` / `11` / `12` / `13` / `14` / `15` / `16`

8. 最后运行：

```bash
git diff --check
```

## 子智能体启动提示词模板

复制给每个 worker 时，把 `{AGENT_ID}`、`{TASK}`、`{WRITE_SCOPE}` 和 `{VERIFY}` 替换为任务卡内容。

```markdown
你是 MiroFish-Novel SaaS 重构的 {AGENT_ID} 子智能体。请使用 gpt-5.5 主模型，reasoning high，service tier priority。

工作区：
- 只在 /Users/yantianqi/Documents/Noveronline-saas-mainline 或当前子线程派生 worktree 工作。
- 不要修改 /Users/yantianqi/Documents/Noveronline。
- 当前基线分支是 codex/saas-mainline。

必读：
- docs/refactor-saas/DEVELOPMENT_PLAN.md
- docs/refactor-saas/22-midstream-handoff-summary.md
- tasks/refactor-saas-live-progress.md
- tasks/refactor-saas-parallel-board.md
- tasks/refactor-saas-gpt55-subagent-development-plan.md
- 与本任务相关的 phase 文档

硬约束：
- TDD：先写 RED 并确认失败，再最小实现，再 GREEN，再 broader verification。
- 不新增 mock success、fake data、silent fallback、swallowed error 或旧式 LLM env fallback。
- LLM 调用必须走 LLM Facility。
- body tenant_id/project_id 不可信，使用 header/path/context。
- 公开 API/UI 不得暴露 prompt、response、body/content raw text、API key、encrypted credential、credential_ref、object key、draft、manuscript。
- 不要回滚他人改动；你不是代码库里唯一的 worker。

任务：
{TASK}

可写范围：
{WRITE_SCOPE}

不可写范围：
- tasks/refactor-saas-parallel-board.md
- tasks/refactor-saas-live-progress.md
- docs/refactor-saas/18-legacy-coverage-matrix.md
- 任务卡列出的禁止触碰目录

验证：
{VERIFY}

完成后按以下格式交接：

## Status
DONE / DONE_WITH_CONCERNS / BLOCKED

## Identity
- Agent:
- Model: gpt-5.5
- Branch:
- Worktree:

## Files Changed
- ...

## What Changed
- ...

## Verification
- Command:
- Result:

## Contract Changes
- API:
- DB:
- Workflow:
- Shared types:

## Coordinator Doc Updates Needed
- tasks/refactor-saas-live-progress.md:
- tasks/refactor-saas-parallel-board.md:
- docs/refactor-saas/18-legacy-coverage-matrix.md:
- other docs:

## Risks / Follow-ups
- ...
```

## 建议首批启动顺序

1. 立即启动 A1、A2、A3、A4 四个 `gpt-5.5` worker。
2. Coordinator 本地不等待所有 worker，先准备集成验证脚本和 progress 更新模板。
3. A1 返回后优先集成，因为它决定 Phase 5 主线闭环。
4. A2 返回后补 Phase 1/4 live E2E 状态。
5. A3/A4 返回后按写域冲突低优先集成。
6. Wave 1 集成完后再启动 A5/A6/A7，避免 Seed core 和 Worldline/Character runtime 的高冲突重叠。

当前不建议一次性同时启动 8-10 个 coding worker。最优并行度是 4 个 coding worker + 1 个 Coordinator；超过这个数量时，冲突解决和验证成本会吞掉并行收益。
