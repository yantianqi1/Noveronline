import asyncio

from app.services.local_block_fact_extractor import LocalBlockFactExtractor
from app.services.novel_seed_analyzer import NovelSeedAnalyzer
from app.services.skeleton_timeline_builder import SkeletonTimelineBuilder


def build_sample_chapters():
    return [
        {
            "chapter_id": "chapter_0001",
            "order": 1,
            "title": "第1章 山门雪夜",
            "content": (
                "沈夜说道，玄霄宗不会替我查清真相。"
                "秦昭说道，白泽司已经盯上这封密信。"
            ),
        },
        {
            "chapter_id": "chapter_0002",
            "order": 2,
            "title": "第2章 药庐密谈",
            "content": (
                "苏半夏说道，沈临川死前见过白泽司使者。"
                "沈夜说道，我会再去玄霄宗查旧案。"
            ),
        },
    ]


class CapturingLlmClient:
    def __init__(self, payload):
        self.payload = payload
        self.messages = []

    def chat_json_value(self, messages, temperature=0.3, max_tokens=4096):
        self.messages.append(messages)
        return self.payload


def test_skeleton_timeline_builder_collects_global_entities():
    builder = SkeletonTimelineBuilder(NovelSeedAnalyzer())

    payload = builder.build(build_sample_chapters())

    character_map = {item["name"]: item for item in payload["global_characters"]}
    organization_map = {item["name"]: item for item in payload["global_organizations"]}
    chapter_map = {item["chapter_id"]: item for item in payload["chapter_sketches"]}
    arc_map = {item["name"]: item for item in payload["character_arcs"]}

    assert payload["chapter_count"] == 2
    assert character_map["沈夜"]["chapter_ids"] == ["chapter_0001", "chapter_0002"]
    assert character_map["沈夜"]["appearance_count"] == 2
    assert character_map["沈夜"]["mention_count"] >= 2
    assert organization_map["玄霄宗"]["chapter_ids"] == ["chapter_0001", "chapter_0002"]
    assert organization_map["白泽司"]["appearance_count"] == 2
    assert {"沈夜", "秦昭"}.issubset(set(chapter_map["chapter_0001"]["characters"]))
    assert "白泽司" in chapter_map["chapter_0002"]["organizations"]
    assert chapter_map["chapter_0001"]["fingerprint"]
    assert chapter_map["chapter_0001"]["tail_hook"]
    assert "沈夜" in chapter_map["chapter_0001"]["fingerprint"]
    assert arc_map["沈夜"]["first_chapter_id"] == "chapter_0001"
    assert arc_map["沈夜"]["last_chapter_id"] == "chapter_0002"


