"""单块文风提取的 prompt。返回结构化 JSON。"""

from __future__ import annotations


CHUNK_STYLE_SYSTEM = (
    "你是一名资深小说编辑与文体学专家。给你一段小说原文，"
    "请只针对**写作风格 / 文风**做客观分析，绝不要复述剧情、不要评价人物。"
    "你的输出必须是严格 JSON，不要任何 Markdown 代码块包装。"
)


CHUNK_STYLE_SCHEMA_HINT = """请输出 JSON，字段如下：
{
  "narrative_pov": "叙事视角，如 第一人称限知 / 第三人称全知 / 第三人称紧贴角色 等",
  "tense": "时态：过去时 / 现在时 / 混合",
  "sentence_features": ["短句为主", "长短句交错", "大量主从复合句", "多用排比" 等],
  "rhetoric": ["比喻偏好", "通感", "白描", "象征" 等],
  "pacing": "节奏特征：例如 紧凑、舒缓、留白多、镜头快切",
  "vocabulary": "用词偏好：例如 古雅、口语化、欧化、术语密集",
  "dialogue_style": "对白风格：例如 简洁尖锐、戏剧腔、生活化、内心独白比重高",
  "tone": "总体基调：例如 冷峻克制 / 抒情温暖 / 黑色幽默",
  "distinctive_devices": ["该作者特有的笔法或习惯，例如 大量括号补叙、章末留悬念句"],
  "example_snippets": ["从原文中精选 1-3 个最能代表该风格的短句，原样照抄，不要改动"]
}
仅返回 JSON。"""


def build_chunk_messages(chunk_text: str) -> list[dict]:
    user = (
        f"{CHUNK_STYLE_SCHEMA_HINT}\n\n"
        f"=== 小说原文 ===\n{chunk_text}\n=== 结束 ==="
    )
    return [
        {"role": "system", "content": CHUNK_STYLE_SYSTEM},
        {"role": "user", "content": user},
    ]
