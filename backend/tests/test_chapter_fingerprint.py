from app.services.novel_seed_analyzer import NovelSeedAnalyzer
from app.services.skeleton_timeline_builder import SkeletonTimelineBuilder


def test_skeleton_timeline_builder_adds_fingerprint_and_tail_hook():
    builder = SkeletonTimelineBuilder(NovelSeedAnalyzer())
    chapters = [
        {
            "chapter_id": "chapter_0001",
            "order": 1,
            "title": "第1章 山门雪夜",
            "content": (
                "山门大雪封路，沈夜独自跪在玄霄宗外。"
                "秦昭赶来提醒他，白泽司已经盯上那封密信。"
                "远处忽然传来低沉钟声，像是在催促谁现身。"
            ),
        }
    ]

    payload = builder.build(chapters)
    sketch = payload["chapter_sketches"][0]

    assert sketch["chapter_id"] == "chapter_0001"
    assert "fingerprint" in sketch
    assert "tail_hook" in sketch
    assert "沈夜" in sketch["fingerprint"]
    assert "秦昭" in sketch["fingerprint"]
    assert "低沉钟声" in sketch["tail_hook"]
