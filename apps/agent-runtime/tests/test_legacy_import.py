from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from mirofish_agents.legacy_import.cli import parser as legacy_import_parser

from mirofish_agents.legacy_import.models import FAMILY_DEPENDENCIES
from mirofish_agents.legacy_import.service import LegacyImportService, write_report
from mirofish_agents.legacy_import.source import LegacySource
from mirofish_agents.legacy_import.target import PostgresImportTarget
from mirofish_agents.temporal.legacy_import_workflow import worker_spec


IMPORT_ID = "10000000-0000-4000-8000-000000000001"
TENANT_ID = "10000000-0000-4000-8000-000000000002"
PROJECT_ID = "10000000-0000-4000-8000-000000000003"
ACTOR_ID = "10000000-0000-4000-8000-000000000004"
SOURCE_PROJECT_ID = "legacy-project-1"
PRIVATE_TEXT = "synthetic private manuscript body"
SECRET = "sk-synthetic-must-not-leak"


def test_source_is_read_only_and_plan_is_deterministic_and_sanitized(tmp_path: Path) -> None:
    source_path = build_synthetic_source(tmp_path / "legacy.db")
    source = LegacySource(source_path)
    before = _sha256(source_path)

    with source.connect() as connection:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("INSERT INTO project_meta (project_id) VALUES ('forbidden')")

    service = _service(source_path)
    first = service.plan()
    second = service.plan()
    report = service.plan_report()
    encoded = json.dumps(report, sort_keys=True)

    assert first.plan_hash == second.plan_hash
    assert [record.key for record in first.records] == [record.key for record in second.records]
    assert set(first.families) == set(FAMILY_DEPENDENCIES)
    assert first.families["evidence"].deferred_count == 0
    assert any(record.table == "text_segments" for record in first.families["evidence"].records)
    assert any(record.table == "entity_evidence" for record in first.families["evidence"].records)
    assert first.families["source"].deferred_count == 0
    assert first.families["archive"].deferred_count == 0
    assert len(first.families["archive"].records) == 3
    assert first.families["graph"].deferred_count == 0
    assert len([record for record in first.families["graph"].records if record.table == "story_graph_snapshots"]) == 2
    assert len([record for record in first.families["writer"].records if record.table == "chapters"]) == 2
    assert first.families["manuscript"].deferred_count == 0
    assert report["status"] == "complete"
    assert report["object_counts"] == {
        "planned": 1,
        "uploadable": 1,
        "metadata_only": 0,
    }
    assert PRIVATE_TEXT not in encoded
    assert SECRET not in encoded
    assert "postgresql://" not in encoded
    assert _sha256(source_path) == before


def test_relationship_owned_evidence_maps_to_relationship_event(tmp_path: Path) -> None:
    source_path = build_synthetic_source(tmp_path / "legacy.db")
    with sqlite3.connect(source_path) as connection:
        connection.execute(
            "INSERT INTO entity_evidence VALUES "
            "('evidence-relationship', ?, 'relation-a', 'relationship', "
            "'chapter-a', 'private relationship evidence', '2026-01-01')",
            (SOURCE_PROJECT_ID,),
        )

    plan = _service(source_path).plan()
    family = plan.families["evidence"]
    relationship_records = [
        record for record in family.records if record.table == "relationship_events"
    ]

    assert family.deferred_count == 0
    assert family.reason_codes == []
    assert len(relationship_records) == 1
    assert relationship_records[0].values["source_entity_name"] == "Alpha"
    assert relationship_records[0].values["target_entity_name"] == "Beta"
    assert relationship_records[0].values["relationship_type"] == "ally"
    assert relationship_records[0].values["event_summary"] == "private relationship evidence"
    assert relationship_records[0].values["evidence_text"] == "private relationship evidence"
    assert "private relationship evidence" not in json.dumps(
        _service(source_path).plan_report(), sort_keys=True
    )


