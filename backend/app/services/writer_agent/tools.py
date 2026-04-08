"""OpenAI function-calling tool definitions for the novel writer agent."""

from __future__ import annotations

NOVEL_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "query_entity",
            "description": "查询角色/组织/物品/地点/技能的档案设定。返回：完整 profile（核心驱动力、隐藏矛盾、说话风格等）+ 关联伏笔线索 + 适用世界规则 + 近期事件时间线。一次调用即可获得该实体的完整上下文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "实体名称或别名",
                    },
                    "entity_type": {
                        "type": "string",
                        "enum": [
                            "character",
                            "organization",
                            "item",
                            "location",
                            "skill",
                        ],
                        "description": "可选，限定实体类型以缩小搜索范围",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_relationship",
            "description": "查询两个实体之间的关系记录，包括关系类型、信任度、权力动态、历史和冲突触发点。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_a": {
                        "type": "string",
                        "description": "第一个实体名称",
                    },
                    "entity_b": {
                        "type": "string",
                        "description": "第二个实体名称",
                    },
                },
                "required": ["entity_a", "entity_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_chapter",
            "description": "查询指定章节的摘要、大纲、悬念线索和时间线。可选择是否包含正文内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_order": {
                        "type": "integer",
                        "description": "章节序号（从 1 开始）",
                    },
                    "include_content": {
                        "type": "boolean",
                        "description": "是否包含章节正文内容，默认 false",
                    },
                },
                "required": ["chapter_order"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_scene",
            "description": "查询指定章节的场景列表，或查询某个具体场景的详细内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_id": {
                        "type": "string",
                        "description": "章节 ID",
                    },
                    "scene_order": {
                        "type": "integer",
                        "description": "可选，场景序号；不提供则返回该章节所有场景列表",
                    },
                },
                "required": ["chapter_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_settings",
            "description": "全文搜索设定资料，跨实体、章节、场景、记忆等范围检索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "scope": {
                        "type": "string",
                        "enum": [
                            "entities",
                            "chapters",
                            "scenes",
                            "memory",
                            "relationships",
                            "threads",
                            "evidence",
                            "timeline",
                            "arcs",
                            "segments",
                            "volumes",
                            "consistency",
                            "all",
                        ],
                        "description": "搜索范围：entities/chapters/scenes/memory/relationships/threads/evidence/timeline/arcs/segments/volumes/consistency/all，默认 all",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量上限，默认 10",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_scenes",
            "description": "获取当前场景之前的 N 个场景，用于保持叙事连贯性。可跨章节回溯。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_id": {
                        "type": "string",
                        "description": "当前章节 ID",
                    },
                    "scene_order": {
                        "type": "integer",
                        "description": "当前场景序号",
                    },
                    "count": {
                        "type": "integer",
                        "description": "回溯场景数量，默认 2",
                    },
                },
                "required": ["chapter_id", "scene_order"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_world_state",
            "description": "获取世界线会话的当前状态，包括 Agent 状态和近期事件。可选按分支过滤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "世界线会话 ID",
                    },
                    "branch_id": {
                        "type": "string",
                        "description": "可选，分支 ID。不提供则返回所有分支数据",
                    },
                    "entity_id": {
                        "type": "string",
                        "description": "可选，限定查询某个实体的状态",
                    },
                },
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_worldline_branches",
            "description": "列出世界线会话的所有分支及其基本信息（标题、核心变化、当前步数、状态）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "世界线会话 ID",
                    },
                },
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_branch_timeline",
            "description": "获取指定分支的事件时间线，按步骤顺序排列。可用于了解该分支的世界演化历史。",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "世界线会话 ID",
                    },
                    "branch_id": {
                        "type": "string",
                        "description": "分支 ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回事件数量上限，默认 20",
                    },
                },
                "required": ["session_id", "branch_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_branch_agent_state",
            "description": "获取指定分支中 Agent 的当前状态。可选限定到某个实体。",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "世界线会话 ID",
                    },
                    "branch_id": {
                        "type": "string",
                        "description": "分支 ID",
                    },
                    "entity_id": {
                        "type": "string",
                        "description": "可选，限定查询某个实体",
                    },
                },
                "required": ["session_id", "branch_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_open_threads",
            "description": "获取截至指定章节的所有未解决伏笔和悬念线索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "up_to_chapter": {
                        "type": "integer",
                        "description": "截至章节序号（包含该章���",
                    },
                },
                "required": ["up_to_chapter"],
            },
        },
    },
    {"type": "function", "function": {"name": "get_character_voice", "description": "获取角色的完整语言风格资料：说话风格、口头禅、经典台词、性格特征，专用于写对话。", "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "角色名"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "query_relationship_timeline", "description": "查询两个角色之间的关系演变时间线，按故事顺序展示每次变化。", "parameters": {"type": "object", "properties": {"entity_a": {"type": "string", "description": "角色A名"}, "entity_b": {"type": "string", "description": "角色B名"}}, "required": ["entity_a", "entity_b"]}}},
    {"type": "function", "function": {"name": "query_character_timeline", "description": "查询角色的事件时间线：行动、状态变化、获得的知识等，按故事顺序排列。", "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "角色名"}, "event_type": {"type": "string", "enum": ["action", "state_change", "knowledge", "emotional", "all"], "description": "事件类型过滤，默认 all"}, "limit": {"type": "integer", "description": "返回数量上限，默认 20"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "query_thread_history", "description": "查询伏笔线索的完整生命周期：开启、推进、解决的全过程。", "parameters": {"type": "object", "properties": {"thread_key": {"type": "string", "description": "伏笔线索名称或关键词"}}, "required": ["thread_key"]}}},
    {"type": "function", "function": {"name": "search_world_rules", "description": "搜索世界观规则及其原文证据链。", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索关键词"}, "limit": {"type": "integer", "description": "返回数量上限，默认 10"}}, "required": ["query"]}}},
    {
        "type": "function",
        "function": {
            "name": "get_story_overview",
            "description": "获取故事全局概览：当前叙事阶段、总段数、叙事弧线摘要、卷册摘要。用于了解故事的宏观结构和进展。",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_arcs": {
                        "type": "boolean",
                        "description": "是否包含叙事弧线摘要，默认 true",
                    },
                    "include_volumes": {
                        "type": "boolean",
                        "description": "是否包含卷册摘要，默认 true",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_segment_summaries",
            "description": "查询逐段精读摘要：每个阅读段落的详细叙事摘要，以及精读过程中发现的设定一致性注释（矛盾/逻辑问题）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "segment_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选，指定段落ID列表（如 ['seg_001', 'seg_005']）。不提供则按顺序返回",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "起始偏移量，默认 0",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回数量上限，默认 30",
                    },
                    "include_consistency_notes": {
                        "type": "boolean",
                        "description": "是否包含一致性注释，默认 true",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_story_ontology",
            "description": "获取故事本体论定义：该故事世界的实体类型（角色、组织、地点等）和关系类型的结构化分类。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["entity_type", "edge_type", "all"],
                        "description": "查询类型：entity_type/edge_type/all，默认 all",
                    },
                },
                "required": [],
            },
        },
    },
    # --- Write tools (incremental world data maintenance) ---
    {
        "type": "function",
        "function": {
            "name": "manage_entity",
            "description": "创建新实体或更新现有实体（角色/组织/物品/地点/技能）的设定。创建时需提供 name、entity_type、summary；更新时只需 name + 要修改的字段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "update"], "description": "操作类型"},
                    "name": {"type": "string", "description": "实体名称"},
                    "entity_type": {"type": "string", "enum": ["character", "organization", "item", "location", "skill"], "description": "实体类型（创建时必填）"},
                    "summary": {"type": "string", "description": "实体简介（创建时必填）"},
                    "core_drive": {"type": "string", "description": "核心驱动力"},
                    "hidden_tension": {"type": "string", "description": "内在矛盾"},
                    "current_objective": {"type": "string", "description": "当前目标"},
                    "aliases": {"type": "array", "items": {"type": "string"}, "description": "别名列表"},
                    "ultimate_goal": {"type": "string", "description": "终极目标"},
                    "surface_mask": {"type": "string", "description": "表面伪装/外在形象"},
                    "values_text": {"type": "string", "description": "价值观"},
                    "fears_text": {"type": "string", "description": "恐惧/弱点"},
                    "decision_pattern": {"type": "string", "description": "决策模式"},
                    "agent_behavior_hint": {"type": "string", "description": "行为提示（供 agent 参考）"},
                },
                "required": ["action", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_thread",
            "description": "创建新伏笔线索，或更新/推进/解决已有伏笔。创建时需提供 thread_key + detail；更新时提供 thread_key + 新状态或补充细节。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "update"], "description": "操作类型"},
                    "thread_key": {"type": "string", "description": "伏笔名称/关键词"},
                    "status": {"type": "string", "enum": ["open", "progressed", "resolved"], "description": "线索状态"},
                    "detail": {"type": "string", "description": "线索详情"},
                    "resolution_detail": {"type": "string", "description": "解决方式（仅 resolved 时使用）"},
                    "chapter_order": {"type": "integer", "description": "关联章节序号"},
                },
                "required": ["action", "thread_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_world_rule",
            "description": "记录或更新世界观规则/设定事实。如果相同规则已存在则更新其证据，否则新建。",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact_text": {"type": "string", "description": "规则/事实描述"},
                    "evidence_snippet": {"type": "string", "description": "原文证据片段"},
                    "chapter_order": {"type": "integer", "description": "出处章节序号"},
                },
                "required": ["fact_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_relationship",
            "description": "创建或更新两个实体之间的关系。若关系已存在则更新提供的字段，否则新建。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_a": {"type": "string", "description": "实体A名称"},
                    "entity_b": {"type": "string", "description": "实体B名称"},
                    "relation_type": {"type": "string", "description": "关系类型（如 师徒、敌对、同盟）"},
                    "description": {"type": "string", "description": "关系描述"},
                    "trust_level": {"type": "number", "description": "信任度（0-1）"},
                    "power_dynamic": {"type": "string", "description": "权力动态"},
                    "conflict_trigger": {"type": "string", "description": "冲突触发点"},
                },
                "required": ["entity_a", "entity_b", "relation_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_character_event",
            "description": "记录角色事件（行动、状态变化、获得知识、情感转变），用于构建角色时间线。写作过程中应主动记录关键角色事件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "角色名称"},
                    "event_type": {"type": "string", "enum": ["action", "state_change", "knowledge", "emotional"], "description": "事件类型"},
                    "summary": {"type": "string", "description": "事件摘要"},
                    "chapter_order": {"type": "integer", "description": "关联章节序号（可选）"},
                },
                "required": ["name", "event_type", "summary"],
            },
        },
    },
]

