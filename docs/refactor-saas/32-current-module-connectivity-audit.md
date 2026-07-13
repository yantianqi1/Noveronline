# 当前 SaaS 全模块连通性与零起点写作审查

审查日期：`2026-07-13`

审查分支：`codex/saas-mainline`

## 文档定位

本文回答以下问题：

1. 当前 Writer 前端是否真实连接 Go API、Temporal 和 Pi Writer Runtime。
2. 作者不导入小说、从空项目逐章写作时，正文是否会真实进入 manuscript、资产库、图谱、Worldline 和下一轮 Writer 上下文。
3. 当前各前端功能实际调用哪个后端模块，哪些功能确实可用，哪些只有组件、表或局部测试而没有产品接线。
4. 当前实例、自动化测试和真实用户闭环之间还缺少哪些证据。

本文是独立时点审查，不替代以下真相源：

1. `DEVELOPMENT_PLAN.md`：范围、阶段顺序和最终完成定义。
2. `24-current-development-progress.md`：唯一当前进度入口。
3. `tasks/refactor-saas-parallel-board.md`：活动任务、依赖和 next gate。
4. 当前 worktree、schema、运行中 Compose 和本轮实际测试：冲突时的最终事实。

本文只审查活跃 SaaS：`apps/api`、`apps/web`、`apps/agent-runtime`、`apps/pi-agent-runtime` 和 `infra`。`backend/` 只做 legacy 回归参考，不作为当前产品入口。

## 执行结论

### 对用户问题的直接回答

**Pi Writer 主链是真的，不是 mock。** Writer composer 会调用 Go API，Go admission 会持久化 `writer_runs` / `workflow_runs`，再启动 Temporal `PiWriterRunWorkflow`，由 `writer-streaming` 队列上的 Pi worker 调用真实 LLM Facility、执行只读 tools、保存 candidate draft，并把事件返回 Writer 页面。

但是，当前不能宣称以下链路已经成立：

```text
空项目
  -> 作者纯手写第一章
  -> 每章自动进入主手稿
  -> 自动提炼角色 / 关系 / 世界规则 / 伏笔
  -> 自动进入智能资产库
  -> 自动更新故事图谱
  -> 自动创建或更新 current_world
  -> 自动成为 Character / Pi Writer 的下一轮结构化上下文
```

实际情况是：

- 纯手写目前保存到 `scenes.content_text`，不会创建 `manuscript_blocks`。
- manuscript 没有创建空白 block 的 API；已有 block 只能更新。
- 蒸馏源还硬性要求 `manuscript_blocks.source_draft_id IS NOT NULL`，即只接受采用 Pi candidate 后生成的 block。
- 当前项目蒸馏模式为 `manual`；`after_adoption` 也只覆盖 AI draft adoption。
- 蒸馏产物先是 disabled candidate + proposal，必须人工接受后才能成为可用资产；这符合“候选不自动变正典”的产品安全边界。
- 接受资产不会同步写入 `entities`、`relationships`、`plot_threads` 或 `world_rule_evidence`，所以多数正文蒸馏事实不会进入 Graph。
- Graph、Worldline 和 Character 都是独立、显式启动的工作流，不会因正文或资产变化自动串联。

因此，当前正确产品表述应为：

> Pi 可以真实生成候选正文；作者采用候选后可以进入 manuscript；作者可手动启动正文资产蒸馏并人工确认候选。纯手写逐章自动资产化、自动图谱化和自动 Worldline 化尚未打通。

### 总体判定

| 目标 | 判定 |
|---|---|
| Writer UI -> Go API | 已接通 |
| Go API -> Temporal -> Pi Runtime | 已接通 |
| Pi -> LLM Facility -> tools -> candidate draft | 已接通，有真实本地 provider E2E |
| candidate -> 显式 adoption -> manuscript | 已接通 |
| manuscript -> reviewer / export | 已接通 |
| 当前章节 / 场景 -> Pi 写作上下文 | 未接通 |
| 纯手写正文 -> manuscript | 未接通 |
| 纯手写正文 -> distillation | 未接通 |
| adoption -> 自动蒸馏 | 有条件接通，但当前默认关闭且存在漏单风险 |
| distillation proposal -> 人工确认资产 | 局部接通，update 路径有确定性缺陷 |
| 已确认蒸馏资产 -> Graph | 未形成通用投影 |
| Graph / Assets -> Worldline preparation | 可手动选择，但图节点引用存在 ID 错配 |
| Worldline preparation -> session / director context | 未自然接通 |
| Worldline / Character -> Writer | 有独立入口和部分 handoff，不是自动闭环 |
| persistent thread / approval | 表、store、UI 组件存在，产品接线不存在 |
| fresh desktop/mobile 真实用户旅程 | 本轮未认证，Z7 仍未完成 |

## 实际端到端链路

### 当前真实可走通的 Writer 链

```text
Writer composer
  -> POST /v1/projects/{project}/writer-runs
  -> LLM module resolution + auth + admission
  -> Temporal PiWriterRunWorkflow
  -> Pi orchestrator tools
  -> Pi composer
  -> writer_drafts(status=candidate)
  -> Writer event replay / SSE
  -> 作者点击采用
  -> manuscript_blocks
  -> reviewer / manuscript export
```

这条链需要：

