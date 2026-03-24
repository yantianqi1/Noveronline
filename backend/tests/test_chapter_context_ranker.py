from app.services.chapter_context_ranker import ChapterContextRanker


def _item(category: str, summary: str, *, memory_layer: str = "canon", normalized_subject: str = "", salience: float = 0.1):
    return {
        "item_id": f"{category}_{summary}",
        "category": category,
        "summary": summary,
        "why_it_matters": summary,
        "memory_layer": memory_layer,
        "normalized_subject": normalized_subject,
        "salience": salience,
        "match_meta": {
            "scope_hit": True,
            "pov_hit": False,
            "scene_hit": False,
            "thread_hit": category == "open_thread",
            "chapter_distance": 0,
            "freshness": 0.0,
        },
    }


def test_chapter_context_ranker_prioritizes_authoring_core_items():
    ranker = ChapterContextRanker()
    items = [
        _item("relationship", "沈夜与秦昭暂时联手。", normalized_subject="沈夜_秦昭"),
        _item("open_thread", "镜湖真相仍未查清。", normalized_subject="镜湖真相"),
        _item("world_rule", "镜湖引擎会记录识海残痕。"),
        _item("continuity", "秦昭带沈夜来到废塔前。"),
        _item("runtime_memory", "沈夜怀疑顾行舟已拿到密信原件。", memory_layer="candidate", normalized_subject="顾行舟_密信"),
    ]

    ranked = ranker.rank_items(items, {"include_candidates": True}, 10)
    categories = [item["category"] for item in ranked]

    assert categories.index("continuity") < categories.index("relationship")
    assert categories.index("world_rule") < categories.index("open_thread")
    assert categories[-1] == "runtime_memory"


def test_chapter_context_ranker_filters_candidates_and_deduplicates_subjects():
    ranker = ChapterContextRanker()
    items = [
        _item("relationship", "沈夜与秦昭暂时联手。", normalized_subject="沈夜_秦昭", salience=0.4),
        _item("relationship", "沈夜与秦昭仍保持试探性联手。", normalized_subject="沈夜_秦昭", salience=0.2),
        _item("runtime_memory", "沈夜准备公开密信残页。", memory_layer="candidate", normalized_subject="公开密信"),
    ]

    ranked = ranker.rank_items(items, {"include_candidates": False}, 10)

    assert len(ranked) == 1
    assert ranked[0]["summary"] == "沈夜与秦昭暂时联手。"