# Manuscript-specific tools (added to agent toolset during continuation tasks)
MANUSCRIPT_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_manuscript_context",
            "description": (
                "获取已提交稿件的续写上下文：最近段落摘要、活跃伏笔、上一段POV/地点/叙事状态、原文尾部。"
                "按 token 预算自动裁剪，用于保持续写连贯性。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "token_budget": {
                        "type": "integer",
                        "description": "token 预算上限，默认 8000",
                    },
                    "last_block_id": {
                        "type": "string",
                        "description": "从此稿件块末尾续写，如不提供则使用最新块",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_manuscript",
            "description": "在已提交稿件中全文搜索，用于回溯查找特定情节、角色出场、对话等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量上限，默认 10",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_manuscript_stats",
            "description": "获取已提交稿件的概况：总字数、段落数、章节标签列表。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

# ----------------------------------------------------------------------
# Asset library tools (cross-project knowledge: writing styles, world-views,
# character archetypes, prompt templates, etc.)
# ----------------------------------------------------------------------
ASSET_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_assets",
            "description": (
                "在资产库（全局 + 当前项目）中按关键词全文搜索可被 agent 调用的资产，"
                "如写作风格(writing_style)、作家风格(author_style)、世界观(worldview)、"
                "角色原型(character_archetype)、提示词模板(prompt_template)、稿件块(manuscript_block) 等。"
                "只返回已启用 (enabled) 的资产。query 必须 ≥ 3 字符；过短直接报错，"
                "**不会**降级为模糊匹配。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "关键词，至少 3 个字符；FTS5 trigram 严格匹配，过短会显式失败。",
                        "minLength": 3,
                    },
                    "asset_type": {
                        "type": "string",
                        "description": "可选：限定资产类型，例如 writing_style / worldview / character_archetype",
                    },
                    "category": {
                        "type": "string",
                        "description": "可选：限定创作者自定义分类",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["global", "project", "all"],
                        "description": "搜索范围，默认 all（项目+全局合并）",
                    },
                    "limit": {"type": "integer", "description": "返回数量上限，默认 10"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_asset",
            "description": "按 asset_id 取出完整资产内容（content + payload），用于把已搜索到的资产展开到上下文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "description": "资产 ID"},
                },
                "required": ["asset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_assets",
            "description": (
                "列出某一类资产的简表（标题/分类/摘要），便于 agent 先看清单再决定取用哪一条。"
                "默认只列已启用的资产。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_type": {"type": "string", "description": "资产类型"},
                    "category": {"type": "string", "description": "可选：分类过滤"},
                    "scope": {
                        "type": "string",
                        "enum": ["global", "project", "all"],
                        "description": "默认 all",
                    },
                    "limit": {"type": "integer", "description": "默认 30"},
                },
                "required": ["asset_type"],
            },
        },
    },
]

