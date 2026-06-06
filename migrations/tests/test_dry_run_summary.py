from pathlib import Path

from migrations.dry_run import build_dry_run_summary


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_build_dry_run_summary_reports_counts_and_zero_byte_assets(tmp_path):
    uploads = tmp_path / "uploads"
    project_root = uploads / "projects" / "proj_demo"
    system_root = uploads / "system"

    write_bytes(project_root / "project.json", b"{}")
    write_bytes(project_root / "story_graph.sqlite3", b"")
    write_bytes(project_root / "worldlines" / "prepare.sqlite3", b"prepare")
    write_bytes(project_root / "worldlines" / "sessions" / "ws_demo" / "session.json", b"{}")
    write_bytes(system_root / "task_runtime.sqlite3", b"task")

    summary = build_dry_run_summary(uploads)

    assert summary.project_count == 1
    assert summary.entry_count == 5
    assert summary.classification_counts["structured_import:projects"] == 1
    assert summary.classification_counts["structured_import:workflow_runs+workflow_steps"] == 1
    assert summary.classification_counts["projection_rebuild_reference:graph_query_projection"] == 1
    assert summary.zero_byte_assets == ("projects/proj_demo/story_graph.sqlite3",)
    assert summary.anomalies == ()


def test_build_dry_run_summary_keeps_inventory_anomalies_visible(tmp_path):
    uploads = tmp_path / "uploads"
    write_bytes(uploads / "projects" / "graph_only" / "worldlines" / "prepare.sqlite3", b"prepare")

    summary = build_dry_run_summary(uploads)

    assert summary.project_count == 1
    assert summary.anomalies == ("graph_only: missing project.json",)