- `writer_orchestrator`、`writer_composer` 等模块绑定可用。
- channel credential、quota、provider capability 可用。
- 作者最后显式采用 candidate；Pi 不会直接覆盖正文。

### 当前零起点链的实际断点

```text
创建章节 / 场景
  -> 编辑 scene.content_text
  -X-> manuscript_blocks                 [没有 create block]
  -X-> manual distillation                [只接受 source_draft_id 非空]
  -X-> canonical assets                   [没有候选来源]
  -X-> entities / relationships / rules   [没有结构化投影]
  -X-> graph snapshot                     [没有可消费的事实]
  -X-> worldline / character / Pi context [没有下游闭环]
```

## 严重问题清单

### CONN-001：纯手写正文无法进入 manuscript 和蒸馏

严重级别：`P0 / blocker`

Writer 产品区可以创建章节、场景并更新 `scenes.content_text`，但 manuscript blocks 集合路由只有 `GET`，没有 `POST` 创建空白正文块：

- `apps/api/internal/manuscriptworkspace/handler.go:123-137`
- `apps/web/app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx:347`

现有 manuscript block 的正常创建来源是 candidate draft adoption。即使未来补了手写 block 创建，当前手动蒸馏 SQL 仍要求：

```sql
status = 'active' AND source_draft_id IS NOT NULL
```

证据：

- `apps/api/internal/assetdistillation/store.go:648-653`
- fallback 查询仍有同一限制：`apps/api/internal/assetdistillation/store.go:711-714`

影响：

- 用户可以看到场景内容已经保存，但这些文字不属于主手稿数据模型。
- 纯手写第一章不能被 Reviewer、manuscript export 或 asset distiller 作为统一正文消费。
- “不导入小说、从零一点点写”只能完成结构/场景 CRUD，不能完成知识闭环。

关闭条件：

- 明确唯一正文真相源：scene 是结构元数据，manuscript block 是正文，或建立可靠双向投影；不能继续并存两份无同步正文。
- 增加创建空白 manuscript block 的授权 API 和 Web action。
- distillation 以 active manuscript 内容和版本为边界，不应以是否来自 AI draft 判断合法性。
- 手写、AI adoption、修订、恢复四种来源都必须进入同一版本、审校、蒸馏和导出链。

### CONN-002：Writer composer 丢失当前章节和场景作用域

严重级别：`P0 / blocker`

Writer 页面已经从 URL 读取 `chapterId` / `sceneId`，但启动 run 时只传 mode、instruction、assets、graph nodes 和 worldline paths：

- `apps/web/app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx:143-174`
- `apps/web/lib/api.ts:1264-1270`
- `apps/web/lib/api.ts:1968-1980`

Go HTTP 请求和 workflow input 也没有独立章节/场景字段：

- `apps/api/internal/httpapi/server.go:281-285`
- `apps/api/internal/workflows/writer.go:21-30`
- `apps/api/internal/httpapi/server.go:3464-3473`

采用 candidate 时，Web 又固定发送空 JSON，没有把当前 `chapterId` 作为后端已支持的 adoption override 传入：

- `apps/web/app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx:235-250`
- 后端可接收 chapter override：`apps/api/internal/httpapi/server.go:6936-6943`

虽然 Pi contract 支持可选的 `chapter_id` / `scene_id`，上游没有传入。Go admission 写 `writer_runs` 时也没有写这两个字段：

- `apps/pi-agent-runtime/src/contracts/writer-run.ts:3-16`
- `apps/api/internal/workflows/writer_admission.go:143-165`

Pi 的 `query_chapter_scene` 只读取 `writer_runs.chapter_id`、`scene_id` 和 mode，没有读取 chapter title、outline、scene title、scene content 或 POV：

- `apps/pi-agent-runtime/src/runtime/postgres-pi-writer-deps.ts:285-292`

影响：

- 用户在第二章/某个场景中发出“继续写”时，Pi 不知道当前结构位置。
- candidate draft 可能没有 chapter/scene 绑定，adoption 最终也可能生成未定位 block。
- 章节大纲和刚刚手写的场景正文不会自动成为 Pi 的上下文。

关闭条件：

- Web -> Go request -> admission -> Temporal payload -> Pi -> writer_drafts 全链传递 typed chapter/scene target。
- admission 验证目标属于当前 tenant/project，并将其写入 `writer_runs`。
- `query_chapter_scene` 加载章节标题/大纲、场景标题/正文/POV、相邻场景摘要和目标版本。
- E2E 断言 candidate 和 adopted block 最终绑定到作者当前选择的章节/场景。

### CONN-003：正文蒸馏资产不会自动形成通用 Story Graph

严重级别：`P0 / blocker`

蒸馏 worker 只写：

- `assets` 中 disabled candidate。
- `asset_candidate_proposals`。
- `asset_candidate_evidence`。

接受 proposal 只改变或合并资产记录，不投影到 `entities`、`relationships`、`plot_threads`、`world_rule_evidence` 等 Graph 结构源。

Graph builder 的实际来源是：

- `entities`：`apps/agent-runtime/mirofish_agents/temporal/graph.py:570-579`
- `relationships`：`apps/agent-runtime/mirofish_agents/temporal/graph.py:601-610`
- `plot_threads`：`apps/agent-runtime/mirofish_agents/temporal/graph.py:612-620`
- `world_rule_evidence`：`apps/agent-runtime/mirofish_agents/temporal/graph.py:622-630`

