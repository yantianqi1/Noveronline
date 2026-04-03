"""Prompts for character agent profile generation."""

from __future__ import annotations

from typing import Any, Dict, List


CHARACTER_PROFILE_SYSTEM_PROMPT = """你是一名专业的小说角色 Agent 设定编辑。

请根据提供的角色信息、关系图谱和故事背景，为该角色生成完整的 Agent 人格档案。

硬性要求：
1. 只输出一个合法 JSON 对象，不要包含任何 Markdown 代码块标记、注释或解释。
2. 每个字段必须具体且可执行，禁止空泛套话（如"性格复杂""关系微妙"）。
3. 信息不足时，显式写"暂无记录"或"证据不足"，不要留空字段。
4. 所有数组字段至少包含 1 个元素。
5. 各顶层字段所承载的信息不得重复。

输出 JSON 结构必须严格如下：
{
  "basic_info": {
    "name": "角色主名",
    "aliases": ["别名1", "别名2"],
    "identity": "中文，一句话说明角色在故事中的身份定位",
    "status": "中文，当前状态，如存活/死亡/下落不明"
  },
  "personality": {
    "core_traits": ["中文，核心性格特质1", "中文，核心性格特质2"],
    "values": "中文，角色最优先坚守的价值观或底线",
    "fears": "中文，角色最深的恐惧或禁忌",
    "decision_pattern": "中文，描述该角色在关键抉择时的典型行为倾向"
  },
  "speech": {
    "style": "中文，语言风格，如简洁/迂回/强硬/温柔等",
    "verbal_habits": ["中文，口头禅或习惯用语1"],
    "tone_range": "中文，情绪范围与语气跨度描述",
    "example_quotes": ["中文，典型台词示例1"]
  },
  "relationships": [
    {
      "target": "对象角色名",
      "current_state": "中文，当前关系状态",
      "evolution": "中文，关系演变简述",
      "attitude": "中文，该角色对对象的内心态度"
    }
  ],
  "capabilities": {
    "skills": ["中文，核心能力或手段1"],
    "limitations": ["中文，明显弱点或局限1"],
    "resources": "中文，可调用的资源或势力"
  },
  "knowledge_boundary": {
    "knows": ["中文，角色确认知晓的关键信息1"],
    "does_not_know": ["中文，角色明确不知道的重要信息1"],
    "believes_wrongly": ["中文，角色持有的错误认知1（若无则填暂无记录）"]
  },
  "motivation": {
    "ultimate_goal": "中文，角色的终极目标或深层欲望",
    "current_objective": "中文，当前阶段最优先推进的具体目标",
    "internal_conflict": "中文，内心最主要的矛盾或挣扎"
  }
}
"""


def build_character_profile_prompt(
    character_name: str,
    character_data: Dict[str, Any],
    relationship_entries: List[Dict[str, Any]],
    story_summary: str,
) -> List[Dict[str, str]]:
    """Build messages list for character profile generation.

    Parameters
    ----------
    character_name:
        The character's main name.
    character_data:
        The character dict from ReadingNotesManager (aliases, status, identity,
        personality_traits, speech_style, goals, key_actions, knowledge_gained,
        quote_examples, segments_seen, etc.).
    relationship_entries:
        Filtered list of relationship_graph entries involving this character.
    story_summary:
        A text summary of the story so far (from arc/segment summaries).
    """
    char_lines = [f"角色名：{character_name}"]

    aliases = character_data.get("aliases", [])
    if aliases:
        char_lines.append(f"别名：{', '.join(aliases)}")

    identity = character_data.get("identity", "")
    if identity:
        char_lines.append(f"身份：{identity}")

    status = character_data.get("status", "")
    if status:
        char_lines.append(f"当前状态：{status}")

    traits = character_data.get("personality_traits", [])
    if traits:
        char_lines.append(f"性格特质：{', '.join(traits)}")

    speech_style = character_data.get("speech_style", "")
    if speech_style:
        char_lines.append(f"语言风格：{speech_style}")

    goals = character_data.get("goals", [])
    if goals:
        char_lines.append(f"目标：{'; '.join(goals)}")

    key_actions = character_data.get("key_actions", [])
    if key_actions:
        char_lines.append(f"关键行动：{'; '.join(key_actions[:10])}")

    knowledge_gained = character_data.get("knowledge_gained", [])
    if knowledge_gained:
        char_lines.append(f"已知信息：{'; '.join(knowledge_gained[:10])}")

    quotes = character_data.get("quote_examples", [])
    if quotes:
        char_lines.append(f"台词示例：{'; '.join(quotes[:5])}")

    segs = character_data.get("segments_seen", [])
    char_lines.append(f"出现段落数：{len(segs)}")

    # Relationships
    rel_lines = []
    for entry in relationship_entries[:20]:
        source = entry.get("source", "")
        target = entry.get("target", "")
        relation = entry.get("relation", "")
        trigger = entry.get("trigger", "")
        other = target if source == character_name else source
        rel_lines.append(f"  与 {other}：关系={relation}，触发={trigger}")

    user_content_parts = [
        "=== 角色信息 ===",
        "\n".join(char_lines),
    ]

    if rel_lines:
        user_content_parts.append("\n=== 关系图谱条目 ===")
        user_content_parts.append("\n".join(rel_lines))

    if story_summary:
        user_content_parts.append("\n=== 故事背景摘要 ===")
        user_content_parts.append(story_summary)

    user_content_parts.append(
        f"\n请根据以上信息，为角色「{character_name}」生成完整的 Agent 人格档案 JSON。"
    )

    return [
        {"role": "system", "content": CHARACTER_PROFILE_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(user_content_parts)},
    ]
