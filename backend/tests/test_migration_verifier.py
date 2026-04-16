from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, text

from app.database import init_db


def _project_dir(upload_root: Path, project_id: str) -> Path:
    project_dir = upload_root / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def _write_project_meta(project_dir: Path, project_id: str) -> None:
    (project_dir / "project.json").write_text(
        json.dumps({"project_id": project_id, "name": "Verifier Demo"}, ensure_ascii=False),
        encoding="utf-8",
    )


def _create_legacy_novel_db(path: Path, *, entity_name: str = "Lin", entity_summary: str = "Hero") -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                summary TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO entities (entity_id, name, entity_type, summary, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("ent_1", entity_name, "character", entity_summary, "2026-04-14T00:00:00", "2026-04-14T00:00:00"),
        )
        conn.commit()
    finally:
        conn.close()


def _create_legacy_graph_db(path: Path, *, summary: str = "Lead node") -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE graph_nodes (
                uuid TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                summary TEXT NOT NULL,
                attributes_json TEXT NOT NULL,
                evidence_refs_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO graph_nodes (uuid, name, summary, attributes_json, evidence_refs_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("node_1", "Lin", summary, "{}", "[]"),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_matching_unified_rows(engine, project_id: str, *, entity_summary: str = "Hero", graph_summary: str = "Lead node") -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO entities (
                    entity_id, project_id, name, entity_type, summary, created_at, updated_at
                ) VALUES (
                    :entity_id, :project_id, :name, :entity_type, :summary, :created_at, :updated_at
                )
                """
            ),
            {
                "entity_id": "ent_1",
                "project_id": project_id,
                "name": "Lin",
                "entity_type": "character",
                "summary": entity_summary,
                "created_at": "2026-04-14T00:00:00",
                "updated_at": "2026-04-14T00:00:00",
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO graph_nodes (
                    project_id, uuid, name, summary, attributes_json, evidence_refs_json
                ) VALUES (
                    :project_id, :uuid, :name, :summary, :attributes_json, :evidence_refs_json
                )
                """
            ),
            {
                "project_id": project_id,
                "uuid": "node_1",
                "name": "Lin",
                "summary": graph_summary,
                "attributes_json": "{}",
                "evidence_refs_json": "[]",
            },
        )


def test_verify_project_returns_pass_report_for_matching_data(tmp_path):
    from app.services.migration_verifier import MigrationVerifier

    upload_root = tmp_path / "uploads"
    project_id = "proj_demo"
    project_dir = _project_dir(upload_root, project_id)
    _write_project_meta(project_dir, project_id)
    _create_legacy_novel_db(project_dir / "novel.sqlite3")
    _create_legacy_graph_db(project_dir / "story_graph.sqlite3")

    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    _insert_matching_unified_rows(engine, project_id)

    report = MigrationVerifier(upload_root=upload_root, engine=engine).verify_project(project_id)

    assert report["project_id"] == project_id
    assert report["overall_verdict"] == "pass"
    assert report["legacy_sources"]["project_meta"]["exists"] is True
    assert report["legacy_sources"]["novel_db"]["exists"] is True
    assert report["legacy_sources"]["story_graph_db"]["exists"] is True
    assert report["domains"]["novel"]["status"] == "pass"
    assert report["domains"]["story_graph"]["status"] == "pass"
    assert report["domains"]["novel"]["legacy_row_count"] == 1
    assert report["domains"]["novel"]["unified_row_count"] == 1
    assert report["domains"]["novel"]["mismatch_count"] == 0
    assert report["domains"]["story_graph"]["tables"][0]["table"] == "graph_nodes"


def test_verify_project_reports_missing_rows_and_field_mismatches(tmp_path):
    from app.services.migration_verifier import MigrationVerifier

    upload_root = tmp_path / "uploads"
    project_id = "proj_problem"
    project_dir = _project_dir(upload_root, project_id)
    _write_project_meta(project_dir, project_id)
    _create_legacy_novel_db(project_dir / "novel.sqlite3", entity_summary="Legacy Hero")
    _create_legacy_graph_db(project_dir / "story_graph.sqlite3", summary="Legacy Node")

    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    _insert_matching_unified_rows(engine, project_id, entity_summary="Unified Hero", graph_summary="Changed Node")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM graph_nodes WHERE project_id = :project_id"), {"project_id": project_id})

    report = MigrationVerifier(upload_root=upload_root, engine=engine).verify_project(project_id)

    assert report["overall_verdict"] == "fail"
    assert report["risk_level"] == "high"

    novel_domain = report["domains"]["novel"]
    assert novel_domain["status"] == "fail"
    assert novel_domain["mismatch_count"] == 1
    assert novel_domain["tables"][0]["field_mismatches"][0]["primary_key"] == {"entity_id": "ent_1"}
    assert novel_domain["tables"][0]["field_mismatches"][0]["differing_fields"] == ["summary"]

    graph_domain = report["domains"]["story_graph"]
    assert graph_domain["status"] == "fail"
    assert graph_domain["missing_in_unified_count"] == 1
    assert graph_domain["tables"][0]["missing_in_unified"][0] == {"uuid": "node_1"}


def test_verify_project_migration_cli_prints_json(tmp_path, capsys):
    from scripts.verify_project_migration import main

    upload_root = tmp_path / "uploads"
    project_id = "proj_cli"
    project_dir = _project_dir(upload_root, project_id)
    _write_project_meta(project_dir, project_id)
    _create_legacy_novel_db(project_dir / "novel.sqlite3")
    _create_legacy_graph_db(project_dir / "story_graph.sqlite3")

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(engine)
    _insert_matching_unified_rows(engine, project_id)

    exit_code = main(
        [
            "--project-id",
            project_id,
            "--upload-root",
            str(upload_root),
            "--database-url",
            f"sqlite:///{db_path}",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["project_id"] == project_id
    assert payload["overall_verdict"] == "pass"
