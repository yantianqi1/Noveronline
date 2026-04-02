# Novel Writer Agent Design Spec

## Overview

将 claude-code-from-scratch 的 agent loop 架构改造为小说写作引擎，嵌入现有 MiroFish-Novel 的 WriterWorkbench。核心变化：把代码工具替换为小说设定数据调度工具，采用双层 Agent 架构（编排层 + 写作层），统一数据库存储。

## 目标

- 用户在前端 WriterWorkbench 中选择章节、视角角色、场景、涉及角色后，agent 自动调度设定数据并生成高质量场景正文
- 支持写场景、续写、改写、扩写/缩写、章节大纲生成、一致性检查六种任务
- 编排层用便宜快速模型，写作层用最强模型，通过现有 llm_module_bindings 配置
- 写作层的 system prompt 由用户编辑和管理（预设系统）

## 非目标

- 不替换现有的世界线推演系统（推演和写作共用底层数据，但交互流程独立）
- 不改变项目上传、种子分析、图谱构建等上游流程
- 不做跨项目的全局写作（每次写作限定在一个项目内）

## 与现有写作流程的关系

现有系统已有一套完整的写作流程（`/api/novel/draft/generate` + `NovelDraftOrchestrator` + 5 个子 agent）。新 Writer Agent 系统**替换**这套流程，而非并行共存：

- 现有 `/api/novel/draft/generate` 和 `/api/novel/draft/revise` 端点保留但标记为 deprecated
- 新端点 `/api/writer-agent/run` 承担所有写作任务
- 前端 WriterWorkbench 改造后只调用新端点
- 现有 `ContextAgent`、`MemoryAgent`、`StyleAgent` 的核心查询逻辑被提取为工具实现，原 agent 类不再直接使用
- 现有 `ReviewerAgent` 的逻辑保留在 PostProcessor 中复用

---

## 架构设计

### 双层 Agent 架构

```
前端 WriterWorkbench
    │ POST /api/writer-agent/run (SSE)
    ▼
Flask: WriterAgentAPI
    │
    ▼
Orchestrator Agent（编排层）
    模型：快速便宜（module_key: writer_orchestrator）
    能力：LLM + 8 个数据调度工具
    职责：
      1. 解析用户意图和前端传入的上下文指定
      2. 通过 agent loop 自主调用工具收集设定数据
      3. 组装 writing_brief（结构化写作指令）
      4. 将 writing_brief 传给 Writer Agent
    │
    ▼
Writer Agent（写作层）
    模型：最强（module_key: writer_composer）
    能力：无工具，纯文本生成
    职责：
      接收 writing_brief + 用户预设 prompt，专注产出高质量文本
      输出 streaming 回传前端
    │
    ▼
PostProcessor（后处理）
    ● 保存草稿到 scenes 表
    ● 更新 chapter_content（拼接场景）
    ● 保存 writing_brief_json（留痕）
    ● 可选：用 writer_reviewer 模型做一致性快检
```

### 与现有系统的关系

渐进式改造，不推倒重来：

| 现有模块 | 改造策略 |
|---------|---------|
| `NovelDraftOrchestrator` | 替换为新的 agent loop 编排器 |
| `ContextAgent` 核心逻辑 | 包装为 `query_chapter` / `get_open_threads` 工具 |
| `MemoryAgent` 核心逻辑 | 包装为 `get_world_state` / `query_entity` 工具 |
| `StyleAgent` 核心逻辑 | 包装为编排层可选的预处理步骤 |
| `WriterAgent` | 改造：加入预设 prompt 支持 |
| `ReviewerAgent` | 保留为 PostProcessor 的一致性检查模块 |
| SSE streaming 基础设施 | 直接复用 |
| WriterWorkbench 前端 | 改造为场景化写作 UI |

### Agent Loop 引擎

从 claude-code-from-scratch 移植核心 agent loop，Python 化：

