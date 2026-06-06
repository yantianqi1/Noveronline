from migrations.json_importers.asset_classification import classify_legacy_asset


def test_classify_project_and_seed_assets():
    project_file = classify_legacy_asset("projects/proj_demo/project.json")
    seed_analysis = classify_legacy_asset("projects/proj_demo/seed_analysis.json")
    manuscript = classify_legacy_asset("projects/proj_demo/files/chapter1.txt")

    assert project_file.action == "structured_import"
    assert project_file.target == "projects"
    assert seed_analysis.action == "structured_import"
    assert seed_analysis.target == "artifacts+seed_entities_projection"
    assert manuscript.action == "structured_import"
    assert manuscript.target == "manuscripts+artifact_objects"


def test_classify_projection_rebuild_and_worldline_assets():
    graph_sqlite = classify_legacy_asset("projects/proj_demo/story_graph.sqlite3")
    worldline_prepare = classify_legacy_asset("projects/proj_demo/worldlines/prepare.sqlite3")
    session_json = classify_legacy_asset("projects/proj_demo/worldlines/sessions/ws_demo/session.json")
    system_runtime = classify_legacy_asset("system/global_worldlines/graphs/graph_demo/worldlines/runtime.sqlite3")

    assert graph_sqlite.action == "projection_rebuild_reference"
    assert graph_sqlite.target == "graph_query_projection"
    assert worldline_prepare.action == "structured_import"
    assert worldline_prepare.target == "worldline_preparations"
    assert session_json.action == "structured_import"
    assert session_json.target == "worldline_sessions+world_states+timeline_events"
    assert system_runtime.action == "structured_import"
    assert "session_agents" in system_runtime.target


def test_classify_unknown_asset_as_anomaly():
    unknown = classify_legacy_asset("projects/proj_demo/unexpected.bin")

    assert unknown.action == "anomaly"
    assert unknown.target == "manual_review"
