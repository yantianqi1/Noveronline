"""资产入库 Agent prompt 模板。"""

from __future__ import annotations

from ....schemas.asset_types import INGESTIBLE_TYPES


# Back-compat alias: older imports referenced this local name.
SUPPORTED_TYPES = INGESTIBLE_TYPES

INGEST_SYSTEM = (
    "你是「资产入库 Agent」。用户会粘贴一段原始素材，你需要把它转化成"
    "结构化、可被其他写作 Agent 高效检索的资产条目。\n"
    "你必须输出严格的 JSON 对象，包含以下字段：\n"
    "  asset_type: 必须是下列之一: " + ", ".join(SUPPORTED_TYPES) + "\n"
    "  title: 8-30 字的中文标题\n"
    "  summary: 1-3 句中文摘要，概括核心要点\n"
    "  category: 简短分类标签（中文，可选）\n"
    "  tags: 字符串数组，3-8 个关键词\n"
    "  payload: 一个对象，按资产类型抽取结构化字段：\n"
    "    - writing_style: pov, sentence, rhetoric, pacing, vocabulary, dialogue\n"
    "    - worldview: setting, era, locations, factions, conflicts\n"
    "    - character_archetype: name, role, traits, motivations, speech_style\n"
    "    - world_rule: rule_name, statement, scope, exceptions\n"
    "    - plot_template: name, premise, beats, payoff\n"
    "    - prompt_template: purpose, template_text, variables\n"
    "    - note: 自由结构\n"
    "禁止输出 markdown 代码块；只输出原始 JSON。"
)


def build_ingest_messages(raw_text: str, hint_type: str | None = None) -> list[dict]:
    user = "原始素材如下：\n```\n" + raw_text.strip() + "\n```"
    if hint_type:
        user += f"\n用户期望的 asset_type 是 `{hint_type}`，若合理请优先采用。"
    return [
        {"role": "system", "content": INGEST_SYSTEM},
        {"role": "user", "content": user},
    ]
