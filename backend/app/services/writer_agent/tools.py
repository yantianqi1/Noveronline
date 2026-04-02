"""OpenAI function-calling tool definitions for the novel writer agent."""

from __future__ import annotations

NOVEL_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "query_entity",
            "description": "查询角色、组织、物品、地点、技能的档案设定。返回实体的完整 profile 包括核心驱动力、隐藏矛盾、详细设定等。",
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
                            "all",
                        ],
                        "description": "搜索范围，默认 all",
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
                        "description": "截至章节序号（包含该章）",
                    },
                },
                "required": ["up_to_chapter"],
            },
        },
    },
]

TOOL_NAME_SET: set[str] = {t["function"]["name"] for t in NOVEL_TOOLS}
