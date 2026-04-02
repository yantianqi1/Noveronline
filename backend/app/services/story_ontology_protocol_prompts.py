"""小说本体生成的行协议提示词。"""

from __future__ import annotations


def build_story_ontology_protocol_prompt(task: str) -> str:
    common = (
        "你是一位小说结构分析师和本体设计师。\n"
        "只允许输出行协议，不要输出 JSON，不要输出解释，不要输出代码块。\n"
        "每行一条记录，字段之间使用 | 分隔，字段采用 key=value。不要使用 | 字符。\n"
    )
    rules = {
        "entity_types": (
            "输出 ENTITY_TYPE 记录。\n"
            "ENTITY_TYPE|name=...|description=...|attributes=attr_name:attr_type:attr_desc;attr_name:attr_type:attr_desc|examples=示例A,示例B"
        ),
        "edge_types": (
            "输出 EDGE_TYPE、SUMMARY、FOCUS 记录。\n"
            "EDGE_TYPE|name=...|description=...|source_targets=Character>Organization;Character>Character|attributes=attr_name:attr_type:attr_desc\n"
            "SUMMARY|text=...\n"
            "FOCUS|text=..."
        ),
    }
    return f"{common}{rules[task]}\n如果没有内容，返回空字符串。"
