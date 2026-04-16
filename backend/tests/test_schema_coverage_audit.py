import io
import json
import sqlite3
from pathlib import Path


def _make_sqlite(path: Path, statements: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        for statement in statements:
            connection.execute(statement)
        connection.commit()


def test_audit_schema_coverage_reports_differences(tmp_path):
    upload_root = tmp_path / "uploads"
    project_dir = upload_root / "projects" / "project-1"

    _make_sqlite(
        project_dir / "novel.sqlite3",
        [
            "CREATE TABLE entities (entity_id TEXT, name TEXT, legacy_tag TEXT)",
            "CREATE TABLE bespoke_legacy_only (id TEXT PRIMARY KEY, note TEXT)",
        ],
    )
    _make_sqlite(
        project_dir / "story_graph.sqlite3",
        [
            "CREATE TABLE graph_nodes (uuid TEXT, name TEXT, summary TEXT, attributes_json TEXT, evidence_refs_json TEXT)",
        ],
    )
    (project_dir / "seed_analysis.json").write_text("{}", encoding="utf-8")

    from scripts.audit_schema_coverage import audit_schema_coverage

    report = audit_schema_coverage(
        upload_root,
        json_artifact_rules={
            "seed_analysis.json": {
                "tables": {
                    "relationships": ["relation_id", "source_id", "target_id"],
                    "missing_target_table": ["id"],
                }
            }
        },
    )

    assert "missing_target_table" in report["missing_tables"]
    assert report["missing_columns"]["entities"] == ["legacy_tag"]
    assert report["legacy_only_tables"] == ["bespoke_legacy_only"]
    assert "agent_registry" in report["unified_only_tables"]


def test_main_writes_json_report_to_stdout(tmp_path):
    upload_root = tmp_path / "uploads"
    project_dir = upload_root / "projects" / "project-2"

    _make_sqlite(
        project_dir / "novel.sqlite3",
        ["CREATE TABLE entities (entity_id TEXT, name TEXT, legacy_tag TEXT)"],
    )
    (project_dir / "seed_analysis.json").write_text("{}", encoding="utf-8")

    from scripts.audit_schema_coverage import main

    buffer = io.StringIO()
    main(
        ["--upload-root", str(upload_root)],
        stdout=buffer,
        json_artifact_rules={
            "seed_analysis.json": {
                "tables": {
                    "relationships": ["relation_id"],
                }
            }
        },
    )

    payload = json.loads(buffer.getvalue())
    assert sorted(payload) == [
        "legacy_only_tables",
        "missing_columns",
        "missing_tables",
        "unified_only_tables",
    ]
    assert payload["missing_columns"]["entities"] == ["legacy_tag"]
