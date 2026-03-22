from app.services.local_story_graph_builder import LocalStoryGraphBuilder
from app.services.local_story_graph_support import evidence_ref
from app.services.narrative_entity_archivist import NarrativeEntityArchivist
from app.services.seed_llm_payload_normalizer import (
    normalize_contextual_block_payload,
    normalize_local_block_payload,
)
from app.services.zep_entity_reader import EntityNode


LONG_TEXT = "这是一个很长的剧情描述" * 20
LONG_RULE_TEXT = "天地法则发生偏转，所有修士都会感知到新的约束" * 6
CHARACTER_UPDATE_TEXT = f"沈夜{LONG_TEXT}"
RELATIONSHIP_UPDATE_TEXT = f"沈夜与玄霄宗{LONG_TEXT}"


def test_seed_llm_payload_normalizer_preserves_full_text_fields():
    analysis = {
        "characters": [{"name": "沈夜", "profile_summary": "主角"}],
        "organizations": [{"name": "玄霄宗", "summary": "宗门"}],
        "relations": [],
    }
    payload = {
        "local_events": [
            {
                "summary": LONG_TEXT,
                "characters": ["沈夜"],
                "organizations": ["玄霄宗"],
                "evidence": [LONG_TEXT],
            }
        ],
        "local_entities": ["沈夜", "玄霄宗"],
        "local_relationship_changes": [LONG_TEXT],
        "local_threads": [LONG_TEXT],
        "unresolved_refs": [LONG_TEXT],
        "local_summary": LONG_TEXT,
        "evidence_spans": [LONG_TEXT],
        "world_rules": [LONG_RULE_TEXT],
    }

    normalized = normalize_local_block_payload(payload, analysis, ["chapter_0001"])

    assert normalized["local_events"][0]["summary"] == LONG_TEXT
    assert normalized["local_events"][0]["evidence"] == [LONG_TEXT]
    assert normalized["local_relationship_changes"][0]["evidence"] == [LONG_TEXT]
    assert normalized["local_threads"][0]["summary"] == LONG_TEXT
    assert normalized["evidence_spans"][0]["snippet"] == LONG_TEXT
    assert normalized["world_rules"] == [LONG_RULE_TEXT]


def test_contextual_block_payload_preserves_full_llm_text_evidence():
    packet = {
        "local_entities": [
            {"name": "沈夜", "entity_type": "character"},
            {"name": "玄霄宗", "entity_type": "organization"},
        ],
        "local_threads": [{"thread_key": "镜湖真相", "status": "open", "summary": LONG_TEXT}],
        "local_summary": LONG_TEXT,
    }
    payload = {
        "plot_summary": LONG_TEXT,
        "character_state_updates": [CHARACTER_UPDATE_TEXT],
        "relationship_updates": [RELATIONSHIP_UPDATE_TEXT],
        "thread_updates": [LONG_TEXT],
        "block_end_state": LONG_TEXT,
    }

    normalized = normalize_contextual_block_payload(payload, packet)

    assert normalized["plot_summary"] == LONG_TEXT
    assert normalized["character_state_updates"][0]["evidence"] == [CHARACTER_UPDATE_TEXT]
    assert normalized["relationship_updates"][0]["evidence"] == [RELATIONSHIP_UPDATE_TEXT]
    assert normalized["thread_updates"][0]["summary"] == LONG_TEXT
    assert normalized["block_end_state"]["summary"] == LONG_TEXT


def test_story_graph_builder_preserves_full_event_rule_and_evidence_text():
    builder = LocalStoryGraphBuilder()
    event = {
        "event_id": "event_1",
        "chapter_id": "chapter_0001",
        "block_id": "block_0001",
        "summary": LONG_TEXT,
        "evidence": [LONG_TEXT],
    }

    event_candidate = builder._event_candidate({}, event)
    rule_candidate = builder._rule_candidate({}, LONG_RULE_TEXT)
    snippet_ref = evidence_ref(snippet=LONG_TEXT)

    assert event_candidate["name"] == LONG_TEXT
    assert event_candidate["summary"] == LONG_TEXT
    assert event_candidate["evidence_refs"][0].snippet == LONG_TEXT
    assert rule_candidate["name"] == LONG_RULE_TEXT
    assert rule_candidate["summary"] == LONG_RULE_TEXT
    assert snippet_ref.snippet == LONG_TEXT


def test_narrative_archivist_offline_mode_preserves_full_summary_text():
    related_name = LONG_TEXT + "相关节点"
    entity = EntityNode(
        uuid="char_1",
        name="沈夜",
        labels=["Entity", "Character"],
        summary=LONG_TEXT,
        attributes={"importance_tier": "protagonist"},
        related_nodes=[{"name": related_name}],
    )

    archive = NarrativeEntityArchivist().generate_archive(entity, use_llm=False)

    assert archive.entity_role == LONG_TEXT
    assert archive.relationship_summary == f"关键关联对象：{related_name}"
