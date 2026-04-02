"""逐章调用 LLM 生成结构化章节卡。"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from .chapter_card_fallback_builder import ChapterCardFallbackBuilder
from .chapter_card_line_protocol import ChapterCardLineProtocolExecutor
from .llm_router import LlmRouter
from .sentence_atlas_builder import build_sentence_atlas
from .seed_stage_fallback_support import attach_rule_fallback, should_use_rule_fallback, summarize_stage_failure
from ..utils.llm_json import normalize_json_object


SUMMARY_MODULE_KEY = "novel_chapter_summarizer"
MAX_PREVIOUS_CARDS = 3
MAX_CONTEXT_EVENTS = 6
MAX_CONTEXT_THREADS = 6
logger = logging.getLogger(__name__)

CHAPTER_CARD_SYSTEM_PROMPT = """你是一名小说章节分析师。

请基于当前章节正文、已有前情摘要、故事记忆与块分析，输出严格有效的 JSON 对象。
不要输出 markdown，不要输出解释，不要省略字段。

JSON 结构必须如下：
{
  "summary_text": "中文，100-160字，概括本章核心推进。必须包含：主要角色做了什么、为什么、结果如何",
  "start_anchor": "中文，30-60字，描述本章开场承接了上一章的什么情节或状态",
  "end_anchor": "中文，30-60字，描述本章结尾给下一章留下了什么悬念或转折点",
  "key_events": [
    {"summary": "中文，40-80字，格式：[谁]在[何处][做了什么]，导致[什么结果]"}
  ],
  "open_threads": [
    {"thread_key": "8-20字线索命名", "summary": "中文，未收束线索的具体内容，30-60字"}
  ],
  "character_state_updates": [
    {"name": "角色名", "state": "active/dead/injured/missing", "summary": "中文，状态变化的具体描述"}
  ],
  "relationship_updates": [
    {"source": "实体A", "target": "实体B", "state": "ally/conflict/co_occurrence/mentor/betrayal/reunion", "summary": "中文，关系变化描述"}
  ],
  "timeline_note": "中文，时间线注记。格式：'{时间范围}，{时间跨度}'。如果章节中没有明确的时间线索，写'时间线无明确推进'",
  "key_entities": [
    {"name": "实体名", "entity_type": "character/organization/location/artifact/other"}
  ]
}

key_events 数量标准：
- 每章 2-4 个关键事件
- 只记录推动主线或子线的事件，不记录日常描写
- 事件之间应体现因果或时序逻辑

