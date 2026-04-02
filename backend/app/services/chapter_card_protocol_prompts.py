"""章节卡生成的行协议提示词。"""

from __future__ import annotations


def build_chapter_card_protocol_prompt(task: str) -> str:
    common = (
        "你是一名小说章节分析师。\n"
        "只允许输出行协议，不要输出 JSON，不要输出解释，不要输出代码块。\n"
        "每行一条记录，字段之间使用 | 分隔，字段采用 key=value。\n"
        "sentence_refs 只能填写输入里出现过的 sentence_id。不要使用 | 字符。\n"
    )
    task_rules = {
        "summary": (
            "输出 SUMMARY 记录。\n"
            "SUMMARY|summary_text=...|start_anchor=...|end_anchor=...|timeline_note=...|sentence_refs=..."
        ),
        "events_threads": (
            "输出 EVENT 和 THREAD 记录。\n"
            "EVENT|summary=...|sentence_refs=...\n"
            "THREAD|thread_key=...|summary=...|sentence_refs=..."
        ),
        "entities_states": (
            "输出 CHAR_STATE、REL_STATE、ENTITY 记录。\n"
            "CHAR_STATE|name=...|state=active或dead或injured或missing|summary=...|sentence_refs=...\n"
            "REL_STATE|source=...|target=...|state=ally或conflict或co_occurrence或mentor或betrayal或reunion|summary=...|sentence_refs=...\n"
            "ENTITY|name=...|entity_type=character或organization或location或artifact或other"
        ),
    }
    return f"{common}{task_rules[task]}\n如果没有内容，返回空字符串。"
