import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bootstrap.app_factory import create_app
from src.bootstrap.settings import AppSettings
from src.shared.db.base import metadata


def make_settings(database_url: str) -> AppSettings:
    return AppSettings.model_construct(
        app_name="MiroFish-Novel API v2",
        api_prefix="/api/v2",
        env="test",
        host="127.0.0.1",
        port=5102,
        redis_url="redis://127.0.0.1:6379/0",
        temporal_target="127.0.0.1:7233",
        database_url_override=database_url,
    )


def seed_worldline_database(database_url: str) -> None:
    now = datetime(2026, 4, 11, tzinfo=timezone.utc)
    engine = create_engine(database_url)
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            metadata.tables["workspaces"].insert().values(
                workspace_id="legacy-workspace",
                name="Legacy Imported Workspace",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["projects"].insert().values(
                project_id="proj_demo",
                workspace_id="legacy-workspace",
                name="世界线项目",
                legacy_status="created",
                analysis_summary="worldline ready",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["worldline_preparations"].insert().values(
                prepare_id="prep_1",
                project_id="proj_demo",
                status="completed",
                session_scope="project",
                focus_question="主角会如何推进",
                started_session_id="ws_1",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["prepared_agent_dossiers"].insert().values(
                prepared_agent_dossier_id="pad_1",
                prepare_id="prep_1",
                agent_id="agent_1",
                agent_kind="character",
                display_name="沈夜",
                template_key="character.protagonist.v1",
                template_version="v1",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["worldline_sessions"].insert().values(
                session_id="ws_1",
                project_id="proj_demo",
                session_scope="project",
                simulation_goal="观察主角推进路径",
                focus_question="主角会如何推进",
                status="running",
                created_from_prepare_run_id="prep_1",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["world_states"].insert().values(
                world_state_id="state_1",
                session_id="ws_1",
                version_no=1,
                is_current=True,
                created_at=now,
            )
        )
        connection.execute(
            metadata.tables["entities"].insert(),
            [
                {
                    "entity_id": "ent_1",
                    "project_id": "proj_demo",
                    "entity_uuid": "entity_shenye",
                    "entity_kind": "character",
                    "canonical_name": "沈夜",
                    "display_name": "沈夜",
                    "summary": "主角",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "entity_id": "ent_2",
                    "project_id": "proj_demo",
                    "entity_uuid": "entity_qinzhao",
                    "entity_kind": "character",
                    "canonical_name": "秦昭",
                    "display_name": "秦昭",
                    "summary": "对手",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        connection.execute(
            metadata.tables["archives"].insert(),
            [
                {
                    "archive_id": "arc_1",
                    "project_id": "proj_demo",
                    "entity_id": "ent_1",
                    "archive_type": "character",
                    "agent_kind": "character",
                    "importance_tier": "protagonist",
                    "selected_importance_tier": "protagonist",
                    "template_key": "character.protagonist.v1",
                    "template_version": "v1",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "archive_id": "arc_2",
                    "project_id": "proj_demo",
                    "entity_id": "ent_2",
                    "archive_type": "character",
                    "agent_kind": "character",
                    "importance_tier": "major",
                    "selected_importance_tier": "major",
                    "template_key": "character.major.v1",
                    "template_version": "v1",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        connection.execute(
            metadata.tables["memories"].insert(),
            [
                {
                    "memory_id": "mem_1",
                    "project_id": "proj_demo",
                    "archive_id": "arc_1",
                    "memory_type": "fact",
                    "memory_layer": "canon",
                    "status": "active",
                    "normalized_subject": "agent_1",
                    "summary": "沈夜记得密信来自内门。",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "memory_id": "mem_2",
                    "project_id": "proj_demo",
                    "archive_id": "arc_1",
                    "memory_type": "strategy",
                    "memory_layer": "candidate",
                    "status": "candidate",
                    "normalized_subject": "agent_1",
                    "summary": "可以先试探外门弟子。",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        connection.execute(
            metadata.tables["timeline_events"].insert().values(
                timeline_event_id="evt_1",
                session_id="ws_1",
                world_state_id="state_1",
                step_no=1,
                event_type="evolution",
                title="主动追查",
                summary="沈夜决定主动追查密信来源。",
                status="canon",
                created_at=now,
            )
        )
        connection.execute(
            metadata.tables["timeline_events"].insert().values(
                timeline_event_id="evt_2",
                session_id="ws_1",
                world_state_id="state_1",
                step_no=2,
                event_type="candidate",
                title="试探出手",
                summary="沈夜准备试探对手底牌。",
                status="candidate",
                created_at=now,
            )
        )
        connection.execute(
            metadata.tables["session_agents"].insert(),
            [
                {
                    "session_agent_id": "sag_1",
                    "session_id": "ws_1",
                    "agent_id": "agent_1",
                    "archive_id": "arc_1",
                    "entity_id": "ent_1",
                    "agent_kind": "character",
                    "display_name": "沈夜",
                    "role": "protagonist",
                    "drive": "查明真相",
                    "tension": "担心暴露",
                    "status": "engaged",
                    "summary": "主角",
                    "can_chat": True,
                    "can_act": True,
                    "state_json": "{}",
                    "state_source": "runtime",
                    "state_version": 2,
                    "source_ref": "archive",
                    "last_action_at": now,
                    "last_dialogue_at": now,
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "session_agent_id": "sag_2",
                    "session_id": "ws_1",
                    "agent_id": "agent_2",
                    "archive_id": "arc_2",
                    "entity_id": "ent_2",
                    "agent_kind": "character",
                    "display_name": "秦昭",
                    "role": "major",
                    "drive": "争夺主动",
                    "tension": "互相提防",
                    "status": "active",
                    "summary": "对手",
                    "can_chat": True,
                    "can_act": True,
                    "state_json": "{}",
                    "state_source": "runtime",
                    "state_version": 1,
                    "source_ref": "archive",
                    "last_action_at": None,
                    "last_dialogue_at": None,
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        connection.execute(
            metadata.tables["agent_state_snapshots"].insert().values(
                snapshot_id="snap_1",
                session_id="ws_1",
                session_agent_id="sag_1",
                state_version=2,
                status="engaged",
                reason="推进事件后更新",
                state_json='{"mood":"tense"}',
                created_at=now,
            )
        )
        connection.execute(
            metadata.tables["agent_actions"].insert().values(
                action_id="act_1",
                session_id="ws_1",
                session_agent_id="sag_1",
                action="秘密接触外门弟子",
                intent="摸清底牌",
                target="外门弟子",
                source="manual",
                status="queued",
                detail_json='{"risk":"low"}',
                queued_at=now,
                applied_at=None,
                discarded_at=None,
            )
        )
        connection.execute(
            metadata.tables["agent_dialogues"].insert().values(
                dialogue_id="dlg_1",
                session_id="ws_1",
                session_agent_id="sag_1",
                user_message="今晚你会怎么行动？",
                reply="我会先摸清对方底牌。",
                generator_mode="template",
                model_name="",
                context_summary="命中近期行动",
                llm_module_binding_id=None,
                created_at=now,
            )
        )
        connection.execute(
            metadata.tables["relation_events"].insert().values(
                relation_event_id="rel_1",
                session_id="ws_1",
                relation_session_agent_id="sag_1",
                source_session_agent_id="sag_1",
                target_session_agent_id="sag_2",
                source_name="沈夜",
                target_name="秦昭",
                change="conflict",
                note="互相试探",
                status="candidate",
                last_action="秘密接触外门弟子后出现猜疑",
                state_json='{"heat":0.7}',
                created_at=now,
            )
        )


def test_worldline_queries_return_agent_console_and_timeline_views(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'worldline.db'}"
    seed_worldline_database(database_url)
    client = TestClient(create_app(make_settings(database_url)))

    preparation_response = client.get("/api/v2/worldlines/preparations/prep_1")
    assert preparation_response.status_code == 200, preparation_response.json()
    assert preparation_response.json()["data"]["prepare_id"] == "prep_1"

    agents_response = client.get("/api/v2/worldlines/preparations/prep_1/agents")
    assert agents_response.status_code == 200, agents_response.json()
    assert agents_response.json()["data"]["items"][0]["agent_id"] == "agent_1"

    sessions_response = client.get("/api/v2/worldlines/sessions")
    assert sessions_response.status_code == 200, sessions_response.json()
    assert sessions_response.json()["data"]["items"][0]["session_id"] == "ws_1"

    session_response = client.get("/api/v2/worldlines/sessions/ws_1")
    assert session_response.status_code == 200, session_response.json()
    assert session_response.json()["data"]["session_id"] == "ws_1"

    timeline_response = client.get("/api/v2/worldlines/sessions/ws_1/timeline")
    assert timeline_response.status_code == 200, timeline_response.json()
    assert timeline_response.json()["data"]["items"][0]["timeline_event_id"] == "evt_1"

    agent_response = client.get("/api/v2/worldlines/sessions/ws_1/agents/agent_1")
    assert agent_response.status_code == 200, agent_response.json()
    assert agent_response.json()["data"]["history_counts"]["action_count"] == 1

    history_response = client.get("/api/v2/worldlines/sessions/ws_1/agent-history", params={"agent_id": "agent_1"})
    assert history_response.status_code == 200, history_response.json()
    history_payload = history_response.json()["data"]
    assert history_payload["actions"][0]["action_event_id"] == "act_1"
    assert history_payload["dialogues"][0]["dialogue_id"] == "dlg_1"
    assert history_payload["snapshots"][0]["snapshot_id"] == "snap_1"
    assert history_payload["relations"][0]["relation_event_id"] == "rel_1"

    actions_response = client.get("/api/v2/worldlines/sessions/ws_1/agent-actions", params={"agent_id": "agent_1"})
    assert actions_response.status_code == 200, actions_response.json()
    assert actions_response.json()["data"]["items"][0]["intent"] == "摸清底牌"

    dialogues_response = client.get("/api/v2/worldlines/sessions/ws_1/agent-dialogues", params={"agent_id": "agent_1"})
    assert dialogues_response.status_code == 200, dialogues_response.json()
    assert dialogues_response.json()["data"]["items"][0]["reply"] == "我会先摸清对方底牌。"

    relations_response = client.get("/api/v2/worldlines/sessions/ws_1/relations", params={"agent_id": "agent_1"})
    assert relations_response.status_code == 200, relations_response.json()
    assert relations_response.json()["data"]["items"][0]["change"] == "conflict"

    events_response = client.get("/api/v2/worldlines/sessions/ws_1/events", params={"status": "candidate"})
    assert events_response.status_code == 200, events_response.json()
    assert events_response.json()["data"]["items"][0]["timeline_event_id"] == "evt_2"

    memory_response = client.get("/api/v2/worldlines/sessions/ws_1/agent-memory", params={"agent_id": "agent_1"})
    assert memory_response.status_code == 200, memory_response.json()
    memory_payload = memory_response.json()["data"]
    assert memory_payload["session_memories"]
    assert memory_payload["long_term_memories"][0]["memory_id"] == "mem_1"
    assert memory_payload["candidate_memories"][0]["memory_id"] == "mem_2"

    context_response = client.get(
        "/api/v2/worldlines/sessions/ws_1/agent-memory-context",
        params={"agent_id": "agent_1", "message": "外门弟子现在可靠吗？"},
    )
    assert context_response.status_code == 200, context_response.json()
    context_payload = context_response.json()["data"]
    assert "秘密接触外门弟子" in context_payload["rendered_context"]
    assert context_payload["debug_hits"]