```python
class AgentLoop:
    """
    agent loop 核心：LLM 思考 → 调工具 → 拿结果 → 再思考，
    直到 LLM 不再调用工具为止。
    """

    def __init__(self, model_config, tools, system_prompt):
        self.model_config = model_config    # channel_key + model_id
        self.tools = tools                  # 工具定义列表
        self.system_prompt = system_prompt
        self.messages = []

    def run(self, user_message: str) -> Generator:
        """
        运行 agent loop，yield 中间状态事件。
        最后一轮 LLM 不调工具时，输出即为 writing_brief。
        """
        self.messages.append({"role": "user", "content": user_message})

        while True:
            response = call_llm(self.model_config, self.system_prompt,
                                self.messages, self.tools)
            self.messages.append(response.to_message())

            tool_calls = response.get_tool_calls()
            if not tool_calls:
                # LLM 决定不再调工具，输出最终结果
                yield {"type": "brief_ready", "content": response.text}
                break

            # 执行工具并收集结果
            tool_results = []
            for call in tool_calls:
                yield {"type": "tool_call", "name": call.name, "input": call.input}
                result = execute_tool(call.name, call.input)
                tool_results.append({"tool_use_id": call.id, "content": result})
                yield {"type": "tool_result", "name": call.name, "summary": truncate(result)}

            self.messages.append({"role": "user", "content": tool_results})
```

---

## 工具集设计

编排层专用，共 8 个工具。每个工具本质是对 novel.sqlite3 的查询封装。

### 1. query_entity

```json
{
    "name": "query_entity",
    "description": "查询角色、组织、物品、地点、技能的档案设定。返回实体的完整 profile 包括核心驱动力、隐藏矛盾、详细设定等。",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "实体名称或别名"},
            "entity_type": {
                "type": "string",
                "enum": ["character", "organization", "item", "location", "skill"],
                "description": "可选，限定实体类型以缩小搜索范围"
            }
        },
        "required": ["name"]
    }
}
```

实现：查 entities 表 + entity_aliases 表，返回 name, entity_type, importance_tier, summary, core_drive, surface_mask, hidden_tension, profile_json 的格式化文本。

### 2. query_relationship

```json
{
    "name": "query_relationship",
    "description": "查询两个实体之间的关系，包括关系类型、信任度、权力动态、冲突触发点等。",
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_a": {"type": "string", "description": "第一个实体名称"},
            "entity_b": {"type": "string", "description": "第二个实体名称"}
        },
        "required": ["entity_a", "entity_b"]
    }
}
```

实现：先通过 entity_aliases 解析名称到 entity_id，再查 relationships 表（双向查询 source_id/target_id）。

### 3. query_chapter

```json
{
    "name": "query_chapter",
    "description": "查询指定章节的摘要、大纲、时间线、悬念线索。可选返回章节正文。",
    "input_schema": {
        "type": "object",
        "properties": {
            "chapter_order": {"type": "integer", "description": "章节序号"},
            "include_content": {"type": "boolean", "description": "是否包含章节正文（较长）", "default": false}
        },
        "required": ["chapter_order"]
    }
}
```

实现：查 chapter_meta + chapter_content 表。include_content=false 时只返回摘要/大纲/悬念，节省 token。

### 4. query_scene

```json
{
    "name": "query_scene",
    "description": "查询指定章节下已有的场景列表或某个场景的正文。",
    "input_schema": {
        "type": "object",
        "properties": {
            "chapter_id": {"type": "string", "description": "章节 ID"},
            "scene_order": {"type": "integer", "description": "可选，指定场景序号。不传则返回该章节所有场景的概览列表"}
        },
        "required": ["chapter_id"]
    }
}
```

实现：查 scenes 表。不传 scene_order 时返回列表（title, word_count, status），传了则返回完整正文。

### 5. search_settings

```json
{
    "name": "search_settings",
    "description": "按关键词全文搜索小说设定，包括角色描述、章节内容、记忆等。用于模糊查找特定设定信息。",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词，如'火系法术'、'竹林'、'背叛'"},
            "scope": {
                "type": "string",
                "enum": ["entities", "chapters", "scenes", "memory", "all"],
                "description": "搜索范围，默认 all",
                "default": "all"
            },
            "limit": {"type": "integer", "description": "最大返回条数，默认 10", "default": 10}
        },
        "required": ["query"]
    }
}
```