UNIFIED_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "global_search",
            "description": (
                "跨所有数据源做一次全局 FTS5 搜索。返回每条命中的 source / source_ref / "
                "title / 摘要片段。**严格 FTS**：query 不足 3 字符或所有 token 都过短"
                "会直接报错，绝不降级为模糊匹配。\n\n"
                "数据源标识与含义（source 参数取值——只接受英文 key）：\n"
                "  - assets       → 资产库（写作素材：文风/世界观/原型/桥段）\n"
                "  - archive      → 档案库（角色/组织/势力/关系正典档案）\n"
                "  - story_graph  → 故事图谱节点\n"
                "  - novel_db     → 写作工坊（实体/情节线/世界规则/场景）\n"
                "  - worldline    → 世界线推演会话\n"
                "  - seed         → 总览种子流水线产物\n"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "关键词或短语，至少 3 字符；任何 token 过短都会显式报错。",
                        "minLength": 3,
                    },
                    "source": {
                        "type": "array",
                        "description": "可选：限定一个或多个数据源，使用上面表中的英文 key。",
                        "items": {
                            "type": "string",
                            "enum": [
                                "assets",
                                "archive",
                                "story_graph",
                                "novel_db",
                                "worldline",
                                "seed",
                            ],
                        },
                    },
                    "limit": {"type": "integer", "description": "默认 20，上限 100"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_graph_neighbors",
            "description": (
                "查询故事图谱中某个节点（角色/地点/物件）的图邻居：返回该节点信息 + 所有相连边 + 对端节点摘要。"
                "用于挖掘『这个角色身边都有谁、有什么羁绊』。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "节点名称（精确或别名）"},
                    "limit": {"type": "integer", "description": "邻居数量上限，默认 20"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_event",
            "description": (
                "查询故事图谱中的剧情事件节点（PlotEvent）。返回事件标题、正文描述、参与角色、所属弧线、影响。"
                "支持按 event_id 精确查询，或按事件标题做模糊匹配。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "可选：事件 ID（如 arc_001_ev_01）"},
                    "name": {"type": "string", "description": "可选：事件标题或关键词"},
                    "limit": {"type": "integer", "description": "默认 5"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_relationship_network",
            "description": (
                "查询某个角色的一阶关系网络：列出图谱中所有与该角色相连的实体 + 关系类型 + 边权重。"
                "比 query_graph_neighbors 更聚焦于角色↔角色的直接关系，便于写作时快速引用人物羁绊。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "角色名（精确或别名）"},
                    "limit": {"type": "integer", "description": "默认 30"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_worldline_session",
            "description": (
                "查询本项目最近一次（或指定）世界线推演会话的摘要：题目、变量、参与角色、最近事件流。"
                "用于让写作 agent 知道『推演了哪些可能性』，作为续写参考。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "可选：指定 session id；留空则取最近一次"},
                },
            },
        },
    },
]


TOOL_NAME_SET: set[str] = {t["function"]["name"] for t in NOVEL_TOOLS}
MANUSCRIPT_TOOL_NAME_SET: set[str] = {t["function"]["name"] for t in MANUSCRIPT_TOOLS}
ASSET_TOOL_NAME_SET: set[str] = {t["function"]["name"] for t in ASSET_TOOLS}
UNIFIED_TOOL_NAME_SET: set[str] = {t["function"]["name"] for t in UNIFIED_TOOLS}

# Human-readable display formatters for timeline log
TOOL_DISPLAY_FORMATTERS: dict[str, callable] = {
    "query_entity": lambda inp: f"查询角色档案：{inp.get('name', '?')}",
    "query_relationship": lambda inp: f"查询关系：{inp.get('entity_a', '?')} ↔ {inp.get('entity_b', '?')}",
    "query_chapter": lambda inp: f"查询章节：第{inp.get('chapter_order', '?')}章",
    "query_scene": lambda inp: f"查询场景：{inp.get('chapter_id', '?')}" + (f" #{inp['scene_order']}" if inp.get("scene_order") else ""),
    "search_settings": lambda inp: f"搜索设定：{inp.get('query', '?')}",
    "get_recent_scenes": lambda inp: f"获取最近 {inp.get('count', 2)} 个场景",
    "get_world_state": lambda inp: f"查询世界线状态" + (f"（分支 {inp['branch_id']}）" if inp.get("branch_id") else ""),
    "list_worldline_branches": lambda inp: f"列出分支：{inp.get('session_id', '?')}",
    "get_branch_timeline": lambda inp: f"查询分支时间线：{inp.get('branch_id', '?')}",
    "get_branch_agent_state": lambda inp: f"查询分支 Agent 状态：{inp.get('branch_id', '?')}",
    "get_open_threads": lambda inp: f"获取未解决伏笔（至第{inp.get('up_to_chapter', '?')}章）",
    "get_manuscript_context": lambda inp: f"获取稿件续写上下文（预算{inp.get('token_budget', 8000)}" + (f"，锚定{inp['last_block_id']}" if inp.get("last_block_id") else "") + "）",
    "search_manuscript": lambda inp: f"搜索稿件：{inp.get('query', '?')}",
    "get_manuscript_stats": lambda _: "获取稿件概况",
    "get_character_voice": lambda inp: f"获取角色语言风格：{inp.get('name', '?')}",
    "query_relationship_timeline": lambda inp: f"查询关系时间线：{inp.get('entity_a', '?')} ↔ {inp.get('entity_b', '?')}",
    "query_character_timeline": lambda inp: f"查询角色时间线：{inp.get('name', '?')}",
    "query_thread_history": lambda inp: f"查询伏笔历史：{inp.get('thread_key', '?')}",
    "search_world_rules": lambda inp: f"搜索世界观规则：{inp.get('query', '?')}",
    "get_story_overview": lambda inp: "故事全局概览",
    "query_segment_summaries": lambda inp: f"逐段摘要 (offset={inp.get('offset', 0)})",
    "get_story_ontology": lambda inp: f"故事本体论 ({inp.get('kind', 'all')})",
    "manage_entity": lambda inp: f"{'创建' if inp.get('action') == 'create' else '更新'}实体：{inp.get('name', '?')}",
    "manage_thread": lambda inp: f"{'创建' if inp.get('action') == 'create' else '更新'}伏笔：{inp.get('thread_key', '?')}",
    "manage_world_rule": lambda inp: f"记录世界规则：{inp.get('fact_text', '?')[:30]}",
    "manage_relationship": lambda inp: f"管理关系：{inp.get('entity_a', '?')} ↔ {inp.get('entity_b', '?')}",
    "query_event": lambda inp: f"查询事件：{inp.get('event_id') or inp.get('name', '?')}",
    "query_relationship_network": lambda inp: f"查询关系网络：{inp.get('name', '?')}",
    "search_assets": lambda inp: f"搜索资产：{inp.get('query', '?')}" + (f" [{inp.get('asset_type')}]" if inp.get("asset_type") else ""),
    "get_asset": lambda inp: f"取资产：{inp.get('asset_id', '?')}",
    "list_assets": lambda inp: f"列资产：{inp.get('asset_type', '?')}",
}