Graph 对通用 assets 还只接受：

```text
archive_entity / artifact / location / concept
```

证据：`apps/agent-runtime/mirofish_agents/temporal/graph.py:632-644`。

而正文 distiller 支持的角色、关系、世界规则、剧情线等类型多数不在上述 asset allowlist 中。特别是 relationship 资产不会形成 graph edge，因为 edge 只读 `relationships` 表。

影响：

- “接受为正典”在资产库中成功，不代表 Graph 已更新。
- Pi 的 typed `query_character_profile` / `query_world_rules` 仍看不到这些新事实。
- 用户后续手动重建 Graph，也不能解决缺少结构化投影的问题。

关闭条件：

- 定义 canonical projection：接受 character / relationship / world_rule / plot_thread proposal 时，事务性写入对应结构表和 evidence。
- 或修改 Graph builder，使其以统一资产 schema 消费所有已确认正文事实，并正确生成 entity identity 与 relationship edge。
- 接受、更新、拒绝、stale、supersede 都有幂等版本语义。
- proposal acceptance 后明确触发/提示 Graph rebuild，并以 live test 证明新角色节点和关系边出现。

### CONN-004：自动蒸馏存在非事务漏单和静默吞错

严重级别：`P0 / data integrity`

Draft adoption 在一个事务中先 commit：

- `apps/api/internal/workflows/writer_draft_adoption.go:202-206`

HTTP handler 随后另行 enqueue，且直接丢弃错误：

- `apps/api/internal/httpapi/server.go:6949-6958`

这不是 transactional outbox。进程在 adoption commit 后崩溃、enqueue 数据库失败或 starter 失败时，正文已经采用，但蒸馏请求可能永久缺失。

错误还在多个层次被吞掉：

- settings / source lookup 失败被当成“不需要触发”：`apps/api/internal/assetdistillation/runtime.go:162-182`
- outbox claim 查询失败返回 `nil, nil`：`apps/api/internal/assetdistillation/store.go:240-252`
- dispatcher tick 错误被后台循环丢弃：`apps/api/cmd/api/main.go:1346-1355`
- start retry 的持久化错误也被忽略：`apps/api/internal/assetdistillation/runtime.go:127-133`

此外：

- `chapter_complete` 在 Web 可选：`apps/web/components/writer-product-workspace.tsx:134-139`。
- 生产代码没有 chapter-complete producer。
- `manuscript_update` / `manuscript_restore` 没有 enqueue 接线。
- `StaleProposalsForBlock` 有实现但没有生产调用。

关闭条件：

- adoption 与 outbox insert 同一数据库事务提交，或使用可补偿、可扫描的 durable handoff。
- 所有 claim、dispatch、retry 错误进入 structured log、metric、workflow event 和可操作 UI 状态。
- update/restore/chapter-complete 具备真实 producer，未实现的 trigger 不应出现在 UI。
- manuscript 版本变化会可靠 stale 旧 proposal，并有并发 live test。

### CONN-005：proposal update / conflict 生命周期存在确定性缺陷

严重级别：`P0 / data integrity`

有三个独立问题：

1. Python identity resolver 对 update 永远产生 `expected_target_version = 1`：`apps/agent-runtime/mirofish_agents/temporal/manuscript_asset_distillation.py:408-419`。
2. Web 接受 update 同样硬编码版本 `1`：`apps/web/components/writer-product-workspace.tsx:174-181`。
3. Go 后端用 `max(asset_versions.version_number)+1` 作为当前版本校验：`apps/api/internal/assetdistillation/store.go:499-519`。

Go proposal summary 实际返回 `expected_target_version`，但 Web `AssetProposal` 类型没有该字段：`apps/web/lib/writer-workspace-api.ts:159-172`。这说明版本信息在 API -> Web 投影中已经丢失。

结果是资产第一次更新后，后续正常 merge 会稳定冲突。

冲突分支先把 proposal 更新为 `conflict`，随后返回 `AppError`；`withTenant` 遇到任何 error 都 rollback：

- conflict 更新与返回：`apps/api/internal/assetdistillation/store.go:516-519`
- transaction rollback 语义：`apps/api/internal/assetdistillation/store.go:798-814`

因此预期持久化的 conflict 状态也可能实际被回滚。

finalize 还先把本批 staging proposal 提升为 pending，再 supersede 旧 pending：

- `apps/agent-runtime/mirofish_agents/temporal/manuscript_asset_distillation.py:270-303`

但 migration 有“同项目同 normalized identity 只能有一个 pending”的 partial unique index：

- `infra/postgres/migrations/0018_manuscript_asset_distillation.sql:180-183`

同 identity 已有 pending 时，新批次可能在执行 supersede 前就违反唯一索引。

关闭条件：

- API 返回 proposal 查询所得的真实 `expected_target_version`，Web 不再构造版本号。
- conflict/stale 状态在成功提交后再返回 typed conflict，或显式使用 savepoint/结果类型。
- finalize 先锁定并 supersede 旧 pending，再提升新 proposal；并发批次必须幂等。
- 增加第二次/第三次 merge、并发同 identity、目标版本变化的 Postgres live tests。

### CONN-006：正文乐观并发冲突会丢失用户未保存文本

严重级别：`P0 / user data loss`

TipTap 编辑器在失焦 450ms 后自动提交：