实现：查 FTS5 虚拟表（entities_fts, chapter_content_fts, scenes_fts, agent_memory_fts），返回匹配的摘要片段。

### 6. get_recent_scenes

```json
{
    "name": "get_recent_scenes",
    "description": "获取当前章节之前最近 N 个场景的正文，用于保持叙事连贯性。",
    "input_schema": {
        "type": "object",
        "properties": {
            "chapter_id": {"type": "string", "description": "当前章节 ID"},
            "scene_order": {"type": "integer", "description": "当前场景序号"},
            "count": {"type": "integer", "description": "向前取几个场景，默认 2", "default": 2}
        },
        "required": ["chapter_id", "scene_order"]
    }
}
```

实现：查 scenes 表，取 scene_order 之前的 N 个场景正文。如果当前章节的前面场景不够，跨到上一章节取。

### 7. get_world_state

```json
{
    "name": "get_world_state",
    "description": "获取世界线会话中角色/组织的当前状态快照和最近事件。",
    "input_schema": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "世界线会话 ID"},
            "entity_id": {"type": "string", "description": "可选，指定实体。不传则返回所有活跃实体的状态概览"}
        },
        "required": ["session_id"]
    }
}
```

实现：查 sessions + agent_states + world_events 表。

### 8. get_open_threads

```json
{
    "name": "get_open_threads",
    "description": "获取截至指定章节的所有未解决悬念线索，帮助保持叙事连贯性。",
    "input_schema": {
        "type": "object",
        "properties": {
            "up_to_chapter": {"type": "integer", "description": "截至第几章（含），默认当前章节前一章"}
        },
        "required": ["up_to_chapter"]
    }
}
```

实现：查 chapter_meta 表的 open_threads_json，聚合截至指定章节的所有未关闭悬念。

---

## 统一数据库设计

### 存储策略

```
全局:
  uploads/system/platform.sqlite3       ← LLM 配置、任务状态（不变）

每个项目:
  projects/{id}/novel.sqlite3           ← 该项目所有小说数据统一存储
```

### novel.sqlite3 表结构

#### 设定层

```sql
CREATE TABLE entities (
    entity_id       TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    name            TEXT NOT NULL,
    entity_type     TEXT NOT NULL,           -- character|organization|item|location|skill
    importance_tier TEXT DEFAULT 'minor',    -- protagonist|major|supporting|minor
    summary         TEXT,
    core_drive      TEXT,
    surface_mask    TEXT,
    hidden_tension  TEXT,
    profile_json    TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE entity_aliases (
    alias       TEXT NOT NULL,
    entity_id   TEXT NOT NULL REFERENCES entities ON DELETE CASCADE,
    PRIMARY KEY (alias, entity_id)
);

CREATE TABLE entity_labels (
    entity_id   TEXT NOT NULL REFERENCES entities ON DELETE CASCADE,
    label       TEXT NOT NULL,
    PRIMARY KEY (entity_id, label)
);

CREATE TABLE relationships (
    relation_id      TEXT PRIMARY KEY,
    source_id        TEXT NOT NULL REFERENCES entities ON DELETE CASCADE,
    target_id        TEXT NOT NULL REFERENCES entities ON DELETE CASCADE,
    relation_type    TEXT NOT NULL,
    description      TEXT,
    trust_level      REAL,
    power_dynamic    TEXT,
    history          TEXT,
    conflict_trigger TEXT,
    updated_at       TEXT NOT NULL
);

CREATE TABLE entity_evidence (
    evidence_id TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL,
    owner_type  TEXT NOT NULL,               -- entity|relationship
    chapter_id  TEXT,
    snippet     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
```

#### 内容层

