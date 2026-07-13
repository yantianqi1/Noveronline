# 28. Zero-start Writer 与正文资产蒸馏

更新时间：`2026-07-13`

## 1. 文档定位

本文定义 SaaS 新项目从零创作，以及已采用正文持续反哺资产库的完整实施方案。

它补充现有 Writer-first 路线，不改变以下既有事实：

- Writer Workbench 是主要创作入口。
- Seed Pipeline 是导入已有小说时的可选知识初始化器，不是创建项目或使用 Writer 的前置条件。
- Agent 只能产生 candidate/draft；进入 manuscript/canon 必须经过用户动作或另行批准的明确策略。
- `assets`、`manuscript_blocks`、`workflow_runs`、LLM Facility 和现有 RLS 仍是主数据与执行底座。
- 本能力不恢复 legacy 应用，不恢复多分支 Worldline，也不建立第二套资产数据库。

范围、当前进度和任务状态仍分别以以下文件为准：

1. `DEVELOPMENT_PLAN.md`
2. `24-current-development-progress.md`
3. `tasks/refactor-saas-parallel-board.md`
4. 当前 worktree、schema 和本轮测试输出

本文是实施设计，不是新的进度真相源。

## 2. 产品目标

新项目必须支持两条平等入口。

### 2.1 入口 A：从零创作

```text
注册 / 新建空项目
  -> Writer Workbench
  -> 故事前提 / Book Plan / Outline
  -> Chapter / Scene
  -> Writer draft 或作者手写正文
  -> 用户采用 / 保存为 manuscript
  -> 正文资产蒸馏 Agent
  -> disabled asset candidates
  -> 用户接受、合并或拒绝
  -> canon/material assets
  -> 后续 Writer 检索
```

该入口不得要求项目先存在：

- 上传文件。
- `source_files`。
- `text_segments`。
- Seed run。
- ontology。
- story graph。
- Worldline session。

### 2.2 入口 B：导入已有小说

```text
上传 TXT / MD / PDF
  -> Seed Pipeline
  -> entities / relationships / world rules / assets / graph
  -> Writer Workbench
  -> 后续 adopted manuscript 继续触发正文资产蒸馏
```

导入项目和空项目最终汇入同一 Writer、资产、手稿和检索模型。Seed 产物与正文蒸馏产物通过 `source_kind`、证据和 lifecycle 区分，不建立两套长期数据结构。

### 2.3 目标结果

- 用户不导入任何原文也能开始创作。
- 资产库随已确认正文逐章增长。
- Agent 自动完成发现、结构化和候选持久化，不自动决定正史。
- 新事实、既有事实更新、冲突和重复拥有明确不同的审阅语义。
- 每条建议能追溯到精确 manuscript block/version/span。
- 正文改版后，旧候选能失效，但已确认资产不会被 Agent 静默回滚。
- 后续 Writer 只消费允许使用的资产，不被未确认候选污染。

## 3. 核心原则

### 3.1 Writer-first，而非 Seed-first

项目创建完成后默认进入可创作状态。项目 readiness 可以提示“尚无资产”“尚无大纲”，但不得阻止 Book Plan、Chapter、Scene、Writer run 或 manuscript 编辑。

### 3.2 正文真相边界

自动蒸馏默认只读取：

- 用户已采用的 Writer draft 对应的 active manuscript block。
- 用户在 Manuscript Workspace 中显式保存的新 content version。
- 用户显式选择并确认用于手动蒸馏的 active manuscript blocks。

未采用 draft、Reviewer issue、Worldline candidate、Character candidate 和临时编辑器缓冲区都不是自动入库来源。

### 3.3 自动入库不等于自动 canon

“自动入库”定义为：Agent 自动把 schema-valid 结果持久化为可审阅的 asset candidate。

默认约束：

```text
lifecycle = candidate
enabled = false
pinned = false
source_kind = manuscript_distillation
```

候选只有在用户接受后才能成为 `canon` 或 `material`。不提供根据 confidence 自动采用的隐式路径。

### 3.4 证据优先

每条候选必须有来源版本和证据 span。模型只返回摘要而没有可验证证据时，该条候选不能进入 pending review。

### 3.5 版本与并发优先

- 正文读取必须绑定 block version 和 SHA-256。
- 更新已有资产必须绑定 expected target asset version。
- 任一版本在处理期间漂移，都必须返回 stale/conflict，而不是覆盖新内容。

### 3.6 隐私优先

- 原文不得出现在 Temporal workflow input、public event、public result、普通日志或 DOM 技术详情中。
- evidence text 只能通过 private permission 路径读取。
- LLM trace 继续沿用现有 private trace 权限，不新增公开 prompt/response 投影。

### 3.7 不按键触发

不得在用户每次键入或普通自动保存时调用 LLM。自动触发只发生在明确内容边界：

- draft adoption。
- manuscript content version 保存或恢复。
- chapter complete。
- 用户手动选择范围并触发。

## 4. 非目标

本方案不包含：

