import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.shared.db.base import metadata


def test_shared_schema_baseline_registers_core_tables():
    expected_tables = {
        "artifact_objects",
        "archives",
        "entities",
        "memories",
        "memory_events",
        "workspace_settings",
        "workspaces",
        "projects",
        "manuscripts",
        "artifacts",
        "workflow_runs",
        "workflow_steps",
        "workflow_events",
    }

    assert expected_tables.issubset(set(metadata.tables))


def test_projects_and_workflows_keep_required_columns():
    projects = metadata.tables["projects"]
    workspace_settings = metadata.tables["workspace_settings"]
    artifact_objects = metadata.tables["artifact_objects"]
    entities = metadata.tables["entities"]
    archives = metadata.tables["archives"]
    memories = metadata.tables["memories"]
    memory_events = metadata.tables["memory_events"]
    artifacts = metadata.tables["artifacts"]
    manuscripts = metadata.tables["manuscripts"]
    workflow_runs = metadata.tables["workflow_runs"]
    workflow_events = metadata.tables["workflow_events"]

    assert {"project_id", "workspace_id", "name", "legacy_status"}.issubset(projects.columns.keys())
    assert {"workspace_id", "reviewer_rules_text", "updated_at"}.issubset(workspace_settings.columns.keys())
    assert {"artifact_object_id", "bucket", "storage_key", "sha256", "size_bytes"}.issubset(
        artifact_objects.columns.keys()
    )
    assert {"manuscript_id", "project_id", "artifact_object_id", "original_filename"}.issubset(
        manuscripts.columns.keys()
    )
    assert {"artifact_id", "project_id", "artifact_object_id", "artifact_type", "storage_key", "sha256"}.issubset(
        artifacts.columns.keys()
    )
    assert {"entity_id", "project_id", "entity_kind", "canonical_name"}.issubset(entities.columns.keys())
    assert {"archive_id", "project_id", "entity_id", "agent_kind", "template_key"}.issubset(
        archives.columns.keys()
    )
    assert {"memory_id", "archive_id", "memory_layer", "status", "normalized_subject"}.issubset(
        memories.columns.keys()
    )
    assert {"memory_event_id", "memory_id", "archive_id", "event_type", "actor_type"}.issubset(
        memory_events.columns.keys()
    )
    assert {"workflow_run_id", "project_id", "legacy_task_id", "status", "progress_percent"}.issubset(
        workflow_runs.columns.keys()
    )
    assert {"workflow_event_id", "workflow_run_id", "event_type", "title", "payload_json", "emitted_at"}.issubset(
        workflow_events.columns.keys()
    )