```sql
CREATE TABLE chapter_content (
    chapter_id      TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    chapter_order   INTEGER NOT NULL,
    title           TEXT DEFAULT '',
    content         TEXT NOT NULL DEFAULT '',
    word_count      INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'draft',     -- draft|review|final
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(project_id, chapter_order)
);

CREATE TABLE chapter_meta (
    chapter_id          TEXT PRIMARY KEY REFERENCES chapter_content ON DELETE CASCADE,
    summary             TEXT DEFAULT '',
    outline_json        TEXT DEFAULT '[]',
    timeline_note       TEXT DEFAULT '',
    open_threads_json   TEXT DEFAULT '[]',
    pov_character       TEXT,
    updated_at          TEXT NOT NULL
);

CREATE TABLE scenes (
    scene_id                TEXT PRIMARY KEY,
    chapter_id              TEXT NOT NULL REFERENCES chapter_content ON DELETE CASCADE,
    scene_order             INTEGER NOT NULL,
    title                   TEXT DEFAULT '',
    content                 TEXT NOT NULL DEFAULT '',
    word_count              INTEGER DEFAULT 0,
    pov_entity_id           TEXT,
    location                TEXT,
    involved_entities_json  TEXT DEFAULT '[]',
    status                  TEXT DEFAULT 'draft',
    writing_brief_json      TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    UNIQUE(chapter_id, scene_order)
);
```

#### 世界线层（推演 + 写作统一）

```sql
CREATE TABLE sessions (
    session_id      TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    session_type    TEXT NOT NULL,            -- simulation|writing
    title           TEXT,
    focus_question  TEXT,
    status          TEXT DEFAULT 'running',
    config_json     TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE agent_states (
    state_id    TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions ON DELETE CASCADE,
    entity_id   TEXT NOT NULL REFERENCES entities,
    state_json  TEXT NOT NULL,
    status      TEXT DEFAULT 'active',
    version     INTEGER DEFAULT 1,
    updated_at  TEXT NOT NULL
);

CREATE TABLE agent_memory (
    memory_id   TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions ON DELETE CASCADE,
    entity_id   TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    summary     TEXT NOT NULL,
    detail_json TEXT,
    salience    REAL DEFAULT 0,
    source_kind TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE world_events (
    event_id                TEXT PRIMARY KEY,
    session_id              TEXT NOT NULL REFERENCES sessions ON DELETE CASCADE,
    step                    INTEGER NOT NULL,
    title                   TEXT NOT NULL,
    summary                 TEXT NOT NULL,
    event_type              TEXT,
    driving_entities_json   TEXT DEFAULT '[]',
    state_changes_json      TEXT DEFAULT '[]',
    status                  TEXT DEFAULT 'canon',
    created_at              TEXT NOT NULL
);
```

#### 预设层

```sql
CREATE TABLE writer_presets (
    preset_id   TEXT PRIMARY KEY,
    project_id  TEXT,                         -- NULL 表示全局预设
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    system_prompt TEXT NOT NULL,
    is_default  INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

#### 搜索层

```sql
CREATE VIRTUAL TABLE entities_fts USING fts5(
    name, summary, core_drive, hidden_tension,
    content=entities, tokenize='unicode61'
);

CREATE VIRTUAL TABLE chapter_content_fts USING fts5(
    title, content,
    content=chapter_content, tokenize='unicode61'
);

CREATE VIRTUAL TABLE scenes_fts USING fts5(
    title, content,
    content=scenes, tokenize='unicode61'
);