- Agent 自动修改 canon entity、relationship、world rule 核心表。
- Agent 自动接受或覆盖已有资产。
- 从未采用 draft、模拟结果或聊天内容自动抽取资产。
- 逐字实时 LLM 监听。
- 自动删除已确认资产。
- 为每种资产创建独立数据库表。
- 新增第二套向量库或独立知识库。
- 恢复 legacy 多 Agent 永久在线模型。
- 以蒸馏结果替代作者事实判断。
- 在本能力中解决超长导入小说的完整 Seed 分层阅读问题。

## 5. 当前实现复用

### 5.1 空项目

当前注册服务已在同一事务创建 user、personal workspace、project owner membership 和首个空项目。该项目不依赖上传或 Seed 数据。

Z0 需要冻结并证明以下契约，而不是重建项目创建流程：

```text
empty project
  -> book plan
  -> chapter / scene / outline
  -> writer run
  -> draft
  -> adoption
  -> manuscript
```

### 5.2 Manuscript

复用：

- `writer_drafts.status = candidate | adopted | rejected`。
- `manuscript_blocks` active/deleted、version、chapter/scene location、source draft/run。
- `manuscript_block_versions` immutable history。
- Manuscript Workspace 的 optimistic version、restore、delete、move、tag。

实施前需要补强 initial adoption：

- 写入 `scene_id`。
- 写入 `source_writer_run_id`。
- 写入 `updated_by`。
- 为初始 block version 创建 immutable `snapshot_reason = adopt` 快照。

### 5.3 Assets

复用：

- `assets` 作为候选和确认资产主表。
- lifecycle、enabled、source、tags、payload。
- `asset_versions` 的 snapshot envelope 和 restore 语义。
- Asset Catalog detail/version/collection。
- FTS/hybrid search 和 reindex workflow。
- candidate adoption、bulk actions 和审计基础。

正文蒸馏不直接调用当前 generic candidate adoption 完成 update/merge，因为现有接口只改变 candidate 自身 lifecycle，不能原子快照并更新 target asset。

### 5.4 Workflow / LLM Facility

复用：

- `workflow_runs` / `workflow_events`。
- Temporal retry/cancel/replay 基础设施。
- app-role tenant context。
- LLM module binding、credential decrypt、quota reservation、usage、private trace。
- Writer Planning 中 adopted manuscript reader 和 disabled dedup candidate 模式。
- `writer-planning` worker 和 task queue。

不新增独立容器。正文蒸馏作为 Writer Planning 后处理能力注册到现有 worker。

## 6. 数据模型：0018

新增 migration：

```text
infra/postgres/migrations/0018_manuscript_asset_distillation.sql
```

不得编辑 `0001`、`0005` 或其他已应用 revision。

### 6.1 `project_asset_distillation_settings`

用途：项目级触发策略，和 LLM 模型设置分离。

```text
tenant_id UUID NOT NULL
project_id UUID NOT NULL
trigger_mode TEXT NOT NULL
enabled_asset_types TEXT[] NOT NULL DEFAULT '{}'
created_by UUID
updated_by UUID
created_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL
PRIMARY KEY (tenant_id, project_id)
```

`trigger_mode`：

- `off`
- `manual`
- `after_adoption`
- `chapter_complete`

约束：

- 空 `enabled_asset_types` 表示采用当前完整受支持类型集合，不表示“禁用全部”。
- 现有项目迁移后保持 `manual`，避免未告知的费用和行为变化。
- 新建项目默认 `after_adoption`，用户可以改为 manual/off。
- 模型、temperature、token 配置仍只来自 `writer_asset_distiller` LLM binding。

### 6.2 `manuscript_asset_distillation_requests`

用途：workflow 扩展记录、输入快照和事务 outbox。

```text
tenant_id UUID NOT NULL
request_id UUID PRIMARY KEY
project_id UUID NOT NULL
run_id UUID NOT NULL
trigger_kind TEXT NOT NULL
source_manifest_jsonb JSONB NOT NULL
input_fingerprint TEXT NOT NULL
extractor_contract_version INTEGER NOT NULL
dispatch_status TEXT NOT NULL DEFAULT 'pending'
attempt_count INTEGER NOT NULL DEFAULT 0
next_attempt_at TIMESTAMPTZ
last_dispatch_error_code TEXT
requested_by UUID
created_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL
UNIQUE (tenant_id, project_id, run_id)
UNIQUE (tenant_id, project_id, input_fingerprint, extractor_contract_version)
```

`trigger_kind`：

- `draft_adoption`
- `manuscript_update`
- `manuscript_restore`
- `chapter_complete`
- `manual`

`dispatch_status` 只描述 outbox 分发：

- `pending`
- `dispatched`
- `cancelled`

工作流业务状态仍只以 `workflow_runs.status` 为真相源，避免双状态机。

`source_manifest_jsonb` 只允许以下薄信息：

```json
{
  "schema_version": 1,
  "sources": [
    {
      "block_id": "uuid",
      "block_version": 3,
      "content_sha256": "64 hex",
      "chapter_id": "uuid-or-null",
      "scene_id": "uuid-or-null"
    }
  ]
}
```

不得在 manifest 保存正文、evidence quote、prompt 或 candidate body。

### 6.3 `asset_candidate_proposals`

