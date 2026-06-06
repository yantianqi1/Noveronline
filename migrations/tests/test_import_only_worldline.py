import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, select

from migrations.import_only import run_import_only


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_prepare_db(path: Path) -> None:
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
    connection.execute(
        """
        insert into prepare_runs
        values
        ('prep_1','task_1','proj_demo','graph_1','project','completed','done',1,'主角会如何推进','1','{}','{}','[]','{}','[]','[]',0,'ws_1',null,'2026-04-11T00:00:00','2026-04-11T00:00:00')
        """
    )
    connection.execute(
        """
        insert into prepared_agent_dossiers
        values
        ('prep_1','agent_1','character','沈夜','','ent_1','protagonist','character.protagonist.v1','v1','[]','model-a','[]','{}','{}','{}','{}','{}','{}','2026-04-11T00:00:00','2026-04-11T00:00:00')
        """
    )
    connection.commit()
    connection.close()


def create_session_json(path: Path) -> None:
    payload = {
        "session_id": "ws_1",
        "project_id": "proj_demo",
        "graph_id": "graph_1",
        "simulation_goal": "观察主角推进路径",
        "focus_question": "主角会如何推进",
        "branch_count": 1,
        "prepare_id": "prep_1",
        "session_scope": "project",
        "status": "running",
        "branches": [
            {
                "branch_id": "main",
                "title": "当前世界",
                "core_change": "主角决定主动追查",
                "narrative_value": "提高主动性",
                "current_step": 1,
                "status": "running",
                "key_agents": ["沈夜"],
                "expected_conflicts": ["玄霄宗阻拦"],
                "actor_states": {},
                "organization_states": {},
                "relationship_states": [],
                "timeline": [
                    {
                        "event_id": "evt_1",
                        "step": 1,
                        "title": "主动追查",
                        "summary": "沈夜决定主动追查密信来源。",
                        "event_type": "evolution",
                        "status": "canon",
                        "confidence": "high",
                        "event_source": "archive_based",
                        "created_at": "2026-04-11T00:00:00",
                    }
                ],
                "pending_variables": [],
                "pending_actions": [],
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


def test_import_only_imports_worldline_prepare_and_session(tmp_path):
    uploads = tmp_path / "uploads"
    db_path = tmp_path / "import.db"
    write_text(
        uploads / "projects" / "proj_demo" / "project.json",
        '{"project_id":"proj_demo","name":"世界线导入项目","status":"created","created_at":"2026-04-11T00:00:00","updated_at":"2026-04-11T00:00:00"}',
    )
    create_prepare_db(uploads / "projects" / "proj_demo" / "worldlines" / "prepare.sqlite3")
    create_session_json(uploads / "projects" / "proj_demo" / "worldlines" / "sessions" / "ws_1" / "session.json")

    report = run_import_only(uploads, f"sqlite:///{db_path}")

    assert "projects/proj_demo/worldlines/prepare.sqlite3 -> worldline_preparations" not in report.blocked_targets
    assert (
        "projects/proj_demo/worldlines/sessions/ws_1/session.json -> worldline_sessions+world_states+timeline_events"
        not in report.blocked_targets
    )

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        preparations = connection.execute(select(report.metadata.tables["worldline_preparations"])).all()
        dossiers = connection.execute(select(report.metadata.tables["prepared_agent_dossiers"])).all()
        sessions = connection.execute(select(report.metadata.tables["worldline_sessions"])).all()
        world_states = connection.execute(select(report.metadata.tables["world_states"])).all()
        timeline_events = connection.execute(select(report.metadata.tables["timeline_events"])).all()

    assert len(preparations) == 1
    assert preparations[0].prepare_id == "prep_1"
    assert len(dossiers) == 1
    assert dossiers[0].agent_id == "agent_1"
    assert len(sessions) == 1
    assert sessions[0].session_id == "ws_1"
    assert len(world_states) == 1
    assert world_states[0].version_no == 1
    assert len(timeline_events) == 1
    assert timeline_events[0].timeline_event_id == "evt_1"
