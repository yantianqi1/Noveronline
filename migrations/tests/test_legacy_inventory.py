from pathlib import Path

from migrations.json_importers.legacy_inventory import scan_legacy_root


def write_text(path: Path, content: str = "{}") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_scan_legacy_root_collects_projects_worldlines_and_system_assets(tmp_path):
    uploads = tmp_path / "uploads"
    project_root = uploads / "projects" / "proj_demo"
    system_root = uploads / "system"

    write_text(project_root / "project.json")
    write_text(project_root / "seed_analysis.json")
    write_text(project_root / "story_graph.sqlite3", "sqlite")
    write_text(project_root / "files" / "chapter1.txt", "chapter")
    write_text(project_root / "worldlines" / "prepare.sqlite3", "sqlite")
    write_text(project_root / "worldlines" / "runtime.sqlite3", "sqlite")
    write_text(project_root / "worldlines" / "sessions" / "ws_demo" / "session.json")

    write_text(system_root / "task_runtime.sqlite3", "sqlite")
    write_text(system_root / "archive_library.sqlite3", "sqlite")
    write_text(system_root / "global_worldlines" / "graphs" / "graph_demo" / "worldlines" / "runtime.sqlite3", "sqlite")
    write_text(
        system_root / "global_worldlines" / "graphs" / "graph_demo" / "worldlines" / "sessions" / "ws_demo" / "session.json"
    )

    report = scan_legacy_root(uploads)

    assert report.project_count == 1
    assert sorted(report.system_sqlite_names) == ["archive_library.sqlite3", "task_runtime.sqlite3"]
    assert report.system_worldline_runtime_files[0].name == "runtime.sqlite3"
    assert report.system_worldline_session_files[0].name == "session.json"
    project = report.projects[0]
    assert project.project_id == "proj_demo"
    assert project.project_file.name == "project.json"
    assert project.manuscript_files[0].name == "chapter1.txt"
    assert sorted(path.name for path in project.top_level_json_files) == ["project.json", "seed_analysis.json"]
    assert sorted(path.name for path in project.top_level_sqlite_files) == ["story_graph.sqlite3"]
    assert project.worldline_prepare_db.name == "prepare.sqlite3"
    assert project.worldline_runtime_db.name == "runtime.sqlite3"
    assert project.worldline_session_files[0].name == "session.json"
    assert report.anomalies == ()


def test_scan_legacy_root_reports_missing_project_json_as_anomaly(tmp_path):
    uploads = tmp_path / "uploads"
    project_root = uploads / "projects" / "proj_missing"

    write_text(project_root / "seed_analysis.json")

    report = scan_legacy_root(uploads)

    assert report.project_count == 1
    assert report.projects[0].project_file is None
    assert report.anomalies == ("proj_missing: missing project.json",)
