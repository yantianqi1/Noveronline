import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.shared.db.base import metadata


def test_llm_facility_tables_are_registered():
    expected_tables = {
        "llm_providers",
        "llm_channels",
        "llm_models",
        "llm_module_bindings",
    }

    assert expected_tables.issubset(set(metadata.tables))


def test_worldline_tables_are_registered():
    expected_tables = {
        "worldline_preparations",
        "prepared_agent_dossiers",
        "worldline_sessions",
        "world_states",
        "timeline_events",
        "session_agents",
        "agent_actions",
        "agent_dialogues",
        "agent_state_snapshots",
        "relation_events",
    }

    assert expected_tables.issubset(set(metadata.tables))


def test_llm_and_worldline_key_columns_exist():
    llm_channels = metadata.tables["llm_channels"]
    llm_bindings = metadata.tables["llm_module_bindings"]
    worldline_preparations = metadata.tables["worldline_preparations"]
    worldline_sessions = metadata.tables["worldline_sessions"]
    world_states = metadata.tables["world_states"]
    timeline_events = metadata.tables["timeline_events"]
    session_agents = metadata.tables["session_agents"]
    agent_actions = metadata.tables["agent_actions"]
    agent_dialogues = metadata.tables["agent_dialogues"]
    agent_state_snapshots = metadata.tables["agent_state_snapshots"]
    relation_events = metadata.tables["relation_events"]

    assert {"llm_channel_id", "channel_key", "name", "max_concurrency", "is_enabled"}.issubset(
        llm_channels.columns.keys()
    )
    assert {"llm_module_binding_id", "module_key", "llm_channel_id", "llm_model_id"}.issubset(
        llm_bindings.columns.keys()
    )
    assert {"prepare_id", "project_id", "status", "session_scope", "focus_question"}.issubset(
        worldline_preparations.columns.keys()
    )
    assert {"session_id", "project_id", "session_scope", "simulation_goal", "focus_question"}.issubset(
        worldline_sessions.columns.keys()
    )
    assert {"world_state_id", "session_id", "version_no", "is_current"}.issubset(world_states.columns.keys())
    assert {"timeline_event_id", "session_id", "world_state_id", "step_no", "event_type"}.issubset(
        timeline_events.columns.keys()
    )
    assert {
        "session_agent_id",
        "session_id",
        "agent_id",
        "archive_id",
        "agent_kind",
        "display_name",
        "role",
        "status",
        "can_chat",
        "can_act",
    }.issubset(
        session_agents.columns.keys()
    )
    assert {
        "action_id",
        "session_id",
        "session_agent_id",
        "action",
        "intent",
        "target",
        "source",
        "status",
        "detail_json",
    }.issubset(
        agent_actions.columns.keys()
    )
    assert {
        "dialogue_id",
        "session_id",
        "session_agent_id",
        "user_message",
        "reply",
        "generator_mode",
        "model_name",
        "context_summary",
    }.issubset(
        agent_dialogues.columns.keys()
    )
    assert {"snapshot_id", "session_id", "session_agent_id", "state_version", "status", "state_json"}.issubset(
        agent_state_snapshots.columns.keys()
    )
    assert {
        "relation_event_id",
        "session_id",
        "relation_session_agent_id",
        "source_session_agent_id",
        "target_session_agent_id",
        "change",
        "status",
    }.issubset(relation_events.columns.keys())