- `apps/web/components/writer-manuscript-editor-inner.tsx:157-162`

server action 使用 `expected_version` 更新 block，但不论成功还是 conflict 都进入 redirect：

- `apps/web/app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx:360`
- `workspaceRedirect`：同文件 `703-713`

redirect 只带 status/code，不携带用户刚编辑的正文。页面错误提示也是通用“检查输入后重试”，没有保留 draft、compare、merge 或 duplicate-as-new-block：

- `apps/web/components/writer-product-workspace.tsx:505-520`

两个标签页同时编辑同一 block 时，后提交页面收到乐观锁冲突并重载服务端旧版本，本地未保存文字会消失。这属于正文数据丢失风险，不能只作为 UX 问题处理。

关闭条件：

- 客户端维护 save state 和本地 pending draft，冲突不能触发丢弃正文的 redirect。
- 返回 server version + client draft 的 typed conflict，提供 compare/merge/另存新块。
- 增加双标签并发浏览器测试，断言失败提交的全文仍可恢复。

### CONN-007：选区 revise 生成了候选，但没有行内回填闭环

严重级别：`P0 / content corruption`

选区动作会构造 revise run，Pi 也真实发出 `writer.revision.proposed`：

- `apps/web/components/writer-manuscript-panel-client.tsx:55-75`
- `apps/pi-agent-runtime/src/activities/pi-writer-activities.ts:940-969`

但 manuscript panel 创建 `WriterManuscriptPanelClient` 时没有传 `pendingRevision`，所以客户端默认始终为 `null`：

- `apps/web/components/writer-product-workspace.tsx:384-401`
- default：`apps/web/components/writer-manuscript-panel-client.tsx:28-40`

右侧 dock 仍把 revise 输出保存为普通 candidate draft并提供普通 adoption。后端普通 adoption 会插入新的 manuscript block，而不是按 selection/version 替换原 block：

- candidate 仍被保存：`apps/pi-agent-runtime/src/activities/pi-writer-activities.ts:952-978`
- adoption 创建新 block：`apps/api/internal/workflows/writer_draft_adoption.go:267-301`

结果可能是作者点击“采用”后，修订片段被追加成一个独立正文块，原选区没有被替换。

关闭条件：

- Web 从 run events 解析 `writer.revision.proposed` 并将 base/proposed/selection/version 传给 editor。
- 接受/拒绝 hunk 使用专用 optimistic patch API；revise candidate 不得进入普通整块 adoption。
- 原 block 已变化时显示 typed conflict，不能应用到错误版本。

## 高优先级断点

### CONN-008：Pi 可读上下文真实存在，但章节连续性和选择边界过浅

严重级别：`P1`

Pi orchestrator 当前允许调用：project、chapter/scene、assets、world rules、character profiles、graph neighbors、worldline paths、manuscript context：

- `apps/pi-agent-runtime/src/activities/pi-writer-activities.ts:824-848`

问题包括：

- `query_chapter_scene` 只回 ID 和 mode，不读章节/场景正文。
- `query_manuscript_context` 不过滤 `status='active'`，会把 deleted block 送给模型。
- manuscript context 是全项目最后 20 个 block，不按当前章节、场景或叙事邻域组织。
- `query_worldline_paths` 在没有选择 ID 时返回全项目最后 20 条，违反工具说明中的“explicitly selected”。
- `query_world_rules` 与 `query_character_profile` 只读 Seed 结构表，不读已接受的正文蒸馏 assets。

证据：

- `apps/pi-agent-runtime/src/runtime/postgres-pi-writer-deps.ts:285-335`
- `apps/pi-agent-runtime/src/runtime/postgres-pi-writer-deps.ts:367-384`
- 工具对外语义：`apps/pi-agent-runtime/src/runtime/pi-writer-agent.ts:276-286`

当前已接受正文资产最多通过通用 `query_assets` 被读到，不能替代角色/规则的 typed context。

### CONN-009：persistent thread 和 approvals 是孤立实现

严重级别：`P1`

`0019_writer_threads` 已创建 thread、messages、approvals 表；`SQLWriterThreadStore` 也实现了 ensure/list/append/decide：

- `apps/api/internal/workflows/writer_threads.go:80-96`
- `apps/api/internal/workflows/writer_threads.go:297-340`

但当前生产入口没有：

- 在 `cmd/api/main.go` 构造并注入 `SQLWriterThreadStore`。
- 在 `httpapi/server.go` 暴露 thread/messages/approval routes。
- 在 Writer admission 中 ensure thread / append user message。
- 在 Pi runtime 中 append assistant message 或创建 approval。

Web shell 支持 `threadMessages` 和 `decideApprovalAction`，但 page 没有传这两个 props：

- 可选 props：`apps/web/components/writer-workbench-shell.tsx:110-123`
- page 实际 props：`apps/web/app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx:414-462`
- shell 为空时回退到当前单 run 展示：`apps/web/components/writer-workbench-shell.tsx:323-375`

因此当前“常驻对话”仍是一次 run 的视觉呈现，不是跨 run persistent thread；approval card 有组件和事件类型，但没有可操作生产闭环。

### CONN-010：Worldline preparation、session 和 Character 没有共享完整上下文

严重级别：`P1`

Worldline 是独立的人工流程，不是 Graph 或资产接受后的自动后续。当前还有三处具体断点：

