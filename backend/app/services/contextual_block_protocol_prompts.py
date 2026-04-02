"""剧情块分析的行协议提示词。"""

from __future__ import annotations


def build_contextual_block_protocol_prompt(task: str) -> str:
    common = (
        "你是一名小说结构分析师。\n"
        "只允许输出行协议，不要输出 JSON，不要输出解释，不要输出代码块。\n"
        "每行一条记录，字段之间使用 | 分隔，字段采用 key=value。\n"
        "sentence_refs 只能填写输入里出现过的 sentence_id。\n"
        "任何字段值都不能包含换行，不要使用 | 字符。\n"
    )
    task_rules = {
        "plot_summary": "输出 SUMMARY|text=...|sentence_refs=...",
        "state_updates": (
            "输出 CHAR_STATE、REL_STATE、END_STATE 记录。\n"
            "CHAR_STATE|name=...|state=active或dead或injured或missing|sentence_refs=...\n"
            "REL_STATE|source=...|target=...|state=ally或conflict或co_occurrence或mentor或betrayal或reunion|sentence_refs=...\n"
            "END_STATE|focus_characters=角色A,角色B|focus_organizations=组织A|open_threads=线索A,线索B|narrative_momentum=...|summary=...|sentence_refs=..."
        ),
        "thread_updates": "输出 THREAD_UPDATE|thread_key=...|status=open或closed或progressed|summary=...|sentence_refs=...",
    }
    return f"{common}{task_rules[task]}\n如果没有内容，返回空字符串。"