用途：扩展现有 candidate asset 的审阅、目标和合并语义。

```text
tenant_id UUID NOT NULL
project_id UUID NOT NULL
candidate_asset_id UUID PRIMARY KEY
request_id UUID NOT NULL
operation TEXT NOT NULL
target_asset_id UUID
expected_target_version INTEGER
normalized_identity TEXT NOT NULL
confidence NUMERIC
review_status TEXT NOT NULL DEFAULT 'staging'
accepted_asset_id UUID
decision_note TEXT
reviewed_by UUID
reviewed_at TIMESTAMPTZ
created_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL
```

`operation`：

- `create`
- `update`

“合并到已有资产”使用 `operation = update` 和 `target_asset_id`，不新增第三套资产形态。

`review_status`：

- `staging`：当前活动正在持久化或聚合，不进入用户 pending 列表。
- `pending`：等待用户判断。
- `accepted`。
- `rejected`。
- `superseded`：同一身份已有更新候选。
- `stale`：来源正文版本失效。
- `conflict`：目标资产冲突或需要用户选定目标。

索引：

- request/status。
- project/status/created_at。
- target asset。
- 对 pending 的 `(tenant_id, project_id, normalized_identity)` 建 partial unique index，防止同一事实出现多个当前候选。

候选主体继续写入 `assets`：

```text
lifecycle = candidate
enabled = false
pinned = false
source_kind = manuscript_distillation
source_ref = request_id + stable candidate identity
```

### 6.4 `asset_candidate_evidence`

用途：保存私有、可验证的 manuscript 证据。

```text
tenant_id UUID NOT NULL
evidence_id UUID PRIMARY KEY
project_id UUID NOT NULL
candidate_asset_id UUID NOT NULL
block_id UUID NOT NULL
block_version INTEGER NOT NULL
content_sha256 TEXT NOT NULL
start_offset INTEGER NOT NULL
end_offset INTEGER NOT NULL
evidence_text TEXT NOT NULL
confidence NUMERIC
created_at TIMESTAMPTZ NOT NULL
```

约束：

- `start_offset >= 0`。
- `end_offset > start_offset`。
- SHA-256 必须是 64 位小写十六进制。
- 同一候选、版本和 span 唯一。
- FK 关联 candidate asset、project、manuscript block/version。
- evidence 表开启 FORCE RLS。
- evidence text 不进入普通 Asset List、search document、workflow event 或公开 detail。

### 6.5 Manuscript 约束增量

0018 需要通过新增约束替换允许：

```text
manuscript_block_versions.snapshot_reason += adopt
```

Draft adoption 应在同一事务创建初始 version snapshot。后续 evidence 才能稳定引用立即采用但尚未编辑过的 version 1。

### 6.6 权限和 RLS

四张新表必须：

- tenant/project FK 完整。
- `ENABLE ROW LEVEL SECURITY`。
- `FORCE ROW LEVEL SECURITY`。
- `mirofish_app` 只获得实现所需的 SELECT/INSERT/UPDATE；不为 evidence 提供不必要 DELETE。
- policy 继续使用 `app.current_tenant_id`。
- app-role live test 覆盖同租户跨项目和跨租户隔离。

## 7. LLM Module 与输出契约

新增模块：

```text
module_key = writer_asset_distiller
group = Writer
requires JSON capability = true
```

不复用 `asset_ingestion` module key。二者语义不同：

- `asset_ingestion` 接受用户自由素材。
- `writer_asset_distiller` 读取 adopted manuscript、必须提供 evidence span，并需要对已有资产生成 create/update/conflict proposal。

### 7.1 支持的首批类型

- `character`
- `organization`
- `location`
- `item`
- `world_rule`
- `relationship`
- `event`
- `plot_thread`
- `terminology`

`style_profile` 不默认从每章重复抽取；文风应由显式 style extraction 或较大范围的手动蒸馏触发。

### 7.2 Candidate 输出

每条模型候选至少包含：

```json
{
  "local_id": "stable-local-id",
  "asset_type": "character",
  "title": "角色名",
  "summary": "公开摘要",
  "category": "character",
  "tags": [],
  "payload": {},
  "operation_hint": "create-or-update",
  "identity_hints": ["角色名", "别名"],
  "confidence": 0.86,
  "evidence": [
    {
      "block_id": "uuid",
      "block_version": 3,
      "start_offset": 120,
      "end_offset": 174,
      "quote": "正文中的精确片段"
    }
  ]
}
```

模型返回的 target asset id 不可信。target 只能由 tenant/project-scoped resolver 根据候选 identity 和已有资产决定。

### 7.3 Evidence 验证

持久化前必须验证：

```text
source_text[start_offset:end_offset] == quote
```

如果 offset 不匹配：

1. 只允许在相同 block/version 中做 exact quote lookup。
2. 仅当 quote 唯一出现时修正 span。
3. 零次或多次出现时该 evidence 无效。
4. 候选没有任何有效 evidence 时不进入 pending。

confidence 不能替代证据验证。

## 8. Temporal Workflow

### 8.1 Workflow 定义

