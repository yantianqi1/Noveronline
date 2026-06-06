import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, select

from migrations.import_only import run_import_only


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_archive_library_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        """
        create table archive_library (
          archive_id text primary key,
          project_id text not null,
          project_name text not null,
          entity_uuid text not null,
          entity_name text not null,
          entity_type text not null,
          agent_kind text not null,
          importance_tier text not null,
          recommended_importance_tier text not null,
          selected_importance_tier text not null,
          template_key text not null,
          template_version text not null,
          entity_role text not null,
          core_drive text not null,
          surface_mask text not null,
          hidden_tension text not null,
          relationship_summary text not null,
          agent_behavior_hint text not null,
          human_ai_relation_tag text not null,
          can_act_as_agent integer not null,
          notable_risks_json text not null,
          template_sections_json text not null,
          template_payload_json text not null,
          template_metadata_json text not null,
          synced_at text not null
        )
        """
    )
    connection.execute(
        """
        create table archive_agent_memory (
          memory_id text primary key,
          archive_id text not null,
          agent_id text not null,
          memory_type text not null,
          normalized_subject text not null,
          summary text not null,
          detail_json text not null,
          source_kind text not null,
          source_ref_id text not null,
          salience real not null,
          created_at text not null,
          updated_at text not null,
          memory_layer text not null,
          status text not null,
          version integer not null,
          parent_memory_id text not null,
          source_session_id text not null,
          source_branch_id text not null,
          evidence_json text not null,
          adopted_at text,
          rejected_at text
        )
        """
    )
    connection.execute(
        """
        create table archive_agent_memory_events (
          event_id text primary key,
          memory_id text not null,
          archive_id text not null,
          normalized_subject text not null,
          memory_type text not null,
          event_type text not null,
          memory_layer text not null,
          status text not null,
          version integer not null,
          parent_memory_id text not null,
          source_session_id text not null,
          source_branch_id text not null,
          summary text not null,
          evidence_json text not null,
          created_at text not null
        )
        """
    )
    connection.execute(
        """
        insert into archive_library
        values
        ('arc_1','proj_demo','档案项目','ent_1','沈夜','Character','character','protagonist','protagonist','protagonist','character.protagonist.v1','v1','主角','查清真相','冷静','怀疑','与宗门对立','先搜证据','human',1,'[]','[]','{}','{}','2026-04-11T00:00:00')
        """
    )
    connection.execute(
        """
        insert into archive_agent_memory
        values
        ('mem_1','arc_1','agent_1','event','密信','沈夜得到密信','{}','artifact','seed_analysis','0.8','2026-04-11T00:00:00','2026-04-11T00:00:00','canon','active',1,'','','','[]','2026-04-11T00:00:00',null)
        """
    )
    connection.execute(
        """
        insert into archive_agent_memory_events
        values
        ('evt_1','mem_1','arc_1','密信','event','bootstrap_legacy','canon','active',1,'','','','沈夜得到密信','[]','2026-04-11T00:00:00')
        """
    )
    connection.commit()
    connection.close()


def test_import_only_imports_archive_library_sqlite(tmp_path):
    uploads = tmp_path / "uploads"
    db_path = tmp_path / "import.db"
    write_text(
        uploads / "projects" / "proj_demo" / "project.json",
        '{"project_id":"proj_demo","name":"档案导入项目","status":"created","created_at":"2026-04-11T00:00:00","updated_at":"2026-04-11T00:00:00"}',
    )
    create_archive_library_db(uploads / "system" / "archive_library.sqlite3")

    report = run_import_only(uploads, f"sqlite:///{db_path}")

    assert "system/archive_library.sqlite3 -> archives+memories+memory_events" not in report.blocked_targets

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        entities = connection.execute(select(report.metadata.tables["entities"])).all()
        archives = connection.execute(select(report.metadata.tables["archives"])).all()
        memories = connection.execute(select(report.metadata.tables["memories"])).all()
        memory_events = connection.execute(select(report.metadata.tables["memory_events"])).all()

    assert len(entities) == 1
    assert entities[0].canonical_name == "沈夜"
    assert len(archives) == 1
    assert archives[0].archive_id == "arc_1"
    assert len(memories) == 1
    assert memories[0].memory_id == "mem_1"
    assert len(memory_events) == 1
    assert memory_events[0].memory_event_id == "evt_1"
