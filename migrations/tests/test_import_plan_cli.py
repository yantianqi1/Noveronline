import json
import subprocess
import sys
from pathlib import Path


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_import_plan_cli_prints_json_payload(tmp_path):
    uploads = tmp_path / "uploads"
    write_bytes(uploads / "projects" / "proj_demo" / "project.json", b"{}")

    result = subprocess.run(
        [sys.executable, "-m", "migrations.import_plan", str(uploads)],
        cwd="/Volumes/Fanxiang S500Pro/项目/MiroFish-Novel",
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert payload["entry_count"] == 1
    assert payload["entries"][0]["relative_path"] == "projects/proj_demo/project.json"