```text
workflow_type = manuscript_asset_distillation
workflow_name = ManuscriptAssetDistillationWorkflow
task_queue = writer-planning
temporal_workflow_id = manuscript_asset_distillation_{run_id}
```

稳定 workflow id 用于处理 dispatcher 重试和 API 崩溃恢复。

### 8.2 输入边界

Workflow payload 只包含：

- tenant/project/run/request ids。
- trigger kind。
- source manifest。
- module key。
- trace id。
- permissions。

不得包含正文。

### 8.3 Activities

#### `validate_distillation_source_activity`

- 设置 tenant context。
- 读取 request 和 source manifest。
- 验证 block 属于当前 tenant/project。
- 验证 active status、version、SHA-256。
- 验证自动来源为 adopted manuscript。
- version/hash 漂移则完成为 stale，不调用 provider。
- 返回 sanitized counts，不返回正文。

#### `distill_manuscript_assets_activity`

- 在 activity 内私下读取正文。
- 解析 LLM binding 和 credential。
- 通过 quota gate 获取稳定 provider call identity。
- 根据 provider context window 做显式、可 checkpoint 的 block/window 分片。
- 禁止静默截断或只处理前 N 字。
- schema validate 和 evidence validate。
- 解析当前 project 的相关资产，生成 create/update/conflict 决策。
- 直接写 staging candidate/proposal/evidence。
- activity 返回 counts 和稳定 candidate refs，不返回正文、quote 或完整 candidate body。

#### `finalize_distillation_activity`

- 合并同 request 内重复 identity。
- 将有效 staging proposal 切换为 pending。
- 将更旧 pending proposal 标为 superseded。
- 完成 workflow run。
- 公开 result 只包含：source count、candidate count、create/update/conflict/stale counts、module/model metadata。

### 8.4 长章节和重试

- `after_adoption` 默认一次处理新 block/version，避免无界输入。
- `chapter_complete` 和 manual chapter scope 按 block/version 产生稳定 work units。
- 每个 work unit 的 provider call id 由 run、block、version、window index 构成。
- activity heartbeat 记录完成的 work unit fingerprint，不记录正文。
- DB upsert source ref、proposal partial unique index和 evidence unique key共同保证 Temporal retry 不重复写入。
- 必须遵守 LLM Facility quota/concurrency；不得另写一套并发限制。

## 9. 自动触发与 Outbox

### 9.1 Draft adoption

禁止在 adoption 数据库事务内发起网络调用。

推荐事务：

```text
lock candidate draft
  -> create manuscript block
  -> create manuscript block version 1
  -> mark draft adopted
  -> write adoption audit
  -> if project setting == after_adoption:
       insert workflow_runs queued
       insert distillation request dispatch_status=pending
  -> commit
```

只有 new adoption 创建 outbox。现有 idempotent adoption replay 返回原 block，不重复创建 run。

### 9.2 Manuscript content update / restore

- 仅 `content_text` 变化和 version restore 创建新 request。
- tag、move、reorder、仅 location 变化不调用 LLM。
- update transaction 已写 immutable version 后再写 outbox manifest。
- delete 不创建 LLM run，只触发 proposal stale reconciliation。

### 9.3 Chapter complete

只在真实 chapter status 从非完成态转成完成态的显式用户动作后触发。重复提交相同 status 不重复运行。

### 9.4 Dispatcher

dispatcher：

- 以 `FOR UPDATE SKIP LOCKED` 领取 `dispatch_status=pending` 且到达 `next_attempt_at` 的请求。
- 使用稳定 workflow id 启动 Temporal。
- `WorkflowExecutionAlreadyStarted` 视为已分发。
- 临时错误增加 attempt 并设置下一次尝试。
- 公开错误只保存稳定 error code，不保存 Temporal/provider 原始错误或正文。
- admission commit 后即使 API 崩溃，请求仍可恢复。

首期可以由 API 内已有后台执行框架承载 dispatcher；不得为此新增第二个业务数据库或新容器。

## 10. Candidate 合并和决策

### 10.1 Identity resolution

顺序：

1. 规范化 asset type、title、alias/identity hints。
2. 在当前 tenant/project 查找 enabled seed/canon/material 和 pending proposal。
3. exact identity 唯一命中时产生 update proposal。
4. 无命中时产生 create proposal。
5. 多命中、类型冲突或低确定性时产生 conflict proposal，由用户选 target。

不得把 LLM 返回的任意 UUID 直接作为 target。

### 10.2 Accept create

同一事务：

```text
lock pending proposal + candidate asset
  -> verify source is not stale
  -> candidate lifecycle = canon | material
  -> candidate enabled = true
  -> proposal status = accepted
  -> accepted_asset_id = candidate_asset_id
  -> audit_logs asset_proposal.accept_create
```

### 10.3 Accept update / merge

同一事务：

```text
lock pending proposal + candidate + target asset
  -> verify expected_target_version
  -> write target snapshot using current asset version envelope
  -> merge approved fields into target asset
  -> candidate lifecycle = archived, enabled = false
  -> proposal status = accepted
  -> accepted_asset_id = target_asset_id
  -> audit_logs asset_proposal.accept_update
```

