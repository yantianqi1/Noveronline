"""
sequential_reader_prompts.py — LLM prompt templates for SequentialReader.

Three prompt sets:
1. SEGMENT_READING — per-segment deep analysis.
2. ARC_SUMMARY — consolidate N segment summaries into one arc summary.
3. VOLUME_SUMMARY — consolidate M arc summaries into one volume summary.
"""
from __future__ import annotations

from typing import Any, Dict, List

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

注意：
- 只分析本段正文，不要臆造未出现的内容
- character_updates 只包含本段出现或被提及的角色
- relationship_changes 只记录本段发生的关系变化
- 所有字符串字段必须是字符串，不能为 null"""


ARC_SUMMARY_SYSTEM_PROMPT = """你是一名小说分析师，需要将多段阅读摘要整合为一个结构化弧线摘要。

你会收到：
1. 当前已知的故事核心设定（可选，可能为空）
2. 若干段落摘要（按顺序排列）

请将这些段落摘要整合为结构化弧线分析，输出严格有效的 JSON 对象：

{
  "arc_summary": "约800字的弧线整合摘要，聚焦核心冲突、角色成长、开端→发展→结尾/悬念、对后续的铺垫",
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

注意：
- character_arcs 只包含本弧线中有显著变化的角色
- 如果某个数组为空，输出空数组 []
- 不要包含任何额外解释"""


VOLUME_SUMMARY_SYSTEM_PROMPT = """你是一名小说分析师，需要将多个弧线摘要整合为一个卷摘要。

你会收到若干弧线摘要（按顺序排列）。

请将这些弧线摘要整合为约 2000 字的卷摘要，聚焦于：
- 本卷的主题与核心议题
- 主要角色贯穿全卷的弧线发展
- 世界观或势力格局的演变
- 本卷在全书中的地位与承上启下作用

输出严格有效的 JSON 对象，不要包含任何额外解释：

{
  "volume_summary": "约2000字的卷整合摘要"
}"""


# ---------------------------------------------------------------------------
# Prompt builder functions
# ---------------------------------------------------------------------------

def build_segment_reading_prompt(context: str, segment_text: str) -> List[Dict[str, str]]:
    """Build messages for per-segment LLM analysis.

    Parameters
    ----------
    context:
        Assembled reading notes context from ReadingNotesManager.assemble_context().
        May be empty string for the first segment.
    segment_text:
        The raw text of the current segment (joined chapter contents).

    Returns
    -------
    list
        [{"role": "system", ...}, {"role": "user", ...}]
    """
    if context.strip():
        user_content = (
            f"【前情上下文】\n{context}\n\n"
            f"【本段正文】\n{segment_text}"
        )
    else:
        user_content = f"【本段正文（首段，暂无前情）】\n{segment_text}"

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
