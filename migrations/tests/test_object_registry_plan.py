from pathlib import Path

from migrations.object_registry_plan import build_object_registry_plan


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_object_registry_plan_collects_manuscripts_and_artifact_payloads(tmp_path):
    uploads = tmp_path / "uploads"
    project_root = uploads / "projects" / "proj_demo"

    write_bytes(project_root / "project.json", b"{}")
    write_bytes(project_root / "files" / "chapter1.txt", b"chapter-1")
    write_bytes(project_root / "seed_analysis.json", b"{\"characters\": []}")
    write_bytes(project_root / "analysis_blocks.json", b"{\"blocks\": []}")
    write_bytes(project_root / "story_graph.sqlite3", b"")

    plan = build_object_registry_plan(uploads)

    assert plan.entry_count == 3
    by_path = {entry.relative_path: entry for entry in plan.entries}
    assert by_path["projects/proj_demo/files/chapter1.txt"].registry_kind == "manuscript_source"
    assert by_path["projects/proj_demo/seed_analysis.json"].registry_kind == "artifact_payload"
    assert by_path["projects/proj_demo/analysis_blocks.json"].registry_kind == "artifact_payload"
    assert "story_graph.sqlite3" not in "".join(by_path)


def test_object_registry_plan_uses_deterministic_storage_keys(tmp_path):
    uploads = tmp_path / "uploads"
    write_bytes(uploads / "projects" / "proj_demo" / "files" / "chapter1.txt", b"chapter-1")

    first = build_object_registry_plan(uploads)
    second = build_object_registry_plan(uploads)

    assert first.entries[0].storage_key == second.entries[0].storage_key
