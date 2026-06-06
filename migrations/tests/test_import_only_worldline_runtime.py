import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, select

from migrations.import_only import run_import_only


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_session_json(path: Path, session_id: str, project_id: str | None, branch_ids: list[str]) -> None:
    payload = {
        "session_id": session_id,
        "project_id": project_id,
        "graph_id": "graph_demo",
        "simulation_goal": "观察世界推进",
        "focus_question": "谁会先出手",
        "branch_count": len(branch_ids),
        "session_scope": "project",
        "status": "running",
        "branches": [
            {
                "branch_id": branch_id,
                "title": f"世界线 {index}",
                "status": "running",
                "timeline": [
                    {
                        "event_id": f"evt_{index}",
                        "step": index,
                        "title": f"事件 {index}",
                        "summary": f"分支 {branch_id} 事件",
                        "event_type": "evolution",
                        "status": "canon",
                        "created_at": "2026-04-11T00:00:00",
                    }
                ],
                "actor_states": {},
                "organization_states": {},
                "relationship_states": [],
                "pending_variables": [],
                "pending_actions": [],
                "created_at": "2026-04-11T00:00:00",
                "updated_at": "2026-04-11T00:00:00",
            }
            for index, branch_id in enumerate(branch_ids, start=1)
        ],
        "world_variables": [],
        "timeline_focus": [],
        "agent_behavior_axes": [],
        "source_summary": {},
        "created_at": "2026-04-11T00:00:00",
        "updated_at": "2026-04-11T00:00:00",
    }
    write_text(path, json.dumps(payload, ensure_ascii=False))