字段合并必须由用户确认后的 candidate snapshot 驱动；不得让 Agent 在 decision API 中再次调用 LLM。

target version 漂移返回稳定 conflict，proposal 保持 pending/conflict，不覆盖作者修改。

### 10.4 Reject

```text
proposal status = rejected
candidate lifecycle = archived
candidate enabled = false
audit_logs asset_proposal.reject
```

保留 proposal/evidence，便于审计和避免同一版本重复建议。

### 10.5 Undo

- accept-update 使用既有 asset version restore，且必须带 expected current version。
- accept-create 的撤销将新资产 archive/disable，不做物理删除。
- reject 可以在来源仍 current、且没有新 proposal supersede 时重新打开。
- 任何 undo 都写 audit。

## 11. 正文改版与失效

### 11.1 Pending proposal

当来源 block 被更新、恢复或删除时：

- 只依赖旧版本的 pending proposal 变为 stale。
- 有多条 evidence 且至少一条仍 current 的 proposal 可以保持 pending，但 UI 显示部分证据过期。
- 新版本蒸馏产生新的 proposal，并 supersede 同 identity 的旧 pending。

### 11.2 Accepted asset

已接受资产不会随正文变化自动删除、降级或覆盖。

它保留历史 evidence，并在详情显示：

- evidence current。
- evidence superseded。
- evidence source deleted。

作者决定是否恢复资产历史、接受新的 update proposal 或继续保留旧 canon。

### 11.3 Read-time 与 write-time 校验

- content update/delete 时主动 stale pending proposal。
- proposal detail 和 decision 时再次比较 block version/hash，防止遗漏事件或并发窗口。
- decision 时校验是最终安全边界。

## 12. API Contract

### 12.1 Settings

```http
GET /v1/projects/{projectId}/asset-distillation-settings
PATCH /v1/projects/{projectId}/asset-distillation-settings
```

PATCH body：

```json
{
  "trigger_mode": "after_adoption",
  "enabled_asset_types": ["character", "location", "world_rule"]
}
```

### 12.2 Start / Read

```http
POST /v1/projects/{projectId}/manuscript-asset-distillations
GET /v1/manuscript-asset-distillations/{runId}
```

手动请求只允许以下二选一：

```json
{
  "block_ids": ["uuid"],
  "expected_versions": {"uuid": 3}
}
```

```json
{
  "chapter_id": "uuid",
  "expected_block_versions": {"block-uuid": 3}
}
```

API 不接受正文或 body tenant/project identity。

### 12.3 Proposal List / Detail

```http
GET /v1/projects/{projectId}/asset-proposals?status=pending&source=manuscript_distillation
GET /v1/asset-proposals/{candidateAssetId}
```

普通 detail 返回：

- candidate public snapshot。
- operation 和 target public summary。
- chapter/scene/block/version anchors。
- evidence count 和 current/stale 状态。

private read permission 才返回 `evidence_text`。

### 12.4 Decisions

```http
POST /v1/asset-proposals/{candidateAssetId}/decisions
```

```json
{
  "decision": "accept_create",
  "target_lifecycle": "canon"
}
```

```json
{
  "decision": "accept_update",
  "target_asset_id": "uuid",
  "expected_target_version": 4,
  "target_lifecycle": "canon"
}
```

```json
{
  "decision": "reject",
  "note": "本段是角色误解，不是事实"
}
```

bulk decision 属于后续增强，不是首个闭环前置条件。

## 13. RBAC

- Settings read：`project_read`。
- Settings update：`asset_manage`；从 `off | manual` 切换为自动发送正文的模式还要求 project owner/owner/admin 显式确认外部处理说明。
- Manual distillation：`creative_write`。
- Proposal list/detail metadata：`project_read`。
- Evidence text：`asset_manage`。
- Accept/reject/merge：`asset_manage`，沿用当前资产管理角色边界；普通 writer 只能触发提取，不能修改项目知识正史。
- Viewer 只能查看公开候选摘要，不能启动、接受、拒绝或查看 evidence text。

所有 resource-id route 先做 owner lookup，再使用返回的真实 project id 执行 RBAC。不得信任 body、header 或 candidate payload 中的 project identity。

## 14. Writer 检索边界

当前 Writer `query_assets` 只按 `enabled=true` 过滤；现有 generic ingestion candidate 也可能被写成 enabled。正文蒸馏上线前必须收紧默认查询。

默认自动检索允许：

```text
enabled = true
lifecycle IN (seed, canon, material)
```

默认排除：

- candidate。
- draft。
- simulation。
- archived。

`manuscript` 正文只能通过 `query_manuscript_context` 读取；`simulation` 只能通过经过验证的 worldline path/reference 工具读取。Pending candidate 只在资产审阅 UI 可见，不提供进入 writing brief 的旁路。

accepted create/update 完成后触发或排队 asset reindex，随后才进入 Writer 的 FTS/hybrid 检索。

## 15. Web UX

### 15.1 新项目首屏

空项目进入 Writer Workbench，不显示“必须先上传”的阻断页面。

主要动作：

- 写下故事想法。
- 建立书籍计划。
- 创建第一章。
- 开始写作。

“导入已有小说”作为并列项目操作，不是唯一主 CTA。

