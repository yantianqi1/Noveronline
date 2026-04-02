from app.services.analysis_block_builder import AnalysisBlockBuilder
from app.services.continuity_consistency_auditor import ContinuityConsistencyAuditor
from app.services.contextual_block_analyzer import ContextualBlockAnalyzer
from app.services.local_block_fact_extractor import (
    LocalBlockFactExtractor,
    MAX_LOCAL_CHARACTER_ENTITY_COUNT,
    MAX_LOCAL_ORGANIZATION_ENTITY_COUNT,
    MAX_LOCAL_RELATIONSHIP_CHANGE_COUNT,
)
from app.services.story_memory_builder import StoryMemoryBuilder


def _chapter(order: int) -> dict:
    return {
        "chapter_id": f"chapter_{order:04d}",
        "order": order,
        "title": f"第{order}章",
        "source_name": "demo.txt",
        "content": f"沈夜在第{order}章与秦昭讨论镜湖真相，玄霄宗与白泽司的冲突持续升级。",
    }


def _sized_chapter(order: int, body_size: int) -> dict:
    return {
        "chapter_id": f"chapter_{order:04d}",
        "order": order,
        "title": f"标题{order}",
        "source_name": "demo.txt",
        "content": "甲" * body_size,
    }


def _chapter_char_count(chapter: dict) -> int:
    return len(chapter["title"]) + len(chapter["content"])


def _packet(block_id: str, order: int, summary: str) -> dict:
    chapter_id = f"chapter_{order:04d}"
    return {
        "block_id": block_id,
        "owned_chapters": [chapter_id],
        "context_chapters": [],
        "local_events": [
            {
                "event_id": f"{block_id}_event",
                "chapter_id": chapter_id,
                "summary": summary,
                "characters": ["沈夜", "秦昭"],
                "organizations": ["玄霄宗"],
                "evidence": [summary],
            }
        ],
        "local_entities": [
            {
                "name": "沈夜",
                "entity_type": "character",
                "aliases": [],
                "evidence": [summary],
            },
            {
                "name": "秦昭",
                "entity_type": "character",
                "aliases": [],
                "evidence": [summary],
            },
        ],
        "local_relationship_changes": [
            {
                "source": "沈夜",
                "target": "秦昭",
                "change": "ally",
                "chapter_id": chapter_id,
                "evidence": [summary],
            }
        ],
        "local_threads": [
            {
                "thread_key": "镜湖真相",
                "status": "open",
                "summary": summary,
                "chapter_id": chapter_id,
            }
        ],
        "unresolved_refs": [],
        "local_summary": summary,
        "evidence_spans": [{"chapter_id": chapter_id, "snippet": summary}],
    }


def test_analysis_block_builder_splits_at_chapter_boundary_after_target_threshold():
    chapters = [
        _sized_chapter(1, 1600),
        _sized_chapter(2, 1600),
        _sized_chapter(3, 1800),
        _sized_chapter(4, 5200),
        _sized_chapter(5, 1000),
        _sized_chapter(6, 1100),
    ]

    payload = AnalysisBlockBuilder().build(chapters)

    assert payload["block_count"] == 3
    assert payload["target_owned_char_count"] == 5000
    assert "owned_chapter_count" not in payload
    first_block = payload["blocks"][0]
    second_block = payload["blocks"][1]
    third_block = payload["blocks"][2]

    assert first_block["owned_chapter_ids"] == ["chapter_0001", "chapter_0002", "chapter_0003"]
    assert first_block["context_chapter_ids"] == ["chapter_0004", "chapter_0005"]
    assert first_block["owned_char_count"] == sum(_chapter_char_count(item) for item in chapters[:3])

    assert second_block["owned_chapter_ids"] == ["chapter_0004"]
    assert second_block["context_chapter_ids"] == ["chapter_0002", "chapter_0003", "chapter_0005", "chapter_0006"]
    assert second_block["owned_char_count"] == _chapter_char_count(chapters[3])

    assert third_block["owned_chapter_ids"] == ["chapter_0005", "chapter_0006"]
    assert third_block["context_chapter_ids"] == ["chapter_0003", "chapter_0004"]
    assert third_block["owned_char_count"] == sum(_chapter_char_count(item) for item in chapters[4:])


