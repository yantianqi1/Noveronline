# 10. Character Console

更新时间：`2026-06-27`

## 模块定位

角色控制是作者以第一人称带入某个角色，降临到小说当前某个节点，从这个节点开始互动式写小说。系统记录互动过程，再由 Agent 优化润色成小说章节。

它不是普通聊天页，而是 worldline session 上的角色扮演与剧情采样工具。

## 旧功能覆盖

旧 Character Console 能力：

- list worldline sessions。
- project/session filter。
- select session。
- worldline agent roster。
- select agent。
- issue agent action。
- chat with agent。
- load agent history。
- load agent actions/dialogues/memory。
- interaction log。
- session command panel。

新系统必须覆盖，并新增“互动记录转章节”。

## 核心流程

```text
选择项目
  -> 选择 worldline session / saved path / chapter node
  -> 选择可扮演角色
  -> 确认降临节点
  -> 作者以第一人称输入行动/对话/心理
  -> Agent/Director 反馈世界反应
  -> 记录 interaction log
  -> 选择片段
  -> 转化为章节草稿
  -> 写作台继续润色
```

## 角色控制模式

### First-Person Mode

作者扮演角色。

输入：

- 我说什么。
- 我做什么。
- 我的内心判断。
- 我试图影响谁。

输出：

- 角色行动记录。
- 世界反馈。
- 其他角色反应。
- 新事件候选。

### Director-Assisted Mode

作者给行动意图，Director 判定结果。

适合：

- 战斗。
- 谈判。
- 阵营选择。
- 信息误判。

### Dialogue Mode

作者和指定角色对话。

覆盖旧 `chatWithWorldlineAgent`。

### Replay Mode

查看过往互动，选择片段转写。

## UI 设计

```text
Header
  session selector
  character selector
  current node
  mode

Left Panel
  session list
  agent roster
  saved paths

Center Panel
  interactive scene stream
  input composer
  action/dialogue toggles

Right Panel
  character dossier
  memory
  relationship state
  interaction outline

Bottom Action
  save interaction
  convert to chapter draft
```

## 降临节点

可以来自：

- worldline current step。
- saved path event。
- chapter/scene。
- graph node。
- plot thread。

当前 metadata skeleton 已接入 worldline session、saved path、selected session event、prepared agent 和 Story Graph viewport node 的 public metadata 选择器，并在侧栏预览 public session/path/graph-node/agent metadata。Character dossier inspector 会用 selected interaction 的 `pov_agent_id` 匹配已加载的 prepared-agent public metadata，只展示 role/status/source asset/summary 等公开字段；history panel 只从已保存的 public turn metadata 派生 POV/user turn 摘要，不读取或生成私有角色记忆、runtime history 或 AI 回复。缺对应 backend 时必须显示明确错误，不伪造可降临节点、可扮演角色或角色记忆。

数据结构：

```json
{
  "anchor_type": "worldline_event",
  "anchor_id": "evt_...",
  "title": "雨夜谈判前",
  "world_state_summary": "...",
  "available_agents": []
}
```

## Interaction Record

```text
character_interaction_sessions
  tenant_id
  project_id
  interaction_id
  worldline_session_id
  anchor_type
  anchor_id
  pov_agent_id
  mode
  status
  created_by
  created_at

character_interaction_turns
  tenant_id
  project_id
  interaction_id
  turn_id
  turn_order
  actor_type = user | agent | director | system
  actor_id
  input_text
  output_text
  action_json
  world_state_delta_json
  trace_id
  created_at
```

## 转章节草稿

### Workflow

```text
CharacterInteractionToChapterWorkflow
  load_interaction
  load_project_context
  summarize_turns
  build_scene_outline
  prose_rewrite
  save_draft_scene
  link_source_interaction
```

输出：

- chapter draft。
- scene draft。
- source interaction links。
- style/reviewer warnings。

### Agent 输入

```json
{
  "interaction_id": "int_...",
  "target_chapter_id": "chap_...",
  "pov": "first_person_to_third_person 或 keep_first_person",
  "style_asset_ids": [],
  "author_instruction": "保留压迫感，弱化解释"
}
```

## API

### Create Interaction

```http
POST /v1/projects/{projectId}/character-interactions
```

### Add Turn

```http
POST /v1/character-interactions/{interactionId}/turns
```

### List Turns

```http
GET /v1/character-interactions/{interactionId}/turns
```

### Stream Turn

```http
GET /v1/character-interactions/{interactionId}/events
Accept: text/event-stream
```

### Convert

```http
POST /v1/character-interactions/{interactionId}/chapter-drafts
```

当前 metadata skeleton 已在 Web typed API client、server actions 和 shell 表单中接入 turns read/write、runtime event pending 和 interaction -> Writer run handoff 合约：turns read/write 只返回或记录 public turn metadata；append turn endpoint 会先按当前 `X-Tenant-Id` 读取 parent interaction，缺失、跨租户或无 backend 时返回稳定错误，不写 turn metadata 或返回 fake created turn；页面可通过 `selected_interaction_id` 加载 detail 内嵌 turns，也可通过 `turns_interaction_id` 显式调用独立 `GET /v1/character-interactions/{interactionId}/turns` 读取 public turn replay，不需要重新加载完整 interaction；独立 turns replay endpoint 和底层 SQL store 都会先按当前 `X-Tenant-Id` 读取 parent interaction，缺失、跨租户或无 backend 时返回稳定错误，不把缺失 interaction 显示为空回放列表。`GET /v1/character-interactions/{interactionId}/events` 仍是 explicit runtime pending：Go pending endpoint 在返回 `CHARACTER_CONSOLE_RUNTIME_PENDING` 前会先用当前 `X-Tenant-Id` 读取 `{interactionId}`，缺失、跨租户或无 backend 时返回对应稳定错误，不把任意 interaction id 伪装成可进入 runtime 的 pending 状态。