### 15.2 Writer 集成

正文采用后显示非阻断状态：

```text
正在整理本段资产
发现 6 条候选
需要处理 2 条冲突
```

蒸馏失败不得把成功 adoption 显示为失败；应显示“正文已采用，资产整理待重试”。

### 15.3 Candidate Review

Writer 右侧资产区和 Asset Library 共用 proposal read model：

- 新建建议。
- 更新建议。
- 冲突建议。
- 证据位置。
- 接受为正典。
- 接受为素材。
- 合并到已有资产。
- 拒绝。

点击证据跳转 Manuscript block/version 并高亮 span。移动端使用独立详情视图或抽屉，不嵌套卡片。

### 15.4 Settings

项目设置提供：

- 关闭。
- 仅手动。
- 正文采用后自动生成候选。
- 章节完成后生成候选。
- 资产类型复选框。

界面必须明确：自动模式只生成候选，不会自动改写正史。

## 16. 幂等与并发

### 16.1 Input fingerprint

fingerprint 由以下内容规范化后 SHA-256：

- tenant/project。
- trigger kind。
- 按 block id 排序的 block id/version/content hash。
- enabled asset types。
- extractor contract version。

不得把 API key、正文或 provider credential 加入 fingerprint。

### 16.2 Admission

- 同 fingerprint/contract version 返回已有 run。
- 只有显式 reprocess contract version 或用户确认的重新处理动作才能对相同来源创建新 run。
- 不提供无记录的 `force=true` 绕过。

### 16.3 Persistence

- asset source ref 稳定。
- proposal pending identity 唯一。
- evidence span 唯一。
- workflow row 先持久化。
- Temporal workflow id 稳定。
- provider call id 稳定。

### 16.4 Decision

- proposal row、candidate、target asset 全部 `FOR UPDATE`。
- decision 只允许从 pending/conflict 的合法状态转换。
- accepted/rejected replay 返回原决定，不重复写 asset version。
- 相反决定需要显式 undo，不允许普通 POST 覆盖。

## 17. 隐私与可观测性

公开 workflow event 允许：

- stage/status。
- source count。
- candidate/create/update/conflict/stale counts。
- module/model public id。
- stable error code。

禁止：

- manuscript body。
- evidence text。
- candidate private payload/body。
- prompt/response。
- API key、credential ref、encrypted credential。
- object key 和数据库连接信息。

Private trace 继续由现有 trace API/RBAC 管理；日志只记录 ids、counts、duration、token/cost 和 error code。

## 18. 开发切片

### Z0：空项目创作契约

目标：冻结 Seed 非前置条件。

实施：

- 增加空项目 Writer contract/unit/live 测试。
- 验证零 source/segment/seed row 可创建 book plan、chapter、scene、writer run、draft 和 manuscript。
- 清理任何 Web-only upload readiness 阻断，但不改 Seed。

完成定义：空项目可从故事前提走到 adopted manuscript。

### Z1：0018 Schema / RLS

实施：

- 新增四表、约束、索引、grants、FORCE RLS。
- 增加 manuscript version `adopt` reason。
- registration/project creation 写默认 settings。
- 更新 schema ledger、bootstrap/readiness sentinel。

完成定义：migration/app-role/跨租户/跨项目测试通过，无候选数据 backfill。

### Z2：手动单 Block 蒸馏

实施：

- 新增 module registry key。
- 新增 workflow admission/start/read。
- 新增 Python workflow/activity/store。
- 实现 block version/hash/evidence schema validation。
- 候选必须 `enabled=false`。

完成定义：手动选择一个 adopted block 可得到真实 disabled candidates；retry 不重复。

### Z3：Proposal Review

实施：

- proposal list/detail/private evidence API。
- accept-create/reject。
- Writer/Asset Library 最小 review UI。
- audit 和 public/private privacy tests。

完成定义：候选接受后成为 canon/material；拒绝后 archived；未接受候选不进入 Writer。

### Z4：Update / Merge / Undo

实施：

- tenant/project target resolver。
- expected asset version。
- 抽取可复用 asset snapshot/version helper。
- accept-update、conflict、restore/undo。
- stale source decision guard。

完成定义：已有角色/地点/规则生成 update 而非重复资产；并发修改 fail closed。

### Z5：自动 Outbox

实施：

- draft adoption 补齐 scene/run/initial version 并同事务 enqueue。
- manuscript content update/restore enqueue。
- delete stale reconciliation。
- dispatcher、retry 和 crash recovery。

完成定义：adoption 成功后即使 Temporal 首次启动失败，正文仍成功且 request 最终可恢复；重复 adoption 不重复运行。

### Z6：章节范围、检索和设置

实施：

- chapter complete/manual chapter work units。
- token-aware checkpoint。
- project settings UI/API。
- Writer lifecycle 白名单。
- accepted asset reindex 和后续 Writer retrieval。

完成定义：章节级处理不截断，pending candidate 不污染 Writer，accepted asset 可被后续写作检索。

### Z7：完整认证

实施：