def test_story_memory_builder_merges_packets_in_block_order():
    packets = [
        _packet("block_0002", 2, "第二块里，沈夜决定公开密信。"),
        _packet("block_0001", 1, "第一块里，沈夜和秦昭确认镜湖旧案另有隐情。"),
    ]

    payload = StoryMemoryBuilder().build(packets)

    summaries = payload["story_memory"]["block_summaries"]
    snapshots = payload["snapshots"]

    assert [item["block_id"] for item in summaries] == ["block_0001", "block_0002"]
    second_snapshot = next(item for item in snapshots if item["block_id"] == "block_0002")
    assert "第一块里" in second_snapshot["story_so_far"]
    assert "第二块里" not in second_snapshot["story_so_far"]


def test_consistency_auditor_reports_post_death_activity_and_alias_ambiguity():
    packets = [
        {
            "block_id": "block_0002",
            "unresolved_refs": [
                {
                    "alias": "阿昭",
                    "candidate_names": ["秦昭", "苏昭"],
                    "reason": "同一称呼指向多个角色",
                }
            ],
        }
    ]
    analyses = [
        {
            "block_id": "block_0001",
            "character_state_updates": [
                {"name": "秦昭", "state": "dead", "evidence": ["秦昭坠入镜湖，生死不明。"]}
            ],
            "relationship_updates": [],
            "thread_updates": [],
            "block_end_state": {},
        },
        {
            "block_id": "block_0002",
            "character_state_updates": [
                {"name": "秦昭", "state": "active", "evidence": ["秦昭再次现身山谷指挥众人。"]}
            ],
            "relationship_updates": [],
            "thread_updates": [],
            "block_end_state": {},
        },
    ]

    report = ContinuityConsistencyAuditor().audit(
        story_memory={"entity_registry": {}, "relationship_ledger": [], "open_threads": []},
        block_analyses=analyses,
        local_block_facts=packets,
    )

    assert any(item["kind"] == "post_death_activity" for item in report["conflicts"])
    assert any(item["alias"] == "阿昭" for item in report["ambiguities"])


def test_seed_llm_stage_defaults_use_twenty_workers():
    assert LocalBlockFactExtractor().max_workers == 20
    assert LocalBlockFactExtractor().llm_concurrent_limit == 4
    assert ContextualBlockAnalyzer().max_workers == 20


class DenseAnalysisAnalyzer:
    def analyze_text(self, text: str) -> dict:
        characters = [
            {
                "name": f"角色{i:02d}",
                "importance_tier": "supporting",
                "profile_summary": f"角色{i:02d} 简介",
                "evidence": [f"角色{i:02d} 出现在线索中"],
            }
            for i in range(30)
        ]
        organizations = [
            {
                "name": f"组织{i:02d}宗",
                "importance_tier": "major",
                "organization_type": "sect",
                "summary": f"组织{i:02d} 简介",
                "evidence": [f"组织{i:02d} 参与局势"],
            }
            for i in range(20)
        ]
        relations = [
            {
                "source": f"角色{i:02d}",
                "target": f"角色{i + 1:02d}",
                "relation_type": "ally",
                "weight": 1,
                "evidence": [f"角色{i:02d} 与角色{i + 1:02d} 联手"],
            }
            for i in range(25)
        ]
        return {
            "characters": characters,
            "organizations": organizations,
            "relations": relations,
        }


def test_local_block_fact_extractor_caps_dense_offline_payload():
    extractor = LocalBlockFactExtractor(analyzer=DenseAnalysisAnalyzer())
    block = {"block_id": "block_0001", "owned_chapter_ids": ["chapter_0001"], "context_chapter_ids": []}
    chapter = {
        "chapter_id": "chapter_0001",
        "title": "第1章",
        "content": "角色00与角色01在组织00宗相遇，角色02与角色03也被卷入其中。",
    }

    payload = extractor._extract_offline(block, [chapter], [])

    assert len(payload["local_entities"]) <= MAX_LOCAL_CHARACTER_ENTITY_COUNT + MAX_LOCAL_ORGANIZATION_ENTITY_COUNT
    assert len(payload["local_relationship_changes"]) <= MAX_LOCAL_RELATIONSHIP_CHANGE_COUNT
