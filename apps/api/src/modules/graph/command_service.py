from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.engine import Engine

from src.shared.db.base import metadata


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_project(connection, workspace_id: str, project_id: str | None):
    projects = metadata.tables["projects"]
    stmt = select(projects).where(projects.c.workspace_id == workspace_id)
    if project_id:
        stmt = stmt.where(projects.c.project_id == project_id)
    rows = connection.execute(stmt).all()
    if not rows:
        raise ValueError("workspace 下没有可用 project")
    if len(rows) > 1:
        raise ValueError("workspace 下存在多个 project，请显式提供 project_id")
    return rows[0]


def update_graph_template_config(engine: Engine, workspace_id: str, template_key: str, payload: dict) -> dict:
    graph_template_configs = metadata.tables["graph_template_configs"]
    now = _now()
    status = str(payload.get("status", "")).strip()
    if not status:
        raise ValueError("请提供 status")
    with engine.begin() as connection:
        project = _resolve_project(connection, workspace_id, payload.get("project_id"))
        existing = connection.execute(
            select(graph_template_configs).where(
                graph_template_configs.c.project_id == project.project_id,
                graph_template_configs.c.template_key == template_key,
            )
        ).first()
        values = {
            "project_id": project.project_id,
            "template_key": template_key,
            "status": status,
            "config_artifact_id": payload.get("config_artifact_id"),
            "updated_at": now,
        }
        if existing is None:
            values["graph_template_config_id"] = f"gtc_{uuid.uuid4().hex[:12]}"
            values["created_at"] = now
            connection.execute(graph_template_configs.insert().values(**values))
        else:
            connection.execute(
                graph_template_configs.update()
                .where(graph_template_configs.c.graph_template_config_id == existing.graph_template_config_id)
                .values(**values)
            )
            values["graph_template_config_id"] = existing.graph_template_config_id
            values["created_at"] = existing.created_at
        return {
            "graph_template_config_id": values["graph_template_config_id"],
            "project_id": project.project_id,
            "template_key": template_key,
            "status": status,
            "config_artifact_id": values["config_artifact_id"],
            "created_at": values["created_at"].isoformat(),
            "updated_at": now.isoformat(),
        }
