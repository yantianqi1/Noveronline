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
                            "all",
                        ],
                        "description": "搜索范围：entities/chapters/scenes/memory/relationships/threads/evidence/timeline/all，默认 all",
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
            "description": "获取世界线会话的当前状态，包括 Agent 状态和近期事件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "世界线会话 ID",
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

TOOL_NAME_SET: set[str] = {t["function"]["name"] for t in NOVEL_TOOLS}
MANUSCRIPT_TOOL_NAME_SET: set[str] = {t["function"]["name"] for t in MANUSCRIPT_TOOLS}

# Human-readable display formatters for timeline log
TOOL_DISPLAY_FORMATTERS: dict[str, callable] = {
    "query_entity": lambda inp: f"查询角色档案：{inp.get('name', '?')}",
    "query_relationship": lambda inp: f"查询关系：{inp.get('entity_a', '?')} ↔ {inp.get('entity_b', '?')}",
    "query_chapter": lambda inp: f"查询章节：第{inp.get('chapter_order', '?')}章",
    "query_scene": lambda inp: f"查询场景：{inp.get('chapter_id', '?')}" + (f" #{inp['scene_order']}" if inp.get("scene_order") else ""),
    "search_settings": lambda inp: f"搜索设定：{inp.get('query', '?')}",
    "get_recent_scenes": lambda inp: f"获取最近 {inp.get('count', 2)} 个场景",
    "get_world_state": lambda _: "查询世界线状态",
    "get_open_threads": lambda inp: f"获取未解决伏笔（至第{inp.get('up_to_chapter', '?')}章）",
    "get_manuscript_context": lambda inp: f"获取稿件续写上下文（预算{inp.get('token_budget', 8000)}）",
    "search_manuscript": lambda inp: f"搜索稿件：{inp.get('query', '?')}",
    "get_manuscript_stats": lambda _: "获取稿件概况",
    "get_character_voice": lambda inp: f"获取角色语言风格：{inp.get('name', '?')}",
    "query_relationship_timeline": lambda inp: f"查询关系时间线：{inp.get('entity_a', '?')} ↔ {inp.get('entity_b', '?')}",
    "query_character_timeline": lambda inp: f"查询角色时间线：{inp.get('name', '?')}",
    "query_thread_history": lambda inp: f"查询伏笔历史：{inp.get('thread_key', '?')}",
    "search_world_rules": lambda inp: f"搜索世界观规则：{inp.get('query', '?')}",
    "manage_entity": lambda inp: f"{'创建' if inp.get('action') == 'create' else '更新'}实体：{inp.get('name', '?')}",
    "manage_thread": lambda inp: f"{'创建' if inp.get('action') == 'create' else '更新'}伏笔：{inp.get('thread_key', '?')}",
    "manage_world_rule": lambda inp: f"记录世界规则：{inp.get('fact_text', '?')[:30]}",
    "manage_relationship": lambda inp: f"管理关系：{inp.get('entity_a', '?')} ↔ {inp.get('entity_b', '?')}",
}
