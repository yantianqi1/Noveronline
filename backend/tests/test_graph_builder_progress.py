"""Tests for the progress_callback wiring in graph build."""
from unittest.mock import patch

import pytest

from app.services.graph_builder import GraphBuilderService
from app.services.local_story_graph_builder import LocalStoryGraphBuilder


# ---- fixtures ----------------------------------------------------------------

EXPECTED_STAGES = [
    "load_artifacts",
    "collect_entities",
    "merge_nodes",
    "build_relationships",
    "build_events",
    "build_artifacts_rules",
    "persist",
    "finalize",
]


def _minimal_story_memory():
    return {
        "entity_registry": {
            "林惊羽": {
                "entity_type": "character",
                "importance_tier": "protagonist",
                "summary": "主角少年",
                "aliases": ["阿羽"],
                "evidence": ["林惊羽踏入北冥宗"],
                "mention_blocks": [],
            },
            "苏璃": {
                "entity_type": "character",
                "importance_tier": "major",
                "summary": "师姐",
                "aliases": [],
                "evidence": ["苏璃出现在山门"],
                "mention_blocks": [],
            },
            "北冥宗": {
                "entity_type": "organization",
                "importance_tier": "major",
                "organization_type": "sect",
                "summary": "正道大宗",
                "aliases": [],
                "evidence": [],
                "mention_blocks": [],
            },
        },
        "event_timeline": [
            {
                "event_id": "evt1",
                "summary": "林惊羽初入北冥宗",
                "chapter_id": "ch1",
                "block_id": "b1",
                "characters": ["林惊羽"],
                "organizations": ["北冥宗"],
                "evidence": ["林惊羽踏入北冥宗山门"],
            }
        ],
        "world_rules": ["修炼者须遵守宗门戒律"],
        "relationship_ledger": [
            {
                "source": "林惊羽",
                "target": "苏璃",
                "changes": [
                    {"change": "ally", "chapter_id": "ch1", "block_id": "b1", "evidence": ["并肩作战"]}
                ],
            }
        ],
    }


def _minimal_block_facts():
    return {"block_count": 1, "packets": []}


def _minimal_chapter_continuity():
    return {"chapter_count": 1}


def _minimal_block_analyses():
    return {"block_count": 1}


# ---- builder-level callback --------------------------------------------------


def test_builder_emits_all_stages_in_order(tmp_path):
    builder = LocalStoryGraphBuilder()

    events = []

    with patch.object(builder._repo, "save_snapshot") as mock_save:
        mock_save.return_value = None
        builder.build_for_project(
            project_id="proj_test",
            graph_name="g",
            ontology={"entity_types": []},
            extracted_text="林惊羽进入北冥宗,苏璃同行。",
            local_block_facts=_minimal_block_facts(),
            block_analyses=_minimal_block_analyses(),
            story_memory=_minimal_story_memory(),
            chapter_continuity=_minimal_chapter_continuity(),
            progress_callback=events.append,
        )

    stages = [e["stage"] for e in events]
    assert stages == EXPECTED_STAGES, f"unexpected stage sequence: {stages}"

    # progress is monotonic non-decreasing and ends at 100
    progresses = [e["progress"] for e in events]
    assert progresses == sorted(progresses)
    assert progresses[-1] == 100

    # every event has counts dict + elapsed_ms
    for e in events:
        assert isinstance(e["counts"], dict)
        assert "elapsed_ms" in e
        assert isinstance(e["elapsed_ms"], int)

    # merge_nodes event reports the actual node count > 0
    merge_evt = next(e for e in events if e["stage"] == "merge_nodes")
    assert merge_evt["counts"].get("nodes", 0) > 0

    # finalize reports node + edge counts
    final = events[-1]
    assert final["counts"].get("nodes", 0) > 0


def test_builder_without_callback_is_unchanged():
    """Backward compat: builder must not require a callback."""
    builder = LocalStoryGraphBuilder()
    with patch.object(builder._repo, "save_snapshot"):
        snapshot = builder.build_for_project(
            project_id="proj_compat",
            graph_name="g",
            ontology={"entity_types": []},
            extracted_text="林惊羽进入北冥宗。",
            local_block_facts=_minimal_block_facts(),
            block_analyses=_minimal_block_analyses(),
            story_memory=_minimal_story_memory(),
            chapter_continuity=_minimal_chapter_continuity(),
        )
    assert snapshot.node_count > 0


def test_builder_does_not_swallow_callback_exceptions():
    """Per debug-first policy: callback errors must surface, not be silenced."""
    builder = LocalStoryGraphBuilder()

    def boom(_event):
        raise RuntimeError("callback exploded")

    with patch.object(builder._repo, "save_snapshot"):
        with pytest.raises(RuntimeError, match="callback exploded"):
            builder.build_for_project(
                project_id="proj_boom",
                graph_name="g",
                ontology={"entity_types": []},
                extracted_text="林惊羽进入北冥宗。",
                local_block_facts=_minimal_block_facts(),
                block_analyses=_minimal_block_analyses(),
                story_memory=_minimal_story_memory(),
                chapter_continuity=_minimal_chapter_continuity(),
                progress_callback=boom,
            )


# ---- service passes callback through ----------------------------------------


def test_service_passes_callback_to_builder():
    from unittest.mock import MagicMock

    mock_builder = MagicMock()
    mock_builder.build_for_project.return_value = MagicMock(graph_id="g1", node_count=1, edge_count=0)

    with patch("app.repositories.project_artifact_repo.load_project_artifact") as mock_load:
        mock_load.return_value = {"block_count": 0, "packets": [], "entity_registry": {}}
        service = GraphBuilderService(builder=mock_builder)
        cb = lambda e: None
        service.build_graph("p", "text", {}, "g", progress_callback=cb)

    kwargs = mock_builder.build_for_project.call_args.kwargs
    assert kwargs.get("progress_callback") is cb
