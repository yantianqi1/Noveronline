"""块内事实提取的行协议提示词。"""

from __future__ import annotations


def build_local_block_protocol_prompt(task: str) -> str:
    rules = (
        "只允许输出行协议，不要输出 JSON，不要输出解释，不要输出代码块。\n"
        "每行一条记录，字段之间使用 | 分隔，字段格式固定为 key=value。\n"
        "sentence_refs 只能填写输入里出现过的 sentence_id，多个值用英文逗号分隔。\n"
        "任何字段值都不能包含换行。不要使用 | 字符。\n"
    )
    task_format = {
        "events": (
            "输出 EVENT 记录。\n"
            "格式：EVENT|summary=...|characters=角色A,角色B|organizations=组织A|sentence_refs=chapter_0001_s001,chapter_0001_s002"
        ),
        "entities": (
            "输出 ENTITY 记录。\n"
            "格式：ENTITY|name=...|entity_type=character或organization|aliases=别名A,别名B|summary=...|importance_tier=protagonist或major或supporting或minor|sentence_refs=..."
        ),
        "relationships": (
            "输出 REL 记录。\n"
            "格式：REL|source=...|target=...|change=ally或conflict或co_occurrence或mentor或betrayal或reunion|weight=1|sentence_refs=..."
        ),
        "threads": (
            "输出 THREAD 和 SUMMARY 记录。\n"
            "THREAD 格式：THREAD|thread_key=...|status=open或closed|summary=...|sentence_refs=...\n"
            "SUMMARY 格式：SUMMARY|text=...|sentence_refs=..."
        ),
    }
    return (
        "你是一名小说块级事实抽取器。\n"
        "只抽取当前主块章节中可以明确证实的事实，上下文章节只用于理解边界。\n"
        f"{rules}"
        f"{task_format[task]}\n"
        "如果没有内容，返回空字符串，不要编造占位记录。"
    )