## 输出示范
{
  "summary_text": "沈渊携中毒昏迷的柳如烟赶回苍澜宗，途中遭暗影组织伏击。沈渊被迫首次使用古卷禁术击退敌人，但禁术反噬导致他短暂失明。柳如烟在高烧中说出陌生名字，暗示其另有身份。两人在危机中被苍澜宗巡逻弟子发现救回。",
  "start_anchor": "承接上章沈渊获得古卷、柳如烟被暗影蛇咬伤中毒后，两人急需返回苍澜宗救治",
  "end_anchor": "沈渊暂时失明等待恢复，柳如烟的隐藏身份成为新的悬念，暗影组织的追杀仍在持续",
  "key_events": [
    {"summary": "暗影组织在归途中设伏拦截沈渊和柳如烟，要求交出古卷"},
    {"summary": "沈渊首次使用古卷禁术击退暗影组织，但遭受禁术反噬短暂失明"},
    {"summary": "柳如烟高烧昏迷中说出陌生名字，暗示其拥有隐藏身份"}
  ],
  "open_threads": [
    {"thread_key": "古卷禁术副作用", "summary": "禁术使用后沈渊暂时失明，长期影响未知"},
    {"thread_key": "柳如烟真实身份", "summary": "昏迷中说出的陌生名字暗示其身份另有隐情"}
  ],
  "character_state_updates": [
    {"name": "沈渊", "state": "injured", "summary": "禁术反噬导致暂时失明和体力透支"},
    {"name": "柳如烟", "state": "injured", "summary": "暗影蛇毒蔓延至肩部，持续高烧昏迷"}
  ],
  "relationship_updates": [
    {"source": "暗影组织", "target": "沈渊", "state": "conflict", "summary": "暗影组织正式对沈渊发出追杀，矛盾从暗转明"}
  ],
  "timeline_note": "第七层塔试炼后第二天至第三天，约一天半时间跨度",
  "key_entities": [
    {"name": "沈渊", "entity_type": "character"},
    {"name": "柳如烟", "entity_type": "character"},
    {"name": "暗影组织", "entity_type": "organization"},
    {"name": "古卷", "entity_type": "artifact"}
  ]
}
"""


class ChapterCardGenerator:
    """生成完整项目章节卡，或为单章正文生成章节卡。"""

    def __init__(
        self,
        llm_router: Optional[LlmRouter] = None,
        fallback_builder: Optional[ChapterCardFallbackBuilder] = None,
    ):
        self.llm_router = llm_router or LlmRouter()
        self.fallback_builder = fallback_builder or ChapterCardFallbackBuilder()

    def generate_cards(
        self,
        chapters: Sequence[Dict[str, Any]],
        story_memory: Dict[str, Any],
        block_analyses: Dict[str, Any],
        sentence_atlas: Optional[Sequence[Dict[str, Any]]] = None,
        progress_callback=None,
    ) -> Dict[str, Any]:
        atlas = list(sentence_atlas or build_sentence_atlas(chapters)[1])
        cards: List[Dict[str, Any]] = []
        for chapter in sorted(chapters, key=_chapter_order):
            if progress_callback:
                progress_callback("start", chapter)
            cards.append(self.generate_single_card(chapter, story_memory, block_analyses, cards, atlas))
            if progress_callback:
                progress_callback("complete", cards[-1])
        return {"chapter_count": len(cards), "chapters": cards}

    def generate_single_card(
        self,
        chapter: Dict[str, Any],
        story_memory: Dict[str, Any],
        block_analyses: Dict[str, Any],
        previous_cards: Optional[Sequence[Dict[str, Any]]] = None,
        sentence_atlas: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        previous = list(previous_cards or [])
        try:
            client = self.llm_router.build_client(SUMMARY_MODULE_KEY)
            if hasattr(client, "chat"):
                prompt = self._build_user_prompt(
                    chapter,
                    story_memory,
                    block_analyses,
                    previous,
                )
                payload = ChapterCardLineProtocolExecutor(client, chapter.get("sentence_ids", [])).generate(prompt)
                return self._normalize_card(chapter, payload)
            payload = client.chat_json_value(
                messages=[
                    {"role": "system", "content": CHAPTER_CARD_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": self._build_user_prompt(
                            chapter,
                            story_memory,
                            block_analyses,
                            previous,
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=4096,
            )
            return self._normalize_card(chapter, payload)
        except Exception as exc:
            if not should_use_rule_fallback(exc):
                raise
            chapter_id = chapter.get("chapter_id", chapter.get("title", ""))
            logger.warning("章节卡生成转为规则回退 (%s): %s", chapter_id, summarize_stage_failure(exc))
            return attach_rule_fallback(
                self.fallback_builder.build(chapter, story_memory, block_analyses, previous),
                exc,
            )

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
        sentence_catalog = _sentence_catalog(chapter)
        return (
            f"chapter_id: {chapter.get('chapter_id', '')}\n"
            f"chapter_order: {chapter_order}\n"
            f"title: {chapter.get('title', '')}\n"
            f"## 当前章节句子编号\n{sentence_catalog}\n\n"
            f"## 当前章节正文\n{chapter.get('content', '')}\n\n"
            f"## 最近章节卡\n{prior_cards}\n\n"
            f"## 到当前章为止的故事事件\n{events}\n\n"
            f"## 到当前章为止的未解线索\n{threads}\n\n"
            f"## 世界规则\n{story_memory.get('world_rules', [])}\n\n"
            f"## 当前章节相关块分析\n{block_context}\n"
        )

    def _normalize_card(self, chapter: Dict[str, Any], payload: Any) -> Dict[str, Any]:
        payload = normalize_json_object(payload, "章节卡生成结果")
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
            "summary_sentence_refs": _string_list(payload.get("summary_sentence_refs")),
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
            items.append({"summary": summary, "sentence_refs": _string_list(item.get("sentence_refs"))})
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
            items.append({"thread_key": thread_key, "summary": summary, "sentence_refs": _string_list(item.get("sentence_refs"))})
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
            items.append({"name": name, "state": state, "summary": summary, "sentence_refs": _string_list(item.get("sentence_refs"))})
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
            items.append({"source": source, "target": target, "state": state, "summary": summary, "sentence_refs": _string_list(item.get("sentence_refs"))})
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


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


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


def _sentence_catalog(chapter: Dict[str, Any]) -> str:
    content = str(chapter.get("content") or "")
    sentence_ids = list(chapter.get("sentence_ids") or [])
    sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])\s*|\n+", content) if item.strip()]
    pairs = []
    for index, sentence_id in enumerate(sentence_ids):
        text = sentences[index] if index < len(sentences) else ""
        pairs.append(f"[{sentence_id}] {text}")
    return "\n".join(pairs) or "无"