1. preparation 与 session 未绑定。Web 创建 session 只传 goal / anchor path，不传 `prepare_id`：`apps/web/app/(app)/[tenantSlug]/projects/[projectId]/worldline/page.tsx:154-162`。
2. step 只传 `{source: 'worldline_shell'}`，不传 preparation 或选中 source refs：`apps/web/app/(app)/[tenantSlug]/projects/[projectId]/worldline/page.tsx:177-196`。
3. director prompt 只包含 session ID、mode、options；只有 options 显式给 `source_refs` 才加载 asset/event summary，不自动读取 session goal、prepared agents、Graph、manuscript 或 current-world state：`apps/agent-runtime/mirofish_agents/temporal/worldline.py:224-251`、`1980-2018`。

另有确定性 ID 错配：

- Web 从 story graph nodes 发送 `entity:${node.node_id}`：`apps/web/components/worldline-shell.tsx:744-763`。
- preparation worker 按 `entities.entity_id` 查询：`apps/agent-runtime/mirofish_agents/temporal/worldline_prepare.py:402-409`。

story graph `node_id` 不等于 canonical `entity_id`；选择图节点可能得到 `WORLDLINE_PREPARATION_SOURCE_NOT_FOUND`。

Character dialogue 只读取 interaction 元数据、`pov_agent_id` 字符串和最近 20 条互动历史，不查询 prepared agent/profile、world rules、graph neighbors 或 manuscript：

- `apps/agent-runtime/mirofish_agents/temporal/character.py:123-180`
- `apps/agent-runtime/mirofish_agents/temporal/character.py:215-227`
- prompt payload：`apps/agent-runtime/mirofish_agents/temporal/character.py:786-819`

### CONN-011：长章蒸馏没有 window、checkpoint 或增量策略

严重级别：`P1`

distiller 把所有所选 block 全文拼成一个 user message：

- `apps/agent-runtime/mirofish_agents/temporal/manuscript_asset_distillation.py:502-521`

没有 token-aware window、章节 checkpoint、分段聚合或跨窗口 identity merge。`enabled_asset_types` 虽进入 fingerprint，但没有进入 worker prompt/manifest 的可执行过滤；非空设置不能真正限制提取类型。

影响：长章/多 block 请求会受 provider context window 限制，失败后也没有可恢复的局部进度。

### CONN-012：当前 embedding 绑定是不可用配置

严重级别：`P1 / instance configuration`

当前数据库把 `asset_search_embedding` 绑定到聊天模型 `gpt-5.5`，settings 只有 `max_tokens`，没有 `embedding_dimensions`，也没有匹配的 asset embedding index。

代码会明确判定：

- 缺 dimensions：`apps/api/internal/assets/search_capabilities.go:54-57`
- 缺匹配 index：`apps/api/internal/assets/search_capabilities.go:60-73`

因此 keyword 搜索可用，vector / hybrid 当前实例不可用。`24-current-development-progress.md` 仍称 embedding 未绑定，与数据库现状有漂移；当前实际是“已绑定但无效”，比未绑定更容易误导 UI 和排障。

### CONN-013：当前运行实例没有一条真实创作闭环数据

严重级别：`P1 / evidence`

本轮只读主库快照：

| 数据 | 当前值 |
|---|---:|
| migration ledger | `0019_writer_threads` |
| projects | `1` |
| chapters / scenes | `0 / 0` |
| writer runs / drafts | `0 / 0` |
| manuscript blocks | `0` |
| assets | `0` |
| graph snapshots / nodes / edges | `2 / 0 / 0` |
| worldline sessions | `0` |
| character interactions | `0` |
| distillation requests / proposals | `0 / 0` |
| distillation mode | `manual` |
| seed workflows | `3 failed` |
| graph workflows | `2 completed`，但生成空图 |

这不证明代码不可用，但证明当前实例没有“真实用户输入 -> Pi -> adoption -> distillation -> graph -> worldline”的成功证据。

### CONN-014：Z7 的真实浏览器与全链认证仍未完成

严重级别：`P1 / release gate`

本轮无法取得可用的应用内浏览器实例，未能执行 fresh desktop/mobile Writer 旅程。普通 Web suite 中 9 个 browser/live 项目被 skip。

活动任务板当前也明确写明：`Z7 Temporal provider + browser` 是 Z-028 的 next gate。源码、组件和分层测试为绿不能替代：

- 当前页面表单真实提交。
- SSE / reconnect / adoption / distillation 状态在浏览器可见。
- desktop/mobile 无遮挡、无隐私泄漏、无 pageerror。
- 同一隔离项目完成全链。

### CONN-015：Writer run 的幂等 header 未生效，Temporal 启动失败会留下 queued 孤儿

严重级别：`P1 / reliability and billing`

Web 为创建 run 发送 `Idempotency-Key`：`apps/web/lib/api.ts:1968-1979`。但 Go `requestID` 只读取 `X-Request-Id`，没有读取 `Idempotency-Key`：

- `apps/api/internal/httpapi/server.go:9010-9018`

Writer admission 每次先生成新 run，并插入 `workflow_runs` / `writer_runs`，没有按 request ID 或 fingerprint replay：

- `apps/api/internal/workflows/writer_admission.go:117-168`

随后才调用 Temporal；`ExecuteWorkflow` 失败时只返回 error，没有把已提交记录补偿为 failed/cancelled：

