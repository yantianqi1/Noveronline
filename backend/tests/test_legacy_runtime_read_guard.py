from __future__ import annotations

import io
import json
from pathlib import Path


def test_runtime_read_guard_detects_new_legacy_runtime_reads(tmp_path):
    repo_root = tmp_path / "repo"
    bad_file = repo_root / "backend" / "app" / "services" / "new_feature.py"
    bad_file.parent.mkdir(parents=True)
    bad_file.write_text(
        "\n".join(
            [
                "import sqlite3",
                "from app.models.project import ProjectManager",
                "from app.services.reading_notes_manager import ReadingNotesManager",
                "",
                "def load(project_id):",
                "    ProjectManager.load_project_json(project_id, 'seed_analysis.json')",
                "    ProjectManager.save_project_json(project_id, 'seed_analysis.json', {})",
                "    ReadingNotesManager.load('reading_notes.json')",
                "    conn.execute('SELECT * FROM sqlite_master')",
                "    sqlite3.connect('novel.sqlite3')",
            ]
        ),
        encoding="utf-8",
    )

    from scripts.audit_legacy_runtime_reads import audit_legacy_runtime_reads

    report = audit_legacy_runtime_reads(repo_root, allowed_paths=set())

    assert [item["marker"] for item in report["violations"]] == [
        "ProjectManager.load_project_json(",
        "ProjectManager.save_project_json(",
        "ReadingNotesManager.load(",
        "sqlite_master",
        "sqlite3.connect(",
        "novel.sqlite3",
    ]
    assert report["unauthorized_violations"] == report["violations"]


def test_current_runtime_read_guard_has_no_unregistered_violations():
    repo_root = Path(__file__).resolve().parents[2]

    from scripts.audit_legacy_runtime_reads import audit_legacy_runtime_reads

    report = audit_legacy_runtime_reads(repo_root)

    assert report["unauthorized_violations"] == []


def test_runtime_read_guard_allowlist_no_longer_includes_runtime_artifact_reads():
    from scripts.audit_legacy_runtime_reads import DEFAULT_ALLOWED_PATHS

    assert "backend/app/main.py" not in DEFAULT_ALLOWED_PATHS
    assert "backend/app/services/seed_extract_runner.py" not in DEFAULT_ALLOWED_PATHS
    assert "backend/app/services/assets/unified_asset_view.py" not in DEFAULT_ALLOWED_PATHS
    assert "backend/app/services/worldline_engine.py" not in DEFAULT_ALLOWED_PATHS
    assert "backend/app/services/archive_library_service.py" not in DEFAULT_ALLOWED_PATHS
    assert "backend/app/config.py" not in DEFAULT_ALLOWED_PATHS
    assert "backend/app/api_fastapi/writer_agent.py" not in DEFAULT_ALLOWED_PATHS


def test_runtime_read_guard_cli_writes_json_report():
    from scripts.audit_legacy_runtime_reads import main

    buffer = io.StringIO()
    exit_code = main([], stdout=buffer)

    assert exit_code == 0
    payload = json.loads(buffer.getvalue())
    assert sorted(payload) == ["allowed_paths", "scanned_files", "unauthorized_violations", "violations"]
