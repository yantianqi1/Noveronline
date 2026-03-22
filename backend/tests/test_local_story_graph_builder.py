from app.services.local_story_graph_builder import LocalStoryGraphBuilder


def test_raw_candidates_do_not_invent_location_nodes_from_free_text():
    builder = LocalStoryGraphBuilder()
    candidates = builder._raw_candidates(
        ontology={"entity_types": []},
        extracted_text="医生转身出门。陈迹来到洛城。桌上的密信被打开。",
        registry={},
    )

    assert any(item["label"] == "Artifact" and "密信" in item["name"] for item in candidates)
    assert all(item["label"] != "Location" for item in candidates)
