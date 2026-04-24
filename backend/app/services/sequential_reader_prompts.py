"""
sequential_reader_prompts.py — LLM prompt templates for SequentialReader.

Three prompt sets:
1. SEGMENT_READING — per-segment deep analysis.
2. ARC_SUMMARY — consolidate N segment summaries into one arc summary.
3. VOLUME_SUMMARY — consolidate M arc summaries into one volume summary.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SEGMENT_READING_SYSTEM_PROMPT = """你是一名专业的小说分析师，正在顺序精读一部小说。

你会收到：
1. 当前已知的故事背景摘要（前情上下文）
2. 本段正文内容

请仔细阅读正文，输出一个严格有效的 JSON 对象，不要包含任何额外解释、不要用 markdown 代码块包裹。

JSON 结构必须严格遵循以下格式：

{
  "segment_summary": "150-300字概括本段核心事件，采用三段式：[承接]前情如何引发本段开局，[推进]本段发生了什么关键事件，[悬念]段末留下哪些未解问题",
  "character_updates": [
    {
      "name": "角色全名",
      "aliases": ["外号或其他称谓"],
      "status": "alive / dead / injured / missing / unknown",
      "identity": "身份描述（首次出现时填写）",
      "personality_traits": ["性格特征"],
      "speech_style": "语言风格简述（包括常用句式、语气词偏好、说话节奏）",
      "verbal_habits": ["口头禅、常用表达、标志性语气词"],
      "emotional_state": "本段中的情绪状态简述",
      "power_position": "本段中相对其他角色的权力/地位表现",
      "goals": ["当前目标"],
      "key_actions": ["本段重要行动"],
      "knowledge_gained": ["本段获得的关键信息"],
      "quote_examples": ["原文对话或内心独白引用，30-80字，保留语气词和标点，完整摘录"],
      "first_seen": "首次出现段落ID（首次出现时填写，否则留空字符串）"
    }
  ],
  "relationship_changes": [
    {
      "source": "主动方角色名",
      "target": "被动方角色名",
      "relation": "关系类型（盟友/对立/师徒/背叛/重逢/合作/暧昧/其他）",
      "previous_state": "之前关系状态（若已知）",
      "trigger": "导致关系变化的事件",
      "evidence": "原文佐证，15-80字",
      "emotional_shift": "情感变化方向（亲近/疏远/敌对/暧昧/信任增长/信任破裂/无变化）",
      "power_shift": "权力动态变化（上风/下风/平衡/无变化）"
    }
  ],
  "co_occurrence": [
    {
      "a": "角色A",
      "b": "角色B",
      "scene": "本段中两人同场出现的简短场景描述（10-40字）",
      "interaction_type": "互动类型（对话/合作/冲突/旁观/共处/其他）"
    }
  ],
  "organization_dynamics": [
    {
      "organization": "组织名称",
      "event": "组织在本段中的动态/变化（10-60字）",
      "members_involved": ["参与的角色名"]
    }
  ],
  "location_state_changes": [
    {
      "location": "地点名称",
      "change": "地点的状态/氛围/控制权变化（10-60字）"
    }
  ],
  "plot_threads": [
    {
      "thread": "线索名称",
      "status": "open / progressed / resolved",
      "detail": "线索当前状态描述",
      "resolution_detail": "若 status 为 resolved，记录解决方式和结果（否则留空字符串）"
    }
  ],
  "world_building": [
    {
      "fact": "世界观规则或设定（精确、可引用）",
      "evidence": "原文来源，10-30字"
    }
  ],
  "consistency_notes": ["本段出现的前后矛盾或逻辑疑点（如无则留空列表）"],
  "narrative_phase": "当前叙事阶段（序章/铺垫/升级/高潮/转折/收束/尾声）"
}

## 输出示例（仅展示关键字段，实际输出需包含全部字段）

【小说片段】
"林策推门而入，沈无双已等候多时。'你来晚了。'她语气冷淡。林策淡淡一笑：'路上遇刺。'"

【期望输出摘录】
{
  "segment_summary": "[承接] 林策依约赴会。[推进] 林策迟到并坦言路上遭遇刺杀，沈无双语气虽冷却未深究。[悬念] 刺客身份与幕后指使尚未揭开。",
  "character_updates": [
    {"name": "林策", "status": "alive", "key_actions": ["遭遇刺杀", "如约赴会"], "quote_examples": ["路上遇刺。"]},
    {"name": "沈无双", "status": "alive", "personality_traits": ["冷峻"], "quote_examples": ["你来晚了。"]}
  ],
  "relationship_changes": [
    {"source": "沈无双", "target": "林策", "relation": "盟友", "trigger": "约定会面", "evidence": "沈无双等候多时未离开", "emotional_shift": "无变化", "power_shift": "平衡"}
  ],
  "co_occurrence": [
    {"a": "林策", "b": "沈无双", "scene": "约定地点夜会", "interaction_type": "对话"}
  ]
}