- focused Go/Python/Pi/Web tests。
- 独立 live stack DB/Object Storage/Temporal 测试。
- desktop/mobile browser journey。
- privacy scan、RLS、quota、cancel/retry/recovery。

完整旅程：

```text
signup
  -> empty project
  -> book plan / chapter
  -> writer draft
  -> adopt manuscript
  -> automatic distillation
  -> inspect evidence
  -> accept create
  -> accept update
  -> reindex
  -> next writer run retrieves accepted asset
```

## 19. 文件范围

### Schema

- `infra/postgres/migrations/0018_manuscript_asset_distillation.sql`
- schema bootstrap/readiness/ledger tests，仅在 Z1 集成切片修改。

### Go API

- 新增 `apps/api/internal/assetdistillation/`。
- 新增 `apps/api/internal/workflows/manuscript_asset_distillation.go`。
- 新增对应 admission/reader/dispatcher tests。
- `apps/api/internal/workflows/writer_draft_adoption.go`，只在 Z5 接线。
- `apps/api/internal/manuscriptworkspace/store.go`，只在 Z5 接线。
- `apps/api/internal/registration/service.go`，只写新项目默认 setting。
- `apps/api/internal/assetcatalog/`，只抽取复用 version snapshot/merge 事务能力。
- `apps/api/internal/llm/registry.go`。
- 中央 `cmd/api/main.go`、`internal/httpapi/server.go` 只在集成切片接线。

### Python Agent Runtime

- 新增 `apps/agent-runtime/mirofish_agents/temporal/manuscript_asset_distillation.py`。
- `writer_planning_worker.py` 注册 workflow/activity。
- 新增 focused unit/live tests。
- 不把新逻辑继续堆入 `assets.py` 或 `writer_planning.py` 大文件。

### Pi Writer

- `apps/pi-agent-runtime/src/runtime/postgres-pi-writer-deps.ts` 收紧 asset lifecycle 查询。
- 对应 tool contract/app-role live tests。

### Web

- Writer product workspace 增加非阻断 distillation 状态和 proposal review。
- Asset Library 增加 manuscript proposal facet/detail/decision。
- Project settings 增加 trigger mode。
- 复用现有 workspace、drawer、submit、confirm 和 public error 组件。

### Docs

- 完成里程碑后更新 `24-current-development-progress.md`。
- 任务状态变化后更新 parallel board。
- API/schema 契约稳定后同步 `08-asset-library.md`、`11-writer-workbench.md`、`14-data-model.md` 和 `15-api-contracts.md`。

不得创建新的 handoff/progress 副本。

## 20. 测试矩阵

### 20.1 Go

- 空项目无 Seed 仍可 Writer/adopt。
- settings validation/default/RBAC。
- manual admission 不接收 raw text。
- input fingerprint replay。
- adoption new/replay outbox 数量。
- content update/restore/delete trigger 差异。
- dispatcher stable workflow id/recovery。
- proposal accept-create/reject。
- accept-update asset snapshot/version conflict。
- owner lookup 和 body identity rejection。
- public result sanitizer。

### 20.2 Python

- source version/hash 校验。
- non-adopted source rejection。
- module unbound/capability missing/quota failure。
- output schema validation。
- evidence exact span/unique fallback/no-match/multi-match。
- create/update/conflict resolver。
- candidate disabled persistence。
- activity retry idempotency。
- no manuscript/candidate body in public event/result。
- long chapter work-unit checkpoint，无硬截断。

### 20.3 Pi

- default query 排除 candidate/draft/simulation/archived。
- accepted canon/material 可读取。
- 同租户跨项目和跨租户隔离。
- explicit preview 与 normal retrieval 不混淆。

### 20.4 Web

- 空项目首屏不是上传阻断页。
- adoption 成功和 distillation failure 分开显示。
- pending/update/conflict/stale UI。
- private evidence permission。
- accept/reject/merge confirmation。
- desktop/mobile 无重叠、无正文泄露。

### 20.5 Live/E2E

所有写 DB、对象存储或队列的 live/E2E 必须通过：

```bash
infra/scripts/run-live-test-stack.sh --app -- <command>
```

不得指向主 `mirofish` 数据库。

Live 必须覆盖：

- real Postgres app-role/RLS。
- real Temporal worker。
- real configured local/provider test adapter，不能 mock success。
- duplicate admission/retry。
- block mid-flight edit -> stale/no adoption。
- target mid-flight edit -> conflict。
- public privacy scan。
- candidate 零自动 canon/manuscript 写入。

## 21. Definition of Done

本能力只有在以下全部成立时完成：

- 新用户不上传小说也能从空项目写到 manuscript。
- Seed 导入和从零创作共享同一 Writer/Asset 主模型。
- adopted manuscript 自动或手动产生 disabled candidates。
- 每条 pending proposal 有可验证 block/version/span evidence。
- create/update/conflict 被正确区分。
- 接受和拒绝是显式、可审计用户动作。
- update 使用 asset immutable snapshot 和 optimistic version。
- source version 变化会 stale pending proposal。
- 已接受资产不会被正文变化自动删除或覆盖。
- duplicate admission、Temporal retry、dispatcher retry 不重复扣费或写候选。
- pending candidate 不进入 Writer 默认检索。
- accepted asset 完成 reindex 后可被后续 Writer 使用。
- LLM Facility unbound/quota/provider failure 全部 fail closed。
- public API/event/log/DOM 不含正文、evidence text、prompt、API key 或 credential。
- RLS/RBAC、unit、live 和 browser journey 通过。

