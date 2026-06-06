from pathlib import Path

from migrations.import_plan import build_import_plan


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_import_plan_splits_direct_db_and_object_then_db_assets(tmp_path):
    uploads = tmp_path / "uploads"
    project_root = uploads / "projects" / "proj_demo"
    system_root = uploads / "system"

    write_bytes(project_root / "project.json", b"{}")
    write_bytes(project_root / "files" / "chapter1.txt", b"chapter-1")
    write_bytes(project_root / "analysis_blocks.json", b"{\"blocks\": []}")
    write_bytes(project_root / "worldlines" / "prepare.sqlite3", b"prepare")
    write_bytes(project_root / "worldlines" / "sessions" / "ws_demo" / "session.json", b"{}")
    write_bytes(project_root / "story_graph.sqlite3", b"")
    write_bytes(system_root / "task_runtime.sqlite3", b"task")
    write_bytes(system_root / "global_worldlines" / "graphs" / "graph_demo" / "worldlines" / "runtime.sqlite3", b"runtime")

    plan = build_import_plan(uploads)

    assert plan.entry_count == 7
    by_path = {entry.relative_path: entry for entry in plan.entries}
    assert by_path["projects/proj_demo/project.json"].execution_mode == "direct_db"
    assert by_path["projects/proj_demo/files/chapter1.txt"].execution_mode == "object_then_db"
    assert by_path["projects/proj_demo/files/chapter1.txt"].object_storage_key is not None
    assert by_path["projects/proj_demo/analysis_blocks.json"].execution_mode == "object_then_db"
    assert by_path["projects/proj_demo/worldlines/prepare.sqlite3"].execution_mode == "direct_db"
    assert by_path["projects/proj_demo/worldlines/sessions/ws_demo/session.json"].execution_mode == "direct_db"
    assert by_path["system/global_worldlines/graphs/graph_demo/worldlines/runtime.sqlite3"].execution_mode == "direct_db"
    assert "projects/proj_demo/story_graph.sqlite3" not in by_path


def test_import_plan_keeps_inventory_anomalies_and_skip_counts(tmp_path):
    uploads = tmp_path / "uploads"
    write_bytes(uploads / "projects" / "graph_only" / "worldlines" / "prepare.sqlite3", b"prepare")
    write_bytes(uploads / "projects" / "graph_only" / "story_graph.sqlite3", b"")

    plan = build_import_plan(uploads)

    assert plan.anomalies == ("graph_only: missing project.json",)
    assert plan.skipped_rebuild_refs == ("projects/graph_only/story_graph.sqlite3",)
