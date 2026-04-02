import re

from app.services.chapter_card_generator import ChapterCardGenerator
from app.services.chapter_continuity_service import ChapterContinuityService


CHAPTER_ID_PATTERN = re.compile(r"chapter_id:\s*(chapter_\d+)")


class StubChapterCardClient:
    def chat_json_value(self, messages, temperature=0.2, max_tokens=4096):
        user_message = messages[-1]["content"]
        match = CHAPTER_ID_PATTERN.search(user_message)
        chapter_id = match.group(1) if match else "chapter_0001"
        chapter_order = int(chapter_id.rsplit("_", 1)[-1])
        return {
            "summary_text": f"第{chapter_order}章摘要：镜湖线索继续推进。",
            "start_anchor": f"第{chapter_order}章起点：承接上一章的镜湖压力。",
            "end_anchor": f"第{chapter_order}章尾声：新的对峙即将发生。",
            "key_events": [
                {"summary": f"第{chapter_order}章事件：沈夜继续追查镜湖真相。"},
                {"summary": f"第{chapter_order}章事件：顾行舟开始收束局面。"},
            ],
            "open_threads": [
                {"thread_key": "镜湖真相", "summary": "镜湖真相仍未查明。"},
            ],
            "character_state_updates": [
                {"name": "沈夜", "state": "active", "summary": "持续推进调查。"},
            ],
            "relationship_updates": [
                {"source": "沈夜", "target": "顾行舟", "state": "conflict", "summary": "双方对立继续升级。"},
            ],
            "timeline_note": f"第{chapter_order}章发生在当日夜间。",
            "key_entities": [
                {"name": "沈夜", "entity_type": "character"},
                {"name": "顾行舟", "entity_type": "character"},
                {"name": "玄霄宗", "entity_type": "organization"},
            ],
        }


class StubRouter:
    def build_client(self, module_key):
        assert module_key == "novel_chapter_summarizer"
        return StubChapterCardClient()


def test_chapter_card_generator_outputs_structured_cards():
    generator = ChapterCardGenerator(llm_router=StubRouter())
    chapters = [
        {"chapter_id": "chapter_0001", "order": 1, "title": "风雪将起", "content": "沈夜收到密信。"},
        {"chapter_id": "chapter_0002", "order": 2, "title": "废塔残响", "content": "秦昭带沈夜潜入废塔。"},
    ]
    story_memory = {
        "event_timeline": [
            {"chapter_id": "chapter_0001", "summary": "沈夜拿到密信。", "characters": ["沈夜"]},
        ],
        "open_threads": [
            {"chapter_id": "chapter_0001", "thread_key": "镜湖真相", "summary": "镜湖真相仍未查清。"},
        ],
        "world_rules": ["镜湖引擎会记录识海残痕。"],
    }
    block_analyses = {
        "blocks": [
            {"block_id": "block_0001", "plot_summary": "前两章持续推进镜湖旧案。"},
        ]
    }

    payload = generator.generate_cards(chapters, story_memory, block_analyses)

    assert payload["chapter_count"] == 2
    assert payload["chapters"][0]["chapter_id"] == "chapter_0001"
    assert payload["chapters"][1]["chapter_order"] == 2
    assert payload["chapters"][1]["summary_text"]
    assert payload["chapters"][1]["key_events"]
    assert payload["chapters"][1]["open_threads"][0]["thread_key"] == "镜湖真相"


def test_chapter_continuity_service_derives_continuity_from_cards():
    service = ChapterContinuityService()
    chapter_cards = [
        {
            "chapter_id": "chapter_0001",
            "chapter_order": 1,
            "title": "风雪将起",
            "summary_text": "第1章摘要：沈夜拿到密信。",
            "start_anchor": "密信把沈夜推向镜湖旧案。",
            "end_anchor": "秦昭提出潜入废塔。",
            "key_events": [
                {"summary": "沈夜怀疑玄霄宗在掩盖旧案。"},
            ],
            "open_threads": [
                {"thread_key": "镜湖真相", "summary": "镜湖真相仍未查清。"},
            ],
            "character_state_updates": [
                {"name": "沈夜", "state": "active", "summary": "继续调查。"},
            ],
            "relationship_updates": [],
            "timeline_note": "第一天傍晚。",
            "key_entities": [
                {"name": "沈夜", "entity_type": "character"},
                {"name": "玄霄宗", "entity_type": "organization"},
            ],
        }
    ]

    continuity = service.build_from_chapter_cards(chapter_cards)

    assert continuity["chapter_count"] == 1
    assert continuity["chapters"][0]["head_context"] == "密信把沈夜推向镜湖旧案。"
    assert continuity["chapters"][0]["tail_hooks"][0] == "秦昭提出潜入废塔。"
    assert continuity["chapters"][0]["key_characters"] == ["沈夜"]
    assert "镜湖真相" in continuity["chapters"][0]["continuity_summary"]
