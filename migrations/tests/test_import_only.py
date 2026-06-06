from pathlib import Path

from sqlalchemy import create_engine, select

from migrations.import_only import run_import_only


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_import_only_persists_project_objects_manuscripts_and_artifacts(tmp_path):
    uploads = tmp_path / "uploads"
    project_root = uploads / "projects" / "proj_demo"
    db_path = tmp_path / "import.db"

    write_text(
        project_root / "project.json",
        '{"project_id":"proj_demo","name":"导入测试项目","status":"created","created_at":"2026-04-11T00:00:00","updated_at":"2026-04-11T00:00:00","analysis_summary":"seed ready"}',
    )
    write_bytes(project_root / "files" / "chapter1.txt", b"chapter-1")
    write_text(project_root / "analysis_blocks.json", '{"blocks": []}')
    write_bytes(project_root / "story_graph.sqlite3", b"")

    report = run_import_only(uploads, f"sqlite:///{db_path}")

    assert report.workspace_count == 1
    assert report.project_count == 1
    assert report.artifact_object_count == 2
    assert report.manuscript_count == 1
    assert report.artifact_count == 1
    assert report.skipped_rebuild_refs == ("projects/proj_demo/story_graph.sqlite3",)
    assert report.anomalies == ()

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        workspace_rows = connection.execute(select(report.metadata.tables["workspaces"])).all()
        project_rows = connection.execute(select(report.metadata.tables["projects"])).all()
        manuscript_rows = connection.execute(select(report.metadata.tables["manuscripts"])).all()
        artifact_rows = connection.execute(select(report.metadata.tables["artifacts"])).all()

    assert len(workspace_rows) == 1
    assert len(project_rows) == 1
    assert project_rows[0].project_id == "proj_demo"
    assert project_rows[0].name == "导入测试项目"
    assert len(manuscript_rows) == 1
    assert len(artifact_rows) == 1


def test_import_only_surfaces_inventory_anomalies_without_hiding_them(tmp_path):
    uploads = tmp_path / "uploads"
    write_bytes(uploads / "projects" / "graph_only" / "worldlines" / "prepare.sqlite3", b"prepare")

    report = run_import_only(uploads, f"sqlite:///{tmp_path / 'import.db'}")

    assert report.project_count == 0
    assert report.anomalies == ("graph_only: missing project.json",)