注意：
- 只分析本段正文，不要臆造未出现的内容
- character_updates 只包含本段出现或被提及的角色
- 如本段角色匹配【已知实体表】中的 canonical 名或别名，**name 字段必须填 canonical 名**，新发现的别名追加到 aliases；不要为同一实体创建新条目
- **relationship_changes 必须列出本段所有有文本证据的互动关系**，包括：主角与配角、配角与配角、短暂同场的对手。只要有一句对话、一个动作、或一次明确的态度表露作为依据，就应记录。要求是"有文本证据"而非"戏份充足"——宁可把配角之间的短暂互动也记下，也不要漏掉。只有当本段完全是独白 / 景物描写 / 世界观陈述且毫无互动时，才返回空数组。
- **co_occurrence 记录本段所有同场出现且至少有一次动作/对话接触的角色对**（含配角之间）；纯背景提及不算
- organization_dynamics / location_state_changes 如无内容请留空数组 []
- 所有字符串字段必须是字符串，不能为 null"""


ARC_SUMMARY_SYSTEM_PROMPT = """你是一名小说分析师，需要将多段阅读摘要整合为一个结构化弧线摘要。

你会收到：
1. 当前已知的故事核心设定（可选，可能为空）
2. 若干段落摘要（按顺序排列）

请将这些段落摘要整合为结构化弧线分析，输出严格有效的 JSON 对象：

{
  "arc_summary": "约800字的弧线整合摘要，聚焦核心冲突、角色成长、开端→发展→结尾/悬念、对后续的铺垫",
  "key_events": [
    {
      "event_id": "ev_01",
      "title": "事件标题（10-25字，能独立识别该事件）",
      "description": "事件正文描述（80-200字）：起因、经过、结果、影响",
      "participants": ["参与角色名（含配角，至少 2 人）"],
      "chapter_hint": "事件大致发生的章节/段落标识（若已知）",
      "consequence": "对后续剧情的影响（30-80字）"
    }
  ],
  "character_arcs": [
    {"name": "角色名", "change": "本弧线中角色的变化/成长/转折"}
  ],
  "relationship_shifts": [
    {"source": "角色A", "target": "角色B", "shift": "关系变化描述"}
  ],
  "threads_resolved": ["本弧线中解决的伏笔线索名称"],
  "threads_opened": ["本弧线中新开启的伏笔线索名称"],
  "world_rules_introduced": ["本弧线中首次揭示的世界观规则"]
}

## 输出示例（3 段输入摘要 → 弧线输出摘录）

【输入摘要】
[seg_001] 林策与沈无双在听风楼立约，约定铲除陆君言。
[seg_002] 二人潜入陆府密室，盗取三十七人名册。
[seg_003] 名册曝光，陆君言反扑，沈无双重伤撤退。

【期望输出摘录】
{
  "arc_summary": "本弧线围绕\"潜入陆府\"展开...（约800字）",
  "key_events": [
    {"event_id": "ev_01", "title": "夜会结盟", "description": "林策与沈无双于听风楼定约...", "participants": ["林策", "沈无双"], "consequence": "联盟正式形成"},
    {"event_id": "ev_02", "title": "潜入密室", "description": "二人深夜入陆府...", "participants": ["林策", "沈无双"], "consequence": "获取三十七人名册"},
    {"event_id": "ev_03", "title": "反扑负伤", "description": "陆君言识破后反击...", "participants": ["陆君言", "沈无双"], "consequence": "沈无双重伤撤退"}
  ],
  "character_arcs": [{"name": "沈无双", "change": "从冷静策划者到身负重伤的复仇者"}],
  "threads_opened": ["陆君言的反扑"]
}

注意：
- key_events 列出本弧线中确有的关键事件（通常 3-7 条；若本弧线事件较少，可少于 3 条，**宁少勿编**）；title ≠ description；participants 必须列出真实参与者（含配角）
- relationship_shifts 优先记录配角之间、阵营内部的关系变动；主角参与的关系变动不强制配额
- character_arcs 只包含本弧线中有显著变化的角色
- 如果某个数组为空，输出空数组 []
- 不要包含任何额外解释"""


VOLUME_SUMMARY_SYSTEM_PROMPT = """你是一名小说分析师，需要将多个弧线摘要整合为一个卷摘要。

你会收到若干弧线摘要（按顺序排列）。

请将这些弧线摘要整合为结构化卷摘要，输出严格有效的 JSON 对象，不要包含任何额外解释：

{
  "volume_summary": "约2000字的卷整合摘要，聚焦本卷主题、主要角色弧线、世界格局演变、本卷在全书中的承上启下作用",
  "theme": "本卷核心主题（一句话，30-60字，概括本卷在全书中的位置和母题）",
  "main_arcs": [
    {"character": "角色名", "arc": "本卷中该角色贯穿性的成长/转折/抉择"}
  ],
  "faction_changes": [
    {"faction": "势力/组织名", "change": "本卷中该势力地位/格局/路线的变化"}
  ],
  "cross_volume_threads": [
    "本卷未解决、需在后续卷继续推进的关键线索"
  ]
}

