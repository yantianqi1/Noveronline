"""Test that GraphBuilderService falls back to reading_notes adapter."""
from unittest.mock import patch, MagicMock

from app.services.graph_builder import GraphBuilderService


def test_build_graph_falls_back_to_reading_notes():
    """When block-based artifacts are missing but reading_notes exists, adapter is used."""
    reading_notes = {
        "core_facts": {
            "characters": {"角色A": {"aliases": [], "status": "active", "identity": "测试角色",
                "segments_seen": ["s1"], "key_actions": ["行动1"], "quote_examples": []}},
            "organizations": {},
            "world_rules": [],
            "key_locations": {},
        },
        "relationship_graph": [],
        "plot_state": {"arc_summaries": [], "open_threads": [], "narrative_phase": ""},
    }
    seed_analysis = {
        "characters": [{"name": "角色A", "importance_tier": "major"}],
        "organizations": [],
        "relations": [],
    }

    with patch("app.repositories.project_artifact_repo.load_project_artifact") as mock_load:
        def load_artifact(pid, filename):
            mapping = {
                "local_block_facts.json": None,
                "block_analyses.json": None,
                "story_memory.json": None,
                "chapter_continuity.json": None,
                "reading_notes.json": reading_notes,
                "seed_analysis.json": seed_analysis,
                "smart_segments.json": None,
                "chapter_segments.json": None,
            }
            return mapping.get(filename)
        mock_load.side_effect = load_artifact

        mock_builder = MagicMock()
        mock_builder.build_for_project.return_value = MagicMock(
            graph_id="g1", node_count=1, edge_count=0
        )
        service = GraphBuilderService(builder=mock_builder)
        service.build_graph("test_proj", "some text", {}, "test graph")

        # Verify build_for_project was called with adapted data
        call_kwargs = mock_builder.build_for_project.call_args
        story_memory = call_kwargs.kwargs.get("story_memory") or call_kwargs[1].get("story_memory")
        assert "角色A" in story_memory["entity_registry"]