- `apps/api/internal/workflows/writer.go:540-575`

影响：

- 模糊网络失败后用户重试会创建第二个可计费 run。
- Temporal 启动失败会留下永久 queued 的数据库孤儿。
- Web 每次提交又生成新的 UUID，无法用同一 key 恢复未知结果。

关闭条件：服务端正式消费幂等 key，admission 以 tenant/project/key + payload fingerprint 实现 replay/conflict，并在 Temporal start 失败时事务补偿或 durable retry。

### CONN-016：API 只预检一个 LLM 模块，真实 Pi run 固定依赖两个模块

严重级别：`P2 / delayed failure`

HTTP admission 只解析 `moduleKeyFromOptions` 选出的一个模块，默认是 `writer_composer`：

- `apps/api/internal/httpapi/server.go:3444-3463`
- `apps/api/internal/httpapi/server.go:8315-8324`

真实 Pi dual-stage 则固定依次解析：

- `writer_orchestrator`：`apps/pi-agent-runtime/src/activities/pi-writer-activities.ts:811-848`
- `writer_composer`：同文件 `900-925`

因此 composer 可用但 orchestrator 未绑定时，API 仍返回 `202 queued`，workflow 之后才异步失败。`review_after_write` 也只存在于 contract / parser，没有 runtime 消费者，不会自动启动独立 Reviewer。

关闭条件：Writer admission 一次性预检实际执行计划需要的全部模块、能力、credential 和 quota；未实现的 `review_after_write` 不应进入公开 contract，或应接到真实 reviewer workflow。

### CONN-017：缺少 Temporal 配置时 Writer API 会退回内存 queued

严重级别：`P1 / deployment correctness`

API 启动默认构造 `LocalWriterStarter`；只有存在 `TEMPORAL_ADDRESS` 才替换为 Temporal starter：

- `apps/api/cmd/api/main.go:143-150`
- `apps/api/cmd/api/main.go:265-284`

当前 Compose 正确配置了 Temporal，因此当前容器不受影响。但独立启动或错误部署中，POST 可返回只存在内存中的 queued run，而 GET 使用 SQL reader 时查不到该 run。这违反“无 mock 成功、模块未配置显式失败”的硬约束。

关闭条件：非测试 API 在配置数据库后必须要求 Temporal，缺失时 readiness 和 writer admission 都 fail closed；Local starter 只允许显式 test/dev mode。

### CONN-018：SSE 恢复与移动端 Writer 仍缺少当前产品认证

严重级别：`P2 / UX reliability`

当前 SSE、排序去重、terminal、cancel 和 poll fallback 已真实接线。但客户端没有 sequence-gap 检测或权威 snapshot，畸形 frame 会被忽略，连接中断提示也没有显式 retry action：

- `apps/web/lib/writer-sse-client.ts:100-127`
- `apps/web/components/writer-live-draft.tsx:160-177`

移动断点会把稿件和 Agent dock 纵向堆叠，dock 仍有较大的最低高度；本轮没有软键盘、composer 可达性和无重叠截图证据：

- `apps/web/app/workbench-polish.css:1512-1530`

这不是 Pi 数据链 blocker，但在 Z7 浏览器认证前不能宣称 Writer 的实时恢复和移动创作体验可交付。

## 前端功能与 Pi / 后端联系矩阵

| 前端功能 | 实际后端 | 是否直接进入 Pi | 当前判定 |
|---|---|---:|---|
| Writer Agent composer：draft / continue / outline | Go writer admission -> Temporal -> Pi | 是 | 真实接通 |
| Writer 选区 revise | 同一 writer run，mode=`revise` -> Pi | 是 | run/event 真实接通；diff 回填与专用采用未接通，当前有误追加正文风险 |
| Writer assets 勾选 | Pi `query_assets` | 是 | 可读 enabled seed/canon/material assets |
| Writer graph nodes 勾选 | Pi `query_graph_neighbors` | 是 | 选中真实 node 时可读节点与邻边 |
| Writer saved paths 勾选 | Pi `query_worldline_paths` | 是 | 可读；空选择却会读全部，边界错误 |
| Writer 最近手稿上下文 | Pi `query_manuscript_context` | 是 | 自动可调用；不滤 deleted、全项目仅 20 块 |
| Writer 章节 / 场景导航 | Go writerworkspace | 否 | CRUD 可用，但选择不会进入 Pi run |
| Writer 场景正文编辑 | Go writerworkspace -> `scenes.content_text` | 否 | 保存可用；不进入 manuscript |
| Candidate adoption | Go draft adoption store | 否 | 可用；是创建 manuscript block 的主路径 |
| Manuscript 编辑 / 恢复 / 移动 | Go manuscriptworkspace | 否 | 已有 block 基本可用；不能创建空白 block，并发冲突会丢本地正文 |
| Reviewer | Python writer reviewer worker | 否 | candidate/review 链可用，与 Pi 分离 |
| Book plan / dedup / manuscript commands | Python writer-planning worker | 否 | 独立工作流，不是 Pi tool |
| Asset distillation | Python `writer_asset_distiller` worker | 否 | 独立工作流；当前默认 manual |
| Manuscript export | Go export handler | 否 | 对 active manuscript blocks 可用 |
| Worldline page | Go admission + Python worldline worker | 否 | 独立显式流程，不由 Pi 自动触发 |
| Character Console | Go admission + Python character worker | 否 | 独立流程；转章节草稿时可再启动 Writer run |
| Persistent messages / approvals | 未挂载 store/routes | 否 | 当前不可用 |