## 输出示例（3 个弧线摘要 → 卷输出摘录）

【输入弧线】
[arc_001] 林策与沈无双结盟潜入陆府失败，沈无双重伤。
[arc_002] 林策为救沈无双投奔白泽司，发现陆君言与朝廷勾结。
[arc_003] 林策反间计成功，陆君言被罢官，但白泽司主君另有图谋。

【期望输出摘录】
{
  "volume_summary": "本卷围绕\"林策对抗陆君言\"的明线展开...（约 2000 字）",
  "theme": "本卷以\"信任与利用\"为母题，林策从孤身复仇到借势制敌，揭示朝堂背后的更大棋盘。",
  "main_arcs": [
    {"character": "林策", "arc": "从孤身复仇者成长为懂得借势的政治玩家"},
    {"character": "沈无双", "arc": "重伤后从行动派转为林策的智囊"}
  ],
  "faction_changes": [
    {"faction": "陆党", "change": "陆君言被罢官，陆党在朝中势力大幅削弱"},
    {"faction": "白泽司", "change": "在本卷崛起为新的隐形棋手，但主君图谋未明"}
  ],
  "cross_volume_threads": ["白泽司主君的真实意图", "三十七人名册剩余成员的下落"]
}

注意：
- volume_summary 力求 1500-2500 字，覆盖本卷整体脉络
- theme 必须是一句话，避免泛化（如\"成长与救赎\"过于空泛）
- main_arcs 只列本卷中有显著弧线变化的角色（通常 2-5 个，**宁少勿编**）
- faction_changes 列本卷中地位/路线确有变化的组织（无则空数组）
- cross_volume_threads 列后续卷需要继续推进的悬念（无则空数组）
- 所有数组字段如无内容，请输出空数组 []，不要省略字段"""


# ---------------------------------------------------------------------------
# Prompt builder functions
# ---------------------------------------------------------------------------

def build_segment_reading_prompt(
    context: str,
    segment_text: str,
    known_entities: Optional[Dict[str, List[str]]] = None,
) -> List[Dict[str, str]]:
    """Build messages for per-segment LLM analysis.

    Parameters
    ----------
    context:
        Assembled reading notes context from ReadingNotesManager.assemble_context().
        May be empty string for the first segment.
    segment_text:
        The raw text of the current segment (joined chapter contents).
    known_entities:
        Optional ``{canonical_name: [aliases]}`` mapping from
        ``ReadingNotesManager.canonical_entity_table()``. When non-empty, an
        explicit "known entity table" block is injected into the user message
        so the LLM uses canonical names instead of creating duplicate records.

    Returns
    -------
    list
        [{"role": "system", ...}, {"role": "user", ...}]
    """
    sections: List[str] = []

    if context.strip():
        sections.append(f"【前情上下文】\n{context}")

    if known_entities:
        entity_lines = []
        for canonical, aliases in known_entities.items():
            if aliases:
                entity_lines.append(f"- {canonical}（别名：{', '.join(aliases)}）")
            else:
                entity_lines.append(f"- {canonical}")
        sections.append(
            "【已知实体表】（本段如出现以下实体，请使用 canonical 名而非创建新实体；"
            "新别名追加到对应 aliases 字段）\n" + "\n".join(entity_lines)
        )

    if context.strip() or known_entities:
        sections.append(f"【本段正文】\n{segment_text}")
    else:
        sections.append(f"【本段正文（首段，暂无前情）】\n{segment_text}")

    user_content = "\n\n".join(sections)

    return [
        {"role": "system", "content": SEGMENT_READING_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_arc_summary_prompt(
    core_facts_context: str,
    segment_summaries: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Build messages for arc summary generation.

    Parameters
    ----------
    core_facts_context:
        Brief core-facts block (characters, world rules) for grounding.
    segment_summaries:
        List of {"segment_id": ..., "summary": ...} dicts to consolidate.
    """
    summaries_text = "\n\n".join(
        f"[{entry['segment_id']}] {entry['summary']}"
        for entry in segment_summaries
    )
    if core_facts_context.strip():
        user_content = (
            f"【核心设定参考】\n{core_facts_context}\n\n"
            f"【各段摘要】\n{summaries_text}"
        )
    else:
        user_content = f"【各段摘要】\n{summaries_text}"

    return [
        {"role": "system", "content": ARC_SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_volume_summary_prompt(arc_summaries: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Build messages for volume summary generation.

    Parameters
    ----------
    arc_summaries:
        List of {"arc_id": ..., "summary": ...} dicts.
    """
    arcs_text = "\n\n".join(
        f"[{entry['arc_id']}] {entry['summary']}"
        for entry in arc_summaries
    )
    return [
        {"role": "system", "content": VOLUME_SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": f"【各弧线摘要】\n{arcs_text}"},
    ]
