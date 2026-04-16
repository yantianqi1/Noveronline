import asyncio

from app.services.anchor_point_builder import AnchorPointBuilder
from app.services.chapter_card_generator import ChapterCardGenerator
from app.services.contextual_block_analyzer import ContextualBlockAnalyzer
from app.services.entity_resolution_service import EntityResolutionService
from app.services.local_block_fact_extractor import LocalBlockFactExtractor
from app.services.story_ontology_generator import StoryOntologyGenerator


INVALID_JSON_ERROR = ValueError('LLM返回的JSON格式无效: {"broken": ')


class AlwaysInvalidJsonClient:
    def chat_json_value(self, messages, temperature=0.1, max_tokens=4096):
        raise INVALID_JSON_ERROR


def test_local_block_fact_extractor_falls_back_to_offline_when_llm_json_is_invalid():
    extractor = LocalBlockFactExtractor(llm_client=AlwaysInvalidJsonClient())

    payload = asyncio.run(extractor.extract_blocks(
        blocks=[
            {
                "block_id": "block_0001",
                "owned_chapter_ids": ["chapter_0001"],
                "context_chapter_ids": [],
                "owned_chapter_range": {"start_order": 1, "end_order": 1},
                "order": 1,
            }
        ],
        chapters=[
            {
                "chapter_id": "chapter_0001",
                "title": "第1章",
                "content": "沈夜继续追查镜湖旧案，玄霄宗开始收网。",
            }
        ],
        use_llm=True,
        skeleton={"global_characters": [], "global_organizations": [], "chapter_sketches": []},
        anchors={"anchors": []},
    ))

    packet = payload["packets"][0]
    assert payload["block_count"] == 1
    assert packet["local_summary"]
    assert packet["generation_mode"] == "rule_fallback"
    assert packet["fallback_reason"] == "LLM JSON 结构不合法"


def test_contextual_block_analyzer_falls_back_to_offline_when_llm_json_is_invalid():
    analyzer = ContextualBlockAnalyzer(llm_client=AlwaysInvalidJsonClient())

    payload = asyncio.run(analyzer.analyze_blocks(
        blocks=[
            {
                "block_id": "block_0001",
                "owned_chapter_ids": ["chapter_0001"],
                "context_chapter_ids": [],
            }
        ],
        local_block_facts=[
            {
                "block_id": "block_0001",
                "local_summary": "沈夜推进镜湖旧案。",
                "local_entities": [{"name": "沈夜", "entity_type": "character"}],
                "local_relationship_changes": [],
                "local_threads": [{"thread_key": "镜湖旧案", "status": "open", "summary": "线索未结。"}],
                "local_events": [{"characters": ["沈夜"], "evidence": ["沈夜继续追查镜湖旧案。"]}],
            }
        ],
        snapshots=[{"block_id": "block_0001", "recent_blocks": []}],
        chapters=[{"chapter_id": "chapter_0001", "title": "第1章", "content": "沈夜继续追查镜湖旧案。"}],
        use_llm=True,
    ))

    block = payload["blocks"][0]
    assert payload["block_count"] == 1
    assert block["plot_summary"]
    assert block["generation_mode"] == "rule_fallback"
    assert block["fallback_reason"] == "LLM JSON 结构不合法"


def test_anchor_point_builder_falls_back_to_rule_based_anchor_when_llm_json_is_invalid():
    builder = AnchorPointBuilder(llm_client=AlwaysInvalidJsonClient())

    payload = builder.build(
        blocks=[{"block_id": "block_0001", "order": 1, "owned_chapter_ids": ["chapter_0001"], "owned_chapter_range": {"start_order": 1, "end_order": 1}}],
        chapters=[{"chapter_id": "chapter_0001", "order": 1, "title": "第1章", "content": "沈夜继续追查镜湖旧案。章末留下新的悬念。"}],
        skeleton={
            "global_characters": [{"name": "沈夜", "appearance_count": 1}],
            "chapter_sketches": [
                {
                    "chapter_id": "chapter_0001",
                    "order": 1,
                    "characters": ["沈夜"],
                    "organizations": ["玄霄宗"],
                    "fingerprint": "沈夜推进调查。",
                    "tail_hook": "新的悬念浮现。",
                }
            ],
        },
        anchor_interval=1,
    )

    anchor = payload["anchors"][0]
    assert payload["anchor_count"] == 1
    assert anchor["world_state"]["recent_events_summary"]
    assert anchor["generation_mode"] == "rule_fallback"
    assert anchor["fallback_reason"] == "LLM JSON 结构不合法"


class InvalidJsonRouter:
    def build_client(self, module_key):
        return AlwaysInvalidJsonClient()


def test_chapter_card_generator_falls_back_to_rule_based_card_when_llm_json_is_invalid():
    generator = ChapterCardGenerator(llm_router=InvalidJsonRouter())

    payload = generator.generate_cards(
        chapters=[{"chapter_id": "chapter_0001", "order": 1, "title": "风雪将起", "content": "沈夜收到密信。秦昭提醒他危险将近。"}],
        story_memory={"event_timeline": [], "open_threads": [], "world_rules": []},
        block_analyses={"blocks": [{"block_id": "block_0001", "plot_summary": "沈夜开始行动。"}]},
    )

    chapter = payload["chapters"][0]
    assert chapter["summary_text"]
    assert chapter["key_events"]
    assert chapter["generation_mode"] == "rule_fallback"
    assert chapter["fallback_reason"] == "LLM JSON 结构不合法"


def test_story_ontology_generator_falls_back_to_offline_ontology_when_llm_json_is_invalid():
    generator = StoryOntologyGenerator(llm_client=AlwaysInvalidJsonClient())

    payload = generator.generate(
        document_texts=["第1章\n沈夜进入玄霄宗调查旧案。"],
        analysis_goal="观察角色与组织关系",
        use_llm=True,
    )

    assert payload["entity_types"]
    assert payload["edge_types"]
    assert payload["generation_mode"] == "offline_fallback"
    assert payload["fallback_reason"] == "LLM JSON 结构不合法"


def test_entity_resolution_service_keeps_conservative_no_merge_when_llm_json_is_invalid():
    service = EntityResolutionService(llm_client=AlwaysInvalidJsonClient())

    story_memory = {
        "entity_registry": {
            "沈夜": {
                "name": "沈夜",
                "entity_type": "character",
                "summary": "主角",
                "aliases": [],
                "mention_blocks": ["block_0001"],
                "evidence": ["沈夜继续追查镜湖旧案。"],
            },
            "夜哥": {
                "name": "夜哥",
                "entity_type": "character",
                "summary": "别名候选",
                "aliases": [],
                "mention_blocks": ["block_0002"],
                "evidence": ["众人提到沈夜又叫夜哥。"],
            },
        },
        "alias_map": {},
    }

    payload = service.resolve(story_memory)

    assert "沈夜" in payload["entity_registry"]
    assert "夜哥" in payload["entity_registry"]
    assert payload["alias_map"] == {}
