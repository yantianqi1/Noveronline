from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class AssetImportDecision:
    action: str
    target: str
    reason: str


def _decision(action: str, target: str, reason: str) -> AssetImportDecision:
    return AssetImportDecision(action=action, target=target, reason=reason)


def classify_legacy_asset(relative_path: str) -> AssetImportDecision:
    path = PurePosixPath(relative_path)
    parts = path.parts
    if _is_system_worldline_asset(parts):
        return _classify_system_worldline_asset(parts)
    if parts[:1] == ("system",):
        return _classify_system_asset(path.name)
    if len(parts) < 3 or parts[0] != "projects":
        return _decision("anomaly", "manual_review", "path is outside known system/projects roots")
    if parts[2] == "files":
        return _decision("structured_import", "manuscripts+artifact_objects", "uploaded manuscript asset")
    if len(parts) >= 4 and parts[2] == "worldlines":
        return _classify_worldline_asset(parts)
    return _classify_project_root_asset(path.name)


def _classify_system_asset(filename: str) -> AssetImportDecision:
    mapping = {
        "task_runtime.sqlite3": ("structured_import", "workflow_runs+workflow_steps"),
        "archive_library.sqlite3": ("structured_import", "archives+memories+memory_events"),
        "chapter_meta.sqlite3": ("structured_import", "chapters+chapter_history_items"),
        "llm_facility.sqlite3": ("structured_import", "llm_channels+llm_models+llm_module_bindings"),
    }
    if filename not in mapping:
        return _decision("anomaly", "manual_review", "unknown system sqlite asset")
    action, target = mapping[filename]
    return _decision(action, target, "frozen system sqlite mapping")


def _is_system_worldline_asset(parts: tuple[str, ...]) -> bool:
    return len(parts) >= 6 and parts[:3] == ("system", "global_worldlines", "graphs")


def _classify_system_worldline_asset(parts: tuple[str, ...]) -> AssetImportDecision:
    if parts[-2:] == ("worldlines", "prepare.sqlite3"):
        return _decision("structured_import", "worldline_preparations", "system global worldline prepare source")
    if parts[-2:] == ("worldlines", "runtime.sqlite3"):
        return _decision(
            "structured_import",
            "session_agents+agent_state_snapshots+agent_actions+agent_dialogues+relation_events",
            "system global worldline runtime source",
        )
    if len(parts) >= 8 and parts[-1] == "session.json" and parts[-3] == "sessions":
        return _decision(
            "structured_import",
            "worldline_sessions+world_states+timeline_events",
            "system global worldline session source",
        )
    return _decision("anomaly", "manual_review", "unknown system global worldline asset")


def _classify_worldline_asset(parts: tuple[str, ...]) -> AssetImportDecision:
    if parts[3:] == ("prepare.sqlite3",):
        return _decision("structured_import", "worldline_preparations", "prepare runtime source")
    if parts[3:] == ("runtime.sqlite3",):
        return _decision(
            "structured_import",
            "session_agents+agent_state_snapshots+agent_actions+agent_dialogues+relation_events",
            "worldline runtime source",
        )
    if len(parts) >= 6 and parts[3] == "sessions" and parts[-1] == "session.json":
        return _decision(
            "structured_import",
            "worldline_sessions+world_states+timeline_events",
            "worldline session source",
        )
    if parts[3:] == ("index.json",):
        return _decision("projection_rebuild_reference", "worldline_session_index", "legacy session index cache")
    return _decision("anomaly", "manual_review", "unknown worldline asset")


def _classify_project_root_asset(filename: str) -> AssetImportDecision:
    mapping = {
        "project.json": ("structured_import", "projects"),
        "extracted_text.txt": ("structured_import", "artifacts"),
        "chapter_segments.json": ("structured_import", "artifacts+chapter_segment_projection"),
        "analysis_blocks.json": ("artifact_archive", "artifacts"),
        "anchor_points.json": ("structured_import", "artifacts+anchor_point_projection"),
        "story_memory.json": ("structured_import", "artifacts+story_memory_projection"),
        "story_memory_snapshots.json": ("artifact_archive", "artifacts"),
        "block_analyses.json": ("artifact_archive", "artifacts"),
        "chapter_cards.json": ("structured_import", "artifacts+chapters+chapter_history_items"),
        "chapter_continuity.json": ("structured_import", "artifacts+chapter_continuity_projection"),
        "consistency_report.json": ("structured_import", "artifacts+consistency_warning_projection"),
        "seed_analysis.json": ("structured_import", "artifacts+seed_entities_projection"),
        "narrative_archives.json": ("structured_import", "artifacts+archives"),
        "parallel_world_config.json": ("artifact_archive", "artifacts"),
        "reviewer_rules.json": ("structured_import", "workspace_settings.reviewer_rules"),
        "story_graph.json": ("structured_import", "graph_snapshots"),
        "story_graph.sqlite3": ("projection_rebuild_reference", "graph_query_projection"),
        "skeleton_timeline.json": ("artifact_archive", "artifacts"),
    }
    if filename not in mapping:
        return _decision("anomaly", "manual_review", "unknown project-root asset")
    action, target = mapping[filename]
    return _decision(action, target, "frozen project asset mapping")