结论：当前真正直接联系 Pi 的前端主入口只有 Writer Agent composer、选区 revise，以及 composer 携带的 assets / graph / saved-path references。其余 Writer tabs 和其他工作台使用 Go 或 Python 领域 worker，不是 Pi 的子工具。

## 全模块可用性矩阵

状态定义：

- `可用`：当前代码、运行依赖和核心行为都有本轮证据。
- `局部可用`：单模块真实可用，但前置条件、下游 handoff 或当前实例配置不完整。
- `不可正确使用`：界面/表/组件存在，但当前自然用户路径不能实现其宣称行为。
- `未认证`：没有发现确定代码断点，但本轮缺少当前浏览器或 external provider 旅程。

| 模块 | 状态 | 本轮结论 |
|---|---|---|
| Auth / Session / RBAC | 可用，浏览器未认证 | Go 回归和运行态正常；未重复执行 fresh 登录浏览器旅程 |
| Workspace / Project / Collaboration | 可用，浏览器未认证 | schema、API 和 Web 存在；不是本次主断点 |
| LLM Facility / quota / activity | 局部可用 | Writer/distiller bindings 存在；embedding 绑定无效；当前真实创作调用为 0 |
| Overview / 上传 / Seed | 局部可用 | worker healthy、测试通过；当前项目 3 个 Seed run 均 failed，没有成功内容基线 |
| Assets / Archive / keyword search | 可用 | CRUD、版本、集合、keyword 路径有测试；当前库没有用户资产 |
| vector / hybrid search | 不可正确使用 | 当前 binding 缺 embedding dimensions 和 index |
| Story Graph | 局部可用 | Seed 结构表可建图；正文蒸馏事实没有通用投影；当前两张空图 |
| Worldline preparation / current_world | 局部可用 | 显式准备、session、step、adoption 各层存在；handoff、上下文和 node/entity ID 有断点 |
| Character Console | 局部可用 | 独立对话 worker 可运行；未消费完整 prepared agent / graph / manuscript 上下文 |
| Writer Web / Go admission / Temporal | 局部可用 | 真实接 Pi；章节/场景、幂等补偿、revise apply 和 persistent thread 缺失 |
| Pi Writer Runtime | 可用但上下文不足 | provider/tool/candidate persistence 真实；typed context 不覆盖正文蒸馏知识 |
| Writer Reviewer | 可用 | 独立 LLM reviewer，不是硬编码评分；依赖真实 candidate |
| Candidate adoption | 可用 | 显式采用能创建 manuscript；自动蒸馏 enqueue 不可靠 |
| Manuscript workspace / export | 局部可用 | adopted blocks 可编辑、恢复、导出；纯手写不能创建首块 |
| Manuscript asset distillation | 局部可用 | manual admission/worker/proposal 分层可用；update、触发和长文本有缺陷 |
| Persistent thread / approvals | 不可正确使用 | migration/store/components 有，生产接线无 |
| Legacy import | 独立 gate | worker healthy；real cutover 仍需单独授权，不是零起点断点 |
| Ops / readiness / isolation runner | 可用 | Compose healthy、`/readyz` ready、独立 live runner 正常清理 |
| Fresh browser / release evidence | 未认证 | 当前无浏览器实例；Z7 未完成 |

## 本轮运行与测试证据

### 当前运行态

- API、Web、Pi Runtime、Seed、Asset、Graph、Worldline、Character、Reviewer、Writer Planning、Legacy Import workers 全部 running/healthy。
- Postgres、Redis、Temporal、MinIO healthy。
- `GET http://127.0.0.1:3888/readyz` 返回 `status=ready`，四个依赖均 ready。
- migration ledger 最新为 `0019_writer_threads`。

### 回归

| 范围 | 结果 |
|---|---|
| Go API `go test ./...` | passed |
| Web `npm test` | `241 passed, 9 skipped` |
| Web typecheck | passed |
| Web build | passed |
| Pi Runtime tests | `71 passed, 4 skipped` |
| Pi typecheck / build | passed |
| Python Agent Runtime | `443 passed, 31 skipped` |
| Infra tests | `67 passed` |
| Legacy backend full | `827 passed, 2 failed, 5 skipped` |
| Legacy 两个失败用例独立复跑 | `2 passed`，判定为顺序/共享状态 flake |

### Live / E2E 证据边界

已通过：

- 隔离 Postgres + 本地真实 provider 的 Pi Writer live E2E：`2 passed`。
- `TestLiveAssetDistillation*`。
- `TestLiveEmptyProject*`。

这些证据能证明 Pi provider/tool/draft persistence 和各领域 store/admission 可运行，但不能证明完整零起点闭环：

- `empty_project_writer_live_test.go` 直接 SQL 插入 completed writer run / draft。
- `store_live_test.go` 手工插入 candidate。
- 因此它们绕过了真实 Web -> Go -> Temporal -> Pi -> adoption -> distillation 的连续路径。
- 当前没有一条测试继续验证 proposal acceptance -> Graph node/edge -> Worldline preparation -> Character -> 下一次 Pi context。

## 文档与测试漂移

### 进度描述比生产接线更完整

