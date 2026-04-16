"""FastAPI dependency factories."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy import Connection, Engine

from .config import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db_engine(request: Request) -> Engine:
    return request.app.state.engine


def get_db_connection(engine: Engine = Depends(get_db_engine)) -> Iterator[Connection]:
    with engine.connect() as connection:
        yield connection
        connection.commit()


def get_project_manager(settings: Settings = Depends(get_settings)):
    from .models.project import ProjectManager

    ProjectManager.PROJECTS_DIR = f"{settings.UPLOAD_FOLDER}/projects"
    return ProjectManager


def get_task_manager():
    from .models.task import TaskManager

    return TaskManager()


def get_llm_router():
    from .services.llm_router import LlmRouter

    return LlmRouter()


def get_novel_db():
    """Deprecated – kept for test compatibility. Use repositories directly."""
    from .database import get_engine
    return get_engine()