CREATE VIRTUAL TABLE agent_memory_fts USING fts5(
    summary,
    content=agent_memory, tokenize='unicode61'
);
```

### 迁移策略

需要编写迁移脚本，将现有 7 个 SQLite 库的数据灌入 novel.sqlite3：

| 来源 | 目标 |
|------|------|
| archive_library.sqlite3 → archive_library 表 | entities + entity_aliases + entity_labels |
| archive_library.sqlite3 → archive_agent_memory 表 | agent_memory |
| chapter_meta.sqlite3 → chapter_meta 表 | chapter_meta |
| chapter_meta.sqlite3 → chapter_history_item 表 | world_events（转换 item_type） |
| story_graph.sqlite3 → graph_nodes | entities（补充/合并） |
| story_graph.sqlite3 → graph_edges | relationships |
| story_graph.sqlite3 → graph_evidence | entity_evidence |
| prepare.sqlite3 → prepared_agent_dossiers | agent_states（初始状态） |
| runtime.sqlite3 → agent_registry | agent_states |
| runtime.sqlite3 → agent_episodic_memory | agent_memory |
| runtime.sqlite3 → agent_action_log | world_events |
| chapter_segments.json → chapters[].content | chapter_content |

现有的 7 个库和 JSON 文件在迁移完成后保留（不删除），但新代码只读写 novel.sqlite3。

---

## API 设计

### 新增 Blueprint: writer_agent_bp

注册为 `/api/writer-agent/`。

### 端点列表

#### 核心写作

```
POST /api/writer-agent/run
```

请求体：

```json
{
    "project_id": "proj_xxx",
    "task_type": "write_scene",
    "chapter_id": "ch_12",
    "scene_order": 3,
    "pov_entity_id": "ent_lingyuan",
    "involved_entity_ids": ["ent_xiewuchen", "ent_lingyuan"],
    "scene_focus": "竹林密谈，林远试探谢无尘的真实目的",
    "user_instruction": "这段要有张力，两人表面客气但暗流涌动",
    "preset_id": "preset_xianxia_01",
    "session_id": "sess_xxx",
    "selected_text": "",
    "continue_from_scene_id": ""
}
```

task_type 枚举：
- `write_scene` — 写新场景
- `continue` — 从断点续写
- `rewrite` — 改写选中文本
- `expand` — 扩写选中文本
- `outline` — 生成章节大纲（场景拆分）
- `consistency_check` — 一致性检查

响应（SSE streaming）：

```
event: orchestrator_status
data: {"phase": "tool_call", "tool": "query_entity", "input": {"name": "林远"}}

event: orchestrator_status
data: {"phase": "tool_result", "tool": "query_entity", "summary": "林远：主角，剑修..."}

event: orchestrator_status
data: {"phase": "brief_ready", "tool_calls_count": 5}

event: writer_token
data: {"token": "月光穿过"}

event: done
data: {"scene_id": "sc_xxx", "word_count": 1523, "warnings": []}
```

```
POST /api/writer-agent/stop
```

中断当前写作任务。

#### 场景管理

```
GET    /api/writer-agent/scenes/{chapter_id}             — 获取章节下所有场景
PUT    /api/writer-agent/scenes/{scene_id}               — 用户手动编辑场景正文
POST   /api/writer-agent/scenes/{scene_id}/regenerate    — 重新生成场景
DELETE /api/writer-agent/scenes/{scene_id}               — 删除场景
POST   /api/writer-agent/scenes/{chapter_id}/reorder     — 调整场景顺序
POST   /api/writer-agent/scenes/{chapter_id}/compile     — 拼接场景为章节正文
```

#### 预设管理

```
GET    /api/writer-agent/presets                  — 获取预设列表（含全局 + 项目级）
POST   /api/writer-agent/presets                  — 创建预设
PUT    /api/writer-agent/presets/{preset_id}      — 更新预设
DELETE /api/writer-agent/presets/{preset_id}      — 删除预设
```

#### 章节管理

```
GET    /api/writer-agent/chapters/{project_id}            — 获取项目所有章节列表
POST   /api/writer-agent/chapters/{project_id}            — 新建章节
PUT    /api/writer-agent/chapters/{chapter_id}             — 更新章节元数据
DELETE /api/writer-agent/chapters/{chapter_id}             — 删除章节
```

---

## 模型调度

通过现有 llm_module_bindings 机制，新增 module_key：

| module_key | 用途 | 推荐绑定 |
|------------|------|---------|
| `writer_orchestrator` | 编排层：工具调度、意图理解 | 快速便宜模型（GPT-4o-mini, Haiku） |
| `writer_composer` | 写作层：正文生成 | 最强模型（Opus, Claude Sonnet 4） |
| `writer_reviewer` | 后处理：一致性检查 | 中等模型（GPT-4o-mini, Haiku） |

用户可在前端 LLM Facility 面板中自由切换绑定。

---

## 前端改造

### WriterWorkbench 改造要点

在现有 WriterWorkbenchView.vue（1043 行）基础上改造，不重写：

#### 新增 UI 元素

1. **场景列表面板**（左侧）
   - 显示当前章节的场景列表（序号、标题、字数、状态）
   - 支持点击选择、拖拽排序、添加/删除场景
   - 状态图标：draft / review / final

2. **预设选择器**（顶部控制栏）
   - 下拉选择写作风格预设
   - 编辑按钮 → 弹窗编辑预设内容
   - 新建/删除预设

3. **场景编辑区**（中央）
   - streaming 实时显示 agent 输出
   - 写完后可直接编辑
   - 选中文字后显示浮动工具栏：改写 / 扩写

4. **上下文指定面板**（左下）
   - 视角角色选择
   - 涉及角色多选
   - 场景描述输入
   - 用户写作指令输入

5. **任务类型切换**
   - 写场景 / 续写 / 改写 / 扩写 / 大纲 / 一致性检查

#### 新增前端 API 客户端

```javascript
// frontend/src/api/writerAgent.js