def test_apply_and_rollback_are_read_only_without_execute_flag(tmp_path: Path) -> None:
    source_path = build_synthetic_source(tmp_path / "legacy.db")
    before = _sha256(source_path)
    service = _service(source_path)

    apply_report = service.apply(execute=False)
    rollback_report = service.rollback(execute=False)

    assert apply_report["status"] == rollback_report["status"] == "partial"
    assert "EXECUTION_NOT_REQUESTED" in apply_report["blockers"]
    assert "EXECUTION_NOT_REQUESTED" in rollback_report["blockers"]
    assert _sha256(source_path) == before


def test_cli_apply_and_verify_require_plan_binding() -> None:
    common = [
        "--source", "legacy.db", "--import-id", IMPORT_ID,
        "--tenant-id", TENANT_ID, "--project-id", PROJECT_ID,
        "--actor-user-id", ACTOR_ID, "--source-project-id", SOURCE_PROJECT_ID,
        "--target", "postgresql://app-role.invalid/db",
    ]
    cli = legacy_import_parser()

    with pytest.raises(SystemExit):
        cli.parse_args(["apply", *common, "--execute"])
    with pytest.raises(SystemExit):
        cli.parse_args(["verify", *common])
    with pytest.raises(SystemExit):
        cli.parse_args(["rollback", *common, "--execute"])
    with pytest.raises(SystemExit):
        cli.parse_args(
            [
                "reconcile-version", *common, "--execute",
                "--object-id", "object-id", "--version-id", "private-version-id",
            ]
        )

    parsed = cli.parse_args(
        [
            "apply", *common, "--execute",
            "--expected-source-fingerprint", "source-fingerprint",
            "--expected-plan-hash", "plan-hash",
        ]
    )
    assert parsed.expected_source_fingerprint == "source-fingerprint"
    assert parsed.expected_plan_hash == "plan-hash"


def test_plan_with_missing_source_project_metadata_is_partial(tmp_path: Path) -> None:
    source_path = tmp_path / "empty-legacy.db"
    with sqlite3.connect(source_path) as connection:
        connection.execute("CREATE TABLE project_meta (project_id TEXT PRIMARY KEY)")

    report = _service(source_path).plan_report()

    assert report["status"] == "partial"
    assert report["blockers"] == ["SOURCE_PROJECT_METADATA_ABSENT"]
    assert report["family_reasons"] == {
        "project": ["SOURCE_PROJECT_METADATA_ABSENT"],
    }
    assert sum(counts["planned"] for counts in report["family_counts"].values()) == 0

    target = PostgresImportTarget(lambda: pytest.fail("target connection must not be opened"))
    apply_report = target.apply(_service(source_path).plan())

    assert apply_report["status"] == "failed"
    assert apply_report["blockers"] == ["SOURCE_PROJECT_METADATA_ABSENT"]


def test_source_fingerprint_changes_when_source_changes(tmp_path: Path) -> None:
    source_path = build_synthetic_source(tmp_path / "legacy.db")
    first = LegacySource(source_path).inspect()
    with sqlite3.connect(source_path) as connection:
        connection.execute(
            "INSERT INTO project_artifacts VALUES (?, ?, ?, ?, ?)",
            (SOURCE_PROJECT_ID, "changed", "{}", "2026-01-01", "2026-01-01"),
        )
    second = LegacySource(source_path).inspect()

    assert first.fingerprint != second.fingerprint
    assert first.schema_hash == second.schema_hash


def test_report_writer_is_atomic_and_worker_is_standalone(tmp_path: Path) -> None:
    report = _service(build_synthetic_source(tmp_path / "legacy.db")).plan_report()
    output = tmp_path / "reports" / "legacy-import.json"
    write_report(report, output)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert not list(output.parent.glob(".legacy-import.json.*"))
    assert worker_spec() == {
        "task_queue": "legacy-import",
        "workflows": ["LegacyImportWorkflow"],
        "activities": [
            "legacy_import_plan_activity",
            "legacy_import_apply_activity",
            "legacy_import_verify_activity",
        ],
    }


