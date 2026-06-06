from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.bootstrap.settings import AppSettings


def create_database_engine(settings: AppSettings) -> Engine:
    return create_engine(settings.postgres_dsn)


def resolve_database_engine(app) -> Engine:
    if not hasattr(app.state, "db_engine"):
        app.state.db_engine = create_database_engine(app.state.settings)
    return app.state.db_engine