## 22. 风险与缓解

### 22.1 Candidate 污染 Writer

风险：当前 generic candidate writer 可能写 `enabled=true`，而 Writer 只按 enabled 过滤。

缓解：正文候选强制 disabled；Writer 增加 lifecycle 白名单；增加零 candidate retrieval 回归测试。

### 22.2 Adoption 与 Temporal 之间丢任务

风险：正文事务提交后进程在 Temporal start 前崩溃。

缓解：事务内 outbox、stable workflow id、dispatcher recovery。

### 22.3 正文修改竞争

风险：Agent 基于旧文本生成建议。

缓解：block version + content hash 双校验，decision 再校验，旧 pending stale。

### 22.4 覆盖作者资产修改

风险：update proposal 接受时 target 已被作者编辑。

缓解：expected target version、row lock、snapshot、conflict fail closed。

### 22.5 Evidence 幻觉

风险：模型生成不存在的引用。

缓解：exact span 校验，唯一 quote fallback，无有效 evidence 不持久化为 pending。

### 22.6 费用和任务风暴

风险：频繁保存导致大量调用。

缓解：仅明确版本边界触发；现有项目默认 manual；fingerprint replay；quota/concurrency；不按键触发。

### 22.7 长章节截断

风险：单次 prompt 超过 context window。

缓解：按 block/window 稳定分片、heartbeat/checkpoint、finalize 聚合；不静默裁剪。

### 22.8 私有正文进入 Temporal history

风险：将 material text 作为 workflow payload 或 activity result。

缓解：payload 只传 ids/version/hash；activity 内读取和持久化；活动仅返回 sanitized counts/refs。

## 23. 发布策略

### 23.1 阶段开关

- Z2-Z4 首先只开放 manual。
- Z5 完成 outbox/recovery 后，才允许新项目默认 `after_adoption`。
- 现有项目保持 manual，用户自行开启。
- `chapter_complete` 在 Z6 长文本和 checkpoint 认证后开放。

### 23.2 观测指标

- request admitted/dispatched/completed/failed/stale。
- dispatcher delay/retry count。
- source block/window count。
- candidates create/update/conflict/rejected/accepted。
- evidence validation failure count。
- duplicate replay count。
- tokens/cost/latency by tenant/project/module。
- target version conflict count。

指标不得包含正文、evidence quote 或 asset private payload。

### 23.3 灰度顺序

1. local focused tests。
2. isolated live stack。
3. manual internal project。
4. new project after-adoption opt-in。
5. new project default after-adoption。
6. existing project voluntary enablement。
7. chapter-complete opt-in。

## 24. 回滚策略

### 24.1 功能回滚

- 将 settings `trigger_mode` 切换为 `manual` 或 `off`。
- 停止 dispatcher 领取新 pending requests。
- 已运行 workflow 可显式 cancel。
- pending/staging candidate 保持 disabled，不进入 Writer。
- Writer lifecycle 白名单不能随功能关闭回滚。

### 24.2 数据回滚

- 不物理删除已经 accepted 的用户资产。
- accept-update 通过 asset version restore 撤销。
- accept-create 通过 archive/disable 撤销。
- rejected/stale/superseded proposal 保留审计。
- migration rollback 只有在四张新表没有 accepted decision 依赖时才允许 drop；生产环境优先停用功能而不是破坏性降级 schema。

### 24.3 发布失败边界

- Distillation 失败不得回滚已成功的 manuscript adoption/update。
- Reindex 失败不得回滚已确认资产；资产保持已接受并显示索引待重试。
- Provider/module/quota 失败只影响蒸馏 workflow，不影响作者保存正文。

## 25. 关联文档索引

- `DEVELOPMENT_PLAN.md`：Writer-first 总体阶段和最终 DoD。
- `00-product-vision-and-scope.md`：产品主链和非目标。
- `01-target-architecture.md`：服务边界和数据访问原则。
- `03-multi-tenant-saas.md`：tenant/project/RBAC/RLS。
- `04-design-system-and-ui.md`：工作台和审阅 UI 约束。
- `06-seed-pipeline.md`：导入已有小说入口。
- `08-asset-library.md`：asset lifecycle、ingestion、search、adoption。
- `11-writer-workbench.md`：Writer、draft、manuscript、Reviewer、dedup。
- `12-llm-facility.md`：module binding、quota、usage、privacy。
- `13-agent-runtime.md`：workflow、activity、trace、tool 和 human-in-the-loop。
- `14-data-model.md`：Postgres、RLS、资产和 Writer 表。
- `15-api-contracts.md`：公共 API、错误和隐私边界。
- `16-deployment-and-ops.md`：部署、恢复、监控和成本。
- `21-pi-writer-agent-runtime.md`：Pi Writer tools 与上下文消费。
- `24-current-development-progress.md`：唯一当前进度入口。