`POST /v1/character-interactions/{interactionId}/chapter-drafts` 现在是显式 Writer handoff admission：Go API 先读取 tenant-scoped interaction 和 sanitized public turn summaries，要求至少存在一条带非空 public summary 的 saved turn，再解析 `writer_composer` LLM binding，并调用现有 `WriterStarter` 创建真实 `writer_run`，公开响应只返回 `interaction_id`、`run_id`、`trace_id`、`project_id`、`workflow_type` 和 `status`。空 turn list 或只有空白 summary 的 turn list 会以 `CHARACTER_INTERACTION_TURNS_REQUIRED` fail closed，不解析 LLM binding、不排队 Writer run。该 endpoint 不在 Character Console 内生成 AI 回复、不伪造 chapter draft id、不写 Writer draft/manuscript；若缺 LLM binding、缺 interaction 或 Writer backend 不可用，会 fail closed 并返回稳定错误。Next shell 显示 Writer run queued，不把 admission 说成 draft 已创建。

当前 metadata skeleton 还新增显式 interaction status mutation：`PATCH /v1/character-interactions/{interactionId}` 只允许作者把当前 tenant 下的 interaction 标记为 `active` / `saved` / `archived`，Go store 通过 tenant-scoped `UPDATE character_interaction_sessions ... RETURNING` 返回 sanitized public interaction metadata；Next shell 暴露 Save interaction / Archive interaction / Restore active 表单动作。该动作不写 turn、不启动 runtime、不生成 worldline event、不转章节草稿、不写 Writer draft/manuscript。

Go metadata store 会在 SQL 前校验 interaction `anchor_type` 只能是空值或 `worldline_session` / `worldline_event` / `saved_path` / `chapter` / `scene` / `graph_node` / `plot_thread`，interaction `mode` 只能是 `first_person` / `director_assisted` / `dialogue` / `replay`，interaction list `status` filter 只能是空值或 `active` / `saved` / `archived`，turn `actor_type` 只能是 `user` / `agent` / `director` / `system`，turn `turn_kind` 只能是 `action` / `dialogue` / `thought` / `director_note` / `system_note`；非法值返回 `VALIDATION_FAILED`，不写 DB、不触发 runtime。Postgres baseline 对同一批 public enum 也有 CHECK 约束，避免外部 writer 或未来 alternate path 绕过 Go store 写入 runtime-like anchor/action/status 字符串。

Go read side 还会在返回 interaction `metadata`、turn `action` 和 `world_state_delta` 前递归清洗历史或外部写入的 JSON payload，移除 prompt/response/body/content/source text/source material/candidate body/event body/API key/credential/draft/manuscript 类字段。HTTP response boundary 会对 create/list/detail/append/turn replay 返回的 interaction/turn record 再执行同类清洗，避免测试注入 store、替换 store 或未来 alternate writer 绕过 SQL read-side sanitizer。即使旧数据或替换 writer 写入了敏感 key，公开 API 也只能返回 sanitized public metadata。

Character Console store 和 HTTP 错误边界也必须稳定化：DB-backed Go store 在真实 SQL queryer 上会先设置 app-role tenant context，再读写 RLS-protected interaction/turn 表；SQL query、scan、`rows.Err()` 以及 rows close / transaction commit 失败都归类为 `CHARACTER_INTERACTION_QUERY_FAILED`，store 不返回底层 driver 文本；store 层 interaction scan 使用固定 `character interaction query failed`，turn scan 使用固定 `character interaction turn query failed`；scan 失败会 abort tenant-scoped rows / transaction，避免 `INSERT ... RETURNING` scan error 后提交 partial write；HTTP 公开 message 固定为 `character interaction query failed`，不得把底层异常中的 prompt、API key、`credential_ref`、正文或 draft/manuscript 文本透出。HTTP 边界对 coded `NOT_FOUND` / `CHARACTER_INTERACTION_BACKEND_UNCONFIGURED` store error 也使用固定安全文案，避免替换 store 的 message 夹带 prompt、API key 或私密正文；create/append JSON decode validation error 不回显 decoder 原始错误详情，避免 unknown field 名称如 `api_key` / `prompt` 出现在公开响应。

## Agent 模块

复用：

- `worldline_agent_dialogue`
- `worldline_character_proposal`
- `worldline_director`
- `writer_orchestrator`
- `writer_composer`
- `writer_reviewer`

新增建议：

- `character_interaction_director`
- `character_interaction_rewriter`

## 旧功能映射

| 旧功能 | 新功能 |
|---|---|
| SessionCommandPanel | session/anchor/mode command panel |
| WorldlineAgentRoster | character roster |
| AgentDialoguePanel | dialogue/first-person stream |
| AgentDetailPanel | character dossier inspector |
| AgentHistoryPanel | memory/history tab |
| InteractionLogPanel | interaction timeline |
| issueAgentAction | add action turn |
| chatWithWorldlineAgent | dialogue turn |

## 验收清单

- 能从 worldline session 选择角色。
- 能选择降临节点。
- 能记录用户行动和 Agent 反馈。
- 能查看角色记忆和历史。
- 互动记录保存为资产或 interaction session。
- 能把互动记录转成章节草稿。
- 转写草稿能进入写作台。
- 多人同看一个 interaction 不串数据。