export function runWriterAgent(payload, handlers, signal)     // POST SSE
export function stopWriterAgent()                              // POST
export function getScenes(chapterId)                           // GET
export function updateScene(sceneId, payload)                  // PUT
export function regenerateScene(sceneId, payload)              // POST SSE
export function deleteScene(sceneId)                           // DELETE
export function reorderScenes(chapterId, sceneIds)             // POST
export function compileChapter(chapterId)                      // POST
export function getPresets(projectId)                           // GET
export function createPreset(payload)                           // POST
export function updatePreset(presetId, payload)                 // PUT
export function deletePreset(presetId)                          // DELETE
export function getChapters(projectId)                          // GET
export function createChapter(projectId, payload)               // POST
export function updateChapter(chapterId, payload)               // PUT
export function deleteChapter(chapterId)                        // DELETE
```

---

## 不同任务类型的处理流

### write_scene（写场景）

```
编排层：
  1. 查视角角色档案（query_entity）
  2. 查涉及角色档案和关系（query_entity × N, query_relationship × N）
  3. 查上一章/当前章摘要和大纲（query_chapter）
  4. 查最近场景正文（get_recent_scenes）
  5. 查未解决悬念（get_open_threads）
  6. 按需补充查询（search_settings 等）
  7. 组装 writing_brief

写作层：
  接收 writing_brief + 预设 prompt → 生成场景正文

后处理：
  保存到 scenes 表 → 更新 chapter_content
```

### continue（续写）

```
编排层：
  1. 查当前场景正文和末尾上下文（query_scene）
  2. 查后续大纲/悬念（query_chapter, get_open_threads）
  3. 查涉及角色设定（query_entity）
  4. 组装 writing_brief（含 continue_from 指令）

写作层：
  接收上文 + 指令 → 从断点继续写
```

### rewrite（改写）

```
编排层：
  1. 接收用户选中的文本（selected_text）
  2. 查涉及角色设定（query_entity）
  3. 查前后上下文（get_recent_scenes）
  4. 组装 writing_brief（含原文 + 改写指令）

写作层：
  接收原文 + 指令 → 按要求重写
```

### expand（扩写）

```
编排层：
  1. 接收用户选中的文本（selected_text）
  2. 查相关设定以便展开细节（query_entity, search_settings）
  3. 组装 writing_brief（含原文 + 扩写指令）

写作层：
  接收原文 + 指令 → 展开细节
```

### outline（章节大纲）

```
编排层：
  1. 查全书级别大纲（如果有）
  2. 查前后章摘要（query_chapter）
  3. 查未解决悬念（get_open_threads）
  4. 查主要角色当前状态（get_world_state 或 query_entity）
  5. 组装 outline_brief