`24-current-development-progress.md` 将 persistent thread、approvals 和 Z5 outbox 标为 implemented。当前更准确的分层描述是：

```text
migration / store / component implemented
!= server route mounted
!= page data/action connected
!= runtime producer connected
!= browser journey verified
```

### zero-start live tests不是完整产品 E2E

现有测试名称容易让读者误以为“空项目 Writer 已全链打通”，但 fixture 通过 SQL 构造关键中间状态。后续测试名或注释应明确：

- store/live contract。
- temporal/provider integration。
- browser product journey。

三者不得互相替代。

### embedding 文档与数据库不一致

进度文档称 `asset_search_embedding` 未绑定；当前库实际绑定到 `gpt-5.5`，但缺少 embedding settings 和 index。应在修复配置后校准文档，不能把无效绑定记为能力已就绪。

## 推荐修复顺序

### P0：先关闭正文与知识数据完整性

1. 统一纯手写与 AI adoption 的 manuscript 写入模型，增加空白 block 创建。
2. 打通 chapter/scene typed scope：Web -> Go -> DB -> Temporal -> Pi -> draft -> adopted block。
3. 修复 manuscript 并发保存，冲突时保留全文并提供 compare/merge。
4. 将 revise event 接到行内 diff 和专用 optimistic patch，禁止普通 block adoption。
5. 将 adoption + distillation outbox 改为事务性提交，所有错误可观测、可重放。
6. 修复 proposal expected version、conflict commit 和 pending unique ordering。
7. 定义 accepted manuscript assets 到 entity/relationship/rule/thread 的 canonical projection。
8. 为 Writer run 增加服务端幂等 replay 和 Temporal start 失败补偿。

### P1：补齐连续创作上下文

1. Pi chapter/scene tool 读取真实结构、大纲、场景和邻近正文。
2. manuscript context 只读 active、按当前章节/场景组织，并支持长篇 checkpoint/summary。
3. typed character/world-rule tools 消费统一 canon，而不是只看 Seed 表。
4. Worldline session 消费 preparation、goal、prepared agents、Graph、manuscript/current-world state。
5. Character dialogue加载 prepared profile、world rules、关系和当前世界状态。
6. 真正挂载 writer threads/messages/approvals，并让 Pi/Go 生产和消费它们。
7. 删除或禁用无 producer 的 `chapter_complete` 选项，直到链路完成。
8. admission 预检 orchestrator + composer 全部真实依赖；`review_after_write` 接线或移除。

### P2：配置、体验与发布证据

1. 移除无效 embedding binding，或绑定真实 embedding 模型、dimensions 并完成 reindex。
2. 为自动蒸馏失败、proposal conflict、Graph stale、Worldline context 缺失提供作者可恢复状态。
3. 校准 `11`、`21`、`24`、`28`、`30` 与任务板中的 implemented / connected / verified 用词。
4. 在独立 `--app` live stack 上执行 fresh desktop/mobile 全旅程并保留证据。
5. 生产 API 缺 Temporal 时 fail closed，禁止隐式 Local Writer success。

## 最终验收定义

只有同时满足以下条件，才能宣称“用户可从零开始写小说，并持续自动建立智能库、图谱和世界线”：

1. 新账号、新工作区、新项目，不预置小说、章节、资产、图谱或 worldline。
2. 作者创建第一章/场景并纯手写正文；刷新后正文仍在 active manuscript block 中。
3. 同一正文可审校、版本恢复、导出，不依赖先生成 AI candidate。
4. 双标签并发保存冲突时，客户端完整草稿仍可恢复并完成 compare/merge。
5. 选区 revise 只修改目标版本的选区，不能生成或采用为额外正文块。
6. 保存/章节完成按明确设置创建 durable distillation request；失败可见、可重试、不漏单。
7. LLM 只生成 disabled proposals；作者接受后才成为 canon，拒绝不污染资产和图谱。
8. 第二次更新同一角色/规则/关系能正确 merge，不发生固定 version=1 冲突。
9. 接受角色和关系后，重建或自动刷新 Graph 能看到对应节点、别名、证据和边。
10. Worldline preparation 能从真实 Graph/Assets 选角色，session 继承 preparation、goal 和当前世界状态。
11. Character 能读取对应角色档案、规则、关系、worldline 和最近正文，而不是只有 ID。
12. Writer 在选定章节/场景中继续写时，Pi tool trace 能证明读取了正确章节、场景、active manuscript、canon assets、Graph 和选中 path。
13. candidate adoption 后 block 位于正确章节/场景，并触发一次且仅一次蒸馏请求。
14. persistent thread 跨多个 Writer runs 可恢复；需要 approval 的动作能创建、展示、决定并继续 workflow。
15. 全旅程在 `infra/scripts/run-live-test-stack.sh --app -- <command>` 的独立数据库和 volumes 中运行，退出后 `down -v`。
16. desktop/mobile browser 无 pageerror、无隐私泄漏、无误导性成功状态，并保存 fresh 截图。
17. 相同 idempotency key 的模糊重试只产生一个 run；Temporal start 失败不会留下 queued 孤儿。
18. external provider、quota reserve/finalize、usage、activity、private trace、SSE/reconnect 和失败恢复均有本轮证据。

在这些条件全部满足前，Z7 应保持 `in_progress`，零起点创作链不得标记为完整可用。
