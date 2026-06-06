from hashlib import sha256
from pathlib import Path

from migrations.checksums.manifest import build_checksum_manifest
from migrations.json_importers.legacy_inventory import scan_legacy_root


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_build_checksum_manifest_collects_system_and_project_assets(tmp_path):
    uploads = tmp_path / "uploads"
    project_root = uploads / "projects" / "proj_demo"
    system_root = uploads / "system"

    write_bytes(project_root / "project.json", b"{}")
    write_bytes(project_root / "files" / "chapter1.txt", b"chapter-1")
    write_bytes(project_root / "worldlines" / "prepare.sqlite3", b"prepare-db")
    write_bytes(project_root / "worldlines" / "sessions" / "ws_demo" / "session.json", b"{\"session\": true}")
    write_bytes(system_root / "task_runtime.sqlite3", b"task-db")
    write_bytes(
        system_root / "global_worldlines" / "graphs" / "graph_demo" / "worldlines" / "runtime.sqlite3",
        b"runtime-db",
    )

    report = scan_legacy_root(uploads)
    manifest = build_checksum_manifest(report)

    assert manifest.entry_count == 6
    assert manifest.entries[0].scope in {"project", "system"}
    entry_map = {entry.relative_path: entry for entry in manifest.entries}
    assert entry_map["projects/proj_demo/project.json"].owner_id == "proj_demo"
    assert entry_map["projects/proj_demo/files/chapter1.txt"].sha256 == sha256(b"chapter-1").hexdigest()
    assert entry_map["projects/proj_demo/worldlines/prepare.sqlite3"].size_bytes == len(b"prepare-db")
    assert entry_map["system/task_runtime.sqlite3"].owner_id == "system"
    assert entry_map["system/global_worldlines/graphs/graph_demo/worldlines/runtime.sqlite3"].size_bytes == len(
        b"runtime-db"
    )


def test_build_checksum_manifest_sorts_entries_by_scope_owner_and_path(tmp_path):
    uploads = tmp_path / "uploads"
    write_bytes(uploads / "projects" / "proj_b" / "project.json", b"b")
    write_bytes(uploads / "projects" / "proj_a" / "project.json", b"a")

    manifest = build_checksum_manifest(scan_legacy_root(uploads))

    assert [entry.relative_path for entry in manifest.entries] == [
        "projects/proj_a/project.json",
        "projects/proj_b/project.json",
    ]
