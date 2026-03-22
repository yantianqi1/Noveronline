from app.services.local_story_graph_support import find_location_candidates


def test_find_location_candidates_prefers_contextual_place_names():
    text = (
        "护士等会儿带你去六楼病房。"
        "医生转身出门。"
        "你还有哪些关于十二岁的记忆？"
        "陈迹来到洛城，又被送入青山精神病院六楼。"
    )

    candidates = find_location_candidates(text)

    assert "洛城" in candidates
    assert any("青山精神病院" in item for item in candidates)
    assert "出门" not in candidates
    assert "哪些关" not in candidates