写作层（此时作为大纲生成器）：
  生成场景拆分列表 → 保存到 chapter_meta.outline_json
```

### consistency_check（一致性检查）

```
编排层：
  1. 查当前场景正文（query_scene）
  2. 查场景中出现的所有角色设定（query_entity × N）
  3. 查相关关系（query_relationship × N）
  4. 查前文中的相关描述（search_settings）
  5. 组装检查上下文

写作层（此时作为审阅器）：
  逐条比对设定 vs 正文 → 输出矛盾报告（JSON 格式）
```

---

## 后端文件结构

```
backend/app/
├── api/
│   └── writer_agent.py                    ← 新增 Blueprint
├── services/
│   └── writer_agent/
│       ├── __init__.py
│       ├── agent_loop.py                  ← agent loop 引擎（从 claude-code-from-scratch 移植）
│       ├── orchestrator.py                ← 编排层逻辑
│       ├── writer.py                      ← 写作层逻辑
│       ├── post_processor.py              ← 后处理
│       ├── tools.py                       ← 8 个工具定义 + 执行
│       ├── tool_executors.py              ← 工具实现（数据库查询）
│       ├── prompts.py                     ← 编排层 system prompt
│       ├── novel_db.py                    ← novel.sqlite3 统一数据访问层
│       ├── novel_db_migration.py          ← 迁移脚本
│       ├── preset_service.py              ← 预设 CRUD
│       ├── scene_service.py               ← 场景 CRUD
│       └── chapter_service.py             ← 章节 CRUD
```

---

## 编排层 Agent Loop 防护

编排层 LLM 可能出现以下异常行为，需要防护：

- **工具调用死循环** — 设置最大工具调用轮次上限（默认 15 轮），超过则强制输出当前已收集的上下文作为 brief
- **输出非 JSON 的 brief** — 编排层 system prompt 明确要求输出 JSON 格式的 writing_brief；如果最终输出不是合法 JSON，尝试从文本中提取结构化信息，兜底使用前端传入的原始上下文
- **工具调用失败** — 单个工具执行失败（如查询不到实体）返回明确错误信息给 LLM，让它决定是否换个查询方式或跳过
- **上下文溢出** — 工具返回结果截断到最大 8000 字符，编排层总上下文超过模型窗口 80% 时强制结束收集

## writer_presets 全局预设存储

`writer_presets` 表中 `project_id = NULL` 的全局预设存储在 `uploads/system/platform.sqlite3` 中（与 LLM 配置同库），而非项目级 novel.sqlite3。项目级预设（`project_id` 非空）存储在对应项目的 novel.sqlite3 中。前端查询预设时需合并两个来源。

## 迁移计划概要

1. **Phase 1: 数据层** — 创建 novel.sqlite3 schema + 迁移脚本 + NovelDB 数据访问层
2. **Phase 2: Agent 引擎** — 移植 agent loop + 工具定义/执行 + 编排层/写作层
3. **Phase 3: API 层** — writer_agent Blueprint + 场景/预设/章节 CRUD 端点
4. **Phase 4: 前端** — WriterWorkbench 改造（场景列表、预设编辑、任务类型切换）
5. **Phase 5: 集成测试** — 端到端写作流程验证

## 风险和依赖

- **LLM API 兼容性** — agent loop 需要支持 OpenAI 和 Anthropic 两种 tool_use 格式，复用现有 `llm_client.py` 的适配逻辑
- **迁移数据一致性** — archive_library 和 story_graph 中同一实体可能有不同版本的数据，迁移脚本需要定义合并策略（以 archive_library 为准，story_graph 补充）
- **FTS5 中文分词** — `unicode61` tokenizer 对中文分词效果有限（按字分词），对于精确的词组搜索可能需要后续引入 jieba 分词或 simple tokenizer 结合应用层过滤
- **前端改造范围** — WriterWorkbenchView.vue 已有 1043 行，场景化改造可能需要拆分为子组件以保持可维护性