def test_key_value_graph_metadata_is_one_snapshot_and_conflicts_fail_closed(tmp_path: Path) -> None:
    source_path = tmp_path / "graph-meta.db"
    with sqlite3.connect(source_path) as connection:
        connection.executescript(
            """
            CREATE TABLE project_meta (project_id TEXT PRIMARY KEY);
            CREATE TABLE graph_meta (project_id TEXT, key TEXT, value TEXT);
            INSERT INTO project_meta VALUES ('legacy-project-1');
            INSERT INTO graph_meta VALUES ('legacy-project-1', 'graph_id', 'current');
            INSERT INTO graph_meta VALUES ('legacy-project-1', 'build_version', '7');
            INSERT INTO graph_meta VALUES ('legacy-project-1', 'status', 'ready');
            """
        )
    plan = _service(source_path).plan()
    snapshots = [
        record for record in plan.families["graph"].records
        if record.table == "story_graph_snapshots"
    ]
    assert len(snapshots) == 1
    assert snapshots[0].values["version"] == 7
    assert plan.families["graph"].deferred_count == 0

    with sqlite3.connect(source_path) as connection:
        connection.execute(
            "INSERT INTO graph_meta VALUES ('legacy-project-1', 'status', 'failed')"
        )
    with pytest.raises(RuntimeError, match="LEGACY_GRAPH_METADATA_CONFLICT"):
        _service(source_path).plan()


