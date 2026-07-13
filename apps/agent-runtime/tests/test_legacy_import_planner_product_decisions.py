from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from mirofish_agents.legacy_import.planner import LegacyImportPlanner
from mirofish_agents.legacy_import.source import LegacySource


IMPORT_ID = "61000000-0000-4000-8000-000000000001"
TENANT_ID = "61000000-0000-4000-8000-000000000002"
PROJECT_ID = "61000000-0000-4000-8000-000000000003"
ACTOR_ID = "61000000-0000-4000-8000-000000000004"
SOURCE_PROJECT_ID = "legacy-project"
PRIVATE = "must-not-cross-the-import-boundary"


def _source(tmp_path: Path) -> LegacySource:
    path = tmp_path / "planner-decisions.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE prepare_runs (
              prepare_id TEXT, project_id TEXT, status TEXT, goal_summary TEXT,
              private_state_json TEXT, prompt TEXT
            );
            CREATE TABLE prepared_agent_dossiers (
              prepare_id TEXT, project_id TEXT, agent_id TEXT, display_name TEXT,
              role TEXT, status TEXT, profile_summary TEXT, private_memory_json TEXT
            );
            CREATE TABLE worldline_branches (
              branch_id TEXT, project_id TEXT, private_state_json TEXT
            );
            CREATE TABLE writer_runs (
              run_id TEXT, project_id TEXT, status TEXT, mode TEXT, instruction TEXT,
              module_key TEXT, options_json TEXT, error_code TEXT
            );
            CREATE TABLE writer_drafts (
              draft_id TEXT, project_id TEXT, run_id TEXT, status TEXT, content TEXT
            );
            CREATE TABLE writer_run_events (
              event_id TEXT, project_id TEXT, run_id TEXT, lifecycle TEXT, status TEXT,
              tool_name TEXT, item_count TEXT, error_code TEXT, message TEXT,
              prompt TEXT, payload_json TEXT
            );
            CREATE TABLE writer_draft_events (
              event_id TEXT, project_id TEXT, draft_id TEXT, status TEXT, payload_json TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO prepare_runs VALUES ('prepare-a', ?, 'completed', 'Public goal', ?, ?)",
            (SOURCE_PROJECT_ID, json.dumps({"secret": PRIVATE}), PRIVATE),
        )
        connection.execute(
            "INSERT INTO prepared_agent_dossiers VALUES "
            "('prepare-a', ?, 'agent-a', 'Public Agent', 'protagonist', 'ready', "
            "'Public profile', ?)",
            (SOURCE_PROJECT_ID, json.dumps({"memory": PRIVATE})),
        )
        connection.execute(
            "INSERT INTO worldline_branches VALUES ('branch-a', ?, ?)",
            (SOURCE_PROJECT_ID, PRIVATE),
        )
        connection.execute(
            "INSERT INTO writer_runs VALUES "
            "('writer-a', ?, 'completed', 'draft', 'Public instruction', "
            "'writer_composer', '{}', NULL)",
            (SOURCE_PROJECT_ID,),
        )
        connection.executemany(
            "INSERT INTO writer_run_events VALUES (?, ?, 'writer-a', ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "event-a", SOURCE_PROJECT_ID, "running", "running", "query_assets",
                    "2", None, PRIVATE, PRIVATE, json.dumps({"private": PRIVATE}),
                ),
                (
                    "event-b", SOURCE_PROJECT_ID, "completed", "completed", None,
                    "3", "TOOL_TIMEOUT", PRIVATE, PRIVATE, json.dumps({"private": PRIVATE}),
                ),
            ],
        )
        connection.execute(
            "INSERT INTO writer_draft_events VALUES ('draft-event-a', ?, 'draft-a', 'candidate', ?)",
            (SOURCE_PROJECT_ID, json.dumps({"private": PRIVATE})),
        )
    return LegacySource(path)


def _plan(tmp_path: Path):
    return LegacyImportPlanner(
        _source(tmp_path),
        import_id=IMPORT_ID,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        actor_user_id=ACTOR_ID,
        source_project_id=SOURCE_PROJECT_ID,
    ).build()


def test_preparations_import_archived_public_profile_and_count_private_fields(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    family = plan.families["worldline"]
    preparations = [record for record in family.records if record.table == "worldline_preparations"]
    agents = [record for record in family.records if record.table == "worldline_prepared_agents"]

    assert len(preparations) == 1
    assert preparations[0].values["lifecycle"] == "archived"
    assert preparations[0].values["goal_summary"] == "Public goal"
    assert len(agents) == 1
    assert agents[0].values == {
        "tenant_id": TENANT_ID,
        "agent_id": agents[0].key,
        "prepare_id": preparations[0].key,
        "project_id": PROJECT_ID,
        "display_name": "Public Agent",
        "role": "protagonist",
        "status": "archived",
        "source_asset_id": None,
        "summary": "Public profile",
    }
    assert family.unsupported_count == 4
    assert "APPROVED_PRIVATE_PREPARATION_STATE_UNSUPPORTED" in family.reason_codes
    assert "APPROVED_LEGACY_MULTI_BRANCH_UNSUPPORTED" in family.reason_codes
    assert PRIVATE not in json.dumps([record.values for record in family.records], sort_keys=True)


def test_writer_run_events_import_to_workflow_in_source_order_with_public_payload(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    family = plan.families["writer"]
    writer_run = next(record for record in family.records if record.table == "writer_runs")
    workflow_run = next(record for record in family.records if record.table == "workflow_runs")
    events = [record for record in family.records if record.table == "workflow_events"]

    assert writer_run.values["workflow_run_id"] == workflow_run.key
    assert workflow_run.values["workflow_type"] == "writer_run"
    assert [event.values["sequence"] for event in events] == [1, 2]
    assert [event.values["run_id"] for event in events] == [workflow_run.key, workflow_run.key]
    assert [event.values["payload_jsonb"] for event in events] == [
        {"lifecycle": "running", "status": "running", "tool": "query_assets", "count": 2},
        {"lifecycle": "completed", "status": "completed", "count": 3, "error_code": "TOOL_TIMEOUT"},
    ]
    assert family.unsupported_count == 1
    assert family.deferred_count == 0
    assert family.reason_codes == ["APPROVED_TRANSIENT_WRITER_EVENT_HISTORY_UNSUPPORTED"]
    assert PRIVATE not in json.dumps([record.values for record in family.records], sort_keys=True)
