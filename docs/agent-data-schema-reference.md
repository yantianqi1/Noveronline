# Agent 数据结构与提示词参考文档

> 本文档汇总了系统中所有 Agent 相关的数据结构、LLM 生成的数据条目、提示词模板及参数配置。
> 供后续开发查阅。

---

## 目录

1. [角色 Agent 档案生成 (Character Agent Profile)](#1-角色-agent-档案生成)
2. [Agent Schema 注册表](#2-agent-schema-注册表)
3. [Agent 模板注册表 (Template Registry)](#3-agent-模板注册表)
4. [Worldline Agent 注册表](#4-worldline-agent-注册表)
5. [角色对话 Agent (Character Agent Service)](#5-角色对话-agent)
6. [叙事实体档案 (Narrative Entity Archivist)](#6-叙事实体档案)
7. [Writer Agent 提示词 (Writer Workbench)](#7-writer-agent-提示词)
8. [Draft Agent 多代理流水线](#8-draft-agent-多代理流水线)
9. [Agent 记忆系统](#9-agent-记忆系统)
10. [Sequential Reader 提示词](#10-sequential-reader-提示词)
11. [Story Ontology 提示词](#11-story-ontology-提示词)
12. [LLM 参数汇总](#12-llm-参数汇总)
13. [数据流总览](#13-数据流总览)

---

## 1. 角色 Agent 档案生成

**文件**: `backend/app/services/character_agent_profile_generator.py`, `character_agent_prompts.py`

### 生成的数据结构

每个角色 Agent 档案包含以下字段：

```json
{
  "profiles": {
    "<角色名>": {
      "basic_info": {
        "name": "str - 角色名",
        "aliases": ["str - 别名列表"],
        "identity": "str - 身份描述",
        "status": "str - 当前状态"
      },
      "personality": {
        "core_traits": ["str - 核心性格特征"],
        "values": "str - 价值观",
        "fears": "str - 恐惧/弱点",
        "decision_pattern": "str - 决策模式"
      },
      "speech": {
        "style": "str - 说话风格",
        "verbal_habits": ["str - 口头禅/语言习惯"],
        "tone_range": "str - 语调范围",
        "example_quotes": ["str - 原文引用示例"]
      },
      "relationships": [
        {
          "target": "str - 关系对象",
          "relation": "str - 关系类型",
          "detail": "str - 关系详情"
        }
      ],
      "capabilities": {
        "skills": ["str - 技能列表"],
        "limitations": ["str - 局限性"],
        "resources": "str - 可用资源"
      },
      "knowledge_boundary": {
        "knows": ["str - 已知信息"],
        "does_not_know": ["str - 未知信息"],
        "believes_wrongly": ["str - 错误认知"]
      },
      "motivation": {
        "ultimate_goal": "str - 终极目标",
        "current_objective": "str - 当前目标",
        "internal_conflict": "str - 内心冲突"
      }
    }
  },
  "profile_count": "int - 生成数量"
}
```

### 触发条件

- 重要性阈值：`DEFAULT_IMPORTANCE_THRESHOLD = 2`（最少出现在 2 个阅读段落中）
- 处理最近 5 条 arc/segment 摘要作为上下文

### 系统提示词 (CHARACTER_PROFILE_SYSTEM_PROMPT)

**硬性要求**：
- 仅输出 JSON，不包含 Markdown
- 禁止泛泛措辞（"性格复杂"、"关系微妙"）
- 每个数组至少 1 个元素
- 字段之间信息不得重复
- 数据不足时显式标注"暂无记录"或"证据不足"

**LLM 参数**: temperature=0.3, max_tokens=4096, module_key=`"character_agent_profile"`

---

## 2. Agent Schema 注册表

**文件**: `backend/app/services/agents/registry/agent_schema_registry.py`

### BASE_AGENT_SCHEMA（所有 Agent 通用）

| 字段 | 类型 | 标签 | 必填 |
|------|------|------|------|
| `drive` | str | 核心驱动力 | Yes |
| `tension` | str | 内在张力 | Yes |
| `role` | str | 角色定位 | Yes |
| `status` | str | 当前状态 | Yes |

### CHARACTER_EXTENSIONS（角色扩展）

| 字段 | 类型 | 标签 | 必填 |
|------|------|------|------|
| `personality` | str | 性格底色 | No |
| `skills` | list | 关键能力 | No |
| `loyalty` | str | 忠诚指向 | No |
| `secrets` | list | 隐藏秘密 | No |

### ORGANIZATION_EXTENSIONS（组织扩展）

| 字段 | 类型 | 标签 | 必填 |
|------|------|------|------|
| `resources` | list | 核心资源 | No |
| `internal_factions` | list | 内部派系 | No |
| `territorial_control` | str | 势力范围 | No |
| `public_stance` | str | 公开立场 | No |

### RELATIONSHIP_EXTENSIONS（关系扩展）

| 字段 | 类型 | 标签 | 必填 |
|------|------|------|------|
| `history` | str | 关系历史 | No |
| `power_dynamic` | str | 权力动态 | No |
| `trust_level` | str | 信任程度 | No |

### 支持的验证类型

`str`, `list`, `dict`, `number`, `float`, `bool`

---

## 3. Agent 模板注册表

**文件**: `backend/app/services/agents/registry/agent_template_registry.py`

### 重要性层级 (TIER_ORDER)

| Tier | 数值 | 模板 sections 数 |
|------|------|------------------|
| minor | 0 | 3 |
| supporting | 1 | 5 |
| major | 2 | 8 |
| protagonist | 3 | 8 |

### 通用 Sections (COMMON_SECTIONS)

**protagonist / major (8 sections)**:
`identity`, `motivation`, `tension`, `relationship`, `behavior`, `state`, `risk`, `private`

**supporting (5 sections)**:
`identity`, `motivation`, `tension`, `relationship`, `state`

**minor (3 sections)**:
`identity`, `state`, `summary`

### 类型专属字段 (TYPE_FIELDS)

**character**:
`identity_hint`, `personality`, `skills`, `loyalty`, `secrets`, `recent_turning_points`, `long_term_goal`, `short_term_goal`

**organization**:
`organization_type`, `resources`, `internal_factions`, `territorial_control`, `public_stance`, `strategic_goal`, `conflict_targets`

**relationship**:
`history`, `power_dynamic`, `trust_level`, `conflict_trigger`, `stability_forecast`, `last_action`

### 常量

- `TEMPLATE_VERSION = "v1"`
- `DEFAULT_TIER = "supporting"`

---

## 4. Worldline Agent 注册表

**文件**: `backend/app/services/agents/worldline/worldline_agent_registry.py`

### Agent 状态完整结构（角色/组织类型）

```json
{
  "agent_id": "str - hash 生成",
  "agent_kind": "character | organization | relationship",
  "display_name": "str",
  "source_ref": "str - 来源引用",
  "role": "str - 来自 state 或 KIND_ROLE_TEXT",
  "drive": "str - 来自 state.drive / state.core_drive",
  "tension": "str - 来自 state.tension / state.hidden_tension",
  "status": "str - 默认 active",
  "summary": "str - 由 drive/tension 生成",
  "schema": "Dict - 完整 schema 定义",
  "validation_errors": ["str - 校验错误"],
  "can_chat": "bool",
  "can_act": "bool",
  "state_source": "str - 默认 session_bootstrap",
  "source_archive_id": "str (optional)",
  "source_entity_uuid": "str (optional)",
  "importance_tier": "str",
  "template_key": "str",
  "template_version": "str",
  "template_sections": ["str - 对应 tier 的 sections"],
  "state": "Dict - 原始 state 字典"
}
```

### 关系类型 Agent

```json
{
  "agent_id": "relation::id1::id2",
  "agent_kind": "relationship",
  "display_name": "name × name",
  "source": "str - 关系源",
  "target": "str - 关系目标",
  "change": "stable | tension_up | relationship_shift",
  "history": "str",
  "power_dynamic": "str",
  "trust_level": "str",
  "conflict_trigger": "str",
  "stability_forecast": "str",
  "last_action": "str",
  "importance_tier": "str",
  "template_key": "str",
  "template_sections": ["str"]
}
```

### KIND_ROLE_TEXT 映射

| Kind | 文本 |
|------|------|
| character | 角色 |
| organization | 组织 |
| relationship | 关系推动者 |

---

## 5. 角色对话 Agent

**文件**: `backend/app/services/agents/worldline/character_agent_service.py`

### 对话回复结构 (generate_reply)

```json
{
  "agent": "str - 角色名",
  "status": "str - 当前状态",
  "drive": "str - 驱动力",
  "branch_title": "str",
  "reply": "str - LLM 生成的对话",
  "suggested_actions": ["str - 建议动作"],
  "worldline_observation": "str",
  "generator_mode": "template | llm",
  "model_name": "str",
  "memory_context": "str"
}
```

### 动作提案结构 (propose_action)

```json
{
  "agent": "str",
  "act": "bool - 是否行动",
  "action": "str - 动作描述",
  "intent": "str - 意图",
  "target": "str - 目标",
  "reason": "str - 理由",
  "drive": "str",
  "tension": "str",
  "status": "str",
  "model_name": "str"
}
```

### 系统提示词

**PROPOSAL_SYSTEM_PROMPT**:
- 角色独立决定下一步动作
- 输出 JSON：`{"act": true/false, "action", "intent", "target", "reason"}`
- temperature=0.6, max_tokens=500

**WORLDLINE_AGENT_DIALOGUE_SYSTEM_PROMPT**:
- 第一人称回复，基于角色状态和事件
- 纯文本输出，不含 JSON
- temperature=0.7, max_tokens=900

### 记忆渲染优先级

按类型排序：strategy > promise > relationship > goal > preference > 其他
按 salience 降序

---

## 6. 叙事实体档案

**文件**: `backend/app/services/narrative_entity_archivist.py`

### ARCHIVE_SYSTEM_PROMPT - LLM 输出字段

**所有 Agent 通用字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `importance_tier` | str | protagonist / major / supporting / minor |
| `entity_role` | str | 故事功能定位 |
| `core_drive` | str | 核心驱动力 |
| `surface_mask` | str | 表面形象 |
| `hidden_tension` | str | 隐藏张力 |
| `relationship_summary` | str | 关系概述 |
| `agent_behavior_hint` | str | Agent 行为提示 |
| `human_ai_relation_tag` | str | human / ai / hybrid / system / none |
| `notable_risks` | list | 风险标记 |

**角色 (character) 额外字段**:
`personality`, `skills`, `loyalty`, `secrets`, `long_term_goal`, `short_term_goal`

**组织 (organization) 额外字段**:
`resources`, `internal_factions`, `territorial_control`, `public_stance`, `strategic_goal`, `conflict_targets`

**关系 (relationship) 额外字段**:
`history`, `power_dynamic`, `trust_level`, `conflict_trigger`, `stability_forecast`, `last_action`

### NarrativeEntityArchive 数据类

```python
@dataclass
class NarrativeEntityArchive:
    entity_uuid: str
    entity_name: str
    entity_type: str
    agent_kind: str                    # character / organization / relationship
    importance_tier: str
    recommended_importance_tier: str
    selected_importance_tier: str
    template_key: str
    template_version: str
    template_sections: List[str]
    template_payload: Dict[str, Any]
    template_metadata: Dict[str, Any]
    entity_role: str
    core_drive: str
    surface_mask: str
    hidden_tension: str
    relationship_summary: str
    agent_behavior_hint: str
    human_ai_relation_tag: str
    notable_risks: List[str]
    can_act_as_agent: bool = True
```

**LLM 参数**: temperature=0.4, max_tokens=1600

---

## 7. Writer Agent 提示词

**文件**: `backend/app/services/writer_agent/prompts.py`

Writer Agent（写作工作台的 Agent Loop）支持以下任务类型：

### write_scene 任务简报结构

```json
{
  "task": "write_scene",
  "pov": {
    "name": "str - POV 角色",
    "profile_summary": "str",
    "core_drive": "str",
    "surface_mask": "str",
    "hidden_tension": "str",
    "speech_style": "str",
    "key_details": "str"
  },
  "involved_characters": [
    {
      "name": "str",
      "profile_summary": "str",
      "core_drive": "str",
      "hidden_tension": "str",
      "key_details": "str"
    }
  ],
  "relationships": [
    {
      "between": "str",
      "summary": "str (包含 trust, power, conflict)"
    }
  ],
  "scene_context": "str - 场景背景",
  "recent_narrative": "str - 保留原文，不缩写",
  "setting_details": "str - 场景设定",
  "open_threads": ["str - 未解决线索"],
  "constraints": ["str - 约束条件"],
  "user_instruction": "str - 用户指令",
  "scene_focus": "str - 场景焦点"
}
```

### continue 任务简报（在 write_scene 基础上增加）

```json
{
  "continuation_context": {
    "tail_text": "str - 最后 500 字",
    "narrative_note": "str - 叙事提示",
    "last_location": "str - 最后位置"
  },
  "continue_from": "str - 续写起点"
}
```

### 其他任务类型

| 任务 | 说明 |
|------|------|
| `rewrite` | 重写选定内容 |
| `expand` | 扩展选定内容 |
| `outline` | 生成章节大纲 |
| `consistency_check` | 场景一致性检查 |

### 写作 6 步流程

1. 确认 POV 角色状态和位置
2. 检查待延续事实和风险
3. 规划场景节拍
4. 以 POV 角色的感知写作
5. 保持对话与角色语言习惯一致
6. 留下至少一个悬念或线索

---

## 8. Draft Agent 多代理流水线

**文件**: `backend/app/services/agents/draft/`

### 流水线阶段

```
ContextAgent → MemoryAgent → StyleAgent → WriterAgent → ReviewerAgent
```

最大修订轮次：`MAX_REVISION_ROUNDS = 2`

### ContextAgent 输出

```json
{
  "must_know": [{"...必须知道的上下文"}],
  "should_know": [{"...应该知道的上下文"}],
  "warnings": [{"...风险提示"}],
  "scene_candidates": [{"...候选场景"}],
  "context_scope": {},
  "continuity_anchor": {
    "chapter_summaries": [{"...章节摘要"}],
    "prev_chapter_ending": "str",
    "open_threads": ["str"],
    "timeline_note": "str"
  },
  "history_recall": {}
}
```

### MemoryAgent 输出

```json
{
  "character_profile": {
    "name": "str",
    "status|role": "str",
    "traits|drive": "str",
    "description|tension": "str"
  },
  "memories": [
    {
      "type": "str (goal|preference|promise|relationship|strategy|fact)",
      "summary": "str",
      "salience": "float"
    }
  ],
  "relationships": [
    {
      "source": "str",
      "target": "str",
      "note": "str"
    }
  ],
  "rendered_context": "str - 渲染后的上下文文本"
}
```

### StyleAgent 输出

```json
{
  "dialogue_ratio": "float (0-1) - 对话占比",
  "avg_sentence_length": "float - 平均句长",
  "rhythm": "短促紧凑 | 均匀适中 | 绵长舒展",
  "pov_person": "str - 叙事人称",
  "sample_length": "int - 样本长度",
  "rendered_hints": "str - 渲染后的风格提示"
}
```

### WriterAgent

**系统提示词要求**：
- 仅输出小说正文，不包含元数据/注释
- 匹配原文风格、节奏、人称
- 遵循"必须延续的事实"约束
- 尊重"风险提示"警告
- 动作需遵循因果逻辑
- 过滤 `<think>...</think>` 标签

**LLM 参数**: temperature=0.8, max_tokens=8192

### ReviewerAgent 输出

```json
{
  "pass": "bool",
  "score": "0-100",
  "issues": [
    {
      "dimension": "continuity | character_consistency | thread_management | style_consistency",
      "severity": "high | medium | low",
      "description": "str",
      "suggestion": "str"
    }
  ],
  "keep": ["str - 值得保留的亮点"],
  "overall_assessment": "str - 总评"
}
```

**通过标准**: score >= 70 且无 high severity issue

**4 个审查维度**:

| 维度 | 说明 |
|------|------|
| `continuity` | 开场/角色状态与上下文对齐 |
| `character_consistency` | 动机一致性 |
| `thread_management` | 情节线索处理 |
| `style_consistency` | 人称/节奏一致性 |

**LLM 参数**: temperature=0.2, max_tokens=3072

### Orchestrator SSE 事件

| 事件类型 | 说明 |
|----------|------|
| `agent_status` | Agent 进度 (running/done/error) |
| `text_chunk` | 生成的文本片段 |
| `context_ready` | 上下文组装完成 |
| `done` | 最终结果（含 review） |

---

## 9. Agent 记忆系统

**文件**: `backend/app/services/agents/memory/`

### 核心常量

```python
SESSION_LIMIT = 6       # 短期记忆上限
LONG_TERM_LIMIT = 6     # 长期记忆上限
PROMOTABLE_TYPES = {"goal", "preference", "promise", "relationship", "strategy"}
```

### 记忆来源与默认属性

| 来源 (source_kind) | memory_type | salience | summary 格式 |
|---------------------|-------------|----------|--------------|
| `dialogue` | 自动检测 | 0.55 | `对话提及"...", 回应重点: ...` |
| `action_queued` | strategy | 0.70 | `计划执行动作: ...` |
| `action_applied` | fact | 0.82 | `已执行动作: ...` |
| `state_change` | fact | 0.60 | `状态更新为 ..., 原因: ...` |

### EpisodicMemoryStore（短期记忆）字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `memory_id` | str | `mem_{uuid[:16]}` |
| `session_id` | str | 会话 ID |
| `branch_id` | str | 分支 ID |
| `agent_id` | str | Agent ID |
| `archive_id` | str | 档案 ID |
| `memory_type` | str | 记忆类型 |
| `summary` | str | 摘要 |
| `detail_json` | JSON | 详细数据 |
| `source_kind` | str | dialogue / action_queued / action_applied / state_change |
| `source_ref_id` | str | 来源引用 |
| `normalized_subject` | str | 归一化主题 |
| `salience` | float | 显著性 |
| `created_at` | str | ISO 时间戳 |

### LongTermMemoryStore（长期记忆）

**记忆层级**: `candidate` → `canon`

**记忆状态**: `active`, `superseded`, `rejected`

**提升流程**: candidate 记忆通过 promote 操作升级为 canon；同类型+主题的旧记忆自动标记为 superseded。

### Writer Memory Summary 分桶

| 桶 | 包含的 memory_type | 上限 |
|----|---------------------|------|
| `recent_commitments` | promise | 3 |
| `active_strategies` | strategy, goal | 3 |
| `relationship_tensions` | relationship | 3 |
| `identity_constraints` | 其他 | 3 |

**类型优先级**: promise(0) > strategy(1) > relationship(2) > goal(3) > preference(4) > fact(5)

---

## 10. Sequential Reader 提示词

**文件**: `backend/app/services/sequential_reader_prompts.py`

### SEGMENT_READING_SYSTEM_PROMPT（逐段阅读）

LLM 输出 JSON 结构：

```json
{
  "segment_summary": "150-300 字：[承接][推进][悬念]",
  "character_updates": [
    {
      "name": "str",
      "aliases": ["str"],
      "status": "alive | dead | injured | missing | unknown",
      "identity": "str",
      "personality_traits": ["str"],
      "speech_style": "str",
      "verbal_habits": ["str"],
      "emotional_state": "str",
      "power_position": "str",
      "goals": ["str"],
      "key_actions": ["str"],
      "knowledge_gained": ["str"],
      "quote_examples": ["str (30-80字, 保留原文语气)"],
      "first_seen": "str (segment_id 或空)"
    }
  ],
  "relationship_changes": [
    {
      "source": "str",
      "target": "str",
      "relation": "盟友 | 对立 | 师徒 | 背叛 | 重逢 | 合作 | 暧昧 | 其他",
      "previous_state": "str",
      "trigger": "str",
      "evidence": "str (15-80字)",
      "emotional_shift": "亲近 | 疏远 | 敌对 | 暧昧 | 信任增长 | 信任破裂 | 无变化",
      "power_shift": "上风 | 下风 | 平衡 | 无变化"
    }
  ],
  "plot_threads": [
    {
      "thread": "str",
      "status": "open | progressed | resolved",
      "detail": "str",
      "resolution_detail": "str (resolved 时填写)"
    }
  ],
  "world_building": [
    {
      "fact": "str - 精确规则",
      "evidence": "str (10-30字)"
    }
  ],
  "consistency_notes": ["str - 一致性备注"],
  "narrative_phase": "序章 | 铺垫 | 升级 | 高潮 | 转折 | 收束 | 尾声"
}
```

### ARC_SUMMARY_SYSTEM_PROMPT（弧摘要，每 5 段生成）

```json
{
  "arc_summary": "~800 字整合摘要",
  "character_arcs": [
    {"name": "str", "change": "str"}
  ],
  "relationship_shifts": [
    {"source": "str", "target": "str", "shift": "str"}
  ],
  "threads_resolved": ["str"],
  "threads_opened": ["str"],
  "world_rules_introduced": ["str"]
}
```

### VOLUME_SUMMARY_SYSTEM_PROMPT（卷摘要）

```json
{
  "volume_summary": "~2000 字，整合所有 arc 摘要"
}
```

---

## 11. Story Ontology 提示词

**文件**: `backend/app/services/story_ontology_generator.py`

### LLM 输出结构

```json
{
  "entity_types": [
    {
      "name": "PascalCase",
      "description": "str - 故事演化中的角色",
      "attributes": [
        {
          "name": "snake_case",
          "type": "text | number | enum | boolean",
          "description": "str - 如何影响情节模拟"
        }
      ],
      "examples": ["str - 来自原文"]
    }
  ],
  "edge_types": [
    {
      "name": "UPPER_SNAKE_CASE",
      "description": "str",
      "source_targets": [
        {"source": "str", "target": "str"}
      ],
      "attributes": []
    }
  ],
  "analysis_summary": "100-200 字核心叙事结构",
  "story_focus": ["str - 可追踪的叙事轴"]
}
```

### 约束条件

- entity_types: 6-10 个
- edge_types: 6-10 个
- 必须包含 Character, Organization, Faction, PlotEvent 变体
- 每个 entity_type 至少 2 个 attributes
- 若存在 AI/系统角色，需创建专属 entity type
- examples 仅限来自给定素材

---

## 12. LLM 参数汇总

| 模块 | Temperature | Max Tokens | Module Key | 用途 |
|------|------------|------------|------------|------|
| Character Agent Profile | 0.3 | 4096 | `character_agent_profile` | 结构化角色档案生成 |
| Worldline Action Proposal | 0.6 | 500 | — | 角色动作提案 |
| Worldline Dialogue | 0.7 | 900 | — | 角色对话回复 |
| Draft Writer Agent | 0.8 | 8192 | — | 正文生成 |
| Draft Reviewer Agent | 0.2 | 3072 | — | 一致性审查 |
| Narrative Entity Archivist | 0.4 | 1600 | — | 实体档案生成 |
| Sequential Reader | — | — | `sequential_reading` | 逐段深度阅读 |
| Story Ontology | — | — | `ontology_generation` | 故事本体生成 |

---

## 13. 数据流总览

```
┌─────────────────────────────────────────────────────────────┐
│                     Seed Pipeline                           │
│                                                             │
│  上传小说 → 文件解析 → 智能分段                                │
│       → Sequential Reader (逐段 LLM 阅读)                   │
│           ├─ Segment Reading → 角色/关系/线索/世界观           │
│           ├─ Arc Summary (每5段) → 弧摘要                    │
│           └─ Volume Summary → 卷摘要                         │
│       → Global Integration → seed_analysis.json              │
│       → Story Ontology → entity_types + edge_types           │
│       → Character Agent Profiles → 角色 Agent 档案            │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Graph & Archive Pipeline                   │
│                                                             │
│  Reading Notes → Graph Adapter → Story Memory Builder        │
│       → Graph Construction (并发) → story_graph.json/sqlite  │
│       → Archive Candidate Builder                            │
│       → Narrative Entity Archivist (LLM)                     │
│           → NarrativeEntityArchive                           │
│       → Archive Library (SQLite 持久化)                       │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Worldline System                           │
│                                                             │
│  Session Prepare → Agent Registry                            │
│       ├─ Character Agent (对话/动作提案)                      │
│       ├─ Organization Agent                                  │
│       └─ Relationship Agent                                  │
│  Agent Memory: Episodic Store ←→ Long-Term Store             │
│       (dialogue → strategy → canon promotion)                │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Writer Pipeline                           │
│                                                             │
│  Writer Workbench (Agent Loop + Tool Use)                    │
│       → Draft Orchestrator:                                  │
│           ContextAgent → MemoryAgent → StyleAgent            │
│           → WriterAgent (streaming) → ReviewerAgent          │
│       → Scene/Chapter/Manuscript 管理                        │
└─────────────────────────────────────────────────────────────┘
```
