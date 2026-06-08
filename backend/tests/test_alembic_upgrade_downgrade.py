"""Tests for the formalized Alembic migration lifecycle.

Phase D / Task 3: ensure the app boots via ``alembic upgrade head`` rather
than bypassing Alembic with ``metadata.create_all``. These tests verify
that the existing revision chain round-trips (empty DB → upgrade to head →
downgrade to base → upgrade back) and that the resulting schema contains
the expected tables.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _make_alembic_config(db_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_alembic_upgrade_from_empty_creates_all_expected_tables(tmp_path):
    db_path = tmp_path / "alembic_upgrade.db"
    db_url = f"sqlite:///{db_path}"
    cfg = _make_alembic_config(db_url)

    command.upgrade(cfg, "head")

    engine = create_engine(db_url, future=True)
    table_names = set(inspect(engine).get_table_names())
    # Spot-check representative tables from each domain.
    assert {"project_meta", "chapter_content", "assets", "agent_registry"}.issubset(table_names)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT entity_type, category, lifecycle "
                "FROM classification_map "
                "WHERE source='seed' "
                "AND entity_type IN ("
                "'seed_arc_summary', 'seed_key_event', 'seed_ontology_entity', "
                "'seed_volume_summary', 'seed_segment_summary'"
                ") "
                "ORDER BY entity_type"
            )
        ).all()
    assert rows == [
        ("seed_arc_summary", "plot", "seed"),
        ("seed_key_event", "plot", "seed"),
        ("seed_ontology_entity", "world", "seed"),
        ("seed_segment_summary", "plot", "seed"),
        ("seed_volume_summary", "plot", "seed"),
    ]


def test_alembic_downgrade_then_upgrade_round_trips(tmp_path):
    db_path = tmp_path / "alembic_round_trip.db"
    db_url = f"sqlite:///{db_path}"
    cfg = _make_alembic_config(db_url)

    command.upgrade(cfg, "head")
    engine = create_engine(db_url, future=True)
    after_upgrade = set(inspect(engine).get_table_names())
    assert after_upgrade, "upgrade should create tables"

    command.downgrade(cfg, "base")
    engine = create_engine(db_url, future=True)
    after_downgrade = set(inspect(engine).get_table_names())
    # Only alembic_version remains after base downgrade.
    assert after_downgrade - {"alembic_version"} == set()

    command.upgrade(cfg, "head")
    engine = create_engine(db_url, future=True)
    after_reupgrade = set(inspect(engine).get_table_names())
    assert after_reupgrade == after_upgrade


def test_init_db_can_run_via_alembic(tmp_path):
    """``init_db(engine, use_alembic=True)`` runs the alembic upgrade chain
    rather than ``metadata.create_all()`` directly.
    """
    from app.config import Settings
    from app.database import create_engine_from_settings, init_db

    db_path = tmp_path / "init_db_alembic.db"
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    engine = create_engine_from_settings(settings)

    init_db(engine, use_alembic=True)

    table_names = set(inspect(engine).get_table_names())
    assert "alembic_version" in table_names
    assert "project_meta" in table_names


def test_alembic_upgrade_scopes_existing_narrative_ids_by_project(tmp_path):
    db_path = tmp_path / "alembic_narrative_scope.db"
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, future=True)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE narrative_arcs ("
            "arc_id VARCHAR NOT NULL PRIMARY KEY, "
            "project_id VARCHAR NOT NULL, "
            "summary VARCHAR NOT NULL, "
            "covered_segments_json VARCHAR DEFAULT '''[]''', "
            "created_at VARCHAR NOT NULL)"
        ))
        conn.execute(text(
            "CREATE TABLE volume_summaries ("
            "volume_id VARCHAR NOT NULL PRIMARY KEY, "
            "project_id VARCHAR NOT NULL, "
            "volume_order INTEGER NOT NULL, "
            "summary VARCHAR NOT NULL, "
            "covered_arcs_json VARCHAR DEFAULT '''[]''', "
            "created_at VARCHAR NOT NULL)"
        ))
        conn.execute(text(
            "INSERT INTO narrative_arcs "
            "(arc_id, project_id, summary, covered_segments_json, created_at) "
            "VALUES ('arc_1', 'proj_a', 'A arc', '[]', '2026-01-01')"
        ))
        conn.execute(text(
            "INSERT INTO volume_summaries "
            "(volume_id, project_id, volume_order, summary, covered_arcs_json, created_at) "
            "VALUES ('vol_1', 'proj_a', 1, 'A volume', '[]', '2026-01-01')"
        ))

    cfg = _make_alembic_config(db_url)
    command.stamp(cfg, "20260419_0004")
    command.upgrade(cfg, "head")

    inspector = inspect(create_engine(db_url, future=True))
    assert inspector.get_pk_constraint("narrative_arcs")["constrained_columns"] == [
        "project_id",
        "arc_id",
    ]
    assert inspector.get_pk_constraint("volume_summaries")["constrained_columns"] == [
        "project_id",
        "volume_id",
    ]

    engine = create_engine(db_url, future=True)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO narrative_arcs "
            "(arc_id, project_id, summary, covered_segments_json, created_at) "
            "VALUES ('arc_1', 'proj_b', 'B arc', '[]', '2026-01-01')"
        ))
        conn.execute(text(
            "INSERT INTO volume_summaries "
            "(volume_id, project_id, volume_order, summary, covered_arcs_json, created_at) "
            "VALUES ('vol_1', 'proj_b', 1, 'B volume', '[]', '2026-01-01')"
        ))
        arc_projects = conn.execute(
            text("SELECT project_id FROM narrative_arcs WHERE arc_id='arc_1' ORDER BY project_id")
        ).scalars().all()
        volume_projects = conn.execute(
            text("SELECT project_id FROM volume_summaries WHERE volume_id='vol_1' ORDER BY project_id")
        ).scalars().all()

    assert arc_projects == ["proj_a", "proj_b"]
    assert volume_projects == ["proj_a", "proj_b"]
