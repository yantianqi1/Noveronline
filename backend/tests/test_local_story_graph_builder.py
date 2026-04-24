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


def test_event_candidate_attributes_carry_description_and_kind():
    """When a key_event has a real description, node.summary carries it AND
    attributes.description exposes it for the frontend's fallback chain."""
    builder = LocalStoryGraphBuilder()
    event = {
        "event_id": "arc_01_ev_01",
        "title": "京城潜伏线",
        "summary": "细作在京城安插眼线，监视朝局动向。",
        "kind": "key_event",
        "arc_id": "arc_01",
        "consequence": "皇帝对大臣生疑。",
        "characters": ["林动", "细作甲"],
        "evidence": ["细作安插眼线", "宫中情报流出"],
    }
    candidate = builder._event_candidate({"entity_types": []}, event)

    assert candidate["name"] == "京城潜伏线"
    assert "细作" in candidate["summary"]
    attrs = candidate["attributes"]
    assert attrs["description"] == event["summary"]
    assert attrs["title_display"] == "京城潜伏线"
    assert attrs["kind"] == "key_event"
    assert attrs["arc_id"] == "arc_01"
    assert "皇帝对大臣生疑。" == attrs["consequence"]
    assert "林动" in attrs["participants"]


def test_event_candidate_handles_title_only_event_gracefully():
    """When LLM gave only a title (no description), attributes.description
    should be empty but title_display must still be populated so the
    frontend can render a title-with-context card instead of a bare
    'no description' fallback."""
    builder = LocalStoryGraphBuilder()
    event = {
        "event_id": "arc_02",
        "title": "孤身北上",
        "summary": "",  # description missing
        "kind": "arc",
        "arc_id": "arc_02",
        "consequence": "",
        "characters": [],
        "evidence": [],
    }
    candidate = builder._event_candidate({"entity_types": []}, event)
    attrs = candidate["attributes"]

    assert candidate["name"] == "孤身北上"
    # summary falls back to title so existing consumers don't break,
    # but attributes.description stays empty so the frontend can detect
    # the degenerate case and render a kind-specific hint instead.
    assert candidate["summary"] == "孤身北上"
    assert attrs["description"] == ""
    assert attrs["title_display"] == "孤身北上"
    assert attrs["kind"] == "arc"