def test_local_block_fact_extractor_injects_skeleton_context_into_llm_prompt():
    client = CapturingLlmClient(
        {
            "local_events": [
                {
                    "event_id": "chapter_0001_event_01",
                    "chapter_id": "chapter_0001",
                    "summary": "沈夜与秦昭确认白泽司正在追查密信。",
                    "characters": ["沈夜", "秦昭"],
                    "organizations": ["白泽司"],
                    "evidence": ["沈夜与秦昭确认白泽司正在追查密信。"],
                }
            ],
            "local_entities": [
                {
                    "name": "沈夜",
                    "entity_type": "character",
                    "aliases": [],
                    "summary": "正在追查旧案。",
                    "importance_tier": "protagonist",
                    "evidence": ["沈夜与秦昭确认白泽司正在追查密信。"],
                }
            ],
            "local_relationship_changes": [],
            "local_threads": [],
            "unresolved_refs": [],
            "local_summary": "沈夜确认白泽司卷入密信线。",
            "evidence_spans": [
                {
                    "chapter_id": "chapter_0001",
                    "snippet": "沈夜与秦昭确认白泽司正在追查密信。",
                }
            ],
        }
    )
    extractor = LocalBlockFactExtractor(
        analyzer=NovelSeedAnalyzer(),
        llm_client=client,
        max_workers=1,
        block_batch_size=10,
    )
    chapters = build_sample_chapters()
    blocks = [
        {
            "block_id": "block_0001",
            "order": 1,
            "owned_chapter_ids": ["chapter_0001"],
            "context_chapter_ids": [],
            "owned_chapter_range": {"start_order": 1, "end_order": 1},
        },
        {
            "block_id": "block_0002",
            "order": 2,
            "owned_chapter_ids": ["chapter_0001"],
            "context_chapter_ids": ["chapter_0002"],
            "owned_chapter_range": {"start_order": 1, "end_order": 1},
        }
    ]
    skeleton = {
        "global_characters": [
            {
                "name": "沈夜",
                "appearance_count": 2,
                "mention_count": 2,
                "chapter_ids": ["chapter_0001", "chapter_0002"],
            },
            {
                "name": "秦昭",
                "appearance_count": 1,
                "mention_count": 1,
                "chapter_ids": ["chapter_0001"],
            },
        ],
        "global_organizations": [
            {
                "name": "玄霄宗",
                "appearance_count": 2,
                "mention_count": 2,
                "chapter_ids": ["chapter_0001", "chapter_0002"],
            },
            {
                "name": "白泽司",
                "appearance_count": 2,
                "mention_count": 2,
                "chapter_ids": ["chapter_0001", "chapter_0002"],
            },
        ],
        "chapter_sketches": [
            {
                "chapter_id": "chapter_0001",
                "order": 1,
                "characters": ["沈夜", "秦昭"],
                "organizations": ["玄霄宗", "白泽司"],
                "fingerprint": "沈夜与秦昭确认白泽司正在追查密信。",
                "tail_hook": "远处传来异响。",
            }
        ],
    }
    anchors = {
        "anchors": [
            {
                "anchor_id": "anchor_0001",
                "end_block_order": 1,
                "chapter_range": {"start": 1, "end": 1},
                "world_state": {
                    "active_characters": [{"name": "沈夜", "status": "active", "last_action": "继续追查密信"}],
                    "active_organizations": [{"name": "白泽司", "status": "active", "key_change": "暗中追查"}],
                    "key_relationships": [{"source": "沈夜", "target": "白泽司", "state": "conflict"}],
                    "open_plot_threads": ["密信真相"],
                    "recent_events_summary": "沈夜刚刚意识到白泽司卷入旧案。",
                },
            }
        ]
    }

    payload = asyncio.run(extractor.extract_blocks(blocks, chapters, use_llm=True, skeleton=skeleton, anchors=anchors))

    assert payload["block_count"] == 2
    user_message = client.messages[-1][1]["content"]
    assert "全文角色/组织骨架" in user_message
    assert "沈夜(出现2章" in user_message
    assert "白泽司" in user_message
    assert "当前块(block_0002)覆盖第1-1章" in user_message
    assert "该范围内已知出场角色：沈夜, 秦昭" in user_message
    assert "前情锚点摘要" in user_message
    assert "最近锚点：anchor_0001" in user_message
    assert "前文块章节指纹" in user_message
    assert "沈夜与秦昭确认白泽司正在追查密信" in user_message


def test_local_block_fact_extractor_processes_blocks_in_batches(monkeypatch):
    extractor = LocalBlockFactExtractor(
        analyzer=NovelSeedAnalyzer(),
        max_workers=1,
        block_batch_size=2,
    )
    batch_sizes = []

    async def fake_extract_batch(self, batch, chapter_map, use_llm, progress_callback, skeleton, blocks, anchors):
        batch_sizes.append(len(batch))
        return [
            {
                "block_id": block["block_id"],
                "owned_chapters": list(block["owned_chapter_ids"]),
                "context_chapters": list(block["context_chapter_ids"]),
                "local_events": [],
                "local_entities": [],
                "local_relationship_changes": [],
                "local_threads": [],
                "unresolved_refs": [],
                "local_summary": block["block_id"],
                "evidence_spans": [],
                "world_rules": [],
            }
            for block in batch
        ]

    monkeypatch.setattr(LocalBlockFactExtractor, "_extract_batch", fake_extract_batch)
    chapters = build_sample_chapters()
    blocks = [
        {
            "block_id": f"block_{index:04d}",
            "owned_chapter_ids": ["chapter_0001"],
            "context_chapter_ids": [],
            "owned_chapter_range": {"start_order": 1, "end_order": 1},
        }
        for index in range(1, 6)
    ]

    payload = asyncio.run(extractor.extract_blocks(blocks, chapters, use_llm=False, skeleton=None, anchors=None))

    assert batch_sizes == [2, 2, 1]
    assert [item["block_id"] for item in payload["packets"]] == [block["block_id"] for block in blocks]
