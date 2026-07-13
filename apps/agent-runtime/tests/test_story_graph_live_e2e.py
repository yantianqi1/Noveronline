from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from mirofish_agents.common.context import AgentContext
from mirofish_agents.temporal.graph import PostgresStoryGraphBuilder, STORY_GRAPH_BUILD_MODULE_KEY
from live_schema_guard import ensure_live_schema


MIGRATION_SQL = Path(__file__).resolve().parents[3] / "infra" / "postgres" / "migrations" / "0001_core_saas.sql"
TENANT_ID = "ba0e1cd3-f018-4d67-a3e7-f2d664a7ba22"
PROJECT_ID = "905733d9-ef6f-40bb-a7e2-abd21f2467fa"
USER_ID = "8976e54c-bbe5-4540-8b4e-0c8094f0219d"
SEED_RUN_ID = "73f90030-4389-4f9b-b4d3-974ed0288676"
BUILD_RUN_ID = "b6138ea4-f548-42ce-8864-a9e0834a8eaf"
APP_ROLE = "mirofish_graph_live_app"
APP_PASSWORD = "mirofish_graph_live_password"
ENTITY_COUNT = 1005


def test_story_graph_large_build_is_reproducible_and_rls_backed() -> None:
    admin_url = os.environ.get("MIROFISH_GRAPH_LIVE_DATABASE_URL", "").strip()
    if not admin_url:
        pytest.skip("set MIROFISH_GRAPH_LIVE_DATABASE_URL to run the live Story Graph PostgreSQL E2E")
    _prepare_database(admin_url)
    app_url = _app_database_url(admin_url)
    builder = PostgresStoryGraphBuilder.from_database_url(app_url)
    context = AgentContext(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        run_id=BUILD_RUN_ID,
        workflow_type="story_graph_build",
        actor_user_id=USER_ID,
        module_key=STORY_GRAPH_BUILD_MODULE_KEY,
        trace_id="9a088f86-ae9a-42ee-a40f-8232a65ea4a8",
        permissions={STORY_GRAPH_BUILD_MODULE_KEY: ["run"]},
    )

    started = time.perf_counter()
    try:
        first = builder.build(context=context, mode="full", options={"viewport_node_budget": 300})
        second = builder.build(context=context, mode="full", options={"viewport_node_budget": 300})
        elapsed = time.perf_counter() - started

        assert first["node_count"] > 1000
        assert first["edge_count"] >= 1000
        assert first["node_count"] == second["node_count"]
        assert first["edge_count"] == second["edge_count"]
        assert first["cluster_count"] >= 3
        first_state = _graph_state(admin_url, first["graph_id"])
        second_state = _graph_state(admin_url, second["graph_id"])
        assert first_state["source_hash"] == second_state["source_hash"]
        assert first_state["stable_identities"] == second_state["stable_identities"]
        assert first_state["layout"]["schema_version"] == 2
        assert first_state["layout"]["strategy"] == "deterministic_cluster_grid"
        assert first_state["layout"]["node_count"] == first["node_count"]
        assert len(first_state["layout"]["nodes"]) == first["node_count"]
        assert first_state["layout"]["viewport"]["mode"] == "cluster_overview"
        assert first_state["layout"]["viewport"]["recommended_page_size"] == 300
        assert first_state["layout"]["viewport"]["omitted_node_count"] == 0
        assert first_state["snippet_count"] == 0
        assert first_state["evidence_count"] >= first["node_count"]
        assert first_state["merged_entity_count"] == 1
        print(
            "story graph live scale",
            {
                "nodes": first["node_count"],
                "edges": first["edge_count"],
                "evidence": first_state["evidence_count"],
                "clusters": first["cluster_count"],
                "two_build_seconds": round(elapsed, 3),
            },
        )
    finally:
        _cleanup_database(admin_url)


