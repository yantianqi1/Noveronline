"""逐章调用 LLM 生成结构化章节卡。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .llm_router import LlmRouter


SUMMARY_MODULE_KEY = "novel_chapter_summarizer"
MAX_PREVIOUS_CARDS = 3
MAX_CONTEXT_EVENTS = 6
MAX_CONTEXT_THREADS = 6

CHAPTER_CARD_SYSTEM_PROMPT = """你是一名小说章节分析师。

请基于当前章节正文、已有前情摘要、故事记忆与块分析，输出严格有效的 JSON 对象。
不要输出 markdown，不要输出解释，不要省略字段。

JSON 结构必须如下：
{
  "summary_text": "中文，100-220字，概括本章核心推进",
  "start_anchor": "中文，本章开场承接点",
  "end_anchor": "中文，本章结尾留给下一章的承接点",
  "key_events": [{"summary": "中文，关键事件"}],
  "open_threads": [{"thread_key": "线索键", "summary": "中文，未收束线索"}],
  "character_state_updates": [{"name": "角色名", "state": "active/dead/injured/missing", "summary": "中文，状态变化"}],
  "relationship_updates": [{"source": "实体A", "target": "实体B", "state": "ally/conflict/co_occurrence", "summary": "中文，关系变化"}],
  "timeline_note": "中文，时间线注记",
  "key_entities": [{"name": "实体名", "entity_type": "character/organization/location/artifact/other"}]
}
"""


class ChapterCardGenerator:
    """生成完整项目章节卡，或为单章正文生成章节卡。"""

    def __init__(self, llm_router: Optional[LlmRouter] = None):
        self.llm_router = llm_router or LlmRouter()

    def generate_cards(
        self,
        chapters: Sequence[Dict[str, Any]],
        story_memory: Dict[str, Any],
        block_analyses: Dict[str, Any],
        progress_callback=None,
    ) -> Dict[str, Any]:
        cards: List[Dict[str, Any]] = []
        for chapter in sorted(chapters, key=_chapter_order):
            if progress_callback:
                progress_callback("start", chapter)
            cards.append(self.generate_single_card(chapter, story_memory, block_analyses, cards))
            if progress_callback:
                progress_callback("complete", cards[-1])
        return {"chapter_count": len(cards), "chapters": cards}

    def generate_single_card(
        self,
        chapter: Dict[str, Any],
        story_memory: Dict[str, Any],
        block_analyses: Dict[str, Any],
        previous_cards: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        client = self.llm_router.build_client(SUMMARY_MODULE_KEY)
        payload = client.chat_json_value(
            messages=[
                {"role": "system", "content": CHAPTER_CARD_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": self._build_user_prompt(
                        chapter,
                        story_memory,
                        block_analyses,
                        list(previous_cards or []),
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=4096,
        )
        return self._normalize_card(chapter, payload)

    def _build_user_prompt(
        self,
        chapter: Dict[str, Any],
        story_memory: Dict[str, Any],
        block_analyses: Dict[str, Any],
        previous_cards: Sequence[Dict[str, Any]],
    ) -> str:
        chapter_order = _chapter_order(chapter)
        prior_cards = [
            {
                "chapter_order": item["chapter_order"],
                "title": item["title"],
                "summary_text": item["summary_text"],
                "end_anchor": item["end_anchor"],
                "open_threads": item.get("open_threads", [])[:2],
            }
            for item in previous_cards[-MAX_PREVIOUS_CARDS:]
        ]
        events = _history_events(story_memory, chapter_order)
        threads = _history_threads(story_memory, chapter_order)
        block_context = _block_context_for_chapter(block_analyses, chapter.get("chapter_id", ""))
        return (
            f"chapter_id: {chapter.get('chapter_id', '')}\n"
            f"chapter_order: {chapter_order}\n"
            f"title: {chapter.get('title', '')}\n"
            f"## 当前章节正文\n{chapter.get('content', '')}\n\n"
            f"## 最近章节卡\n{prior_cards}\n\n"
            f"## 到当前章为止的故事事件\n{events}\n\n"
            f"## 到当前章为止的未解线索\n{threads}\n\n"
            f"## 世界规则\n{story_memory.get('world_rules', [])}\n\n"
            f"## 当前章节相关块分析\n{block_context}\n"
        )

    def _normalize_card(self, chapter: Dict[str, Any], payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("章节卡生成结果必须是 JSON 对象")
        summary_text = _required_text(payload.get("summary_text"), "summary_text")
        start_anchor = _required_text(payload.get("start_anchor"), "start_anchor")
        end_anchor = _required_text(payload.get("end_anchor"), "end_anchor")
        key_events = _summary_items(payload.get("key_events"), "key_events")
        open_threads = _thread_items(payload.get("open_threads"))
        state_updates = _state_items(payload.get("character_state_updates"))
        relation_updates = _relation_items(payload.get("relationship_updates"))
        timeline_note = _required_text(payload.get("timeline_note"), "timeline_note")
        key_entities = _entity_items(payload.get("key_entities"))
        return {
            "chapter_id": chapter.get("chapter_id", ""),
            "chapter_order": _chapter_order(chapter),
            "title": chapter.get("title", chapter.get("chapter_id", "")),
            "summary_text": summary_text,
            "start_anchor": start_anchor,
            "end_anchor": end_anchor,
            "key_events": key_events,
            "open_threads": open_threads,
            "character_state_updates": state_updates,
            "relationship_updates": relation_updates,
            "timeline_note": timeline_note,
            "key_entities": key_entities,
        }


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"章节卡缺少必需字段: {field}")
    return text


def _summary_items(value: Any, field: str) -> List[Dict[str, str]]:
    items = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary") or "").strip()
        if summary:
            items.append({"summary": summary})
    if not items:
        raise ValueError(f"章节卡缺少必需字段: {field}")
    return items


def _thread_items(value: Any) -> List[Dict[str, str]]:
    items = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        thread_key = str(item.get("thread_key") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if thread_key and summary:
            items.append({"thread_key": thread_key, "summary": summary})
    return items


def _state_items(value: Any) -> List[Dict[str, str]]:
    items = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        state = str(item.get("state") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if name and state and summary:
            items.append({"name": name, "state": state, "summary": summary})
    return items


def _relation_items(value: Any) -> List[Dict[str, str]]:
    items = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        state = str(item.get("state") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if source and target and state and summary:
            items.append({"source": source, "target": target, "state": state, "summary": summary})
    return items


def _entity_items(value: Any) -> List[Dict[str, str]]:
    items = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        entity_type = str(item.get("entity_type") or "other").strip()
        if name:
            items.append({"name": name, "entity_type": entity_type or "other"})
    return items


def _history_events(story_memory: Dict[str, Any], chapter_order: int) -> List[Dict[str, Any]]:
    events = []
    for item in story_memory.get("event_timeline", []):
        if _order_from_ref(item.get("chapter_id", "")) > chapter_order:
            continue
        events.append(
            {
                "chapter_id": item.get("chapter_id", ""),
                "summary": item.get("summary", ""),
                "characters": item.get("characters", [])[:4],
            }
        )
    return events[:MAX_CONTEXT_EVENTS]


def _history_threads(story_memory: Dict[str, Any], chapter_order: int) -> List[Dict[str, Any]]:
    threads = []
    for item in story_memory.get("open_threads", []):
        if _order_from_ref(item.get("chapter_id", "")) > chapter_order:
            continue
        threads.append(
            {
                "chapter_id": item.get("chapter_id", ""),
                "thread_key": item.get("thread_key", ""),
                "summary": item.get("summary", ""),
            }
        )
    return threads[:MAX_CONTEXT_THREADS]


def _block_context_for_chapter(block_analyses: Dict[str, Any], chapter_id: str) -> List[Dict[str, Any]]:
    items = []
    for block in block_analyses.get("blocks", []):
        if chapter_id not in str(block):
            continue
        items.append({"block_id": block.get("block_id", ""), "plot_summary": block.get("plot_summary", "")})
    return items


def _order_from_ref(chapter_id: str) -> int:
    try:
        return int(str(chapter_id).rsplit("_", 1)[-1])
    except (TypeError, ValueError):
        return 0


def _chapter_order(chapter: Dict[str, Any]) -> int:
    return int(chapter.get("chapter_order") or chapter.get("order") or 0)