def build_synthetic_source(path: Path) -> Path:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE project_meta (
              project_id TEXT PRIMARY KEY, project_json TEXT, narrative_phase TEXT,
              total_segments INTEGER, updated_at TEXT
            );
            CREATE TABLE project_artifacts (
              project_id TEXT, artifact_key TEXT, payload_json TEXT, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE entities (
              entity_id TEXT PRIMARY KEY, project_id TEXT, name TEXT, entity_type TEXT,
              importance_tier TEXT, summary TEXT, profile_json TEXT
            );
            CREATE TABLE entity_aliases (project_id TEXT, alias TEXT, entity_id TEXT);
            CREATE TABLE entity_evidence (
              evidence_id TEXT, project_id TEXT, owner_id TEXT, owner_type TEXT,
              chapter_id TEXT, snippet TEXT, created_at TEXT
            );
            CREATE TABLE relationships (
              relation_id TEXT, project_id TEXT, source_id TEXT, target_id TEXT,
              relation_type TEXT, description TEXT, trust_level REAL,
              power_dynamic TEXT, history TEXT
            );
            CREATE TABLE assets (
              asset_id TEXT, project_id TEXT, scope TEXT, asset_type TEXT, category TEXT,
              title TEXT, summary TEXT, content TEXT, payload_json TEXT, tags_json TEXT,
              source_kind TEXT, source_ref TEXT, enabled INTEGER, pinned INTEGER
            );
            CREATE TABLE archive_library (
              archive_id TEXT, project_id TEXT, entity_uuid TEXT, entity_id TEXT,
              entity_name TEXT, entity_type TEXT, agent_kind TEXT, importance_tier TEXT,
              template_key TEXT, template_version TEXT, relationship_summary TEXT
            );
            CREATE TABLE archive_agent_memory (
              memory_id TEXT, project_id TEXT, archive_id TEXT, agent_id TEXT,
              memory_type TEXT, normalized_subject TEXT, summary TEXT, detail_json TEXT,
              source_kind TEXT, source_ref_id TEXT, salience REAL, memory_layer TEXT,
              status TEXT, version INTEGER, parent_memory_id TEXT, source_session_id TEXT,
              source_branch_id TEXT, evidence_json TEXT, adopted_at TEXT, rejected_at TEXT,
              created_at TEXT, updated_at TEXT
            );
            CREATE TABLE archive_agent_memory_events (
              event_id TEXT, project_id TEXT, memory_id TEXT, archive_id TEXT,
              normalized_subject TEXT, memory_type TEXT, event_type TEXT, memory_layer TEXT,
              status TEXT, version INTEGER, parent_memory_id TEXT, source_session_id TEXT,
              source_branch_id TEXT, summary TEXT, evidence_json TEXT, created_at TEXT
            );
            CREATE TABLE graph_meta (
              project_id TEXT, graph_id TEXT, version INTEGER, status TEXT
            );
            CREATE TABLE graph_nodes (
              project_id TEXT, uuid TEXT, name TEXT, summary TEXT,
              attributes_json TEXT, evidence_refs_json TEXT
            );
            CREATE TABLE graph_aliases (project_id TEXT, alias TEXT, node_uuid TEXT);
            CREATE TABLE graph_node_labels (project_id TEXT, node_uuid TEXT, label TEXT);
            CREATE TABLE graph_edges (
              project_id TEXT, uuid TEXT, name TEXT, fact TEXT, source_node_uuid TEXT,
              target_node_uuid TEXT, attributes_json TEXT, weight INTEGER, evidence_refs_json TEXT
            );
            CREATE TABLE graph_evidence (
              project_id TEXT, owner_kind TEXT, owner_uuid TEXT,
              chapter_id TEXT, block_id TEXT, snippet TEXT
            );
            CREATE TABLE worldline_sessions (
              session_id TEXT, project_id TEXT, status TEXT, simulation_goal TEXT,
              focus_question TEXT, label TEXT
            );
            CREATE TABLE prepare_runs (prepare_id TEXT, project_id TEXT);
            CREATE TABLE prepared_agent_dossiers (prepare_id TEXT, project_id TEXT, agent_id TEXT);
            CREATE TABLE writer_runs (
              run_id TEXT, tenant_id TEXT, project_id TEXT, status TEXT, mode TEXT,
              instruction TEXT, module_key TEXT, options_json TEXT, error_code TEXT
            );
            CREATE TABLE writer_drafts (
              draft_id TEXT, tenant_id TEXT, project_id TEXT, run_id TEXT,
              status TEXT, content TEXT
            );
            CREATE TABLE chapter_content (
              chapter_id TEXT, project_id TEXT, chapter_order INTEGER,
              title TEXT, content TEXT, word_count INTEGER, status TEXT
            );
            CREATE TABLE chapter_meta (
              chapter_id TEXT, project_id TEXT, summary TEXT, outline_json TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO project_meta VALUES (?, ?, 'drafting', 2, '2026-01-01')",
            (SOURCE_PROJECT_ID, json.dumps({"title": "Synthetic"})),
        )
        connection.execute(
            "INSERT INTO project_artifacts VALUES (?, 'seed.analysis', ?, '2026-01-01', '2026-01-01')",
            (SOURCE_PROJECT_ID, json.dumps({"secret": SECRET, "body": PRIVATE_TEXT})),
        )
        connection.executemany(
            "INSERT INTO entities VALUES (?, ?, ?, 'character', 'major', ?, ?)",
            [
                ("entity-a", SOURCE_PROJECT_ID, "Alpha", "First synthetic entity", "{}"),
                ("entity-b", SOURCE_PROJECT_ID, "Beta", "Second synthetic entity", "{}"),
            ],
        )
        connection.execute("INSERT INTO entity_aliases VALUES (?, 'A', 'entity-a')", (SOURCE_PROJECT_ID,))
        connection.execute(
            "INSERT INTO entity_evidence VALUES ('evidence-a', ?, 'entity-a', 'entity', 'chapter-a', ?, '2026-01-01')",
            (SOURCE_PROJECT_ID, PRIVATE_TEXT),
        )
        connection.execute(
            "INSERT INTO relationships VALUES ('relation-a', ?, 'entity-a', 'entity-b', 'ally', 'Allies', 0.8, 'equal', 'Shared history')",
            (SOURCE_PROJECT_ID,),
        )
        connection.execute(
            "INSERT INTO assets VALUES ('asset-a', ?, 'material', 'setting', 'world', 'Synthetic setting', 'Summary', ?, '{}', '[\"world\"]', 'manual', 'source-a', 1, 0)",
            (SOURCE_PROJECT_ID, PRIVATE_TEXT),
        )
        connection.execute(
            "INSERT INTO archive_library VALUES ('archive-a', ?, 'entity-a', 'entity-a', 'Alpha dossier', 'character', 'character', 'major', 'character.major.v1', 'v1', 'Archive summary')",
            (SOURCE_PROJECT_ID,),
        )
        connection.execute(
            "INSERT INTO archive_agent_memory VALUES ('memory-a', ?, 'archive-a', 'agent-a', 'fact', 'alpha', 'Memory summary', '{}', 'seed', 'seed-a', 0.8, 'canon', 'active', 1, '', '', '', '[]', NULL, NULL, '2026-01-01', '2026-01-01')",
            (SOURCE_PROJECT_ID,),
        )
        connection.execute(
            "INSERT INTO archive_agent_memory_events VALUES ('memory-event-a', ?, 'memory-a', 'archive-a', 'alpha', 'fact', 'created', 'canon', 'active', 1, '', '', '', 'Memory created', '[]', '2026-01-01')",
            (SOURCE_PROJECT_ID,),
        )
        connection.execute(
            "INSERT INTO graph_meta VALUES (?, 'legacy-graph-a', 1, 'ready')",
            (SOURCE_PROJECT_ID,),
        )
        connection.execute(
            "INSERT INTO graph_meta VALUES (?, 'legacy-graph-b', 2, 'ready')",
            (SOURCE_PROJECT_ID,),
        )
        connection.executemany(
            "INSERT INTO graph_nodes VALUES (?, ?, ?, ?, ?, '[]')",
            [
                (SOURCE_PROJECT_ID, "node-a", "Alpha", "Graph Alpha", '{"node_type":"character","entity_id":"entity-a"}'),
                (SOURCE_PROJECT_ID, "node-b", "Beta", "Graph Beta", '{"node_type":"character","entity_id":"entity-b"}'),
            ],
        )
        connection.execute("INSERT INTO graph_aliases VALUES (?, 'A graph', 'node-a')", (SOURCE_PROJECT_ID,))
        connection.execute("INSERT INTO graph_node_labels VALUES (?, 'node-a', 'lead')", (SOURCE_PROJECT_ID,))
        connection.execute(
            "INSERT INTO graph_edges VALUES (?, 'edge-a', 'ally', 'Graph relation', 'node-a', 'node-b', '{}', 1, '[]')",
            (SOURCE_PROJECT_ID,),
        )
        connection.execute(
            "INSERT INTO graph_evidence VALUES (?, 'node', 'node-a', 'chapter-a', 'block-a', ?)",
            (SOURCE_PROJECT_ID, PRIVATE_TEXT),
        )
        connection.execute(
            "INSERT INTO worldline_sessions VALUES ('session-a', ?, 'completed', 'Synthetic goal', '', 'Session')",
            (SOURCE_PROJECT_ID,),
        )
        connection.execute(
            "INSERT INTO writer_runs VALUES ('writer-run-a', 'legacy', ?, 'completed', 'draft', 'Write synthetic chapter', 'writer_composer', '{}', NULL)",
            (SOURCE_PROJECT_ID,),
        )
        connection.execute(
            "INSERT INTO writer_drafts VALUES ('draft-a', 'legacy', ?, 'writer-run-a', 'candidate', ?)",
            (SOURCE_PROJECT_ID, PRIVATE_TEXT),
        )
        connection.execute(
            "INSERT INTO chapter_content VALUES ('chapter-a', ?, 1, 'Chapter One', ?, 4, 'draft')",
            (SOURCE_PROJECT_ID, PRIVATE_TEXT),
        )
        connection.executemany(
            "INSERT INTO chapter_meta VALUES (?, ?, ?, ?)",
            [
                ("chapter-a", SOURCE_PROJECT_ID, "Chapter one summary", "[]"),
                ("chapter-meta-only", SOURCE_PROJECT_ID, "Planned chapter", "[]"),
            ],
        )
    return path


def _service(source_path: Path) -> LegacyImportService:
    return LegacyImportService(
        source_path=str(source_path),
        artifact_root=None,
        import_id=IMPORT_ID,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        actor_user_id=ACTOR_ID,
        source_project_id=SOURCE_PROJECT_ID,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