def create_runtime_db(path: Path, session_id: str, branch_id: str, extra_branch_id: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        create table agent_registry (
          session_id text not null,
          branch_id text not null,
          agent_id text not null,
          agent_kind text not null,
          display_name text not null,
          source_ref text not null,
          role text not null,
          drive text not null,
          tension text not null,
          status text not null,
          summary text not null,
          can_chat integer not null,
          can_act integer not null,
          state_json text not null,
          state_source text not null,
          state_version integer not null,
          last_action_at text,
          last_dialogue_at text,
          source_archive_id text,
          source_entity_uuid text,
          created_at text not null,
          updated_at text not null,
          primary key (session_id, branch_id, agent_id)
        );
        create table agent_action_log (
          action_event_id text primary key,
          session_id text not null,
          branch_id text not null,
          agent_id text not null,
          display_name text not null,
          action text not null,
          intent text not null,
          target text not null,
          source text not null,
          status text not null,
          detail_json text not null,
          created_at text not null,
          applied_at text,
          discarded_at text
        );
        create table agent_dialogue_log (
          dialogue_id text primary key,
          session_id text not null,
          branch_id text not null,
          agent_id text not null,
          display_name text not null,
          message text not null,
          reply text not null,
          generator_mode text not null,
          model_name text not null,
          context_summary text not null,
          created_at text not null
        );
        create table relation_state_log (
          relation_event_id text primary key,
          session_id text not null,
          branch_id text not null,
          agent_id text not null,
          source_agent_id text not null,
          target_agent_id text not null,
          source_name text not null,
          target_name text not null,
          change text not null,
          note text not null,
          status text not null,
          last_action text not null,
          state_json text not null,
          created_at text not null
        );
        create table agent_state_snapshots (
          snapshot_id text primary key,
          session_id text not null,
          branch_id text not null,
          agent_id text not null,
          state_version integer not null,
          status text not null,
          reason text not null,
          state_json text not null,
          created_at text not null
        );
        """
    )
    rows = [
        (
            session_id,
            branch_id,
            "agent_1",
            "character",
            "沈夜",
            "archive",
            "protagonist",
            "查明真相",
            "担心暴露",
            "engaged",
            "主角",
            1,
            1,
            "{}",
            "runtime",
            2,
            "2026-04-11T00:00:00",
            "2026-04-11T00:01:00",
            None,
            None,
            "2026-04-11T00:00:00",
            "2026-04-11T00:01:00",
        ),
        (
            session_id,
            branch_id,
            "agent_2",
            "character",
            "秦昭",
            "archive",
            "major",
            "争夺主动",
            "疑心加重",
            "active",
            "对手",
            1,
            1,
            "{}",
            "runtime",
            1,
            None,
            None,
            None,
            None,
            "2026-04-11T00:00:00",
            "2026-04-11T00:01:00",
        ),
    ]
    connection.executemany("insert into agent_registry values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    if extra_branch_id:
        connection.execute(
            "insert into agent_registry values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                session_id,
                extra_branch_id,
                "agent_x",
                "character",
                "分支外角色",
                "archive",
                "supporting",
                "",
                "",
                "active",
                "ignored",
                1,
                1,
                "{}",
                "runtime",
                1,
                None,
                None,
                None,
                None,
                "2026-04-11T00:00:00",
                "2026-04-11T00:01:00",
            ),
        )
    connection.execute(
        "insert into agent_action_log values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "act_1",
            session_id,
            branch_id,
            "agent_1",
            "沈夜",
            "秘密接触外门弟子",
            "摸清底牌",
            "外门弟子",
            "manual",
            "queued",
            "{\"risk\":\"low\"}",
            "2026-04-11T00:02:00",
            None,
            None,
        ),
    )
    connection.execute(
        "insert into agent_dialogue_log values (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "dlg_1",
            session_id,
            branch_id,
            "agent_1",
            "沈夜",
            "今晚你会怎么行动？",
            "我会先摸清对方底牌。",
            "template",
            "",
            "命中近期行动",
            "2026-04-11T00:03:00",
        ),
    )
    connection.execute(
        "insert into relation_state_log values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "rel_1",
            session_id,
            branch_id,
            "agent_1",
            "agent_1",
            "agent_2",
            "沈夜",
            "秦昭",
            "conflict",
            "互相试探",
            "candidate",
            "接触外门弟子后出现猜疑",
            "{\"heat\":0.7}",
            "2026-04-11T00:04:00",
        ),
    )
    connection.execute(
        "insert into agent_state_snapshots values (?,?,?,?,?,?,?, ?, ?)",
        (
            "snap_1",
            session_id,
            branch_id,
            "agent_1",
            2,
            "engaged",
            "推进事件后更新",
            "{\"mood\":\"tense\"}",
            "2026-04-11T00:05:00",
        ),
    )
    connection.commit()
    connection.close()


def test_import_only_imports_project_worldline_runtime_projection(tmp_path):
    uploads = tmp_path / "uploads"
    db_path = tmp_path / "import.db"
    write_text(
        uploads / "projects" / "proj_demo" / "project.json",
        '{"project_id":"proj_demo","name":"世界线项目","status":"created","created_at":"2026-04-11T00:00:00","updated_at":"2026-04-11T00:00:00"}',
    )
    create_session_json(
        uploads / "projects" / "proj_demo" / "worldlines" / "sessions" / "ws_1" / "session.json",
        "ws_1",
        "proj_demo",
        ["branch_1", "branch_2"],
    )
    create_runtime_db(
        uploads / "projects" / "proj_demo" / "worldlines" / "runtime.sqlite3",
        "ws_1",
        "branch_1",
        extra_branch_id="branch_2",
    )

    report = run_import_only(uploads, f"sqlite:///{db_path}")

    assert report.blocked_targets == ()
    assert any("ws_1: imported legacy branch branch_1 as current_world" in item for item in report.anomalies)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        agents = connection.execute(select(report.metadata.tables["session_agents"])).all()
        snapshots = connection.execute(select(report.metadata.tables["agent_state_snapshots"])).all()
        actions = connection.execute(select(report.metadata.tables["agent_actions"])).all()
        dialogues = connection.execute(select(report.metadata.tables["agent_dialogues"])).all()
        relations = connection.execute(select(report.metadata.tables["relation_events"])).all()

    assert len(agents) == 2
    assert {row.agent_id for row in agents} == {"agent_1", "agent_2"}
    assert len(snapshots) == 1
    assert len(actions) == 1
    assert actions[0].intent == "摸清底牌"
    assert len(dialogues) == 1
    assert dialogues[0].reply == "我会先摸清对方底牌。"
    assert len(relations) == 1
    assert relations[0].change == "conflict"


def test_import_only_imports_system_global_worldline_runtime_projection(tmp_path):
    uploads = tmp_path / "uploads"
    db_path = tmp_path / "import.db"
    create_session_json(
        uploads
        / "system"
        / "global_worldlines"
        / "graphs"
        / "graph_demo"
        / "worldlines"
        / "sessions"
        / "ws_global"
        / "session.json",
        "ws_global",
        None,
        ["branch_1"],
    )
    create_runtime_db(
        uploads / "system" / "global_worldlines" / "graphs" / "graph_demo" / "worldlines" / "runtime.sqlite3",
        "ws_global",
        "branch_1",
    )

    report = run_import_only(uploads, f"sqlite:///{db_path}")

    assert report.blocked_targets == ()

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        sessions = connection.execute(select(report.metadata.tables["worldline_sessions"])).all()
        agents = connection.execute(select(report.metadata.tables["session_agents"])).all()

    assert len(sessions) == 1
    assert sessions[0].project_id is None
    assert len(agents) == 2