def _prepare_database(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            ensure_live_schema(
                cursor,
                MIGRATION_SQL,
                ("tenants", "projects", "assets", "graph_nodes", "graph_edges", "graph_evidence"),
            )
            _ensure_app_login_role(cursor)
            cursor.execute("DELETE FROM tenants WHERE tenant_id = %s", (TENANT_ID,))
            cursor.execute(
                """INSERT INTO users (user_id, email, display_name)
                   VALUES (%s, 'graph-live@example.test', 'Graph Live')
                   ON CONFLICT (user_id) DO UPDATE SET display_name = EXCLUDED.display_name""",
                (USER_ID,),
            )
            cursor.execute(
                "INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES (%s, 'graph-live-disposable', 'Graph Live Disposable', 'personal')",
                (TENANT_ID,),
            )
            cursor.execute(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES (%s, %s, 'owner')",
                (TENANT_ID, USER_ID),
            )
            cursor.execute(
                "INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES (%s, %s, 'Graph Live Disposable', %s)",
                (TENANT_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                "INSERT INTO project_members (tenant_id, project_id, user_id, role) VALUES (%s, %s, %s, 'project_owner')",
                (TENANT_ID, PROJECT_ID, USER_ID),
            )
            cursor.executemany(
                """INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, progress, started_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                [
                    (TENANT_ID, SEED_RUN_ID, "seed_pipeline", PROJECT_ID, "completed", 100, USER_ID),
                    (TENANT_ID, BUILD_RUN_ID, "story_graph_build", PROJECT_ID, "queued", 0, USER_ID),
                ],
            )
            entities = []
            for index in range(ENTITY_COUNT):
                entities.append(
                    (
                        TENANT_ID,
                        str(uuid.uuid5(uuid.UUID(PROJECT_ID), f"entity:{index}")),
                        PROJECT_ID,
                        SEED_RUN_ID,
                        "别名角色" if index == 1 else f"角色 {index:04d}",
                        "character" if index < 2 or index % 3 else "organization",
                        "high" if index < 20 else "medium",
                        f"公开角色摘要 {index}",
                    )
                )
            cursor.executemany(
                """INSERT INTO entities (
                     tenant_id, entity_id, project_id, source_run_id, canonical_name,
                     entity_type, importance, state_summary
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                entities,
            )
            cursor.execute(
                """INSERT INTO entity_aliases (tenant_id, project_id, entity_id, alias)
                   VALUES (%s, %s, %s, '角色 0000')""",
                (TENANT_ID, PROJECT_ID, entities[1][1]),
            )
            relationships = [
                (
                    TENANT_ID,
                    PROJECT_ID,
                    entities[index][4],
                    entities[index + 1][4],
                    "opposes" if index % 5 == 0 else "relationship",
                    f"公开关系摘要 {index}",
                    SEED_RUN_ID,
                )
                for index in range(ENTITY_COUNT - 1)
            ]
            cursor.executemany(
                """INSERT INTO relationships (
                     tenant_id, project_id, source_entity_name, target_entity_name,
                     relationship_type, summary, source_run_id
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                relationships,
            )
            cursor.executemany(
                """INSERT INTO plot_threads (tenant_id, project_id, source_run_id, title, status, summary)
                   VALUES (%s, %s, %s, %s, 'open', %s)""",
                [
                    (TENANT_ID, PROJECT_ID, SEED_RUN_ID, f"剧情线 {index}", f"公开剧情线摘要 {index}")
                    for index in range(4)
                ],
            )
            cursor.executemany(
                """INSERT INTO assets (
                     tenant_id, project_id, scope, asset_type, category, lifecycle,
                     title, summary, source_kind, source_ref, enabled, pinned, created_by
                   ) VALUES (%s, %s, 'project', 'artifact', 'world', 'canon', %s, %s, 'manual', %s, true, false, %s)""",
                [
                    (TENANT_ID, PROJECT_ID, f"遗物 {index}", f"公开遗物摘要 {index}", f"graph-live:{index}", USER_ID)
                    for index in range(2)
                ],
            )


def _graph_state(admin_url: str, graph_id: str) -> dict[str, Any]:
    with psycopg.connect(admin_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_version_hash FROM story_graph_snapshots WHERE tenant_id = %s AND project_id = %s AND graph_id = %s",
                (TENANT_ID, PROJECT_ID, graph_id),
            )
            source_hash = cursor.fetchone()[0]
            cursor.execute(
                "SELECT attributes_jsonb->>'stable_identity' FROM story_graph_nodes WHERE tenant_id = %s AND project_id = %s AND graph_id = %s ORDER BY 1",
                (TENANT_ID, PROJECT_ID, graph_id),
            )
            stable_identities = [row[0] for row in cursor.fetchall()]
            cursor.execute(
                "SELECT layout_jsonb FROM story_graph_layouts WHERE tenant_id = %s AND project_id = %s AND graph_id = %s AND view_id = 'world'",
                (TENANT_ID, PROJECT_ID, graph_id),
            )
            layout = cursor.fetchone()[0]
            cursor.execute(
                """SELECT count(*), count(snippet), count(*) FILTER (
                     WHERE owner_type = 'node' AND source_type = 'entity'
                   ) FROM story_graph_evidence
                   WHERE tenant_id = %s AND project_id = %s AND graph_id = %s""",
                (TENANT_ID, PROJECT_ID, graph_id),
            )
            evidence_count, snippet_count, _entity_evidence_count = cursor.fetchone()
            cursor.execute(
                """SELECT count(*) FROM story_graph_nodes
                   WHERE tenant_id = %s AND project_id = %s AND graph_id = %s
                     AND (attributes_jsonb->>'merged_source_count')::int > 1""",
                (TENANT_ID, PROJECT_ID, graph_id),
            )
            merged_entity_count = cursor.fetchone()[0]
    return {
        "source_hash": source_hash,
        "stable_identities": stable_identities,
        "layout": layout,
        "evidence_count": evidence_count,
        "snippet_count": snippet_count,
        "merged_entity_count": merged_entity_count,
    }


def _ensure_app_login_role(cursor: Any) -> None:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,))
    if cursor.fetchone() is None:
        cursor.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE mirofish_app").format(
                sql.Identifier(APP_ROLE),
                sql.Literal(APP_PASSWORD),
            )
        )
    else:
        cursor.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(sql.Identifier(APP_ROLE), sql.Literal(APP_PASSWORD))
        )
    cursor.execute(sql.SQL("GRANT mirofish_app TO {}").format(sql.Identifier(APP_ROLE)))


def _app_database_url(admin_url: str) -> str:
    parts = conninfo_to_dict(admin_url)
    parts["user"] = APP_ROLE
    parts["password"] = APP_PASSWORD
    return make_conninfo(**parts)


def _cleanup_database(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM tenants WHERE tenant_id = %s", (TENANT_ID,))
