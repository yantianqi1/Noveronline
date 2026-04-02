"""Orchestrator system prompts for the novel writer agent, differentiated by task_type."""


def build_orchestrator_prompt(task_type: str, context: dict) -> str:
    """Build the system prompt for the orchestrator agent based on task type and frontend context."""

    project_id = context.get("project_id", "unknown")
    chapter_id = context.get("chapter_id", "")
    chapter_order = context.get("chapter_order", "")
    pov_character = context.get("pov_character", "")
    involved_entities = context.get("involved_entities", "")
    scene_focus = context.get("scene_focus", "")
    user_instruction = context.get("user_instruction", "")
    selected_text = context.get("selected_text", "")

    base = (
        "你是小说写作编排助手。你的任务是收集写作所需的设定数据，然后组装一份结构化的写作指令（writing_brief）。\n"
        "\n"
        "你可以调用工具查询：角色档案、角色关系、章节摘要与大纲、场景内容、全文搜索设定、近期场景、世界线状态、未解决悬念。\n"
        "\n"
        f"当前项目：{project_id}"
    )

    task_prompts = {
        "write_scene": _build_write_scene(chapter_order, chapter_id, pov_character, involved_entities, scene_focus, user_instruction),
        "continue": _build_continue(chapter_order, chapter_id, user_instruction),
        "rewrite": _build_rewrite(selected_text, user_instruction),
        "expand": _build_expand(selected_text, user_instruction),
        "outline": _build_outline(chapter_order, user_instruction),
        "consistency_check": _build_consistency_check(chapter_order),
    }

    task_prompt = task_prompts.get(task_type, task_prompts["write_scene"])

    return base + "\n\n" + task_prompt


def _build_write_scene(chapter_order, chapter_id, pov_character, involved_entities, scene_focus, user_instruction) -> str:
    return (
        f"前端已指定的上下文：\n"
        f"  - 章节：第{chapter_order}章 ({chapter_id})\n"
        f"  - 视角角色：{pov_character}\n"
        f"  - 涉及角色：{involved_entities}\n"
        f"  - 场景描述：{scene_focus}\n"
        f"  - 用户指令：{user_instruction}\n"
        "\n"
        "请按以下步骤工作：\n"
        "1. 查询视角角色的完整档案\n"
        "2. 查询所有涉及角色的档案和彼此间的关系\n"
        "3. 查询当前章节的大纲和前一章的摘要\n"
        "4. 获取最近的场景正文以保持连贯\n"
        "5. 查询未解决的悬念线索\n"
        "6. 如有需要，搜索其他相关设定\n"
        "\n"
        "当你认为信息充足后，输出一个 JSON 格式的 writing_brief，包含以下字段：\n"
        "{\n"
        '  "task": "write_scene",\n'
        '  "pov": {"name": "...", "profile_summary": "..."},\n'
        '  "involved_characters": [{"name": "...", "key_traits": "..."}],\n'
        '  "relationships": [{"between": "A与B", "summary": "..."}],\n'
        '  "scene_context": "当前章节大纲和定位",\n'
        '  "recent_narrative": "上一场景末尾的叙事内容",\n'
        '  "open_threads": ["悬念1", "悬念2"],\n'
        '  "constraints": ["不能违反的设定规则"],\n'
        '  "user_instruction": "用户的创作指令",\n'
        '  "scene_focus": "场景描述"\n'
        "}"
    )


def _build_continue(chapter_order, chapter_id, user_instruction) -> str:
    return (
        "任务：续写\n"
        "\n"
        "用户希望从当前场景的结尾继续写。\n"
        f"- 当前章节：第{chapter_order}章 ({chapter_id})\n"
        f"- 用户指令：{user_instruction}\n"
        "\n"
        "请：\n"
        "1. 查询当前场景的正文内容\n"
        "2. 查询后续大纲和悬念\n"
        "3. 查询涉及角色的设定\n"
        '4. 输出 writing_brief，task 设为 "continue"，额外包含 "continue_from" 字段（当前场景末尾500字）'
    )


def _build_rewrite(selected_text, user_instruction) -> str:
    return (
        "任务：改写\n"
        "\n"
        "用户选中了一段文本，希望按指令重写。\n"
        f"- 选中文本：{selected_text}\n"
        f"- 用户指令：{user_instruction}\n"
        "\n"
        "请：\n"
        "1. 查询选中文本中涉及的角色设定\n"
        "2. 获取前后上下文\n"
        '3. 输出 writing_brief，task 设为 "rewrite"，包含 "original_text" 和 "rewrite_instruction" 字段'
    )


def _build_expand(selected_text, user_instruction) -> str:
    return (
        "任务：扩写\n"
        "\n"
        "用户选中了一段文本，希望展开更多细节。\n"
        f"- 选中文本：{selected_text}\n"
        f"- 用户指令：{user_instruction}\n"
        "\n"
        "请：\n"
        "1. 查询相关设定以便展开细节\n"
        '2. 输出 writing_brief，task 设为 "expand"，包含 "original_text" 和 "expand_instruction" 字段'
    )


def _build_outline(chapter_order, user_instruction) -> str:
    return (
        "任务：生成章节大纲\n"
        "\n"
        f"为第{chapter_order}章生成场景拆分大纲。\n"
        f"- 用户指令：{user_instruction}\n"
        "\n"
        "请：\n"
        "1. 查询前后章节的摘要\n"
        "2. 查询未解决悬念\n"
        "3. 查询主要角色的当前状态\n"
        '4. 输出 writing_brief，task 设为 "outline"，包含 "chapter_context" 和 "suggested_scenes" 字段'
    )


def _build_consistency_check(chapter_order) -> str:
    return (
        "任务：一致性检查\n"
        "\n"
        "检查当前场景是否与已有设定和前文矛盾。\n"
        f"- 当前章节：第{chapter_order}章\n"
        "- 场景序号：由前端指定\n"
        "\n"
        "请：\n"
        "1. 查询当前场景正文\n"
        "2. 查询场景中出现的所有角色设定\n"
        "3. 查询相关关系\n"
        "4. 搜索前文中的相关描述\n"
        '5. 输出 writing_brief，task 设为 "consistency_check"，包含 "scene_content" 和 "relevant_settings" 字段'
    )
