"""SQLAlchemy engine and database initialization helpers."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.schema import MetaData

from .config import Settings
from .tables import metadata as default_metadata

SQLITE_PREFIX = "sqlite:///"

# Module-level engine reference, set during app startup via init_db().
_engine: Engine | None = None


def get_engine() -> Engine:
    """Return the shared SQLAlchemy engine.

    Auto-initialises with default settings on first call if
    ``init_db()`` hasn't run yet (e.g. module-level service
    constructors that fire before the FastAPI lifespan).
    """
    global _engine
    if _engine is None:
        _engine = create_engine_from_settings(Settings())
        default_metadata.create_all(_engine)
    return _engine


def create_engine_from_settings(settings: Settings) -> Engine:
    database_url = settings.DATABASE_URL
    _ensure_sqlite_parent(database_url)
    return create_engine(database_url, future=True, **_engine_options(database_url))


def init_db(
    engine: Engine,
    metadata: MetaData | None = None,
    *,
    use_alembic: bool = False,
) -> None:
    """Initialise the unified database schema.

    By default (``use_alembic=False``) calls ``metadata.create_all(engine)``
    for fast test/dev bootstrap. When ``use_alembic=True`` runs
    ``alembic upgrade head`` against ``engine.url`` instead — this is the
    production runtime path and guarantees ``alembic_version`` is stamped
    so later migrations can apply cleanly.
    """
    global _engine
    _engine = engine
    if use_alembic:
        _run_alembic_upgrade(engine)
    else:
        target_metadata = metadata or default_metadata
        target_metadata.create_all(engine)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        connection.commit()


def _run_alembic_upgrade(engine: Engine) -> None:
    from alembic import command
    from alembic.config import Config as AlembicConfig

    backend_root = Path(__file__).resolve().parents[1]
    cfg = AlembicConfig(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    command.upgrade(cfg, "head")


def _engine_options(database_url: str) -> dict:
    if database_url.startswith("sqlite:"):
        return {
            "connect_args": {"check_same_thread": False},
            "pool_pre_ping": True,
        }
    return {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
    }


def _ensure_sqlite_parent(database_url: str) -> None:
    path = _sqlite_file_path(database_url)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)


def _sqlite_file_path(database_url: str) -> Path | None:
    if database_url == "sqlite:///:memory:":
        return None
    if not database_url.startswith(SQLITE_PREFIX):
        return None
    return Path(database_url.removeprefix(SQLITE_PREFIX))
