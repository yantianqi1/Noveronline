import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, select

from migrations.import_only import run_import_only


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_empty_prepare_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        """
        create table prepare_runs (
          prepare_id text primary key,
          task_id text not null,
          project_id text,
          graph_id text not null,
          session_scope text not null,
          status text not null,
          stage text not null,
          can_start integer not null,
          focus_question text not null,
          branch_count integer not null,
          source_summary_json text not null,
          source_json text not null,
          world_variables_json text not null,
          input_payload_json text not null,
          source_archive_ids_json text not null,
          source_project_ids_json text not null,
          source_archive_count integer not null,
          started_session_id text not null,
          error text,
          created_at text not null,
          updated_at text not null
        )
        """
    )
    connection.execute(
        """
        create table prepared_agent_dossiers (
          prepare_id text not null,
          agent_id text not null,
          agent_kind text not null,
          display_name text not null,
          source_archive_id text not null,
          source_entity_uuid text not null,
          importance_tier text not null,
          template_key text not null,
          template_version text not null,
          template_sections_json text not null,
          model_name text not null,
          validation_errors_json text not null,
          public_profile_json text not null,
          private_profile_json text not null,
          runtime_seed_state_json text not null,
          relationship_view_json text not null,
          memory_seed_summary_json text not null,
          source_evidence_summary_json text not null,
          created_at text not null,
          updated_at text not null
        )
        """
    )
    connection.commit()
    connection.close()


def create_orphan_session_json(path: Path) -> None:
    payload = {
        "session_id": "ws_orphan",
        "project_id": None,
        "graph_id": "graph_orphan",
        "simulation_goal": "观察孤立世界线",
        "focus_question": "没有项目时能否保留世界线资产",
        "branch_count": 1,
        "session_scope": "project",
        "status": "running",
        "branches": [
            {
                "branch_id": "main",
                "title": "当前世界",
                "core_change": "孤立世界继续推进",
                "current_step": 1,
                "status": "running",
                "timeline": [
                    {
                        "event_id": "evt_orphan",
                        "step": 1,
                        "title": "孤立事件",
                        "summary": "即使没有 project.json，也应显式保留 session 资产。",
                        "event_type": "evolution",
                        "status": "canon",
                        "confidence": "high",
                        "event_source": "archive_based",
                        "created_at": "2026-04-11T00:00:00",
                    }
                ],
                "pending_variables": [],
                "pending_actions": [],
                "actor_states": {},
                "organization_states": {},
                "relationship_states": [],
                "created_at": "2026-04-11T00:00:00",
                "updated_at": "2026-04-11T00:00:00",
            }
        ],
        "world_variables": [],
        "timeline_focus": [],
        "agent_behavior_axes": [],
        "source_summary": {},
        "created_at": "2026-04-11T00:00:00",
        "updated_at": "2026-04-11T00:00:00",
    }
    write_text(path, json.dumps(payload, ensure_ascii=False))


def test_import_only_imports_orphan_worldline_assets_without_fake_project(tmp_path):
    uploads = tmp_path / "uploads"
    db_path = tmp_path / "import.db"
    create_empty_prepare_db(uploads / "projects" / "graph_only" / "worldlines" / "prepare.sqlite3")
    create_orphan_session_json(uploads / "projects" / "graph_only" / "worldlines" / "sessions" / "ws_orphan" / "session.json")

    report = run_import_only(uploads, f"sqlite:///{db_path}")

    assert "graph_only: missing project.json" in report.anomalies
    assert report.blocked_targets == ()

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        sessions = connection.execute(select(report.metadata.tables["worldline_sessions"])).all()
        states = connection.execute(select(report.metadata.tables["world_states"])).all()
        events = connection.execute(select(report.metadata.tables["timeline_events"])).all()

    assert len(sessions) == 1
    assert sessions[0].project_id is None
    assert len(states) == 1
    assert len(events) == 1
