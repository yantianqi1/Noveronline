import json
import subprocess
import sys
from pathlib import Path


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_import_only_cli_prints_report_json(tmp_path):
    uploads = tmp_path / "uploads"
    db_path = tmp_path / "import.db"
    write_text(
        uploads / "projects" / "proj_demo" / "project.json",
        '{"project_id":"proj_demo","name":"CLI项目","status":"created","created_at":"2026-04-11T00:00:00","updated_at":"2026-04-11T00:00:00"}',
    )

    result = subprocess.run(
        [sys.executable, "-m", "migrations.import_only", str(uploads), f"sqlite:///{db_path}"],
        cwd="/Volumes/Fanxiang S500Pro/项目/MiroFish-Novel",
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert payload["workspace_count"] == 1
    assert payload["project_count"] == 1
    assert payload["blocked_targets"] == []
